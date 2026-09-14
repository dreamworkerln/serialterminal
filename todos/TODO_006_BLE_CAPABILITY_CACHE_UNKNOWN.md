# TODO_006 — BLE capability cache UNKNOWN semantics

Status: OPEN

## Purpose

Prevent a transient/indeterminate BLE capability probe from erasing previously confirmed NUS capability and thereby hiding a valid cached-NUS device from normal capability-based discovery.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

Observed facts at that checkpoint:

- `probe_ble_nus_async()` deliberately returns `status="unknown", nus=None` for timeout/refusal/authentication and documents that this is not proof of capability absence;
- `_scan_ble_async()` persists every probe result with `capabilities={"nus": result.nus}`;
- `update_cached_device()` replaces the cached `capabilities` mapping with the caller-provided mapping rather than preserving a prior confirmed value when the new result is unknown;
- normal BLE discovery accepts a non-advertising device through cache only when `capabilities.nus is True`.

Consequence: a previously confirmed NUS target that does not advertise the NUS service can become undiscoverable after one transient UNKNOWN probe.

## Scope

- BLE NUS probe/cache merge semantics;
- capability-based default BLE discovery behavior after a transient UNKNOWN probe;
- cache metadata/error timestamps needed to preserve diagnostic truth without converting UNKNOWN into a false negative.

## Non-goals

- do not whitelist devices by advertised name;
- do not make a controller profile influence discovery eligibility;
- do not treat UNKNOWN as YES;
- do not change SPP semantics opportunistically unless its current authority and tests demonstrate the same required tri-state rule.

## Implementation

- [ ] Define explicit tri-state cache update semantics for BLE NUS: definitive YES/NO may update capability knowledge; UNKNOWN must not silently destroy prior confirmed knowledge.
- [ ] Preserve current probe status/error/last-probe diagnostics even when prior capability knowledge is retained.
- [ ] Keep capability-based discovery controller-agnostic and based only on advertised NUS or cached confirmed NUS.
- [ ] Review cache schema/version implications if the representation changes.

## Validation

- [ ] Regression test: prior cached `nus=True` + new UNKNOWN probe preserves discoverability when NUS is not advertised.
- [ ] Regression test: definitive `nus=False` can replace prior positive knowledge when the probe genuinely completed and established absence.
- [ ] Regression test: UNKNOWN with no prior knowledge does not invent NUS support.
- [ ] Existing BLE discovery/scanner/cache tests remain PASS.
- [ ] Relevant pytest suite PASS.
- [ ] GitHub Actions PASS on the implementation checkpoint.

## Closure criteria

`CLOSED` requires transient UNKNOWN probes to preserve prior confirmed NUS knowledge without weakening capability-based discovery, while definitive probe results and diagnostic metadata remain accurately represented and tested.
