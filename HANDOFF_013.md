# Handoff snapshot 013

```text
Snapshot: HANDOFF_013.md
Previous: HANDOFF_012.md
Created: 2026-10-02T04:32:29Z
Handoff authority before snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@cbd88e752f772d29475e72347b99fc780f5eb6cb
Source checkpoints:
  stable source baseline:
    dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9
  active TUI / BINARY USER / file-transfer work:
    dreamworkerln/serialterminal/dev_tui@50c2536842aff60cd52f64e1031710cc5739d228
  physical evidence authority:
    dreamworkerln/serialterminal/node_observations@baf0214e1edf18179389580aa0ac56d0fcfaf76c
  firmware reference inspected read-only:
    dreamworkerln/lora-sack-protocol/dev_chat_binary@1cb43d9477b84269bc91003f89c0380f5c03b95f
Knowledge base:
  dreamworkerln/serialterminal/dev_tui@50c2536842aff60cd52f64e1031710cc5739d228
Transfer / promotion boundary:
  dev_tui is the active source branch; no promotion to dev has been performed.
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

`dev_handoff` is authoritative recovery state. `dev` is the stable baseline.
`dev_tui` is the active TUI/file-transfer source branch.
`node_observations` is physical hardware executor/evidence authority.

Before new work, refetch all moving refs. SerialTerminal source work may inspect the
firmware repository read-only when required, but must never modify it.

The current conversation was intentionally stopped for handoff immediately after the
file-transfer timing instrumentation and agent-skill guidance were present on
`dev_tui`.

## 2. Material source changes since HANDOFF_012

`dev_tui` advanced from
`3360be0ba73b4be7693c43c94f482755bd2e0508` to
`50c2536842aff60cd52f64e1031710cc5739d228`.

Material checkpoints include:

- FT1 telemetry-independent local settlement and serial RX low-latency fixes;
- FT1 controller-reset recovery and stale incoming-transfer timeout;
- FT1 send-stage forensic logging;
- Chatter TUI file-transfer preemption without repurposing Ctrl+C;
- faster chooser reuse of known Bluetooth targets;
- Chatter identity seeded from BLE target name;
- exclusive POSIX serial-port ownership to prevent two ST processes reading one tty;
- deferred file-transfer timing instrumentation;
- tests and maintained documentation for the timing trace;
- agent skill guidance that forbids per-chunk LLM/tool orchestration during fast file
  transfers.

The three most recent timing-related commits are:

```text
52bc3c6ce15212c6cdb3d5dc7482aa9f662425ba  diag: add deferred file transfer timing trace
5c3514b28452cc15c927d1003d59ff4d036bd4ec  test: cover deferred transfer timing trace
50c2536842aff60cd52f64e1031710cc5739d228  docs: describe deferred transfer timing log
```

## 3. Current file-transfer timing instrumentation

Each normal TUI or agent run now has a third companion file:

```text
<name>.log
<name>.console.log
<name>.fttiming.jsonl
```

The timing trace is deliberately deferred:

- timing points use `time.perf_counter_ns()` plus wall-clock `time.time()`;
- events are appended to an in-memory `TimingTrace`;
- the `.fttiming.jsonl` file is written only during clean log/session shutdown;
- no BINARY/base64 payload bytes are written into the timing trace;
- instrumentation exceptions are swallowed so timing cannot alter transport/BINARY
  correctness;
- the trace itself adds in-memory timestamp/list/lock overhead, but no per-event timing
  file I/O to the measured transfer path.

Important implication: a hard process kill/crash before normal close can leave no
final timing file because persistence is intentionally deferred.

The trace contains generic/session/FT1 boundaries and explicit timing points including:

```text
run_start / run_stop
transport_write_start / transport_write_done
transport_write_unknown / transport_write_error
transport_read_chunk
ble_gatt_write_start / ble_gatt_write_done / ble_gatt_write_error
ble_notify
binary_submit
binary_tx_queued
binary_tx_written
binary_presentation_line
binary_presentation_match
binary_return
ft1_event
forensic_log_write_start / forensic_log_write_done
console_log_write_start / console_log_write_done
primary_log_write_start / primary_log_write_done
```

This is intended to decompose each BINARY USER/file chunk into:

```text
binary_submit
  -> transport/BLE write
  -> first BLE notification(s)
  -> complete local > [BINARY] presentation
  -> exact presentation match
  -> binary_return
  -> next binary_submit
