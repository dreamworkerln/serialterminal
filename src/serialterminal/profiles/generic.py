from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..transports.ble_nus import NUS_RX_UUID, NUS_TX_UUID
from .base import (
    BleProfileConfig,
    PresentationAdapter,
    ProfileAction,
    ReceiveCharacteristic,
)


_EMPTY_ACTIONS: Mapping[str, ProfileAction] = MappingProxyType({})
_BLE_CONFIG = BleProfileConfig(
    write_characteristic=NUS_RX_UUID,
    receive_streams=(ReceiveCharacteristic(NUS_TX_UUID, "main"),),
)


@dataclass(frozen=True)
class GenericProfile:
    name: str = "generic"
    device_help_command: str | None = None
    system_line_prefix: str | None = None

    def connect_preamble(self) -> tuple[ProfileAction, ...]:
        return ()

    def human_hotkeys(self) -> tuple[tuple[str, str], ...]:
        return ()

    def human_actions(self) -> Mapping[str, ProfileAction]:
        return _EMPTY_ACTIONS

    def human_help_lines(self) -> tuple[str, ...]:
        return ()

    def human_console_streams(self) -> tuple[str, ...]:
        return ("main",)

    def device_help_action(self) -> ProfileAction | None:
        return None

    def ble_config(self) -> BleProfileConfig | None:
        return _BLE_CONFIG

    def make_presentation(self) -> PresentationAdapter | None:
        return None

    def recognized_command(self, line: str) -> str | None:
        return None


GENERIC_PROFILE = GenericProfile()
