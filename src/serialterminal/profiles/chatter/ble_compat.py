from __future__ import annotations

PINGER_NAME = "LoRa-Pinger"
REPEATER_NAME = "LoRa-Repeater"


def is_chatter_ble_name(name: str | None) -> bool:
    """Compatibility hint для project BLE nodes в namespace LoRa-*."""
    return bool(name and name.startswith("LoRa-"))


def normalize_chatter_ble_target(value: str) -> str | None:
    """Разрешить legacy Pinger/Repeater aliases или exact LoRa-* name."""
    value = value.strip()
    lower = value.lower()
    if lower in {"p", "ping", "pinger", PINGER_NAME.lower()}:
        return PINGER_NAME
    if lower in {"r", "rep", "repeater", REPEATER_NAME.lower()}:
        return REPEATER_NAME
    if lower.startswith("lora-"):
        return value
    return None
