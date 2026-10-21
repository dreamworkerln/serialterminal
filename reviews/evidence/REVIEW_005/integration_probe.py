from __future__ import annotations
import hashlib
import json
import pathlib
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from serialterminal.file_transfer import (BinarySendReceipt, DataMessage,
    EndMessage, FileTransferError, FileTransferManager, MetaMessage,
    ResultMessage, decode_message, encode_message)


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("probe timeout")


class Link:
    payload_capacity = 200
    def __init__(self):
        self.receiver = None
        self.peer = None
        self.sent = []
        self.data_started = threading.Event()
        self.data_release = threading.Event()
        self.data_release.set()

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        message = decode_message(data)
        self.sent.append(message)
        if isinstance(message, DataMessage):
            self.data_started.set()
            if not self.data_release.wait(5):
                raise AssertionError("transport gate timeout")
        if self.peer.receiver is not None:
            self.peer.receiver(bytes(data))
        return BinarySendReceipt(tx_id=len(self.sent))


def pair(work, *, tx_sink=None, rx_sink=None, claim=None):
    a, b = Link(), Link()
    a.peer, b.peer = b, a
    tx = FileTransferManager(a, receive_dir=work/"tx", peer_key="review005-rx",
                             event_sink=tx_sink, claim_transfer=claim)
    rx = FileTransferManager(b, receive_dir=work/"rx", peer_key="review005-tx", event_sink=rx_sink)
    return a, b, tx, rx


def run():
    results = {}
    with tempfile.TemporaryDirectory(prefix="st-review005-") as temp:
        work = pathlib.Path(temp)
        # FT1 переносит opaque bytes; codec interoperability здесь не проверяется.
        payload = bytes.fromhex("c0dec201020000") + hashlib.shake_256(b"review005").digest(2000)
        source = work/"voice-probe.stvoice.c2"
        source.write_bytes(payload)
        tx_events, rx_events = [], []
        terminal = threading.Event()
        returned = False
        def tx_sink(event):
            tx_events.append({"kind":event["kind"], "before_return":not returned})
            if event["kind"] in {"transfer_completed", "transfer_failed", "transfer_cancelled"}:
                terminal.set()
        a,b,tx,rx = pair(work/"early", tx_sink=tx_sink, rx_sink=rx_events.append)
        (work/"early/rx"/source.name).write_bytes(b"existing destination")
        real_start = threading.Thread.start
        def scheduled_start(thread):
            real_start(thread)
            # Допустимое расписание: после start() сначала работает sender.
            if thread.name.startswith("serialterminal-file-tx-") and threading.current_thread() is threading.main_thread():
                assert terminal.wait(4)
        try:
            with patch.object(threading.Thread, "start", scheduled_start):
                snapshot = tx.start_send(source)
            returned = True
            wait_for(lambda: not tx.busy and not rx.busy)
            completed = [e for e in rx_events if e["kind"] == "transfer_completed"]
            assert len(completed) == 1
            event = completed[0]
            destination = pathlib.Path(event["progress"]["final_path"])
            assert destination.read_bytes() == payload
            assert event["filename"].endswith(".stvoice.c2")
            assert not destination.name.endswith(".stvoice.c2")
            results["early_terminal"] = {"terminal_before_start_send_return":any(e["kind"]=="transfer_completed" and e["before_return"] for e in tx_events), "returned_state":snapshot["state"]}
            assert results["early_terminal"]["terminal_before_start_send_return"]
            results["filename_collision"] = {"wire_filename":event["filename"],"published_basename":destination.name,"bytes_equal":True,"completion_count":len(completed),"event_has_parent_field":"parent_transfer_id" in event}
            meta = next(m for m in a.sent if isinstance(m, MetaMessage))
            end = next(m for m in a.sent if isinstance(m, EndMessage))
        finally:
            tx.close(); rx.close()
        replay_events = []
        restarted = FileTransferManager(b, receive_dir=work/"early/rx",peer_key="review005-tx",event_sink=replay_events.append)
        sent_before = len(b.sent)
        count = len([m for m in b.sent if isinstance(m, ResultMessage)])
        try:
            restarted.feed_binary(encode_message(meta,200))
            restarted.feed_binary(encode_message(end,200))
            wait_for(lambda: len([m for m in b.sent if isinstance(m,ResultMessage)]) >= count+2)
            results["completed_replay"] = {"durable_file_exists":destination.exists(),"new_ok_results":len([m for m in b.sent[sent_before:] if isinstance(m,ResultMessage) and m.ok]),"new_completion_events":sum(e["kind"]=="transfer_completed" for e in replay_events),"note":"FT1 tombstone replay does not constitute an autoplay inbox"}
            assert results["completed_replay"]["new_completion_events"] == 0
            assert results["completed_replay"]["new_ok_results"] == 2
        finally:
            restarted.close()
        a,b,tx,rx = pair(work/"busy")
        a.data_release.clear()
        try:
            tx.start_send(source)
            assert a.data_started.wait(4)
            wait_for(lambda:rx.busy)
            try:
                rx.start_send(source)
            except FileTransferError as exc:
                results["incoming_admission"]={"receiver_busy":rx.busy,"local_voice_send_error":exc.code,"finalized_source_preserved":source.exists()}
                assert exc.code=="file_transfer_busy"
            else:
                raise AssertionError("expected FT1 busy")
            a.data_release.set()
            wait_for(lambda:not tx.busy and not rx.busy)
        finally:
            a.data_release.set();tx.close();rx.close()
        entered,release,done = threading.Event(),threading.Event(),threading.Event()
        outcome = {}
        def claim(*args):
            entered.set()
            assert release.wait(4)
        a,b,tx,rx=pair(work/"claim",claim=claim)
        def start():
            try: outcome["snapshot"]=tx.start_send(source)
            except Exception as exc: outcome["error"]=repr(exc)
            finally:done.set()
        caller=threading.Thread(target=start)
        try:
            caller.start()
            assert entered.wait(4)
            results["synchronous_admission"]={"claim_entered":True,"start_send_returned_before_claim_release":done.is_set()}
            assert not done.is_set()
            release.set();caller.join(4)
            assert done.is_set() and "error" not in outcome
            wait_for(lambda:not tx.busy and not rx.busy)
        finally:
            release.set();caller.join(4);tx.close();rx.close()
    return results


if __name__ == "__main__":
    output = run()
    dest = pathlib.Path(__file__).with_name("probe-results.json")
    dest.write_text(json.dumps({"result":"PASS","evidence_type":"composed FT1 contract probe; no voice implementation/audio/radio", "checks":output}, indent=2)+"\n")
    print(json.dumps({"result":"PASS","checks":output}, indent=2))
