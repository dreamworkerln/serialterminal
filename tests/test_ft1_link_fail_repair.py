"""Регрессии terminal M1 LINK_FAIL: дыра DATA должна чиниться через FT1 END."""
from contextlib import contextmanager
from dataclasses import dataclass
import itertools
import random
import struct
import time

import pytest

from serialterminal.file_transfer import (
    DataMessage, EndMessage, FileTransferManager, MetaMessage, ResultMessage,
    decode_message,
)
from serialterminal.profiles.chatter.machine_client import ChatterMachineClient
from serialterminal.profiles.chatter.machine_codec import Frame, Kind, decode, encode
from recursive_evidence import service_requests


@dataclass
class Fault:
    depth: int
    message_type: type = DataMessage
    index: int | None = None
    remaining: int | None = 1
    deliver: bool = False
    outcome: Kind = Kind.LINK_FAIL

    def applies(self, message, depth):
        return (depth == self.depth and isinstance(message, self.message_type)
                and (self.index is None or getattr(message, "chunk_index", None) == self.index)
                and (self.remaining is None or self.remaining > 0))


class VirtualNode:
    """M1 и logical RF delivery без USB/BLE, физического времени и настоящего CRC."""

    def __init__(self, epoch, faults):
        self.epoch = epoch
        self.faults = faults
        self.client = self.peer = None
        self.frames = []
        self.messages = []
        self.metadata = {}
        self.outcomes = {}
        self.failures = []
        self.attempts = []

    def emit(self, kind, request, payload=b""):
        self.client.feed_line("main", encode(Frame(kind, self.epoch, request, payload)).decode())

    def send(self, text):
        frame = decode(text.lstrip("\n"))
        self.frames.append(frame)
        if frame.kind == Kind.HELLO:
            self.emit(Kind.WELCOME, frame.request, frame.payload + b"\x02" + struct.pack("<H", 243))
        elif frame.kind == Kind.CLOSE:
            self.emit(Kind.CLOSED, frame.request)
        elif frame.kind == Kind.QUERY:
            self.emit(self.outcomes.get(frame.request, Kind.UNKNOWN), frame.request)
        elif frame.kind == Kind.SUBMIT:
            message = decode_message(frame.payload)
            self.messages.append(message)
            if isinstance(message, MetaMessage):
                self.metadata[message.transfer_id] = message
            meta = self.metadata.get(message.transfer_id)
            depth = meta.depth if meta is not None else 0
            fault = next((f for f in self.faults if f.applies(message, depth)), None)
            outcome, deliver = Kind.LINK_OK, True
            if fault is not None:
                if fault.remaining is not None:
                    fault.remaining -= 1
                outcome, deliver = fault.outcome, fault.deliver
                self.failures.append((message, depth, frame.request))
            self.emit(Kind.ACCEPTED, frame.request)
            self.emit(Kind.TX_DONE, frame.request)
            # LINK_FAIL моделирует исчерпание пяти RF попыток одного SUBMIT.
            # При потерянных ACK peer показывает DATA лишь один раз, как firmware.
            for attempt in range(1, 6 if outcome == Kind.LINK_FAIL else 2):
                self.attempts.append((frame.request, attempt))
            if deliver:
                self.peer.emit(Kind.RX, 0, frame.payload)
                receiver = self.peer.client.receiver
                if receiver is not None:
                    target = receiver.__self__
                    while target._rx_queue.qsize() > 8:
                        time.sleep(.001)
            self.outcomes[frame.request] = outcome
            self.emit(outcome, frame.request)
        return {"tx_id": len(self.frames), "state": "written"}


@contextmanager
def pair(tmp_path, *, faults=(), window=2):
    left, right = VirtualNode(41, list(faults)), VirtualNode(42, list(faults))
    left.peer, right.peer = right, left
    for node in (left, right):
        node.client = ChatterMachineClient(node.send, presentation_timeout_s=1)
        # Меняется file pipeline capability, а не протокол/семантика M1 клиента.
        node.client.pipeline_capacity = window
        node.client._ready(time.monotonic() + 1)
    ids = itertools.count(1000)
    managers = [FileTransferManager(node.client, receive_dir=tmp_path / name,
                                   id_factory=lambda: next(ids), result_timeout_s=1,
                                   control_replay_interval_s=.1)
                for node, name in ((left, "a"), (right, "b"))]
    try:
        yield *managers, left, right
    finally:
        for manager in managers:
            manager.close()


def source_file(tmp_path, chunks=47):
    source = tmp_path / "radio.bin"
    source.write_bytes(random.Random(33).randbytes(227 * chunks))
    return source


