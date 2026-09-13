from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ...transports.ble_nus import (
    NUS_CHAT_TX_UUID,
    NUS_RX_UUID,
    NUS_TELEMETRY_TX_UUID,
)
from ..base import (
    BleProfileConfig,
    PresentationAdapter,
    ProfileAction,
    ReceiveCharacteristic,
    SendLine,
)
from .presentation import ChatterPresentation, recognized_chatter_command


CHATTER_ECHO_TOGGLE = "\x14e"
CHATTER_OUTPUT_MODE_COMMANDS = {
    "output_chat": "\x141",
    "output_telemetry": "\x142",
    "output_both": "\x143",
}
CHATTER_HELP_COMMAND = "/help"
CHATTER_ID_COMMAND = "/id"
CHATTER_SYSTEM_PREFIX = "[SYS]"

# Эти control sequences намеренно остаются SendLine: текущий human UI
# добавляет configured EOL, и этот compatibility slice не меняет wire bytes.
_HUMAN_ACTIONS = MappingProxyType(
    {
        **{
            action: SendLine(command)
            for action, command in CHATTER_OUTPUT_MODE_COMMANDS.items()
        },
        "echo": SendLine(CHATTER_ECHO_TOGGLE),
    }
)
_HUMAN_HOTKEYS = (
    ("1", "output_chat"),
    ("2", "output_telemetry"),
    ("3", "output_both"),
    ("c", "output_chat"),
    ("t", "output_telemetry"),
    ("b", "output_both"),
    ("e", "echo"),
)
_BLE_CONFIG = BleProfileConfig(
    write_characteristic=NUS_RX_UUID,
    receive_streams=(
        ReceiveCharacteristic(NUS_CHAT_TX_UUID, "chat"),
        ReceiveCharacteristic(NUS_TELEMETRY_TX_UUID, "telemetry"),
    ),
)


@dataclass(frozen=True)
class ChatterProfile:
    name: str = "chatter"
    device_help_command: str | None = CHATTER_HELP_COMMAND
    system_line_prefix: str | None = CHATTER_SYSTEM_PREFIX

    def connect_preamble(self) -> tuple[ProfileAction, ...]:
        return (SendLine(CHATTER_ID_COMMAND),)

    def human_hotkeys(self) -> tuple[tuple[str, str], ...]:
        return _HUMAN_HOTKEYS

    def human_actions(self) -> Mapping[str, ProfileAction]:
        return _HUMAN_ACTIONS

    def device_help_action(self) -> ProfileAction | None:
        return SendLine(CHATTER_HELP_COMMAND)

    def ble_config(self) -> BleProfileConfig | None:
        return _BLE_CONFIG

    def make_presentation(self) -> PresentationAdapter | None:
        return ChatterPresentation()

    def recognized_command(self, line: str) -> str | None:
        return recognized_chatter_command(line)


CHATTER_PROFILE = ChatterProfile()
