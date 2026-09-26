# Maintained LoRa-Chatter PHY/payload sweep runner TODO

TODO-ID: TODO_028
Status: OPEN

## Purpose

Implement a maintained deterministic local runner for LoRa-Chatter reliable-USER PHY/payload sweeps so the tight measurement loop executes inside local Python code instead of consuming one LLM/Codex tool turn per USER transaction.

The runner must make repeated hardware measurements faster and less error-prone while preserving SerialTerminal as the transport/session owner and preserving exact forensic logs as the evidence source.

## Current behavior

The hardware executor currently drives repeated sweeps through the low-level SerialTerminal agent API with a high-level loop shaped roughly as:

```text
send_line
-> observe
-> reasoning/tool turn
-> next send_line
-> observe
...
```

Recent hardware execution exposed two orchestration defects in that manual loop:

1. summary telemetry such as:

   ```text
   SESSION ... hdr=4
   ```

   was incorrectly interpreted as a new HDR event;

2. after:

   ```text
   /sf 8
   -> [SYS] SF 8 SAVED
   ```

   the executor waited for `CFG RADIO` before it had actually sent `/config`, producing an unnecessary multi-minute wait.

The manual loop also introduces roughly multi-second spacing between USER transactions even when the underlying BW500 TX/RX/ACK transaction completes in hundreds of milliseconds. The excess delay is orchestration overhead rather than required radio timing.

Relevant historical hardware evidence is already published on `node_observations` and is read-only context for this source task:

```text
runs/RUN_20260926T213834Z_main-bw500-noatten-executor-abort/
node_observations@707bfc07ddeaddb1a778bc87ebe90df2e129e8b6

runs/RUN_20260926T215538Z_main-bw500-noatten-retry-inconclusive/
node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c

hardware skill infrastructure:
node_observations@74270ae276382581fb1ad90bcd7733a251a60414
```

These RUNs are evidence of previous executor/orchestration bugs. They must not be modified by this task.

TODO creation checkpoint:

```text
dev@08c1b8d919cfb04c32068c9b9d63fdb1443139c9
```

## Target behavior

Add a maintained runner, preferably:

```text
scripts/run-chatter-sweep
```

for a two-node BLE LoRa-Chatter reliable USER PHY/payload sweep.

The runner must:

- launch exactly one child process:

  ```text
  python3 serialterminal.py agent --log <unique-path>
  ```

- use only the public SerialTerminal JSONL agent API;
- keep that one agent process alive for discovery, both sessions, the measured sweep, cleanup and close;
- leave BLE/Serial transport ownership, sessions and reconnect mechanics inside SerialTerminal;
- leave creation of `serialterminal.log` and `serialterminal.console.log` to the child SerialTerminal process;
- never reconstruct, edit or append to those logs;
- execute the high-frequency state machine locally in Python without an LLM/tool turn for every USER transaction;
- emit a separate machine-readable structured result, preferably JSON.

The first maintained use case is a reliable USER sweep configurable for at least:

- node A `device_key`;
- node B `device_key`;
- frequency;
- TX power;
- bandwidth;
- list of spreading factors;
- list of USER payload byte lengths;
- normal repetition count;
- anomaly repetition count;
- forensic log path;
- structured result path.

The runner must support the intended example shape:

```text
frequency = 470 MHz
power = 2 dBm
BW = 500 kHz
SF = 7,8,9,10,11,12
payload bytes = 1,8,16,32,64,96,128,160,180,200
normal repetitions = 3 A->B + 3 B->A
anomaly extension = 10 total A->B + 10 total B->A
```

but must not hard-code the implementation to BW500.

## Scope