def terminal(manager, transfer_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = manager._records[transfer_id].snapshot()
        if snapshot["state"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(.005)
    pytest.fail("virtual transfer did not settle within 5s")


def assert_completed(tx, rx, root, source):
    result = terminal(tx, root)
    assert result["state"] == "completed", result
    received = terminal(rx, root)
    assert received["state"] == "completed", received
    assert (rx.receive_dir / source.name).read_bytes() == source.read_bytes()


@pytest.mark.parametrize("window", [1, 2])
def test_virtual_m1_pair_without_loss_completes(tmp_path, window):
    source = source_file(tmp_path)
    with pair(tmp_path, window=window) as (tx, rx, left, right):
        root = int(tx.start_send(source)["transfer_id"], 16)
        assert_completed(tx, rx, root, source)
        assert not left.failures and not right.failures
        assert not service_requests(right.messages, root)


@pytest.mark.parametrize("window", [1, 2])
@pytest.mark.parametrize("data_delivered", [False, True], ids=["lost-data", "lost-ack"])
def test_data_link_fail_reaches_end_and_file_result(tmp_path, window, data_delivered):
    source = source_file(tmp_path)
    fault = Fault(depth=0, index=33, deliver=data_delivered)
    with pair(tmp_path, faults=[fault], window=window) as (tx, rx, left, right):
        root = int(tx.start_send(source)["transfer_id"], 16)
        assert_completed(tx, rx, root, source)
        assert len(left.failures) == 1
        message, depth, request = left.failures[0]
        assert depth == 0 and message.chunk_index == 33
        assert sum(req == request for req, _ in left.attempts) == 5
        first_end = next(i for i, m in enumerate(left.messages)
                         if isinstance(m, EndMessage) and m.transfer_id == root)
        initial = left.messages[:first_end]
        assert [m.chunk_index for m in initial if isinstance(m, DataMessage) and m.transfer_id == root] == list(range(47))
        requests = service_requests(right.messages, root)
        if data_delivered:
            assert not requests
        else:
            assert any([(r.start_chunk, r.count) for r in m.ranges] == [(33, 1)] for m in requests)
            assert sum(isinstance(m, DataMessage) and m.transfer_id == root and m.chunk_index == 33
                       for m in left.messages[first_end + 1:]) == 1
        assert any(isinstance(m, ResultMessage) and m.transfer_id == root and m.ok for m in right.messages)


def test_link_fail_during_requested_root_repair_runs_another_cycle(tmp_path):
    source = source_file(tmp_path)
    with pair(tmp_path, faults=[Fault(depth=0, index=33, remaining=2)]) as (tx, rx, left, right):
        root = int(tx.start_send(source)["transfer_id"], 16)
        assert_completed(tx, rx, root, source)
        assert len(left.failures) == 2
        assert len(service_requests(right.messages, root)) == 2
        assert sum(isinstance(m, DataMessage) and m.transfer_id == root and m.chunk_index == 33
                   for m in left.messages) == 3


def test_link_fail_in_missing_list_data_creates_nested_repair(tmp_path):
    source = source_file(tmp_path)
    faults = [Fault(depth=0, index=33, outcome=Kind.LINK_OK), Fault(depth=1, index=0)]
    with pair(tmp_path, faults=faults) as (tx, rx, left, right):
        root = int(tx.start_send(source)["transfer_id"], 16)
        assert_completed(tx, rx, root, source)
        assert any(depth == 1 for _, depth, _ in right.failures)
        depths = [m.depth for node in (left, right) for m in node.messages if isinstance(m, MetaMessage)]
        assert max(depths) == 2
        assert service_requests(right.messages, root)


def test_permanent_data_link_fail_ends_with_no_progress_not_false_success(tmp_path):
    source = source_file(tmp_path)
    with pair(tmp_path, faults=[Fault(depth=0, index=33, remaining=None)]) as (tx, rx, left, right):
        root = int(tx.start_send(source)["transfer_id"], 16)
        result = terminal(tx, root)
        assert result["state"] == "failed"
        assert result["failure"]["details"].get("remote_code") == "repair_no_progress", result
        assert len(service_requests(right.messages, root)) == 3
        assert not (rx.receive_dir / source.name).exists()
        assert not any(isinstance(m, ResultMessage) and m.transfer_id == root and m.ok for m in right.messages)


@pytest.mark.parametrize("control_type", [MetaMessage, EndMessage], ids=["meta", "end"])
def test_control_link_fail_remains_fatal(tmp_path, control_type):
    source = source_file(tmp_path)
    with pair(tmp_path, faults=[Fault(depth=0, message_type=control_type)]) as (tx, rx, left, right):
        root = int(tx.start_send(source)["transfer_id"], 16)
        result = terminal(tx, root)
        assert result["state"] == "failed", result
        assert result["failure"]["details"]["binary_error"] == "machine_link_failed"
        assert not (rx.receive_dir / source.name).exists()
        assert not service_requests(right.messages, root)
