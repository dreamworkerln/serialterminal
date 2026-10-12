from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Protocol


BinaryReceiver = Callable[[bytes], None]


@dataclass(frozen=True)
class BinarySendReceipt:
    """Controller-local BINARY submission receipt, never remote delivery proof."""

    tx_id: int | None


class BinaryUserError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BinaryUserCancelled(BinaryUserError):
    def __init__(self, message: str = "binary USER send cancelled"):
        super().__init__("cancelled", message)


class BinaryUserTransport(Protocol):
    """Opaque BINARY application transport used by the FT1 file layer.

    send_binary() settles only controller-local submission/backpressure. Remote
    application completion belongs to FT1 RESULT/MISSING semantics.

    Необязательные capabilities: timing_budget_s(purpose) возвращает opaque
    положительный конечный бюджет control/resume/drain; prepare_binary(deadline,
    cancel_event) ограничивает local readiness отдельно от отправки по радио.
    Расчёт физического времени остаётся в конкретном transport/profile.
    """

    payload_capacity: int

    def set_receiver(self, receiver: BinaryReceiver | None) -> None:
        ...

    def send_binary(
        self,
        data: bytes,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BinarySendReceipt:
        ...
