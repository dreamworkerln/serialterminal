from types import SimpleNamespace

import pytest

from serialterminal.transports import bluez_devices


@pytest.fixture(autouse=True)
def isolated_bluez_discovery(monkeypatch):
    # Программные tests не должны читать устройства реального system bus.
    # Tests BlueZ подставляют свой bus поверх этого пустого snapshot.
    class EmptyBus:
        async def call(self, message):
            from dbus_fast.constants import MessageType

            assert message.member == "GetManagedObjects"
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=[{}])

        def disconnect(self):
            pass

        async def wait_for_disconnect(self):
            pass

    async def connect():
        return EmptyBus()

    monkeypatch.setattr(bluez_devices, "_system_bus", connect)
