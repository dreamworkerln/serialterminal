from serialterminal.transports import serial as serial_transport
from serialterminal.transports.serial import SerialDeviceIdentity, SerialTransport


def test_sticky_serial_identity_does_not_fall_back(monkeypatch):
    selected = SerialDeviceIdentity(
        key="serial-usb:303a:1001:ABC",
        path="/dev/ttyACM0",
        description="ESP32-S3",
        vid=0x303A,
        pid=0x1001,
        serial_number="ABC",
    )
    other = SerialDeviceIdentity(
        key="serial-usb:303a:1001:XYZ",
        path="/dev/ttyACM1",
        description="ESP32-S3",
        vid=0x303A,
        pid=0x1001,
        serial_number="XYZ",
    )

    transport = SerialTransport(identity=selected)

    monkeypatch.setattr(serial_transport, "discover_serial_devices", lambda: [other])
    assert transport._choose_device() is None

    selected_after_reboot = SerialDeviceIdentity(
        key=selected.key,
        path="/dev/ttyACM7",
        description="ESP32-S3",
        vid=0x303A,
        pid=0x1001,
        serial_number="ABC",
    )
    monkeypatch.setattr(
        serial_transport,
        "discover_serial_devices",
        lambda: [other, selected_after_reboot],
    )
    assert transport._choose_device() == "/dev/ttyACM7"
