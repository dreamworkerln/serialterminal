# Handoff snapshot 012

```text
Snapshot: HANDOFF_012.md
Previous: HANDOFF_011.md
Created: 2026-09-30T00:34:00Z
Handoff authority before snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@ad0eb1e1afdaaea4b1e185ba6a60b86eaed3f1a3
Source checkpoints:
  stable source baseline:
    dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9
  active TUI / BINARY USER / file-transfer work:
    dreamworkerln/serialterminal/dev_tui@3360be0ba73b4be7693c43c94f482755bd2e0508
  physical evidence authority:
    dreamworkerln/serialterminal/node_observations@4f66626663521fab98eb3b80ef4409719e9ec3a8
  firmware reference inspected read-only:
    dreamworkerln/lora-sack-protocol/dev_chat_binary@e08b3851c6ec506b12f607601a0b7e6cb1af618b
Knowledge base:
  dreamworkerln/serialterminal/dev_tui@3360be0ba73b4be7693c43c94f482755bd2e0508
Transfer / promotion boundary:
  dev_tui is an active feature branch; no promotion to dev has been performed.
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

`dev_handoff` is authoritative recovery state. `dev` is the stable baseline.
`dev_tui` is the active TUI/file-transfer source branch.
`node_observations` is physical evidence authority.

Before new work, refetch moving refs. SerialTerminal source work may inspect firmware
read-only when required, but must never modify the firmware repository.

## 2. Material changes since HANDOFF_011

The workstream moved into `dev_tui` and added:

- profile-aware curses TUI for generic and Chatter profiles;
- Chatter BINARY USER adapter;
- FT1 application-layer file transfer;
- same-process reconnect / missing-chunk repair;
- TUI scrollback, command history, internal scrollbar and mouse mode;
- MC-style filesystem file picker;
- Chatter directional link-quality status;
- default incoming-file directory under the SerialTerminal source root;
- default base64 redaction in all ST log files.

## 3. Current TUI state

Generic TUI:

- bounded logical history with stable line IDs;
- visual wrapping;
- FOLLOW / SCROLL modes;
- PgUp/PgDn, End-to-follow and wheel scrolling;
- internal right-side scrollbar;
- F8 toggles application mouse capture versus native terminal mouse/RMB behavior;
- Up/Down command history with draft restoration;
- F2 device, F3 profile, F4 clear, F9 help, Ctrl+Q exit.

Chatter UI additionally provides:

- profile-owned radio/config status;
- header link quality from existing heartbeat/diag telemetry:
  `RX <rssi>/<snr> | TX <rssi>/<snr> | Q<n>`;
- F5 filesystem browser/send;
- F6 cancel active transfer.

The filesystem browser starts from process cwd, lists directories before files, has
`..`, adaptive columns, reverse/bold selection and the same general visual/navigation
pattern as the operator-provided image-browser example. Enter opens/selects, Esc
cancels, `/` filters and R reloads.

Known limitation: initial device discovery still occurs before curses is created. If no
device is available, the old console discovery loop remains visible.

## 4. File-transfer state

Chatter BINARY USER uses firmware `/bin` only as the local controller boundary.
Base64 is not the RF payload.

FT1 messages:

```text
META
DATA
END
MISSING
RESULT
```

Important semantics:

- transfer identity is `transfer_id`;
- DATA identity is `transfer_id + chunk_index`;
- sender completion requires remote RESULT;
- receiver verifies hashes before final publication;
- generic `ManagedSession` does not own file/chunk/compression semantics.

Same-process repair is implemented:

- incomplete receiver state remains in memory;
- END with holes produces one canonical MISSING range set when it fits;
- sender selectively resends missing DATA and repeats END;
- repeated identical META/END are idempotent;
- bounded META+END replay covers lost control/result boundaries;
- generic `tx_state=unknown` is still not blindly retried.

Limitations:

- no MISSING pagination;
- oversized missing sets fail with `repair_too_large`;
- full resend is an explicit new transfer;
- no persistent resume after process death/restart;
- LoRa SACK is separate future work.

Default incoming directory for checkout/editable install:

```text
<serialterminal source root>/files
```

Packaged fallback is `./files`; `--receive-dir` overrides it.

## 5. Base64 screen/logging contract

Human screen:

- raw Chatter BINARY base64 is never rendered;
- firmware `[BINARY]` presentation lines are suppressed;
- manual local `/bin ...` is displayed as `/bin <base64>`.

Persisted logs by default:

- known BINARY text and structured `*_b64` fields are redacted to `<base64>`;
- applies to human primary logs, companion console logs and agent forensic logs.

Explicit log-only opt-in:

```text
--log-base64
```

This flag does not make raw base64 visible on the human screen. The live agent API
remains byte-accurate for explicit event retrieval.

## 6. Architecture / invariants

Preserve:

- generic TUI mechanics do not branch on concrete profile names for controller semantics;
- Chatter parsing/actions/BINARY presentation stay profile-owned;
- `ManagedSession` may expose generic TX/lifecycle facts but not file semantics;
- transport `written` is not remote application completion;
- progress model is independent of curses rendering;
- firmware repository is read-only from this workstream.

## 7. Validation evidence

Current active source checkpoint:

```text
dev_tui@3360be0ba73b4be7693c43c94f482755bd2e0508
GitHub Actions 36629183647: SUCCESS
pytest: 306 passed
compile/static-analysis workflow: PASS
```

Source changes were committed in focused checkpoints with deletion/function-definition
review and CI validation.

Physical two-node file-transfer/reconnect validation is NOT claimed for this checkpoint.

## 8. Physical/evidence state

Current evidence authority:

```text
node_observations@4f66626663521fab98eb3b80ef4409719e9ec3a8
```

Automated FT1 reconnect tests do not prove physical BLE reconnect behavior. Physical
two-node file-transfer/reconnect validation remains pending unless newer observation
evidence is published.

## 9. Open timing investigation

The last operator question before handoff asks whether SerialTerminal itself introduces
delay during file transfer. Both ST processes are launched from the same source
directory on one computer.

The operator supplied a current console log in chat; it is not yet a canonical
observation bundle. Facts visible in that trace:

- SF7 / BW500, retry ON;
- diag disabled before the file-transfer trace;
- consecutive redacted BINARY presentation lines occur mostly about 0.67-0.77 seconds
  apart after transfer starts, with occasional somewhat longer spacing;
- therefore a real low chunk cadence is visible, but no root cause has been established.

The investigation was interrupted immediately after enumerating
`src/serialterminal/file_transfer/*`.

Do not assume the cadence is caused by ST, BLE, firmware ACK timing, RF timing or the
two processes sharing one cwd until the execution path is traced.

Next checks:

1. inspect `file_transfer/core.py` sender loop for sleeps/pacing/synchronous settlement;
2. inspect `file_transfer/transport.py` and Chatter `binary_user.py`;
3. inspect `ManagedSession` TX outcome/fence behavior and BLE write path;
4. compare local write, firmware delivery WAIT_ACK/ACK and next-chunk timestamps;
5. check whether two ST processes launched from the same directory share any path/state
   that can affect execution; do not infer a process-global lock without evidence;
6. separate host-side delay from reliable-USER ACK/retry/on-air timing.

## 10. Recovery references

Read current `dev_tui` as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
FILE_TRANSFER.md
LOGGING.md
README.md
TODO_INVENTORY.md
todos/TODO_029_FILE_TRANSFER_RECONNECT_REPAIR.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/tui.py
src/serialterminal/file_browser.py
src/serialterminal/file_transfer/core.py
src/serialterminal/file_transfer/protocol.py
src/serialterminal/file_transfer/transport.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/profiles/chatter/tui.py
src/serialterminal/session.py
```

Firmware reference used read-only:

```text
dreamworkerln/lora-sack-protocol/dev_chat_binary@e08b3851c6ec506b12f607601a0b7e6cb1af618b
```

## 11. Immediate continuation

1. Refetch `dev_tui`.
2. Resume the file-transfer timing investigation before changing pacing behavior.
3. Determine where the observed ~0.7 s cadence is introduced.
4. Do not add/remove arbitrary sleeps until timing is evidenced.
5. If a source fix is required, use focused commits and the documented acceptance gate.
6. Keep firmware read-only unless a separate firmware task is explicitly started.
7. Physical file-transfer reconnect validation remains an observation-workspace task.

## 12. Standing reminders

- authoritative handoff branch: `dev_handoff`;
- active TUI/file-transfer source: `dev_tui`;
- published snapshots are immutable;
- GitHub Actions is not physical radio validation;
- do not modify `node_observations` during ordinary source work;
- do not modify firmware from this workstream;
- raw base64 is hidden from screen and redacted from logs by default;
- FT1 same-process repair is not persistent resume.
