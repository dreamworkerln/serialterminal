from .base import (
    BleProfileConfig,
    PresentationAdapter,
    ProfileAction,
    ReceiveCharacteristic,
    SendBytes,
    SendLine,
    TerminalProfile,
)
from .generic import GENERIC_PROFILE, GenericProfile


PROFILE_NAMES = ("generic", "chatter")


def resolve_profile(name: str) -> TerminalProfile:
    normalized = name.strip().lower()
    if normalized == "generic":
        return GENERIC_PROFILE
    if normalized == "chatter":
        from .chatter import CHATTER_PROFILE

        return CHATTER_PROFILE
    raise ValueError(f"unknown terminal profile: {name}")


__all__ = [
    "BleProfileConfig",
    "GENERIC_PROFILE",
    "GenericProfile",
    "PROFILE_NAMES",
    "PresentationAdapter",
    "ProfileAction",
    "ReceiveCharacteristic",
    "SendBytes",
    "SendLine",
    "TerminalProfile",
    "resolve_profile",
]