- inspect and reuse the existing `scripts/run-chatter-scenario` implementation;
- add the maintained sweep runner;
- extract reusable Chatter orchestration primitives into an importable module only when that materially improves the design;
- preserve existing `run-chatter-scenario` behavior and tests after any extraction;
- add deterministic parser/state-machine/correlation logic for the sweep;
- add fake/mock agent transcript tests for normal, anomaly and failure paths;
- define and emit the structured result;
- update user/developer documentation only where the new maintained runner requires it;
- validate through repository tests and normal clean GitHub CI.

## Non-goals

- do not turn `src/serialterminal/agent.py` into a Chatter-specific sweep API;
- do not create a second BLE/Serial transport implementation;
- do not bypass the SerialTerminal JSONL API with direct Bleak or pyserial access;
- do not modify firmware;
- do not modify `node_observations` in this source-development task;
- do not change BlueZ or other host Bluetooth stack state;
- do not add reboot or PHY away/back workarounds;
- do not perform a real hardware sweep as part of this source-development implementation unless separately requested;
- do not change the canonical RUN schema merely to embed the structured sweep result; hardware-coordinator/evidence policy can decide that separately.

## Invariants

### Architecture

The ownership direction remains:

```text
SerialTerminal core
        ↓
generic JSONL agent API
        ↓
reusable Chatter orchestration primitives
        ↓
scripts/run-chatter-scenario
scripts/run-chatter-sweep
```

Generic discovery/session/transport code must remain controller-agnostic. Chatter protocol/state-machine knowledge belongs above the generic API.

### One measured transaction globally

At most one measured reliable USER transaction may be in flight across both nodes combined.

For each logical USER:

```text
send exactly one USER
-> establish sender session / USER identity / sequence
-> correlate receiver USER evidence
-> wait exact matching DELIVERY ACK
   OR explicit terminal reliable outcome
-> ensure transaction settled
-> only then send the next measured USER
```

Never pre-build or submit a queue of future measured `send_line` requests.

Execute the full A->B block before the B->A block for the same point. A new SF/payload point begins only from a settled state.

### Correlation

Do not infer causality from the array/list position of lines from different sessions within one `observe` result.

Correlation must use actual identifiers and context, including as applicable:

- sender session;
- USER session/sequence identity;
- deterministic payload marker;
- direction;
- timestamps/event evidence when needed.

If exact correlation is lost:

1. immediately stop sending new measured USERs;
2. do not finish a pre-planned batch;
3. settle/cancel the affected reliable flow;
4. reconfirm PHY state;
5. retry the contaminated point from scratch only when the recovery contract permits it, otherwise return structured failure.

Never silently continue to the next point after correlation loss.

### Payloads

Generate deterministic ASCII payloads of the exact requested byte length.

Where the length permits, encode a unique marker containing enough context to distinguish:

- SF;
- direction;
- payload size / point;
- request index.

Fill the remainder with deterministic padding.

The one-byte case may use a deterministic single-byte marker such as direction-specific `A`/`B`.

### RF anomaly semantics

Only actual events count as anomalies.

Recognized anomaly classes include:

- `RX CRC ERROR`;
- a real `RX HEADER ERROR` / HDR event;
- `DELIVERY ACK TIMEOUT`;
- retry;
- final reliable delivery failure;
- correlation anomaly.

Explicit exclusions:

```text
SESSION ... hdr=4
```

is summary telemetry and must not be counted as a new HDR event.

```text
DELIVERY WAIT_ACK ... timeout=712ms
```

describes the wait state and must not be counted as an ACK timeout event.

Only an actual:

```text
DELIVERY ACK TIMEOUT ...
```

counts as an ACK-timeout anomaly.

CRC/HDR events do not have a trusted USER protocol sequence. Preserve them as unsequenced RF evidence inside the currently serialized point window with receiver, active PHY/payload/direction context, time/order, frame length, RSSI/SNR and surrounding USER/retry/ACK evidence. Never fabricate a USER sequence for CRC/HDR.

### Repetition policy

A normal point requires:

```text
3 settled A->B
3 settled B->A
```

or the configured normal repetition count.

