import threading

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


class BlockingSerial:
    def __init__(self):
        self.is_open = True
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = threading.Event()
        self.flushed = threading.Event()

    def read(self, size):
        self.started.set()
        assert self.release.wait(timeout=1.0)
        assert not self.closed.is_set()
        return b"ok"[:size]

    def write(self, data):
        self.started.set()
        assert self.release.wait(timeout=1.0)
        assert not self.closed.is_set()
        return len(data)

    def flush(self):
        assert not self.closed.is_set()
        self.flushed.set()

    def close(self):
        self.is_open = False
        self.closed.set()


class FullDuplexSerial:
    def __init__(self):
        self.is_open = True
        self.read_started = threading.Event()
        self.release_read = threading.Event()
        self.write_finished = threading.Event()
        self.closed = threading.Event()

    def read(self, size):
        self.read_started.set()
        assert self.release_read.wait(timeout=1.0)
        assert not self.closed.is_set()
        return b"rx"[:size]

    def write(self, data):
        assert not self.closed.is_set()
        self.write_finished.set()
        return len(data)

    def flush(self):
        assert not self.closed.is_set()

    def close(self):
        self.is_open = False
        self.closed.set()


def _install_fake_serial(transport, fake_serial):
    with transport._lock:
        transport._serial = fake_serial


def _disconnect_in_thread(transport):
    done = threading.Event()

    def run():
        transport.disconnect()
        done.set()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, done


def test_serial_discovery_hides_empty_ttys_but_keeps_identified_uart(monkeypatch):
    monkeypatch.setattr(
        serial_transport.list_ports,
        "comports",
        lambda: [
            PortInfo("/dev/ttyS0"),
            PortInfo("/dev/ttyS31"),
            PortInfo(
                "/dev/ttyS5",
                description="16550A UART",
                hwid="PNP0501",
            ),
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
    by_path = {device.path: device for device in found}

    assert "/dev/ttyS0" not in by_path
    assert "/dev/ttyS31" not in by_path
    assert "/dev/ttyS5" in by_path
    assert by_path["/dev/ttyS5"].is_usb is False
    assert "/dev/ttyUSB0" in by_path
    assert by_path["/dev/ttyUSB0"].is_usb is True
    assert "/dev/ttyACM0" in by_path
    assert by_path["/dev/ttyACM0"].is_usb is True
    assert "/dev/cu.usbmodem-test" in by_path
    assert by_path["/dev/cu.usbmodem-test"].is_usb is True


def test_serial_discovery_prefers_by_id_and_deduplicates_alias(monkeypatch):
    alias = "/dev/serial/by-id/usb-controller"
    device = "/dev/ttyUSB0"
    monkeypatch.setattr(
        serial_transport.list_ports,
        "comports",
        lambda: [
            PortInfo(
                device,
                description="USB Controller",
                vid=0x1A86,
                pid=0x55D3,
                serial_number="ABC",
            )
        ],
    )

    def fake_glob(pattern):
        if pattern == "/dev/serial/by-id/*":
            return [alias]
        if pattern == "/dev/ttyUSB*":
            return [device]
        return []

    monkeypatch.setattr(serial_transport.glob, "glob", fake_glob)
    monkeypatch.setattr(
        serial_transport.os.path,
        "realpath",
        lambda path: device if path in {alias, device} else path,
    )

    found = serial_transport.discover_serial_devices()

    assert len(found) == 1
    assert found[0].path == alias
    assert found[0].key == f"serial-by-id:{alias}"
    assert found[0].serial_number == "ABC"


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


def test_serial_read_does_not_block_concurrent_write():
    transport = SerialTransport(device="/dev/fake")
    fake = FullDuplexSerial()
    _install_fake_serial(transport, fake)
    result = {}

    reader = threading.Thread(
        target=lambda: result.setdefault("data", transport.read(2))
    )
    reader.start()
    assert fake.read_started.wait(timeout=1.0)

    writer = threading.Thread(target=lambda: transport.write(b"hello"))
    writer.start()

    # TX must finish while RX is still intentionally blocked. The old shared
    # transport mutex failed exactly here and imposed up to the RX timeout on TX.
    assert fake.write_finished.wait(timeout=0.1)
    assert reader.is_alive()

    writer.join(timeout=1.0)
    assert not writer.is_alive()

    fake.release_read.set()
    reader.join(timeout=1.0)
    assert not reader.is_alive()
    assert result["data"] == b"rx"


def test_disconnect_waits_for_active_serial_read():
    transport = SerialTransport(device="/dev/fake")
    fake = BlockingSerial()
    _install_fake_serial(transport, fake)
    result = {}

    reader = threading.Thread(
        target=lambda: result.setdefault("data", transport.read(2))
    )
    reader.start()
    assert fake.started.wait(timeout=1.0)

    disconnector, disconnect_done = _disconnect_in_thread(transport)
    assert not disconnect_done.wait(timeout=0.05)
    assert not fake.closed.is_set()

    fake.release.set()
    reader.join(timeout=1.0)
    disconnector.join(timeout=1.0)

    assert result["data"] == b"ok"
    assert disconnect_done.is_set()
    assert fake.closed.is_set()
    assert not transport.is_connected


def test_disconnect_waits_for_active_serial_write_and_flush():
    transport = SerialTransport(device="/dev/fake")
    fake = BlockingSerial()
    _install_fake_serial(transport, fake)

    writer = threading.Thread(target=lambda: transport.write(b"hello"))
    writer.start()
    assert fake.started.wait(timeout=1.0)

    disconnector, disconnect_done = _disconnect_in_thread(transport)
    assert not disconnect_done.wait(timeout=0.05)
    assert not fake.closed.is_set()

    fake.release.set()
    writer.join(timeout=1.0)
    disconnector.join(timeout=1.0)

    assert fake.flushed.is_set()
    assert disconnect_done.is_set()
    assert fake.closed.is_set()
    assert not transport.is_connected
