from __future__ import annotations

import argparse
from datetime import datetime
import sys

from .terminal import TerminalSession
from .transports.serial import SerialTransport, find_ports


def _serial_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Line-oriented terminal (Serial Port by default)",
        epilog=(
            "Transports: use 'serialterminal serial ...' explicitly for Serial, "
            "or 'serialterminal ble [pinger|repeater]' for Nordic UART BLE."
        ),
    )
    parser.add_argument(
        "device",
        nargs="?",
        default=None,
        help="Serial device; if omitted, auto-detect",
    )
    parser.add_argument(
        "-b",
        "--baud",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List detected serial devices and exit",
    )
    parser.add_argument(
        "--log",
        default="serialterminal.log",
        help="Transcript log file (default: serialterminal.log)",
    )
    parser.add_argument(
        "--eol",
        choices=("lf", "crlf", "cr"),
        default="lf",
        help="Line ending sent after Enter (default: lf)",
    )
    return parser


def _ble_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Nordic UART Service terminal for LoRa-Pinger / LoRa-Repeater",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="pinger/repeater (also accepts p/r); auto-select if only one is visible",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="Log file; default: nus-<target>-YYYYMMDD-HHMMSS.log",
    )
    parser.add_argument(
        "--eol",
        choices=("lf", "crlf", "cr"),
        default="lf",
        help="Line ending sent after Enter (default: lf)",
    )
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=3.0,
        help="BLE scan duration for each connect attempt (default: 3)",
    )
    return parser


def _line_ending(name: str) -> str:
    return {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[name]


def _run_serial(argv: list[str], prog: str) -> int:
    args = _serial_parser(prog).parse_args(argv)

    if args.list:
        ports = find_ports()
        if not ports:
            print("No serial devices found.")
            return 1
        for port in ports:
            print(port)
        return 0

    transport = SerialTransport(device=args.device, baud=args.baud)
    TerminalSession(
        transport=transport,
        log_path=args.log,
        line_ending=_line_ending(args.eol),
    ).run()
    return 0


def _choose_ble_target(value: str | None, scan_seconds: float, parser) -> str:
    from .transports.ble_nus import (
        PINGER_NAME,
        REPEATER_NAME,
        discover_echo_nodes,
        normalize_ble_target,
    )

    if value is not None:
        target = normalize_ble_target(value)
        if target is None:
            parser.error("unknown BLE target; use pinger/repeater (or p/r)")
        print(f"Target forced from command line: {target}")
        return target

    while True:
        print("Searching for LoRa-Pinger / LoRa-Repeater...")
        try:
            found = discover_echo_nodes(scan_seconds)
        except Exception as exc:
            parser.error(str(exc))

        if not found:
            print("No Echo BLE nodes found; scanning again...")
            continue

        if len(found) == 1:
            target = next(iter(found))
            print(f"Only one Echo node is visible: {target}")
            return target

        print("Both Echo nodes are visible:")
        print(f"  P - {PINGER_NAME}")
        print(f"  R - {REPEATER_NAME}")

        while True:
            answer = input("Connect to [P/R]: ").strip()
            target = normalize_ble_target(answer)
            if target is not None:
                return target
            print("Please enter P or R.")


def _run_ble(argv: list[str], prog: str) -> int:
    parser = _ble_parser(prog)
    args = parser.parse_args(argv)

    try:
        from .transports.ble_nus import BleNusTransport, ble_log_slug
    except Exception as exc:
        parser.error(str(exc))

    target = _choose_ble_target(args.target, args.scan_seconds, parser)
    print(f"Locked target: {target}")
    print("After disconnect/reboot only this target will be retried.\n")

    log_path = args.log
    if log_path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = f"nus-{ble_log_slug(target)}-{stamp}.log"

    try:
        transport = BleNusTransport(
            target_name=target,
            scan_timeout=args.scan_seconds,
        )
    except Exception as exc:
        parser.error(str(exc))

    print("BLE log commands: LF = full, LC = compact, L = current mode")
    TerminalSession(
        transport=transport,
        log_path=log_path,
        line_ending=_line_ending(args.eol),
        reconnect_delay=1.0,
    ).run()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "ble":
        return _run_ble(args[1:], "serialterminal ble")

    if args and args[0] == "serial":
        return _run_serial(args[1:], "serialterminal serial")

    # Backward compatibility:
    #   serialterminal
    #   serialterminal /dev/ttyUSB0
    #   serialterminal -b 9600 /dev/ttyUSB0
    return _run_serial(args, "serialterminal")
