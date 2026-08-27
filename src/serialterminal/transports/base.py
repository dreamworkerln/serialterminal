from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class TransportError(Exception):
    """Recoverable transport I/O error."""


@dataclass(frozen=True)
class ReceivedChunk:
    """One transport receive event with an optional logical stream tag."""

    stream: str
    data: bytes


class Transport(ABC):
    """Byte-stream transport used by the terminal UI."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @property
    def device_key(self) -> str:
        """Stable-enough identity used to compare explicit device selections."""
        return self.description

    @property
    def stream_capabilities(self) -> tuple[str, ...]:
        """Logical receive streams exposed by this transport."""
        return ("main",)

    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Release transport resources permanently."""
        self.disconnect()

    @abstractmethod
    def read(self, size: int = 512) -> bytes:
        raise NotImplementedError

    def read_chunk(self, size: int = 512) -> ReceivedChunk:
        """Read one tagged chunk. Plain byte transports use the `main` stream."""
        return ReceivedChunk("main", self.read(size))

    @abstractmethod
    def write(self, data: bytes) -> None:
        raise NotImplementedError