If any anomaly occurs in that point, extend the same point to:

```text
10 total A->B
10 total B->A
```

or the configured anomaly repetition count.

The initial samples remain part of the total; do not discard and restart the count merely because the anomaly appeared.

An anomaly at one payload size does not terminate traversal of larger requested payload values unless a bounded failure/invalid state prevents safe continuation.

## Design

### Existing implementation to reuse

`scripts/run-chatter-scenario` already contains useful maintained building blocks:

- `JsonlAgent`;
- one child `serialterminal.py agent` process;
- correlated JSONL request/response;
- `observe` polling;
- `wait_line`;
- Chatter regex/parser helpers;
- cleanup;
- scenario-specific state-machine code.

Inspect it before designing the sweep runner.

If common code is extracted, prefer a normal importable module under `src/serialterminal/` such as a scenarios/orchestration namespace rather than duplicating the same child-process/API mechanics between scripts. The final module name/layout is an implementation decision, but it must preserve dependency direction and existing scenario behavior.

### Pre-flight state machine

Before measured traffic, deterministically:

1. discover targets;
2. open both target nodes in the same child agent process;
3. establish node identities;
4. prove they are different nodes;
5. set/confirm heartbeat OFF;
6. set/confirm diagnostic OFF;
7. set/confirm echo-loop OFF;
8. cancel/settle reliable USER flow;
9. apply requested TX power;
10. apply requested frequency;
11. apply requested BW;
12. apply and confirm the target SF on both nodes.

If either target cannot be opened, return a bounded structured failure. Do not wait indefinitely and do not mutate BlueZ as recovery.

### SF transition state machine

For every SF transition, preserve this explicit command/evidence ordering:

```text
settled
-> send /sf N on node A
-> wait exact SF N SAVED
-> send /sf N on node B
-> wait exact SF N SAVED
-> SEND /config on node A
-> SEND /config on node B
-> wait CFG RADIO / CFG LINK responses
-> verify exact SF/BW/power/frequency
-> only then measured USER traffic
```

The runner must never wait for `CFG RADIO` before the corresponding `/config` command has actually been sent.

### Timeouts and performance

Local-control waits must be bounded and appropriate for local firmware command latency; do not use generic multi-minute waits.

Per-transaction RF timeout logic must account for actual reliable-protocol timing and slower PHY configurations rather than applying one universal one-second timeout.

The local event loop may poll frequently, for example around 100-250 ms, without involving the LLM on every poll.

After a matching ACK and required settle, the next BW500 USER should be eligible to send promptly rather than inheriting an artificial multi-second orchestration pause.

### Point classification

Classify each requested point mechanically:

```text
CLEAN
    all requested logical deliveries completed on first attempt
    and no CRC/HDR/retry/ACK-timeout/correlation anomaly occurred

DEGRADED
    logical deliveries succeeded
    but CRC/HDR/retry/ACK-timeout occurred

FAILED
    bounded final reliable delivery failure occurred

INVALID
    correlation/orchestration/transport evidence defect prevents a valid measurement

UNMEASURED
    requested point was not executed
```

## Structured result

Write a machine-readable result, preferably JSON, that includes at least:

```text
overall result
node identities
requested configuration
actual traversal

per point:
    SF
    BW
    payload bytes
    class/status
    A->B logical requests
    A->B matching ACKs
    A->B physical attempts
    B->A logical requests
    B->A matching ACKs
    B->A physical attempts
    retries
    actual ACK timeouts
    CRC count/evidence
    HDR count/evidence
    final failures
    RSSI/SNR observations or ranges
    correlation/transport anomalies

global anomalies
unmeasured points
reason / stopped_at on failure
log_path
console_log_path
```

The result JSON is a derived scenario summary and does not replace the exact SerialTerminal forensic/console logs.

## Implementation

