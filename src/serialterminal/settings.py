from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SerialDefaults:
    generic_baud: int = 115200
    chatter_baud: int = 921600


@dataclass(frozen=True)
class DiscoveryDefaults:
    terminal_scan_seconds: float = 3.0
    scanner_scan_seconds: float = 5.0
    probe_timeout_seconds: float = 8.0


@dataclass(frozen=True)
class SessionDefaults:
    reconnect_delay: float = 0.5
    human_bluetooth_reconnect_delay: float = 1.0


@dataclass(frozen=True)
class TerminalDefaults:
    serial: SerialDefaults = SerialDefaults()
    discovery: DiscoveryDefaults = DiscoveryDefaults()
    session: SessionDefaults = SessionDefaults()


DEFAULTS = TerminalDefaults()


class SerialBaudProfile(Protocol):
    default_serial_baud: int


def resolve_serial_baud(
    profile: SerialBaudProfile,
    explicit_baud: int | None = None,
) -> int:
    # Профиль выбирает policy; transport получает уже разрешённый baud.
    return profile.default_serial_baud if explicit_baud is None else explicit_baud
