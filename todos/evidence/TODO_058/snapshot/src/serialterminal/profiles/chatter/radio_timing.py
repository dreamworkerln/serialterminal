from __future__ import annotations

from dataclasses import dataclass
import math
import re
import threading
import time

from ...file_transfer.transport import BinaryUserCancelled, BinaryUserError
from .controller_lifecycle import parse_controller_lifecycle_line


# Размеры ProtocolFrame, retry policy и UART guard соответствуют Chatter.
FRAME_HEADER_BYTES = 12
ACK_FRAME_BYTES = 14
MAX_FRAME_BYTES = 255
MAX_ATTEMPTS = 5
ACK_RESPONSE_GUARD_S = math.ceil(640 * 2 * 10 * 1000 / 115200) / 1000 + 0.004
TX_TIMEOUT_TOA_FACTOR = 1.5
MAX_BACKOFF_SHIFT = 2
LOCAL_COMMAND_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class RadioTiming:
    sf: int
    bandwidth_hz: int
    coding_rate: int = 5
    preamble: int = 8
    crc: bool = True
    implicit_header: bool = False
    ldro: bool | None = None
    attempts: int = MAX_ATTEMPTS

    def __post_init__(self):
        if not (6 <= self.sf <= 12 and 7800 <= self.bandwidth_hz <= 500000
                and 5 <= self.coding_rate <= 8 and 1 <= self.preamble <= 65535
                and 1 <= self.attempts <= MAX_ATTEMPTS):
            raise ValueError("invalid Chatter PHY/retry configuration")

    def toa_s(self, frame_bytes: int) -> float:
        if not 0 <= frame_bytes <= MAX_FRAME_BYTES:
            raise ValueError("radio frame outside SX127x capacity")
        symbol_s = (1 << self.sf) / self.bandwidth_hz
        de = self.ldro if self.ldro is not None else symbol_s >= 0.016
        numerator = 8 * frame_bytes - 4 * self.sf + 28 + 16 * self.crc - 20 * self.implicit_header
        payload_symbols = 8 + max(math.ceil(numerator / (4 * (self.sf - 2 * de))) * self.coding_rate, 0)
        # RadioLib SX127x getTimeOnAir округляет вверх до целой миллисекунды.
        return math.ceil((self.preamble + 4.25 + payload_symbols) * symbol_s * 1000) / 1000

    def transaction_s(self, payload_bytes: int = MAX_FRAME_BYTES - FRAME_HEADER_BYTES) -> float:
        user = self.toa_s(FRAME_HEADER_BYTES + payload_bytes)
        ack = self.toa_s(ACK_FRAME_BYTES)
        backoff = sum(math.ceil(user * 1000 * 0.5 * (1 << min(n, MAX_BACKOFF_SHIFT))) / 1000
                      + math.ceil(user * 1000 * (1 << min(n, MAX_BACKOFF_SHIFT))) / 1000
                      for n in range(self.attempts - 1))
        # Это deadline, а не pacing. Учитываем TxDone watchdog, ACK и максимум
        # jitter каждой попытки; посторонний непрерывный RF traffic этим не ограничен.
        return (self.attempts * (TX_TIMEOUT_TOA_FACTOR * user + ack + ACK_RESPONSE_GUARD_S)
                + backoff + 2 * (1 << self.sf) / self.bandwidth_hz + ACK_RESPONSE_GUARD_S)

    def budget_s(self, purpose: str, payload_bytes: int = 243) -> float:
        if purpose == "cancel":
            # CANCEL не запускает следующие attempts, но уже начатый RF packet
            # может завершаться до TxDone watchdog и освобождения ACK/RX boundary.
            return (TX_TIMEOUT_TOA_FACTOR * self.toa_s(FRAME_HEADER_BYTES + payload_bytes)
                    + self.toa_s(ACK_FRAME_BYTES) + ACK_RESPONSE_GUARD_S
                    + 2 * (1 << self.sf) / self.bandwidth_hz + LOCAL_COMMAND_TIMEOUT_S)
        transaction = self.transaction_s(payload_bytes)
        slots = {"binary": 2, "drain": 2, "control": 4, "resume": 4}.get(purpose)
        if slots is None:
            raise ValueError(f"unknown timing purpose: {purpose}")
        # Два firmware slots могут обслуживаться последовательно. Для FT1
        # ответа резервируем обе очереди: передающий END/META и обратный RESULT/RESUME.
        return slots * transaction + LOCAL_COMMAND_TIMEOUT_S


_CFG_RADIO = re.compile(r"CFG RADIO .* sf=(\d+) bw=([\d.]+) kHz")
_CFG_LINK = re.compile(r"CFG LINK .*retry=(ON|OFF) attempts=(\d+)")


