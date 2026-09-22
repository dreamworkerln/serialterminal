# Node RUN auxiliary artifacts

Read this document only when the concrete hardware task explicitly requires a diagnostic capture beyond the two normal SerialTerminal logs.

Ordinary USER/ACK, retry, cancellation, queue, echo, discovery, heartbeat, RSSI/SNR or smoke runs do not load or create auxiliary artifacts merely because the publication format supports them.

## Allowed layout

A canonical RUN may additionally contain regular files under:

```text
runs/RUN_<stamp>_<topic>/
    MANIFEST.json
    REPORT.md
    serialterminal.log
    serialterminal.console.log
    artifacts/
        <diagnostic-file>
```

Examples:

```text
artifacts/btmon.log
artifacts/controller/hci-trace.log
```

Artifact path segments are limited to letters, digits, dot, underscore and hyphen, with an alphanumeric first character. Symlinks are not accepted.

MANIFEST.json schema v1 is unchanged. Its files mapping continues to name only REPORT.md, serialterminal.log and serialterminal.console.log.

## Rules

Auxiliary capture is opt-in.

Do not start btmon or another host diagnostic automatically.

The executor owns creation and interpretation of auxiliary artifacts. Publication helpers do not start diagnostics, choose tools, repair captures or synthesize evidence.

If an auxiliary artifact materially supports the verdict, REPORT.md names its RUN-relative path and explains what evidence boundary it supports.

A distinct control/reproduction performed as a separate process/run is a separate canonical RUN. Do not hide a second run under artifacts/.

Exploratory scratch output that is not used as durable evidence need not be published.

The guarded run helper publishes allowed auxiliary files atomically with the RUN. Do not add an artifact to an already published historical RUN.
