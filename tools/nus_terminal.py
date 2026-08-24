#!/usr/bin/env python3
"""Compatibility wrapper for the old tools/nus_terminal.py entry point."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from serialterminal.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["ble", *sys.argv[1:]]))
