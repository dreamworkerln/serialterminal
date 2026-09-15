# TODO_012 — Preserve SPP capability across transient UNKNOWN probes

Status: OPEN

## Purpose

Give Classic Bluetooth SPP discovery the same durable UNKNOWN semantics already established for BLE NUS capability knowledge.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`scan_spp()` writes every probe result directly as:

```text
capabilities.spp = result.spp
metadata.rfcomm_channel = result.channel
```

A transient SDP/probe failure returns `spp=None`, usually with `channel=None`. `update_cached_device()` replaces the capability map and overwrites the merged metadata keys. One UNKNOWN probe can therefore erase a previously definitive `spp=true` plus its RFCOMM channel.

`discover_spp_devices()` requires both cached confirmed SPP and a valid cached RFCOMM channel, so that transient UNKNOWN can make a previously confirmed target disappear from normal discovery.

The BLE path already preserves prior definitive NUS knowledge when the newest probe is UNKNOWN; the SPP path currently does not.

## Target behavior

- UNKNOWN SPP probe updates newest diagnostic status/error without downgrading prior definitive capability knowledge.
- Preserve the last definitive RFCOMM channel while capability knowledge remains confirmed and no new definitive result supersedes it.
- Definitive YES/NO remains authoritative and may replace previous capability state.
- Do not present a stale channel as a new successful probe result; distinguish durable capability knowledge from newest probe diagnostics.

## Validation

- [ ] confirmed SPP -> transient UNKNOWN -> default discovery still returns the target;
- [ ] UNKNOWN updates error/probe timestamps without claiming a new positive probe;
- [ ] definitive NO supersedes previous YES according to the selected cache contract;
- [ ] definitive YES with changed RFCOMM channel updates the channel;
- [ ] cache serialization remains backward-compatible or migration is explicit;
- [ ] full repository CI PASS.