from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import tempfile

from . import core
from .protocol import Compression


def prepare_source(path: Path, record) -> core._PreparedSource:
    """Prepare an FT1 wire stream that is reproducible after process restart.

    `gzip.GzipFile(fileobj=...)` otherwise derives an FNAME header from the
    random NamedTemporaryFile path. `filename=""` deliberately omits FNAME so
    the same source bytes produce the same wire bytes across processes.
    """
    original_size = path.stat().st_size
    record.original_bytes = original_size
    record.set_state("compressing")
    original_hash = hashlib.sha256()

    temporary = tempfile.NamedTemporaryFile(
        prefix="serialterminal-send-",
        suffix=".gz",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    processed = 0
    try:
        with path.open("rb") as source, temporary:
            with gzip.GzipFile(
                filename="",
                fileobj=temporary,
                mode="wb",
                mtime=0,
            ) as compressed:
                while True:
                    if record.cancel_event.is_set():
                        raise core.FileTransferCancelled()
                    block = source.read(core._IO_CHUNK)
                    if not block:
                        break
                    original_hash.update(block)
                    compressed.write(block)
                    processed += len(block)
                    record.set_progress(
                        bytes_completed=processed,
                        chunks_completed=0,
                    )

        compressed_size = temporary_path.stat().st_size
        original_sha256 = original_hash.digest()
        if compressed_size < original_size:
            return core._PreparedSource(
                source_path=path,
                wire_path=temporary_path,
                remove_wire_path=True,
                filename=path.name,
                original_size=original_size,
                wire_size=compressed_size,
                compression=Compression.GZIP,
                original_sha256=original_sha256,
                wire_sha256=core._sha256_file(
                    temporary_path,
                    record.cancel_event,
                ),
            )

        temporary_path.unlink(missing_ok=True)
        return core._PreparedSource(
            source_path=path,
            wire_path=path,
            remove_wire_path=False,
            filename=path.name,
            original_size=original_size,
            wire_size=original_size,
            compression=Compression.NONE,
            original_sha256=original_sha256,
            wire_sha256=original_sha256,
        )
    except Exception:
        temporary.close()
        temporary_path.unlink(missing_ok=True)
        raise