```

and separately measure synchronous ordinary logging overhead.

## 4. Why this instrumentation was requested

Current Chatter FT1 sender is strictly sequential at the BINARY USER boundary:

```text
FT1 message
-> ChatterBinaryUserAdapter.send_binary()
-> queue /bin <base64>
-> wait local transport write settlement
-> wait exact local > [BINARY] <base64>
-> return
-> only then send next FT1 message
```

There is no accepted per-chunk artificial sleep in the normal path.

Potential host-side contributors under investigation:

1. one BINARY USER in flight at a time;
2. local base64 text envelope expansion over BLE;
3. Bleak `write_gatt_char(..., response=False)` submitted synchronously per command;
4. complete local BINARY presentation must return before the next FT1 DATA;
5. agent/TUI forensic and console log flushes may add synchronous overhead;
6. BLE notification fragmentation may increase callback/log/line-assembly work.

The instrumentation was added to measure rather than speculate.

## 5. Agent file-transfer orchestration rule

`.agents/skills/serialterminal-agent/SKILL.md` now explicitly says:

- do not accompany every DATA chunk with a separate model/tool turn;
- do not drain `file_transfer_observe.events` window-by-window at transfer rate;
- such orchestration cannot keep up, can hit `file_cursor_expired`, and materially
  reduces useful scenario throughput;
- ordinary progress should be monitored using coarse `status` snapshots roughly
  every 2–5 seconds;
- `file_transfer_observe` is for bounded long-poll / lifecycle / fault events when
  actually needed, not as a per-chunk control loop;
- detailed chunk/send-stage evidence should be obtained after the run using targeted
  searches in the finalized forensic log, not by loading the live backlog into the
  model context.

This guidance was added because a diagnostic run demonstrated the model/tool loop
falling behind retained transfer-event history while the actual transfer itself
completed successfully.

## 6. Recent physical/diagnostic findings

### Successful USB diagnostic transfer

A one-transfer diagnostic of `3.jpg` over USB completed successfully:

```text
source size: 134844 bytes
source SHA-256:
  9fe15bb0dc8d2e12513b18d810e69b01751792cc435323167991baf95c73922e

transfer_id:
  d5568e1d957b153c

result:
  sender completed
  receiver completed
  593/593 chunks
  134594 wire bytes
  100.0%
  sender remote_result=ok
  elapsed about 102.59 s
