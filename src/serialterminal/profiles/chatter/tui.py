from __future__ import annotations

from collections.abc import Callable
import re
import time

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
_RX_HEARTBEAT_PONG_RE = re.compile(
    r"RX HEARTBEAT PONG .*? "
    r"RX=(?P<rx_rssi>-?\d+)/(?P<rx_snr>-?\d+) "
    r"TX=(?P<tx_rssi>-?\d+)/(?P<tx_snr>-?\d+) "
    r"Q(?P<quality>\d+)"
)
_DIAG_LINK_RE = re.compile(
    r"\[LNK (?P<outcome>OK|CRC|HDR|NRP)\]\s+"
    r"RX\s+(?P<rx_rssi>-?\d+|---)/(?P<rx_snr>-?\d+|---)\s+"
    r"TX\s+(?P<tx_rssi>-?\d+|---)/(?P<tx_snr>-?\d+|---)\s+"
    r"Q(?P<quality>\d+)"
)
_HEARTBEAT_TIMEOUT_RE = re.compile(
    r"HEARTBEAT TIMEOUT .*? Q=(?P<quality>\d+)"
)
_NODE_RE = re.compile(r"\[SYS\] CHATTER NODE (?P<node>\S+)")
_POWER_RE = re.compile(r"\[SYS\] POWER (?P<power>-?\d+) dBm")
_FREQ_RE = re.compile(r"\[SYS\] FREQ (?P<freq>[0-9.]+) MHz")
_SF_RE = re.compile(r"\[SYS\] SF (?P<sf>\d+)")
_BW_RE = re.compile(r"\[SYS\] BW (?P<bw>[0-9.]+) kHz")


LINK_METRIC_TTL_S = 15.0


class ChatterTuiPanel:
    """Small profile-owned radio summary rendered by the generic TUI."""

    def __init__(
        self,
        *,
        link_metric_ttl_s: float = LINK_METRIC_TTL_S,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if link_metric_ttl_s <= 0:
            raise ValueError("link_metric_ttl_s must be positive")
        self._link_metric_ttl_s = float(link_metric_ttl_s)
        self._clock = time.monotonic if clock is None else clock
        self.node = "?"
        self.power = "?"
        self.frequency = "?"
        self.sf = "?"
        self.bandwidth = "?"
        self.heartbeat = "?"
        self.retry = "?"
        self.diag = "?"
        self.last_rx = "?"
        self.link_rx_rssi: str | None = None
        self.link_rx_snr: str | None = None
        self.link_tx_rssi: str | None = None
        self.link_tx_snr: str | None = None
        self.link_quality: str | None = None
        self._link_rx_at: float | None = None
        self._link_tx_at: float | None = None
        self._link_quality_at: float | None = None

    def connected_actions(self) -> tuple[ProfileAction, ...]:
        # TUI status is refreshed after every reconnect without teaching the
        # generic frontend any Chatter command names or response syntax.
        # Serial identity comes from the profile connect preamble. BLE identity
        # is announced once by Chatter firmware when human-console notifications
        # are subscribed. TUI only refreshes runtime configuration here.
        return (SendLine("/config"),)

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
            now = self._clock()
            self.link_rx_rssi = match.group("rssi")
            self.link_rx_snr = match.group("snr")
            self.link_quality = self._known_metric(match.group("quality"))
            self._link_rx_at = now
            self._link_quality_at = now
            self.last_rx = (
                f'{match.group("rssi")}/{match.group("snr")} '
                f'Q{match.group("quality")}'
            )

        match = _RX_HEARTBEAT_PONG_RE.search(text)
        if match:
            now = self._clock()
            self.link_rx_rssi = match.group("rx_rssi")
            self.link_rx_snr = match.group("rx_snr")
            self.link_tx_rssi = match.group("tx_rssi")
            self.link_tx_snr = match.group("tx_snr")
            self.link_quality = match.group("quality")
            self._link_rx_at = now
            self._link_tx_at = now
            self._link_quality_at = now

        match = _DIAG_LINK_RE.search(text)
        if match:
            now = self._clock()
            self.link_rx_rssi = self._known_metric(match.group("rx_rssi"))
            self.link_rx_snr = self._known_metric(match.group("rx_snr"))
            self.link_tx_rssi = self._known_metric(match.group("tx_rssi"))
            self.link_tx_snr = self._known_metric(match.group("tx_snr"))
            self.link_quality = match.group("quality")
            self._link_rx_at = now
            self._link_tx_at = now
            self._link_quality_at = now

        match = _HEARTBEAT_TIMEOUT_RE.search(text)
        if match:
            # Normal heartbeat timeout carries the current local Q but no
            # trustworthy opposite-direction RSSI/SNR pair.
            self.link_quality = match.group("quality")
            self._link_quality_at = self._clock()

    @staticmethod
    def _known_metric(value: str) -> str | None:
        return None if value == "---" else value

    @staticmethod
    def _metric_pair(rssi: str | None, snr: str | None) -> str:
        if rssi is None or snr is None:
            return "---/---"
        return f"{rssi}/{snr}"

    def _fresh(self, updated_at: float | None, now: float) -> bool:
        if updated_at is None:
            return False
        age = now - updated_at
        return 0.0 <= age <= self._link_metric_ttl_s

    def header_status(self) -> str:
        now = self._clock()
        rx = (
            self._metric_pair(self.link_rx_rssi, self.link_rx_snr)
            if self._fresh(self._link_rx_at, now)
            else "---/---"
        )
        tx = (
            self._metric_pair(self.link_tx_rssi, self.link_tx_snr)
            if self._fresh(self._link_tx_at, now)
            else "---/---"
        )
        quality = (
            self.link_quality
            if (
                self.link_quality is not None
                and self._fresh(self._link_quality_at, now)
            )
            else "---"
        )
        return f"RX {rx} | TX {tx} | Q{quality}"

    def status_lines(self) -> tuple[str, ...]:
        return (
            (
                f"Radio  {self.node} | {self.frequency} MHz | "
                f"SF{self.sf} | BW {self.bandwidth} kHz | {self.power} dBm"
            ),
            (
                f"Link   heartbeat={self.heartbeat} | retry={self.retry} | "
                f"diag={self.diag}"
            ),
        )
