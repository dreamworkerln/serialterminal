# Hardware executor setup moved

The dedicated physical-node executor no longer starts from the serialterminal/dev
source workspace.

Authoritative setup now lives in the independent sibling clone:

```text
serialterminal-observations/
branch: node_observations
file: CODEX_HARDWARE_TEST_SETUP.md
```

Start hardware Codex with that clone as its working directory.

The old extra sandbox writable_roots entry for serialterminal-observations is not
needed in the new layout because the observation clone itself is the writable
workspace.

This source repository remains the read-only SerialTerminal runtime/API provider
for the hardware executor.
