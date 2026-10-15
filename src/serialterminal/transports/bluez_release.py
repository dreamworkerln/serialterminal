"""Адресная проверка освобождения уже принадлежавшего ST BlueZ клиента."""
from __future__ import annotations

import asyncio
import re
from typing import Any


async def _system_bus():
    # Linux dependency загружается только для настоящего BlueZ backend.
    from dbus_fast.aio import MessageBus
    from dbus_fast.constants import BusType

    bus = MessageBus(bus_type=BusType.SYSTEM)
    try:
        return await bus.connect()
    except BaseException:
        # Timeout connect не должен оставить собственный system-bus socket.
        try:
            bus.disconnect()
        except Exception:
            pass
        raise


async def _call(bus, path: str, member: str, timeout: float):
    from dbus_fast import Message
    from dbus_fast.constants import MessageType

    properties = member == "Get"
    reply = await asyncio.wait_for(bus.call(Message(
        destination="org.bluez", path=path,
        interface="org.freedesktop.DBus.Properties" if properties else "org.bluez.Device1",
        member=member, signature="ss" if properties else "",
        body=["org.bluez.Device1", "Connected"] if properties else [],
    )), timeout=timeout)
    if reply.message_type == MessageType.ERROR:
        if reply.error_name in {"org.freedesktop.DBus.Error.UnknownObject", "org.bluez.Error.DoesNotExist"}:
            return False
        raise RuntimeError(f"{reply.error_name}: {reply.body}")
    if properties:
        value = reply.body[0].value
        if not isinstance(value, bool):
            raise ValueError("BlueZ Connected is not boolean")
        return value
    return None


async def verify_release(
    path: str, *, force_allowed: bool, timeout: float = 3.0,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "backend": "bluez", "device_path": path, "result": "unknown",
        "connected_before": None, "connected_after": None, "forced": False,
    }
    # Не выводим adapter/device path из имени или scan/cache: это exact path
    # клиента, захваченный до Bleak.disconnect(), который может стереть backend.
    if not isinstance(path, str) or not re.fullmatch(r"/org/bluez/hci[0-9]+/dev_(?:[0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}", path):
        report["error"] = "BlueZ client device path unavailable or invalid"
        return report
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    bus = None

    def remaining():
        left = deadline - loop.time()
        if left <= 0:
            raise asyncio.TimeoutError("BlueZ release deadline")
        return min(left, 0.75)

    try:
        bus = await asyncio.wait_for(_system_bus(), timeout=remaining())
        before = await _call(bus, path, "Get", remaining())
        report["connected_before"] = report["connected_after"] = before
        if before is False:
            report["result"] = "disconnected"
            return report
        if not force_allowed:
            report["result"] = "failed"
            report["error"] = "BlueZ still connected; no live owned client to force-disconnect"
            return report
        report["forced"] = True
        report["connected_after"] = None
        try:
            await _call(bus, path, "Disconnect", remaining())
        except Exception as exc:
            # Даже timeout ответа не доказывает неуспех Disconnect: читаем
            # независимое состояние, пока общий deadline ещё не истёк.
            report["disconnect_error"] = f"{type(exc).__name__}: {exc}"
        while True:
            report["connected_after"] = await _call(bus, path, "Get", remaining())
            if report["connected_after"] is False:
                report["result"] = "disconnected"
                return report
            await asyncio.sleep(min(0.05, remaining()))
    except Exception as exc:
        report["result"] = "failed" if report["connected_after"] is True else "unknown"
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report
    finally:
        if bus is not None:
            try:
                bus.disconnect()
                await asyncio.wait_for(bus.wait_for_disconnect(), timeout=0.25)
            except Exception as exc:
                report["bus_cleanup_error"] = f"{type(exc).__name__}: {exc}"
