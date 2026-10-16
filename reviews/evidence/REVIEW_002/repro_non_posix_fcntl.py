import builtins
import tempfile
from pathlib import Path
from serialterminal.file_transfer import BinarySendReceipt, FileTransferManager

class Transport:
    payload_capacity = 200
    def set_receiver(self, receiver): self.receiver = receiver
    def send_binary(self, data, *, cancel_event=None): return BinarySendReceipt(tx_id=1)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    source = root / "x.bin"
    source.write_bytes(b"abc")
    manager = FileTransferManager(Transport(), receive_dir=root / "rx", peer_key="peer")
    real_import = builtins.__import__
    def no_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ModuleNotFoundError("No module named 'fcntl'")
        return real_import(name, *args, **kwargs)
    builtins.__import__ = no_fcntl
    try:
        try:
            manager.start_send(source)
        except Exception as exc:
            print(type(exc).__name__, str(exc))
        else:
            print("UNEXPECTED_OK")
    finally:
        builtins.__import__ = real_import
        manager.close()
