from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import secrets
import threading
import time
from typing import Any

from ...file_transfer.transport import BinarySendReceipt, BinaryUserCancelled, BinaryUserError
from .binary_pipeline import PipelinedChatterBinaryUserAdapter
from .machine_codec import Frame, FrameError, Kind, decode, encode


@dataclass
class Ticket:
    epoch: int
    request: int
    generation: int | None
    payload: bytes
    deadline: float
    tx_id: int | None = None
    outcome: Kind | None = None
    rejection: int | None = None
    credit_returned_at: float | None = None
    later_terminal_at: float | None = None


class ChatterMachineClient:
    """Protected local machine client with an explicit legacy compatibility path."""

    payload_capacity = 243
    pipeline_capacity = 2

    def __init__(self, send_line, **kwargs: Any) -> None:
        self.legacy = PipelinedChatterBinaryUserAdapter(send_line, **kwargs)
        self.condition = threading.Condition()
        self.operation_lock = threading.Lock()
        self.epoch = 0
        self.nonce = secrets.randbits(64) or 1
        self.hello_request = secrets.randbits(32) or 1
        self.next_request = 1
        self.mode = "negotiating"
        self.error: BinaryUserError | None = None
        self.pending: dict[int, Ticket] = {}
        self.order: deque[int] = deque()
        self.receiver = None
        self.closed = threading.Event()
        self.start_thread = None
        self.generation = None
        self.negotiated_generation = None
        self.parse_errors = 0
        self.status = {}
        self.close_request = None
        self.close_acknowledged = False
        self.hello_busy = False

    def __getattr__(self, name):
        return getattr(self.legacy, name)

    def start(self) -> None:
        with self.condition:
            if self.start_thread is not None:
                return
            self.start_thread = threading.Thread(target=self._bootstrap, name="chatter-machine-lifecycle", daemon=True)
            self.start_thread.start()

    def _bootstrap(self) -> None:
        try:
            with self.operation_lock:
                self._negotiate(time.monotonic()+5.0, self.closed)
        except BinaryUserError as exc:
            with self.condition:
                self.error=exc; self.mode="failed"; self.condition.notify_all()
            self.legacy._timing("machine_negotiation_failed", reason=exc.code)

        # Idle receiver должен восстановить machine RX после reconnect без
        # нового file_send_start. При pending tickets recovery остаётся у FT1.
        while not self.closed.wait(0.1):
            with self.condition:
                pending=bool(self.pending)
                changed=self.negotiated_generation != self.legacy._generation()
                reset=self.error is not None and self.error.code == "local_controller_reset"
                restore=not pending and ((self.mode == "machine" and changed) or reset
                                         or self._negotiation_retry_reason() is not None)
            if not restore:
                continue
            try:
                with self.operation_lock:
                    self._ready(time.monotonic()+self.legacy._controller_ready_budget_s()+self.legacy._mode_query_timeout_s,self.closed)
            except BinaryUserError as exc:
                with self.condition:
                    self.error=exc; self.mode="failed"; self.condition.notify_all()
                self.legacy._timing("machine_negotiation_failed", reason=exc.code)

    def _negotiation_retry_reason(self) -> str | None:
        with self.condition:
            # HELLO не запускает RF USER. Временный отказ bootstrap не должен
            # навсегда блокировать новый META или приём после ухода старого owner.
            # Pending/UNKNOWN и несовместимый WELCOME не обходятся новым HELLO.
            if self.closed.is_set() or self.mode != "failed" or self.pending:
                return None
            if self.error is not None and self.error.code == "machine_owner_busy" and not self.hello_busy:
                # Остальные REJECTED reasons не являются временным BUSY owner.
                return None
            if self.error is not None and self.error.code in {
                "machine_owner_busy", "machine_negotiation_timeout",
                "local_tx_timeout", "local_tx_unknown", "local_disconnect", "cancelled",
            }:
                return self.error.code
            return None

    def _write(self, frame: Frame, deadline: float, cancel_event=None, *, boundary=False):
        command=encode(frame).decode("ascii").rstrip("\n")
        if boundary: command="\n"+command
        result=self.legacy._submit_line(command,deadline=deadline)
        tx_id=result.get("tx_id") if isinstance(result,dict) else None
        self.legacy._wait_tx_written(tx_id,deadline,cancel_event=cancel_event)
        return tx_id

    def _negotiate(self, deadline: float, cancel_event=None) -> None:
        with self.condition:
            self.mode="negotiating"; self.error=None; self.hello_busy=False
            self.generation=self.legacy._generation()
        try:
            while True:
                if self.closed.is_set() or (cancel_event is not None and cancel_event.is_set()): raise BinaryUserCancelled()
                self._write(Frame(Kind.HELLO,0,self.hello_request,self.nonce.to_bytes(8,"little")),deadline,cancel_event,boundary=True)
                with self.condition:
                    while self.mode == "negotiating" and not self.hello_busy:
                        if self.closed.is_set() or (cancel_event is not None and cancel_event.is_set()): raise BinaryUserCancelled()
                        remaining=deadline-time.monotonic()
                        if remaining <= 0: raise BinaryUserError("machine_negotiation_timeout","no protected WELCOME or explicit legacy rejection")
                        self.condition.wait(min(remaining,0.1))
                    if self.hello_busy:
                        remaining=deadline-time.monotonic()
                        if remaining <= 0: raise BinaryUserError("machine_owner_busy","old machine owner did not settle before deadline")
                        # HELLO не выпускает RF; старый owner может ещё завершать ACK.
                        # HELLO не выпускает RF; старый owner может ещё завершать ACK.
                        self.condition.wait(min(remaining,0.1))
                        if time.monotonic() >= deadline:
                            raise BinaryUserError("machine_owner_busy", "old machine owner did not settle before deadline")
                        self.hello_busy=False
                        continue
                    if self.error is not None: raise self.error
                    self.negotiated_generation=self.legacy._generation()
                    return
        except BinaryUserError as exc:
            # Каждый owner HELLO завершает своё negotiating state, включая
            # foreground retry/cancel; иначе следующий owner ждёт фантомный loop.
            with self.condition:
                self.error = exc
                self.mode = "failed"
                self.condition.notify_all()
            raise

    def _ready(self, deadline: float, cancel_event=None) -> None:
        with self.condition:
            mode=self.mode
            changed=self.negotiated_generation != self.legacy._generation()
            pending=bool(self.pending)
            retry_reason=self._negotiation_retry_reason()
        if mode == "failed" and self.error is not None and self.error.code == "local_controller_reset":
            self.legacy._wait_until_controller_ready(generation=self.legacy._generation(), cancel_event=cancel_event, allow_reconnect_probe=True, deadline=deadline)
            self.legacy.drain_binary(max(0.0,deadline-time.monotonic()))
            with self.condition:
                self.pending.clear(); self.order.clear()
            self.nonce=secrets.randbits(64) or 1; self.hello_request=secrets.randbits(32) or 1
            self._negotiate(deadline,cancel_event)
        elif retry_reason is not None:
            self.legacy._timing("machine_negotiation_retry", reason=retry_reason)
            # Nonce сохраняет identity владельца, новый request отсекает запоздалый
            # ответ прежнего HELLO. Pending tickets здесь запрещены выше.
            self.hello_request=secrets.randbits(32) or 1
            self._negotiate(deadline,cancel_event)
        elif changed and mode == "machine":
            previous_epoch=self.epoch
            self.legacy.drain_binary(max(0.0,deadline-time.monotonic()))
            self.hello_request=secrets.randbits(32) or 1
            # Тот же nonce сохраняет epoch живого USB owner. Новый WELCOME epoch
            # доказывает, что node больше не держит старые outstanding RF slots.
            self._negotiate(deadline,cancel_event)
            if pending:
                if self.epoch == previous_epoch:
                    raise BinaryUserError("local_tx_unsettled","same machine epoch still owns old submissions")
                with self.condition:
                    self.pending.clear(); self.order.clear()
                self.legacy._timing("machine_epoch_invalidated",previous_epoch=previous_epoch,epoch=self.epoch)
                raise BinaryUserError("local_controller_reset","fresh node epoch invalidated old machine tickets")
        elif mode == "negotiating":
            if self.start_thread is None:
                self._negotiate(deadline,cancel_event)
            else:
                with self.condition:
                    while self.mode == "negotiating":
                        if self.closed.is_set() or (cancel_event is not None and cancel_event.is_set()): raise BinaryUserCancelled()
                        remaining=deadline-time.monotonic()
                        if remaining <= 0: raise BinaryUserError("machine_negotiation_timeout","machine bootstrap did not settle")
                        self.condition.wait(min(remaining,0.1))
        with self.condition:
            if self.error is not None: raise self.error
            if self.closed.is_set(): raise BinaryUserCancelled()

    def prepare_binary(self, *, deadline: float, cancel_event=None) -> None:
        # Recovery deadline ограничивает восстановление local controller, а не
        # последующий RF ACK transaction. Здесь не отправляется USER DATA.
        with self.legacy._bounded_lock(self.operation_lock, deadline):
            self._ready(deadline, cancel_event)
            if self.legacy._radio_timing is not None:
                self.legacy._radio_timing.get(deadline=deadline, cancel_event=cancel_event)

    def timing_budget_s(self, purpose: str, *, payload_bytes: int = 243) -> float:
        if purpose == "drain":
            with self.condition:
                remaining = max((ticket.deadline - time.monotonic() for ticket in self.pending.values()), default=0.0)
                if self.error is not None and self.error.code == "local_controller_reset":
                    remaining = 0.0
            # Deadline уже учитывает PHY и slots при admission. Drain не продлевает
            # RF произвольным новым бюджетом и не требует readback мёртвой ноды.
            return max(0.0, remaining) + self.legacy._mode_query_timeout_s
        return self.legacy.timing_budget_s(purpose, payload_bytes=payload_bytes)

    def set_receiver(self, receiver) -> None:
        with self.condition: self.receiver=receiver
        self.legacy.set_receiver(receiver)

    def feed_line(self, stream: str, line: str) -> None:
        if line.startswith("/m1 "):
            try: frame=decode(line)
            except FrameError as exc:
                self.parse_errors += 1; self.legacy.last_parse_error=str(exc); return
            receiver=None
            with self.condition:
                if frame.kind == Kind.WELCOME and self.mode == "negotiating":
                    if frame.request != self.hello_request or len(frame.payload)!=11 or frame.payload[:8] != self.nonce.to_bytes(8,"little") or frame.epoch == 0:
                        return
                    if frame.payload[8] != 2 or int.from_bytes(frame.payload[9:],"little") != self.payload_capacity:
                        self.error=BinaryUserError("machine_version_mismatch","unsupported machine capacity/window"); self.mode="failed"
                    else:
                        # Повторный HELLO живого USB owner сохраняет epoch/cache.
                        # Request counter должен продолжаться, иначе новый SUBMIT
                        # столкнётся со старой identity или cached LINK_OK.
                        if frame.epoch != self.epoch: self.next_request=1
                        self.epoch=frame.epoch; self.mode="machine"
                    self.condition.notify_all(); return
                if frame.kind == Kind.REJECTED and frame.epoch == 0 and frame.request == self.hello_request and self.mode == "negotiating":
                    if frame.payload == b"\x01":
                        self.hello_busy=True
                    else:
                        self.error=BinaryUserError("machine_owner_busy","machine HELLO rejected"); self.mode="failed"
                    self.condition.notify_all(); return
                if self.mode != "machine" or frame.epoch != self.epoch: return
                if frame.kind == Kind.RX and frame.request == 0 and frame.payload:
                    receiver=self.receiver
                elif frame.kind == Kind.STATUS and len(frame.payload)==10:
                    self.status={"credit":frame.payload[0],"drops":int.from_bytes(frame.payload[1:5],"little"),"corrupt":int.from_bytes(frame.payload[5:9],"little"),"high_water":frame.payload[9]}
                    if frame.payload[0] == self.pipeline_capacity and frame.request in self.pending:
                        for ticket in self.pending.values():
                            if ticket.request <= frame.request and ticket.credit_returned_at is None:
                                # STATUS более поздней обработанной request тоже относится
                                # к ранним slots. Identity должна принадлежать pending SUBMIT;
                                # ACCEPTED/TX_DONE могли потеряться вместе с terminal outcome.
                                # Пустая queue не доказывает LINK_OK: узнаем cache через QUERY.
                                ticket.credit_returned_at=time.monotonic()
                    self.condition.notify_all()
                elif frame.kind == Kind.CLOSED and frame.request == self.close_request and not frame.payload:
                    self.close_acknowledged = True
                    self.condition.notify_all()
                elif frame.request in self.pending:
                    ticket=self.pending[frame.request]
                    if ticket.outcome in {Kind.LINK_OK,Kind.LINK_FAIL,Kind.REJECTED,Kind.UNKNOWN,Kind.UNAVAILABLE}: return
                    if frame.kind in {Kind.ACCEPTED,Kind.TX_DONE,Kind.LINK_OK,Kind.LINK_FAIL,Kind.UNKNOWN,Kind.UNAVAILABLE} and not frame.payload:
                        ticket.outcome=frame.kind
                        if frame.kind in {Kind.LINK_OK,Kind.LINK_FAIL}:
                            # Поздний ticket уже завершился, но результат раннего мог
                            # потеряться вместе с full-credit STATUS. Это повод QUERY
                            # cache раннего request, не доказательство его успеха.
                            for earlier in self.pending.values():
                                if earlier.request < ticket.request and earlier.later_terminal_at is None:
                                    earlier.later_terminal_at=time.monotonic()
                    elif frame.kind == Kind.REJECTED and len(frame.payload)==1:
                        ticket.outcome=frame.kind; ticket.rejection=frame.payload[0]
                    self.condition.notify_all()
            if receiver is not None: receiver(frame.payload)
            return
        with self.condition:
            mode=self.mode
            if mode == "negotiating" and "[SYS] COMMAND INVALID: use /help" in line:
                self.mode="legacy"; self.condition.notify_all()
        # Human BINARY presentation не является вторым machine RX consumer.
        if mode != "machine" or "[BINARY]" not in line:
            self.legacy.feed_line(stream,line)
        if any(marker in line for marker in ("ESP-ROM:","rst:","[SYS] CHATTER READY")) and mode == "machine":
            with self.condition:
                self.error=BinaryUserError("local_controller_reset","controller reset invalidated machine epoch")
                self.mode="failed"; self.condition.notify_all()

    def submit_binary(self, data: bytes, *, cancel_event=None) -> Ticket:
        return self._submit_until(data,time.monotonic()+self.legacy._binary_budget_s(len(data), cancel_event=cancel_event),cancel_event)

    def _submit_until(self, data, deadline, cancel_event):
        payload=bytes(data)
        if not 1 <= len(payload) <= self.payload_capacity: raise BinaryUserError("invalid_binary_payload","machine payload outside capacity")
        with self.legacy._bounded_lock(self.operation_lock,deadline):
            self._ready(deadline,cancel_event)
            if self.mode == "legacy": return self.legacy.submit_binary(payload,cancel_event=cancel_event)
            if cancel_event is not None and cancel_event.is_set(): raise BinaryUserCancelled()
            with self.condition:
                if any(item.outcome == Kind.UNKNOWN for item in self.pending.values()):
                    raise BinaryUserError("local_tx_unsettled","unknown machine outcome blocks new SUBMIT")
                if len(self.pending)>=2: raise BinaryUserError("binary_pipeline_full","two machine tickets remain unresolved")
                if self.next_request > 0xffffffff: raise BinaryUserError("machine_request_exhausted","machine request identity exhausted")
                request=self.next_request; self.next_request+=1
                ticket=Ticket(self.epoch,request,self.legacy._generation(),payload,deadline)
                self.pending[request]=ticket; self.order.append(request)
            try:
                ticket.tx_id=self._write(Frame(Kind.SUBMIT,ticket.epoch,request,payload),deadline,cancel_event)
            except BinaryUserError as exc:
                # QUERY не выпускает новый RF USER и сохраняет старую identity.
                # Нельзя повторять SUBMIT лишь потому, что write был unknown.
                try:
                    self._write(Frame(Kind.QUERY,ticket.epoch,request),deadline,cancel_event)
                except BinaryUserError:
                    with self.condition:
                        self.error=BinaryUserError("local_tx_unsettled",f"SUBMIT/QUERY unresolved: {exc}")
                    raise self.error from exc
            return ticket

    def settle_binary(self, ticket, *, cancel_event=None) -> BinarySendReceipt:
        if self.mode == "legacy": return self.legacy.settle_binary(ticket,cancel_event=cancel_event)
        if not isinstance(ticket,Ticket): raise BinaryUserError("binary_pipeline_ticket","invalid machine ticket")
        queried=False
        credit_queried=False
        while True:
            with self.condition:
                if self.pending.get(ticket.request) is not ticket or not self.order or self.order[0]!=ticket.request:
                    raise BinaryUserError("binary_pipeline_order","machine tickets settle in submission order")
                if self.error is not None: raise self.error
                if ticket.epoch != self.epoch:
                    raise BinaryUserError("local_tx_unsettled","machine ticket epoch changed")
                if self.legacy._generation()!=ticket.generation:
                    raise BinaryUserError("local_disconnect","machine ticket connection generation changed")
                outcome=ticket.outcome
                if outcome in {Kind.LINK_OK,Kind.LINK_FAIL,Kind.REJECTED,Kind.UNKNOWN,Kind.UNAVAILABLE}:
                    # UNKNOWN сохраняет ticket/admission до нового доказательства.
                    if outcome == Kind.UNKNOWN: raise BinaryUserError("local_tx_unsettled","node has no retained submission outcome")
                    self.pending.pop(ticket.request); self.order.popleft()
                    if outcome == Kind.LINK_OK: return BinarySendReceipt(ticket.tx_id)
                    code={Kind.LINK_FAIL:"machine_link_failed",Kind.REJECTED:"send_rejected",Kind.UNAVAILABLE:"radio_unavailable"}[outcome]
                    raise BinaryUserError(code,f"machine terminal outcome {outcome.name}, rejection={ticket.rejection}")
                remaining=ticket.deadline-time.monotonic()
                if remaining <= 0: raise BinaryUserError("local_tx_unsettled","machine outcome deadline expired")
                if self.closed.is_set(): raise BinaryUserCancelled()
                if cancel_event is not None and cancel_event.is_set(): raise BinaryUserCancelled()
                deadline_query=not queried and remaining <= 1.0
                hints=[at for at in (ticket.credit_returned_at,ticket.later_terminal_at) if at is not None]
                credit_query=not credit_queried and bool(hints) and time.monotonic()-min(hints) >= 0.1
                should_query=deadline_query or credit_query
                if not should_query: self.condition.wait(min(remaining,0.1))
            if should_query:
                queried=queried or deadline_query
                credit_queried=credit_queried or credit_query
                self._write(Frame(Kind.QUERY,ticket.epoch,ticket.request),ticket.deadline,cancel_event)

    def send_binary(self,data,*,cancel_event=None):
        return self.send_binary_until(data,deadline=time.monotonic()+self.legacy._binary_budget_s(len(data), cancel_event=cancel_event),cancel_event=cancel_event)

    def send_binary_until(self,data,*,deadline,cancel_event=None):
        with self.legacy._bounded_lock(self.operation_lock,deadline):
            self._ready(deadline,cancel_event)
            if self.mode == "legacy": return self.legacy.send_binary_until(data,deadline=deadline,cancel_event=cancel_event)
        ticket=self._submit_until(data,deadline,cancel_event)
        return self.settle_binary(ticket,cancel_event=cancel_event)

    def discard_binary_pipeline(self) -> None:
        if self.mode == "legacy": self.legacy.discard_binary_pipeline(); return
        # Очистка deque не отменяет нижний RF: нужен reset или fresh epoch proof.
        self.legacy.drain_binary(1.0)
        if self.error is not None and self.error.code == "local_controller_reset":
            with self.condition:
                self.pending.clear(); self.order.clear()
        elif self.mode == "machine" and self.negotiated_generation != self.legacy._generation():
            try:
                self._ready(time.monotonic()+self.legacy._controller_ready_budget_s())
            except BinaryUserError as exc:
                if exc.code != "local_controller_reset": raise
        self.drain_binary(self.timing_budget_s("drain"))
        with self.condition:
            if self.pending: raise BinaryUserError("local_tx_unsettled","machine submissions remain unresolved")

    def drain_binary(self,timeout_s):
        deadline=time.monotonic()+max(0.0,timeout_s)
        outcomes=self.legacy.drain_binary(max(0.0,deadline-time.monotonic()))
        queried=set()
        while True:
            with self.condition:
                for request in list(self.order):
                    ticket=self.pending[request]
                    if ticket.outcome in {Kind.LINK_OK,Kind.LINK_FAIL,Kind.REJECTED,Kind.UNAVAILABLE}:
                        self.order.remove(request); self.pending.pop(request)
                if not self.pending: return outcomes
                if any(ticket.outcome==Kind.UNKNOWN for ticket in self.pending.values()):
                    raise BinaryUserError("local_tx_unsettled","machine outcome remains UNKNOWN")
                remaining=deadline-time.monotonic()
                if remaining <= 0: raise BinaryUserError("local_tx_unsettled","machine RF outcomes remain unresolved at drain deadline")
                query=next((ticket for request,ticket in self.pending.items() if request not in queried),None)
                if query is None:
                    self.condition.wait(min(remaining,0.1))
                    continue
                queried.add(query.request)
            # Drain может читать cached outcome, но не повторяет ни одного RF USER.
            self._write(Frame(Kind.QUERY,query.epoch,query.request),deadline)

    def controller_status(self):
        result=self.legacy.controller_status()
        with self.condition:
            result.update(machine_mode=self.mode,machine_epoch=self.epoch,machine_pending=len(self.pending),machine_status=dict(self.status),machine_parse_errors=self.parse_errors)
        return result

    def close(self):
        # CLOSE освобождает idle machine owner, не отменяет outstanding RF.
        if self.mode == "machine" and not self.pending:
            deadline=time.monotonic()+0.5
            with self.condition:
                self.close_request=self.next_request
            try:
                self._write(Frame(Kind.CLOSE,self.epoch,self.close_request),deadline)
                with self.condition:
                    while not self.close_acknowledged:
                        remaining=deadline-time.monotonic()
                        if remaining <= 0: break
                        self.condition.wait(remaining)
            except BinaryUserError: pass
        self.closed.set()
        with self.condition: self.condition.notify_all()
        if self.start_thread is not None and self.start_thread is not threading.current_thread(): self.start_thread.join(timeout=0.5)
