from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ...transports.ble_nus import NUS_RX_UUID, NUS_TX_UUID
from ..base import (
    BleProfileConfig,
    PresentationAdapter,
    ProfileAction,
    ReceiveCharacteristic,
    SendBytes,
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
CHATTER_TELEMETRY_TX_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"

# Raw Chatter controls являются двухбайтовым wire ABI. Human hotkeys отправляют
# их как exact bytes без configured EOL; текстовые /chat, /tele, /both и /echo
# по-прежнему идут через обычный line-oriented input path.
_HUMAN_ACTIONS = MappingProxyType(
    {
        **{
            action: SendBytes(command.encode("ascii"))
            for action, command in CHATTER_OUTPUT_MODE_COMMANDS.items()
        },
        "echo": SendBytes(CHATTER_ECHO_TOGGLE.encode("ascii")),
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
_HUMAN_HELP_LINES = (
    "BLE 0004 telemetry is background/transcript-only; normal console follows 0003",
    "/chat /tele /both /echo /reboot are sent unchanged to Chatter",
    "/cancel /cancel all are sent unchanged to Chatter",
    "/id requests the canonical Chatter node identity",
    "/version (/firmware alias) requests firmware provenance",
    "/power and /power N query/set persisted radio power",
    "/config and /config reset show/reset persisted settings",
    "/help requests Chatter help",
    "Ctrl+T 1/c   Chatter human console: CHAT",
    "Ctrl+T 2/t   Chatter human console: TELEMETRY",
    "Ctrl+T 3/b   Chatter human console: BOTH",
    "Ctrl+T e     Chatter echo mode toggle",
    "Ctrl+T ?     full help (this list + Chatter /help)",
)
_BLE_CONFIG = BleProfileConfig(
    write_characteristic=NUS_RX_UUID,
    receive_streams=(
        ReceiveCharacteristic(NUS_TX_UUID, "chat"),
        # 0004 опционален: отсутствие telemetry characteristic не должно
        # ронять connection; human console остаётся на standard NUS TX.
        ReceiveCharacteristic(
            CHATTER_TELEMETRY_TX_UUID,
            "telemetry",
            required=False,
        ),
    ),
)


@dataclass(frozen=True)
class ChatterProfile:
    name: str = "chatter"
    device_help_command: str | None = CHATTER_HELP_COMMAND

    def connect_preamble(self) -> tuple[ProfileAction, ...]:
        return (SendLine(CHATTER_ID_COMMAND),)

    def human_hotkeys(self) -> tuple[tuple[str, str], ...]:
        return _HUMAN_HOTKEYS

    def human_actions(self) -> Mapping[str, ProfileAction]:
        return _HUMAN_ACTIONS

    def human_help_lines(self) -> tuple[str, ...]:
        return _HUMAN_HELP_LINES

    def human_console_streams(self) -> tuple[str, ...]:
        return ("main", "chat")

    def device_help_action(self) -> ProfileAction | None:
        return SendLine(CHATTER_HELP_COMMAND)

    def ble_config(self) -> BleProfileConfig | None:
        return _BLE_CONFIG

    def make_presentation(self) -> PresentationAdapter | None:
        return ChatterPresentation()

    def recognized_command(self, line: str) -> str | None:
        return recognized_chatter_command(line)


CHATTER_PROFILE = ChatterProfile()
