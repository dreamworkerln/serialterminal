from __future__ import annotations

import asyncio
from dataclasses import dataclass
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

from .ble_discovery import probe_ble_nus_async, scan_all_ble_devices
from .device_cache import default_cache_path, update_cached_device
from .transports.bluetooth_spp import (
    discover_classic_devices,
    probe_spp_device,
)


@dataclass(frozen=True)
class ScannerSummary:
    ble_total: int = 0
    ble_nus: int = 0
    spp_total: int = 0
    spp_confirmed: int = 0
    unknown: int = 0


def _yn(value: bool | None) -> str:
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return "UNKNOWN"


async def _scan_ble_async(
    *,
    scan_seconds: float = 5.0,
    probe_timeout: float = 8.0,
) -> ScannerSummary:
    """Scan and probe every BLE candidate on one asyncio/BlueZ event loop."""
    print(f"Scanning all BLE devices for {scan_seconds:g}s...")
    items = await scan_all_ble_devices(scan_seconds)
    confirmed = 0
    unknown = 0

    for index, item in enumerate(items, start=1):
        identity = item.identity
        print(
            f"[{index}/{len(items)}] BLE  "
            f"{identity.name}  {identity.address}"
        )
        result = await probe_ble_nus_async(item, probe_timeout)
        print(
            f"      NUS={_yn(result.nus)}  "
            f"CHAT={_yn(result.chat)}  "
            f"TELEMETRY={_yn(result.telemetry)}"
        )
        if result.error:
            print(f"      probe: {result.error}")

        update_cached_device(
            kind="ble",
            address=identity.address,
            name=identity.name,
            capabilities={
                "nus": result.nus,
                "chat": result.chat,
                "telemetry": result.telemetry,
            },
            probe_status=result.status,
            error=result.error,
            metadata={
                "advertised_services": list(item.advertised_services),
            },
        )

        if result.nus is True:
            confirmed += 1
        if result.status == "unknown":
            unknown += 1

    return ScannerSummary(
        ble_total=len(items),
        ble_nus=confirmed,
        unknown=unknown,
    )


def scan_ble(
    *,
    scan_seconds: float = 5.0,
    probe_timeout: float = 8.0,
) -> ScannerSummary:
    # One event loop for discovery + every GATT probe. Repeated asyncio.run()
    # around individual Bleak clients can close the dbus-fast transport while
    # callbacks are still pending and surface "Future exception...BrokenPipe".
    return asyncio.run(
        _scan_ble_async(
            scan_seconds=scan_seconds,
            probe_timeout=probe_timeout,
        )
    )


def scan_spp(
    *,
    scan_seconds: float = 5.0,
    probe_timeout: float = 8.0,
    connect_test: bool = True,
) -> ScannerSummary:
    print(
        f"Scanning Classic Bluetooth devices for "
        f"{scan_seconds:g}s..."
    )
    items = discover_classic_devices(scan_seconds)
    confirmed = 0
    unknown = 0

    for index, item in enumerate(items, start=1):
        print(
            f"[{index}/{len(items)}] SPP? "
            f"{item.name}  {item.address}"
        )
        result = probe_spp_device(
            item.address,
            probe_timeout,
            connect_test=connect_test,
        )
        channel = str(result.channel) if result.channel is not None else "-"
        print(
            f"      SPP={_yn(result.spp)}  "
            f"RFCOMM={channel}  "
            f"connect={result.connect_test.upper()}"
        )
        if result.error:
            print(f"      probe: {result.error}")

        update_cached_device(
            kind="classic",
            address=item.address,
            name=item.name,
            capabilities={"spp": result.spp},
            probe_status=result.status,
            error=result.error,
            metadata={
                "rfcomm_channel": result.channel,
                "connect_test": result.connect_test,
            },
        )

        if result.spp is True:
            confirmed += 1
        if result.status == "unknown":
            unknown += 1

    return ScannerSummary(
        spp_total=len(items),
        spp_confirmed=confirmed,
        unknown=unknown,
    )


def run_scanner(
    mode: str,
    *,
    scan_seconds: float = 5.0,
    probe_timeout: float = 8.0,
    connect_test: bool = True,
) -> ScannerSummary:
    total = ScannerSummary()

    if mode in {"ble", "all"}:
        ble = scan_ble(
            scan_seconds=scan_seconds,
            probe_timeout=probe_timeout,
        )
        total = ScannerSummary(
            ble_total=ble.ble_total,
            ble_nus=ble.ble_nus,
            unknown=ble.unknown,
        )

    if mode in {"spp", "all"}:
        spp = scan_spp(
            scan_seconds=scan_seconds,
            probe_timeout=probe_timeout,
            connect_test=connect_test,
        )
        total = ScannerSummary(
            ble_total=total.ble_total,
            ble_nus=total.ble_nus,
            spp_total=spp.spp_total,
            spp_confirmed=spp.spp_confirmed,
            unknown=total.unknown + spp.unknown,
        )

    print(
        "Scanner summary: "
        f"BLE {total.ble_nus}/{total.ble_total} NUS, "
        f"SPP {total.spp_confirmed}/{total.spp_total}, "
        f"unknown={total.unknown}"
    )
    print(f"Capability cache: {default_cache_path()}")
    return total


def _scan_key_bindings() -> KeyBindings:
    """Return scanner-menu bindings where numeric choices act immediately."""
    bindings = KeyBindings()

    def add_choice(key: str) -> None:
        @bindings.add(key, eager=True)
        def _select(event) -> None:
            event.app.exit(result=key)

    for key in ("1", "2", "3"):
        add_choice(key)

    return bindings


def _read_scan_answer(prompt: str) -> str:
    session = PromptSession(
        key_bindings=_scan_key_bindings(),
        erase_when_done=True,
    )
    return session.prompt(prompt)


def choose_scan_mode(*, allow_cancel: bool = True) -> str | None:
    """Interactive scanner menu used by the terminal hotkey."""
    print("Bluetooth scanner")
    print("  1. Probe all BLE devices for NUS")
    print("  2. Probe Classic Bluetooth devices for SPP")
    print("  3. Probe all Bluetooth")
    if allow_cancel:
        print("  Enter. Back to terminal")

    mapping = {
        "1": "ble",
        "ble": "ble",
        "2": "spp",
        "spp": "spp",
        "3": "all",
        "all": "all",
    }

    while True:
        # TerminalSession keeps stdout wrapped by prompt_toolkit.patch_stdout().
        # Flush the menu before opening the nested scanner prompt. Numeric
        # choices use eager bindings and therefore do not require Enter.
        sys.stdout.flush()
        prompt = "Scan [1-3, Enter=back]: " if allow_cancel else "Scan [1-3]: "
        answer = _read_scan_answer(prompt).strip().lower()
        if allow_cancel and answer == "":
            return None
        if answer in mapping:
            return mapping[answer]
        print("Please enter 1, 2 or 3.")


def run_interactive_scanner() -> ScannerSummary | None:
    """Run the scanner menu from an already running serialterminal session."""
    mode = choose_scan_mode(allow_cancel=True)
    if mode is None:
        print("Scanner cancelled.")
        return None
    return run_scanner(mode)
