from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeAlias


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


@dataclass(frozen=True)
class BleProfileConfig:
    write_characteristic: str
    receive_streams: tuple[ReceiveCharacteristic, ...]


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
    system_line_prefix: str | None

    def connect_preamble(self) -> tuple[ProfileAction, ...]:
        ...

    def human_hotkeys(self) -> tuple[tuple[str, str], ...]:
        ...

    def human_actions(self) -> Mapping[str, ProfileAction]:
        ...

    def device_help_action(self) -> ProfileAction | None:
        ...

    def ble_config(self) -> BleProfileConfig | None:
        ...

    def make_presentation(self) -> PresentationAdapter | None:
        ...

    def recognized_command(self, line: str) -> str | None:
        ...
