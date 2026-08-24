from __future__ import annotations

import argparse

from .terminal import TerminalSession
from .transports.serial import SerialTransport, find_ports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Line-oriented terminal with pluggable transports"
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        ports = find_ports()
        if not ports:
            print("No serial devices found.")
            return 1
        for port in ports:
            print(port)
        return 0

    endings = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}
    transport = SerialTransport(device=args.device, baud=args.baud)
    TerminalSession(
        transport=transport,
        log_path=args.log,
        line_ending=endings[args.eol],
    ).run()
    return 0
