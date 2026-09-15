# TODO_023 — Make device capability cache safe for concurrent writers

Status: OPEN

## Purpose

Prevent concurrent scanner/process updates from losing each other's capability records or racing on the shared temporary cache file.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`update_cached_device()` currently performs an unlocked read-modify-write of the whole JSON cache. `save_cache()` always writes the same `<cache>.tmp` path and then `os.replace()`s it.

Two SerialTerminal/scanner processes updating different devices at the same time can both load the same old snapshot and the last writer can overwrite the other process's update. Concurrent use of the same temporary filename also creates an avoidable filesystem race.

Reads are intentionally tolerant of missing/corrupt files, but that does not prevent valid concurrent writes from losing durable capability knowledge.

This is a static concurrency/durability risk; no observed cache corruption is claimed.

## Target behavior

- Serialize whole-cache read-modify-write across processes, or use an equivalent storage/update design that cannot lose unrelated concurrent updates.
- Temporary-file strategy must be safe for concurrent processes.
- Preserve atomic replacement for readers.
- Preserve existing tolerant read behavior and cache schema unless migration is explicitly required.
- Do not add controller-specific knowledge to the generic cache layer.

## Validation

- [ ] deterministic two-writer test updating different device records without lost updates;
- [ ] concurrent update of the same record has documented last-writer/merge semantics;
- [ ] interrupted writer cannot leave a partially written canonical cache file;
- [ ] existing BLE/SPP cache tests remain green;
- [ ] full repository CI PASS.