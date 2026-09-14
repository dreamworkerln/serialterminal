# TODO_006 — BLE capability cache UNKNOWN semantics

Status: CLOSED

## Purpose

Prevent a transient/indeterminate BLE capability probe from erasing previously confirmed NUS capability and thereby hiding a valid cached-NUS device from normal capability-based discovery.

## Finding checkpoint

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

At that checkpoint a probe result `status="unknown", nus=None` replaced the cached capability mapping, so a previously confirmed non-advertising NUS target could disappear from normal discovery.

## Implemented

- BLE NUS capability merge is explicitly tri-state.
- Definitive `nus=True` or `nus=False` replaces prior knowledge.
- `nus=None` preserves an existing definitive `True`/`False` capability but does not invent knowledge when none exists.
- Current probe diagnostics (`probe_status`, `error`, `last_probe`) still describe the newest probe even when prior capability knowledge is retained.
- Default BLE discovery remains profile-agnostic and capability-based: advertised NUS or cached confirmed NUS.
- Cache representation/schema was not changed; SPP semantics were not opportunistically modified.

## Validation

Host-side tests cover prior YES + UNKNOWN, prior YES + definitive NO, and UNKNOWN without prior knowledge, including continued default discoverability of retained confirmed NUS.

```text
accepted checkpoint: dev@522180cf92d573a51020eeb6e84c2edb528ad5d3
GitHub Actions:      34907044192 SUCCESS
compile:             PASS
static/Ruff:         PASS
complexity:          PASS
pytest:              PASS
hardware:            NOT RUN
```

## Closure

`CLOSED`: transient UNKNOWN probe results no longer destroy prior definitive BLE NUS knowledge, while definitive probe results and newest diagnostics remain authoritative.
