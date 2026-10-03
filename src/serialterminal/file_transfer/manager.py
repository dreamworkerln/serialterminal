from __future__ import annotations

import time

from . import core
from .resumable import FileTransferManager as _ResumableFileTransferManager


class FileTransferManager(_ResumableFileTransferManager):
    """Public FT1 manager preserving established runtime timeout semantics.

    An idle receiver is still reported to the current process as the historical
    terminal `remote_sender_timeout` failure and releases the session lease. The
    new durable manifest/partial file is retained underneath that observable
    result so a later SerialTerminal process can restore the same transfer.
    """

    def _expire_stale_incoming(self) -> None:
        with self._lock:
            incoming = self._incoming
        if incoming is None:
            return
        idle_s = time.monotonic() - incoming.last_activity_monotonic
        if idle_s < self.incoming_idle_timeout_s:
            return

        self._checkpoint_incoming(incoming, status="suspended", force=True)
        with self._lock:
            if self._incoming is incoming:
                self._incoming = None

        failure = core.FileTransferError(
            "remote_sender_timeout",
            "remote sender stopped before END completion",
            phase="receiving",
            details={"timeout_seconds": self.incoming_idle_timeout_s},
        )
        incoming.record.event(
            "transfer_suspended",
            reason="remote_sender_timeout",
            durable=True,
        )
        self._terminal_record(incoming.record, "failed", failure=failure)
