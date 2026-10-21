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
class BleCleanupDefaults:
    notify_timeout_s: float = 1.0
    disconnect_timeout_s: float = 2.0
    bluez_timeout_s: float = 3.0
    shutdown_timeout_s: float = 8.0


@dataclass(frozen=True)
class VoiceDefaults:
    event_queue_size: int = 64
    playback_queue_size: int = 4
    process_stop_timeout_s: float = 2.0
    process_kill_timeout_s: float = 1.0
    playback_finish_timeout_s: float = 5.0


@dataclass(frozen=True)
class TerminalDefaults:
    serial: SerialDefaults = SerialDefaults()
    discovery: DiscoveryDefaults = DiscoveryDefaults()
    session: SessionDefaults = SessionDefaults()
    ble_cleanup: BleCleanupDefaults = BleCleanupDefaults()
    voice: VoiceDefaults = VoiceDefaults()


DEFAULTS = TerminalDefaults()


class SerialBaudProfile(Protocol):
    default_serial_baud: int


def resolve_serial_baud(
    profile: SerialBaudProfile,
    explicit_baud: int | None = None,
) -> int:
    # Профиль выбирает policy; transport получает уже разрешённый baud.
    return profile.default_serial_baud if explicit_baud is None else explicit_baud