- [ ] inspect `scripts/run-chatter-scenario` and identify reusable orchestration boundaries;
- [ ] add `scripts/run-chatter-sweep` with parameterized node/config/SF/payload/repetition/result paths;
- [ ] keep exactly one child SerialTerminal agent process per sweep;
- [ ] implement deterministic pre-flight and safe bounded failure behavior;
- [ ] implement explicit SF transition state machine with `/config` command ownership;
- [ ] implement exact-length deterministic payload generation;
- [ ] implement serialized one-USER-in-flight transaction state machine;
- [ ] implement identifier-based cross-session correlation independent of response list order;
- [ ] implement RF anomaly parser with explicit summary/wait-state exclusions;
- [ ] preserve CRC/HDR as unsequenced point-window evidence;
- [ ] implement normal-count to anomaly-count extension without discarding initial samples;
- [ ] continue later payload points after non-terminal degraded points;
- [ ] implement mechanical CLEAN/DEGRADED/FAILED/INVALID/UNMEASURED classification;
- [ ] emit structured result with traversal, per-point counters/evidence and failure boundary;
- [ ] ensure deterministic child-process/session cleanup;
- [ ] extract common code from `run-chatter-scenario` only if useful and keep existing behavior compatible;
- [ ] update affected maintained docs/CLI usage.

## Validation

Automated unit/integration-style tests with fake/mock agent transcripts/state machines must cover at least:

- [ ] normal 3+3 CLEAN point;
- [ ] an anomaly extends exactly to 10+10 total;
- [ ] `SESSION ... hdr=4` does not trigger HDR anomaly;
- [ ] actual `RX HEADER ERROR` does trigger anomaly;
- [ ] `DELIVERY WAIT_ACK ... timeout=...` does not count as ACK timeout;
- [ ] actual `DELIVERY ACK TIMEOUT ...` does count;
- [ ] cross-session `observe` lines in reverse/unexpected order still correlate correctly;
- [ ] ACK correlation requires the current sender/session/USER sequence;
- [ ] the next measured USER is not sent before the previous transaction is settled;
- [ ] no future measured send queue is pre-submitted;
- [ ] SF transition proves `/sf N -> SAVED -> SEND /config -> wait CFG RADIO`;
- [ ] regression specifically prevents waiting for CFG output before sending `/config`;
- [ ] correlation loss stops new sends and enters contamination recovery/failure handling;
- [ ] CRC/HDR remains unsequenced and never acquires a fabricated USER sequence;
- [ ] existing `scripts/run-chatter-scenario` behavior/tests remain passing after any common-code extraction;
- [ ] child SerialTerminal process cleanup is deterministic;
- [ ] relevant targeted test suite PASS;
- [ ] full repository pytest/compile/static validation required by `AGENTS.md` PASS;
- [ ] final `BASE..HEAD` diff reviewed, including all deletions/refactors;
- [ ] GitHub Actions for the resulting pushed checkpoint PASS.

No real hardware sweep is required to close the source implementation/automated-validation portion unless the implementation task explicitly adds a hardware gate. Any later physical validation must be tracked separately and must not be inferred from software tests.

## Findings

Initial finding:

The previous executor-driven sweep model puts protocol parsing, state-machine progression and timing-critical transaction sequencing across repeated model/tool turns. That architecture permits orchestration bugs that are independent of SerialTerminal transport correctness and adds avoidable inter-transaction latency.

Consequence:

Keep the generic agent API low-level and move deterministic Chatter sweep orchestration into maintained local Python code above it.

## Known limitations

- First maintained scenario is two-node reliable USER PHY/payload sweep.
- Structured result is not yet part of canonical hardware RUN schema.
- CRC/HDR evidence is intentionally unsequenced unless future protocol evidence supplies a trustworthy identifier.
- This TODO does not select or change firmware behavior.
- This TODO does not authorize a source-development agent to perform the physical sweep.

## Result

Implemented: not yet

Validated: not yet

Status: OPEN