```

No USB disconnect occurred in that successful run.

The diagnostic controller itself got `file_cursor_expired` because it tried to read
transfer-event history too slowly. That was orchestration failure, not file-transfer
failure. This finding directly motivated the updated agent skill.

### Fault attempt 014

A later stress/fault-capture attempt recorded a real transport disconnect while
transferring in the opposite direction.

Immediately before failure:

```text
sender:   sending   49/593, 11123 bytes, 8.26%
receiver: receiving 50/593, 11350 bytes, 8.43%
```

The forensic log recorded:

```text
2026-10-02T00:04:40.728+03:00  s2 state=disconnected
2026-10-02T00:04:40.730+03:00  s1 state=disconnected
```

Both carried the same pyserial-level error:

```text
device reports readiness to read but returned no data
(device disconnected or multiple access on port?)
```

The real `[STATE] disconnected` timestamps differ by about 2.19 ms. Roughly 9.28 s
had already passed without FT1 progress before those disconnect events.

Correct interpretation:

- both SerialTerminal serial transports really did enter disconnected nearly
  simultaneously;
- this does NOT yet prove the physical root cause was the USB bus itself;
- possible causes still include common USB/hub/power/driver events, simultaneous device
  reboot, or another serial-layer cause;
- the stock pyserial phrase `or multiple access on port?` is not proof of multiple
  access;
- fault naming should prefer neutral wording such as
  `BOTH_SERIAL_TRANSPORTS_DISCONNECTED` over a root-cause claim like
  `USB_SESSION_FAULT`.

The exclusive serial-port ownership fix at
`4233305ab0fd3fa6852e852778cbcbf1a2ca4710` addresses a separate previously proven
case where two ST processes could open the same tty and split firmware output.

## 7. Current manual timing experiment

The operator wants the next timing experiment to be manual, not driven chunk-by-chunk
through the JSONL agent.

Recommended execution:

1. run ordinary TUI;
2. select Chatter profile;
3. connect over BLE;
4. F5 send `3.jpg`;
5. allow a normal clean completion/exit so the deferred timing file is written;
6. repeat the same transfer over USB with unchanged radio configuration;
7. analyze a middle block of about 20–50 DATA chunks to avoid META/startup/END effects.

The key per-message intervals to calculate from `.fttiming.jsonl` are:

```text
transport/ble write duration
write done -> first relevant BLE notification
first notification -> complete presentation match
presentation match -> binary_return
binary_return -> next binary_submit
total binary_submit -> next binary_submit
ordinary log write/flush durations overlapping those intervals
```

Compare BLE and USB medians/percentiles on the same file and radio settings before
changing pacing, protocol, BLE MTU behavior or logging policy.

No hardware run using the new timing instrumentation has yet been accepted in this
snapshot.

## 8. Validation evidence

Current active source checkpoint:

```text
dev_tui@50c2536842aff60cd52f64e1031710cc5739d228
GitHub Actions run 36964002644: SUCCESS
compile: PASS
Ruff/static analysis: PASS
complexity gate: PASS
pytest: 356 passed in 11.62 s
```

The initial instrumentation commit
`52bc3c6ce15212c6cdb3d5dc7482aa9f662425ba` had a failing CI run; follow-up test
and documentation commits produced the final green checkpoint above.

Physical BLE timing validation of the new trace: NOT RUN / not accepted in this
snapshot.

## 9. Architecture / invariants

Preserve:

- firmware repository remains read-only in this workstream;
- generic transport/session code may expose generic timing facts but must not learn
  Chatter/FT1 semantics;
- Chatter BINARY semantics remain profile-owned;
- FT1 remains above the opaque BINARY transport abstraction;
- `tx_state=written` is transport settlement, not peer delivery;
- sender completion still requires remote FT1 RESULT OK;
- timing instrumentation must not add per-event disk I/O to the measured path;
- raw base64 remains hidden/redacted by default;
- do not reintroduce per-chunk LLM/tool orchestration;
- Ctrl+C remains the ordinary quit behavior; file-transfer preemption uses the
  existing TUI mechanisms, not a Ctrl+C semantic change.

## 10. Relevant source/docs

Read current `dev_tui` as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
FILE_TRANSFER.md
LOGGING.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/timing.py
src/serialterminal/runlog.py
src/serialterminal/session.py
src/serialterminal/transports/base.py
src/serialterminal/transports/ble_nus.py
src/serialterminal/profiles/base.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/file_transfer/core.py
src/serialterminal/terminal.py
src/serialterminal/tui.py
src/serialterminal/agent.py
tests/test_timing.py
tests/test_ble_nus.py
tests/test_chatter_binary_user.py
tests/test_agent_console_log.py
tests/test_tui.py
```

## 11. Immediate continuation

1. Refetch `dev_tui`; do not assume `50c253...` is still HEAD.
2. Perform one manual BLE transfer of `3.jpg` and exit ST cleanly.
3. Preserve the resulting `.fttiming.jsonl`.
4. Perform the equivalent USB transfer and preserve its timing trace.
5. Analyze only targeted timing rows; do not load large forensic logs into model
   context.
6. Compute per-chunk distributions for the timing intervals above.
7. Identify whether the dominant delay is BLE write, firmware/RF-to-presentation,
   BLE presentation return, ST/logging, or inter-message host scheduling.
8. Only after measurement consider source changes for throughput.
9. Keep the independent serial-disconnect investigation separate unless timing
   evidence directly connects them.

## 12. Standing reminders

- authoritative handoff branch: `dev_handoff`;
- active source branch: `dev_tui`;
- source head at snapshot: `50c2536842aff60cd52f64e1031710cc5739d228`;
- published snapshots are immutable;
- final timing trace requires clean shutdown because persistence is deferred;
- GitHub Actions is source validation, not physical BLE/radio validation;
- `node_observations` is physical evidence authority;
- do not modify firmware from the SerialTerminal workstream;
- do not publish huge raw forensic logs to Git;
- raw base64 stays redacted by default;
- no persistent FT1 resume across SerialTerminal process death.
