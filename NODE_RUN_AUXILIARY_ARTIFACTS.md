# Node RUN auxiliary artifacts

This document extends `NODE_OBSERVATION_RECORDING_POLICY.md` for exact diagnostic captures that belong to the same hardware run but are not one of the two canonical SerialTerminal logs.

## Scope

Auxiliary artifacts are **optional**. Their support does not make any diagnostic tool part of every hardware run.

In particular, `btmon` is not started automatically by SerialTerminal, the node agent, or `commit-node-run`. Run it only when the concrete hardware task explicitly asks for HCI/Bluetooth-level capture or the source-development reviewer explicitly delegates such a diagnostic scenario.

Ordinary ACK, retry, cancellation, queue, echo, discovery, or smoke runs keep the normal four-file RUN shape and do not gain `btmon.log` merely because the publication helper supports it.

## Layout

A RUN may additionally contain regular files under:

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

Artifact path segments are restricted to letters, digits, `.`, `_`, and `-`, with an alphanumeric first character. Symlinks are not accepted as auxiliary evidence.

`MANIFEST.json` schema v1 is unchanged. Its canonical `files` mapping continues to name only `REPORT.md`, `serialterminal.log`, and `serialterminal.console.log`. Auxiliary artifacts are discovered from the bounded `artifacts/` namespace and published atomically with the RUN.

## Executor rules

The executor owns creation and interpretation of auxiliary artifacts exactly as it owns the core logs. Publication helpers do not launch `btmon`, do not create captures, do not choose diagnostic tools, and do not repair or synthesize artifact contents.

When an auxiliary artifact is materially used in the run conclusion, `REPORT.md` must name its RUN-relative path and state what evidence boundary it supports. Preserve the exact capture; do not replace it with copied excerpts only.

If a separate control or reproduction is a distinct run/process and materially affects the conclusion, publish it as its own canonical RUN/OBS identity and cross-reference it. Do not hide an independently executed follow-up run inside another RUN's `artifacts/` directory.

Exploratory scratch output that is not used as durable evidence need not be published.

## Publication semantics

`python3 -I scripts/commit-node-run` accepts zero or more auxiliary regular files under `artifacts/` in addition to the four required RUN members. It stages them in the same append-only publication commit as the RUN and matching OBS when required.

A file elsewhere inside `RUN_<stamp>_<topic>/` is not an allowed auxiliary artifact and remains a hard publication error. An artifact-only later commit to an already published RUN is not a valid substitute for atomic publication.

Push-failure retry keeps the same append-only validation: a local-ahead RUN publication that already contains auxiliary artifacts can be retried only when the whole commit remains a valid complete RUN publication.
