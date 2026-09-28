from __future__ import annotations

import re

from ..base import ProfileAction, SendLine


_CFG_RADIO_RE = re.compile(
    r"CFG RADIO power=(?P<power>-?\d+) dBm "
    r"freq=(?P<freq>[0-9.]+) MHz sf=(?P<sf>\d+) "
    r"bw=(?P<bw>[0-9.]+) kHz"
)
_CFG_LINK_RE = re.compile(
    r"CFG LINK heartbeat=(?P<heartbeat>\S+) "
    r"retry=(?P<retry>\S+) attempts=(?P<attempts>\d+) "
    r"diag=(?P<diag>\S+)"
)
_RX_USER_RE = re.compile(
    r"RX USER .*? RX=(?P<rssi>-?\d+)/(?P<snr>-?\d+) "
    r"Q(?P<quality>\d+|---)"
)
_NODE_RE = re.compile(r"\[SYS\] CHATTER NODE (?P<node>\S+)")
_POWER_RE = re.compile(r"\[SYS\] POWER (?P<power>-?\d+) dBm")
_FREQ_RE = re.compile(r"\[SYS\] FREQ (?P<freq>[0-9.]+) MHz")
_SF_RE = re.compile(r"\[SYS\] SF (?P<sf>\d+)")
_BW_RE = re.compile(r"\[SYS\] BW (?P<bw>[0-9.]+) kHz")


class ChatterTuiPanel:
    """Small profile-owned radio summary rendered by the generic TUI."""

    def __init__(self) -> None:
        self.node = "?"
        self.power = "?"
        self.frequency = "?"
        self.sf = "?"
        self.bandwidth = "?"
        self.heartbeat = "?"
        self.retry = "?"
        self.diag = "?"
        self.last_rx = "?"

    def connected_actions(self) -> tuple[ProfileAction, ...]:
        # TUI status is refreshed after every reconnect without teaching the
        # generic frontend any Chatter command names or response syntax.
        return (SendLine("/id"), SendLine("/config"))

    def consume_line(self, stream: str, line: str) -> None:
        del stream
        text = line.strip()

        match = _NODE_RE.search(text)
        if match:
            self.node = match.group("node")

        match = _CFG_RADIO_RE.search(text)
        if match:
            self.power = match.group("power")
            self.frequency = match.group("freq")
            self.sf = match.group("sf")
            self.bandwidth = match.group("bw")

        match = _CFG_LINK_RE.search(text)
        if match:
            self.heartbeat = match.group("heartbeat")
            self.retry = f'{match.group("retry")}/{match.group("attempts")}'
            self.diag = match.group("diag")

        for regex, attribute, group in (
            (_POWER_RE, "power", "power"),
            (_FREQ_RE, "frequency", "freq"),
            (_SF_RE, "sf", "sf"),
            (_BW_RE, "bandwidth", "bw"),
        ):
            match = regex.search(text)
            if match:
                setattr(self, attribute, match.group(group))

        match = _RX_USER_RE.search(text)
        if match:
            self.last_rx = (
                f'{match.group("rssi")}/{match.group("snr")} '
                f'Q{match.group("quality")}'
            )

    def status_lines(self) -> tuple[str, ...]:
        return (
            (
                f"Radio  {self.node} | {self.frequency} MHz | "
                f"SF{self.sf} | BW {self.bandwidth} kHz | {self.power} dBm"
            ),
            (
                f"Link   heartbeat={self.heartbeat} | retry={self.retry} | "
                f"diag={self.diag} | last RX {self.last_rx}"
            ),
        )
