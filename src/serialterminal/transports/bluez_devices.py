"""Чтение подключённых Device1 без активного scan и без изменения соединений."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
import sys

from .bluez_release import _system_bus


@dataclass(frozen=True)
class BluezDevice:
    path: str
    address: str
    name: str


async def connected_devices(timeout: float = 3.0) -> list[BluezDevice]:
    if sys.platform != "linux":
        return []

    from dbus_fast import Message
    from dbus_fast.constants import MessageType

    bus = None
    try:
        async def read_devices():
            nonlocal bus
            bus = await _system_bus()
            reply = await bus.call(Message(
                destination="org.bluez", path="/",
                interface="org.freedesktop.DBus.ObjectManager",
                member="GetManagedObjects",
            ))
            if reply.message_type == MessageType.ERROR:
                raise RuntimeError(f"{reply.error_name}: {reply.body}")
            devices = []
            for path, interfaces in reply.body[0].items():
                props = interfaces.get("org.bluez.Device1", {})
                connected = props.get("Connected")
                address = props.get("Address")
                if connected is None or connected.value is not True or address is None:
                    continue
                if not re.fullmatch(r"/org/bluez/hci[0-9]+/dev_(?:[0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}", path):
                    continue
                name = props.get("Alias") or props.get("Name")
                devices.append(BluezDevice(
                    path=path, address=str(address.value),
                    name=str(name.value) if name is not None else "<unnamed>",
                ))
            return sorted(devices, key=lambda item: item.path)

        return await asyncio.wait_for(read_devices(), timeout=timeout)
    finally:
        if bus is not None:
            try:
                bus.disconnect()
                await asyncio.wait_for(bus.wait_for_disconnect(), timeout=0.25)
            except Exception:
                pass
