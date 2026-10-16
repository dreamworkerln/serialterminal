import hashlib
import random
import tempfile
import threading
import time
from pathlib import Path
from serialterminal.file_transfer import (
    BinarySendReceipt, Compression, DataMessage, FileTransferManager,
    MetaMessage, ResultMessage, decode_message, encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity

class Transport:
    payload_capacity = 200
    def __init__(self): self.sent = []; self.receiver = None
    def set_receiver(self, receiver): self.receiver = receiver
    def send_binary(self, data, *, cancel_event=None):
        self.sent.append(bytes(data)); return BinarySendReceipt(tx_id=len(self.sent))

def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value: return value
        time.sleep(0.005)
    return predicate()

with tempfile.TemporaryDirectory() as td:
    transport = Transport()
    manager = FileTransferManager(
        transport, receive_dir=Path(td), incoming_idle_timeout_s=0.05
    )
    payload = random.Random(20).randbytes(700)
    chunk_size = data_payload_capacity(transport.payload_capacity)
    transfer_id = 0x5151
    meta = MetaMessage(
        transfer_id, "resume.bin", len(payload), len(payload), Compression.NONE,
        chunk_size, hashlib.sha256(payload).digest(),
    )
    entered = threading.Event(); proceed = threading.Event()
    real_release = manager._release
    def blocked_release(tid, direction):
        entered.set(); proceed.wait(2.0); return real_release(tid, direction)
    manager._release = blocked_release
    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        manager.feed_binary(encode_message(DataMessage(transfer_id, 0, payload[:chunk_size]), transport.payload_capacity))
        failed = wait_until(lambda: (s if (s := manager.display_snapshot()) and s["state"] == "failed" else None))
        print("failed_code", failed["failure"]["code"])
        print("release_entered", entered.wait(1.0), "active_id", manager._active_id)
        transport.sent.clear()
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        time.sleep(0.1)
        proceed.set(); time.sleep(0.2)
        results = [m for raw in transport.sent if isinstance((m := decode_message(raw)), ResultMessage)]
        print("results", [(m.ok, m.code, m.reason) for m in results])
        print("final_state", manager.display_snapshot()["state"], "active_id", manager._active_id)
    finally:
        proceed.set(); manager.close()