class RadioTimingReader:
    """Кэш прочитанного PHY принадлежит controller epoch и transport generation."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.condition = threading.Condition()
        self.query_lock = threading.Lock()
        self.snapshot: RadioTiming | None = None
        self.identity = None
        self.last_snapshot: RadioTiming | None = None
        self.reading = False
        self.revision = 0
        self.fields = {}
        self.completed = False

    def invalidate(self):
        with self.condition:
            self.revision += 1
            self.snapshot = None
            self.identity = None
            self.condition.notify_all()

    def feed_line(self, line: str):
        with self.condition:
            if parse_controller_lifecycle_line(line) is not None or (
                line.startswith("[SYS]") and any(marker in line for marker in (" SAVED", "phase=repair", "phase=validate"))
            ):
                self.revision += 1
                self.snapshot = None
                self.identity = None
                if " SAVED" in line or "phase=repair" in line:
                    # После изменения PHY старый снимок уже не ограничивает
                    # время boot self-test; до нового readback нужен worst case.
                    self.last_snapshot = None
            if not self.reading:
                return
            radio = _CFG_RADIO.search(line)
            link = _CFG_LINK.search(line)
            if radio:
                self.fields.update(expected_sf=int(radio[1]), expected_bw=int(round(float(radio[2]) * 1000)))
            if link:
                self.fields["attempts"] = int(link[2]) if link[1] == "ON" else 1
            if "RADIO_CONFIG_REGS phase=read" in line or "RADIO_CONFIG_DECODE phase=read" in line:
                for key, value in re.findall(r"(\w+)=([^ ]+)", line.strip()):
                    self.fields[key] = value
            if "RADIO_CONFIG phase=read" in line:
                self.completed = True
            self.condition.notify_all()

    def get(self, *, cancel_event=None, deadline=None) -> RadioTiming:
        if not self.adapter._controller_ready:
            raise BinaryUserError("local_controller_reset", "radio timing is unavailable until controller READY")
        local_deadline = time.monotonic() + LOCAL_COMMAND_TIMEOUT_S
        if deadline is not None:
            local_deadline = min(local_deadline, deadline)
        with self.adapter._bounded_lock(self.query_lock, local_deadline):
            identity = (self.adapter._generation(), self.adapter._controller_epoch, self.revision)
            with self.condition:
                if self.snapshot is not None and self.identity == identity:
                    return self.snapshot
                self.reading = True
                self.fields = {}
                self.completed = False
            try:
                for command in ("/config", "/radio read config"):
                    result = self.adapter._submit_line(command, deadline=local_deadline)
                    tx_id = result.get("tx_id") if isinstance(result, dict) else None
                    self.adapter._wait_tx_written(tx_id, local_deadline, cancel_event=cancel_event)
                with self.condition:
                    while not (self.completed and "attempts" in self.fields and "expected_sf" in self.fields):
                        if cancel_event is not None and cancel_event.is_set():
                            raise BinaryUserCancelled()
                        if identity != (self.adapter._generation(), self.adapter._controller_epoch, self.revision):
                            raise BinaryUserError("local_controller_reset", "controller changed while reading radio timing")
                        remaining = local_deadline - time.monotonic()
                        if remaining <= 0:
                            raise BinaryUserError("radio_timing_unavailable", "no complete /config and radio readback; RF deadline cannot be calculated")
                        self.condition.wait(min(remaining, 0.1))
                    f = self.fields
                    try:
                        if f["bank"] != "LoRa" or int(f["sf"]) != f["expected_sf"] or int(f["bw_Hz"]) != f["expected_bw"]:
                            raise ValueError("radio readback differs from node PHY")
                        result = RadioTiming(sf=int(f["sf"]), bandwidth_hz=int(f["bw_Hz"]),
                                             coding_rate=int(f["cr"].split("/")[1]), preamble=int(f["preamble"]),
                                             crc=bool(int(f["crc"])), implicit_header=f["header"] == "implicit",
                                             ldro=bool(int(f["ldro"])), attempts=int(f["attempts"]))
                    except (KeyError, ValueError, TypeError) as exc:
                        raise BinaryUserError("radio_timing_unavailable", f"invalid radio timing readback: {exc}") from exc
                    if identity != (self.adapter._generation(), self.adapter._controller_epoch, self.revision):
                        raise BinaryUserError("local_controller_reset", "radio timing belongs to old controller")
                    self.snapshot = result
                    self.last_snapshot = result
                    self.identity = identity
                self.adapter._timing("radio_timing_read", sf=result.sf, bandwidth_hz=result.bandwidth_hz,
                                     attempts=result.attempts, binary_budget_s=result.budget_s("binary"),
                                     control_budget_s=result.budget_s("control"))
                return result
            finally:
                with self.condition:
                    self.reading = False
