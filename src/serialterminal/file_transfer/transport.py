from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Protocol, runtime_checkable


BinaryReceiver = Callable[[bytes], None]


@dataclass(frozen=True)
class BinaryDelivery:
    tx_id: int | None
    user_id: str | None


class BinaryUserError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BinaryUserCancelled(BinaryUserError):
    def __init__(self, message: str = "binary USER send cancelled"):
        super().__init__("cancelled", message)


class BinaryUserTransport(Protocol):
    """Opaque reliable binary-message transport used by file-transfer core."""

    payload_capacity: int

    def set_receiver(self, receiver: BinaryReceiver | None) -> None:
        ...

    def send_binary(
        self,
        data: bytes,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BinaryDelivery:
        ...


@runtime_checkable
class BinaryUserTransferLifecycle(Protocol):
    """Опциональная подготовка/очистка вокруг одной binary-передачи."""

    def begin_transfer(self) -> None:
        ...

    def end_transfer(self) -> None:
        ...
