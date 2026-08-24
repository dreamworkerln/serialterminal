from __future__ import annotations

from abc import ABC, abstractmethod


class TransportError(Exception):
    """Recoverable transport I/O error."""


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

    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self, size: int = 512) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def write(self, data: bytes) -> None:
        raise NotImplementedError
