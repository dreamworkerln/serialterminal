from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeAlias

from ..file_transfer.transport import BinaryUserTransport
from ..sweep import SweepAdapterFactory


@dataclass(frozen=True)
class SendLine:
    text: str


@dataclass(frozen=True)
class SendBytes:
    data: bytes


ProfileAction: TypeAlias = SendLine | SendBytes


@dataclass(frozen=True)
class ReceiveCharacteristic:
    uuid: str
    stream: str
    required: bool = True


@dataclass(frozen=True)
class BleProfileConfig:
    write_characteristic: str
    receive_streams: tuple[ReceiveCharacteristic, ...]


class ProfileBinaryUserAdapter(BinaryUserTransport, Protocol):
    def feed_line(self, stream: str, line: str) -> None:
        ...


BinarySendLine: TypeAlias = Callable[[str], Any]
BinaryWaitTxOutcome: TypeAlias = Callable[[int, float], str | None]
BinaryConnectionGeneration: TypeAlias = Callable[[], int]


class TuiProfilePanel(Protocol):
    def connected_actions(self) -> tuple[ProfileAction, ...]:
        ...

    def consume_line(self, stream: str, line: str) -> None:
        ...

    def status_lines(self) -> tuple[str, ...]:
        ...


class PresentationAdapter(Protocol):
    def submit_payload(self, text: str) -> bool:
        ...

    def cancel_unsent_payload(self, text: str) -> None:
        ...

    def mark_sent(self, text: str) -> None:
        ...

    def consume_firmware_line(self, line: str) -> str | None:
        ...

    def consume_sent_on_disconnect(self) -> list[str]:
        ...


class TerminalProfile(Protocol):
    name: str
    device_help_command: str | None

    def connect_preamble(self) -> tuple[ProfileAction, ...]:
        ...

    def human_hotkeys(self) -> tuple[tuple[str, str], ...]:
        ...

    def human_actions(self) -> Mapping[str, ProfileAction]:
        ...

    def human_help_lines(self) -> tuple[str, ...]:
        ...

    def human_console_streams(self) -> tuple[str, ...]:
        ...

    def device_help_action(self) -> ProfileAction | None:
        ...

    def ble_config(self) -> BleProfileConfig | None:
        ...

    def make_presentation(self) -> PresentationAdapter | None:
        ...

    def make_tui_panel(self) -> TuiProfilePanel | None:
        ...

    def make_binary_user_transport(
        self,
        send_line: BinarySendLine,
        *,
        wait_tx_outcome: BinaryWaitTxOutcome | None = None,
        connection_generation: BinaryConnectionGeneration | None = None,
    ) -> ProfileBinaryUserAdapter | None:
        ...

    def recognized_command(self, line: str) -> str | None:
        ...

    def sweep_adapters(self) -> Mapping[str, SweepAdapterFactory]:
        ...
