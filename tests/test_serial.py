from serialterminal.transports import serial as serial_transport
from serialterminal.transports.serial import SerialDeviceIdentity, SerialTransport


class PortInfo:
    def __init__(
        self,
        device,
        *,
        description="n/a",
        hwid="n/a",
        vid=None,
        pid=None,
        serial_number=None,
        location=None,
    ):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.vid = vid
        self.pid = pid
        self.serial_number = serial_number
        self.location = location


def test_usb_discovery_ignores_legacy_ttys(monkeypatch):
    monkeypatch.setattr(
        serial_transport.list_ports,
        "comports",
        lambda: [
            PortInfo("/dev/ttyS0"),
            PortInfo("/dev/ttyS31"),
            PortInfo("/dev/ttyUSB0"),
            PortInfo("/dev/ttyACM0"),
            PortInfo(
                "/dev/cu.usbmodem-test",
                hwid="USB VID:PID=303A:1001",
                vid=0x303A,
                pid=0x1001,
            ),
        ],
    )
    monkeypatch.setattr(serial_transport.glob, "glob", lambda pattern: [])

    found = serial_transport.discover_serial_devices()
    paths = {device.path for device in found}

    assert "/dev/ttyS0" not in paths
    assert "/dev/ttyS31" not in paths
    assert "/dev/ttyUSB0" in paths
    assert "/dev/ttyACM0" in paths
    assert "/dev/cu.usbmodem-test" in paths


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
