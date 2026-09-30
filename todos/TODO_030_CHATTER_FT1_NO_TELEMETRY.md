# Chatter FT1 telemetry-independent settlement TODO

TODO-ID: TODO_030
Status: OPEN

## Purpose

Remove the ordinary FT1/file-transfer correctness dependency on Chatter TELEMETRY output.
File transfer must not switch the controller to `BOTH`, must not temporarily alter the
operator-selected output mode, and must not restore that mode after the transfer.

This follow-up supersedes only the output-mode/telemetry-settlement design introduced
during TODO_029. The reconnect/MISSING repair semantics from TODO_029 remain required.

## Current behavior

The current Chatter binary adapter treats reliable-USER TELEMETRY as mandatory settlement
evidence:

```text
send /bin <BASE64>
-> wait for DELIVERY WAIT_ACK
-> wait for DELIVERY ACK / FAILED
-> only then let FT1 advance
```

To make those lines observable, the adapter owns a transfer-wide output-mode lease:

```text
begin transfer -> /both -> wait for [SYS] OUTPUT BOTH
reconnect       -> reassert /both
end transfer   -> restore prior CHAT/TELEMETRY/BOTH mode
```

The TUI then mutes session/controller scrollback during the transfer so the telemetry
required by the adapter does not flood the human view.

This is the wrong ownership boundary for ordinary file transfer: a human presentation
mode is being mutated to provide a machine correctness signal.

## Target behavior

FT1 must operate without enabling or requiring Chatter TELEMETRY.

Required contract:

- starting a TX or RX file transfer does not send `/both`, `/chat` or `/tele`;
- transfer completion, failure, cancellation and reconnect do not restore or otherwise
  mutate the controller output mode;
- `DELIVERY WAIT_ACK`, `DELIVERY ACK` and `DELIVERY FAILED` may be consumed as optional
  diagnostics when already visible, but they are not required for FT1 progression,
  correctness, backpressure or reconnect recovery;
- the operator-selected display mode remains unchanged for the entire transfer lifecycle;
- FT1 end-to-end truth remains application-level: stable `transfer_id + chunk_index`,
  `MISSING`, repeated idempotent `END`, and final `RESULT`;
- there is still no second per-DATA file ACK and no LoRa-SACK dependency.

For the current Chatter text boundary, non-telemetry BINARY presentation may be used as a
local submission/first-transmit/backpressure signal, but it must not be misrepresented as
remote radio delivery. Remote completion is proven by FT1 `RESULT`; missing DATA is repaired
by `MISSING`; control replay remains bounded and idempotent.

If BINARY application presentation is unavailable in the controller's current output mode
(for example a TELEMETRY-only human mode on a transport with no independent BINARY stream),
the implementation must not silently change the mode. It must either use an already-existing
independent profile capability or fail deterministically with a clear profile/capability
error before claiming transfer progress.

## Scope

- `src/serialterminal/profiles/chatter/binary_user.py` settlement semantics;
- the generic `BinaryUserTransport` / optional transfer-lifecycle contract only if its
  current `link-settled send_binary()` meaning cannot survive this change cleanly;
- FT1 sender/receiver progression and reconnect repair as needed to preserve TODO_029;
- TUI and agent integration affected by transfer lifecycle ownership;
- tests and permanent documentation that currently describe the `BOTH` lease.

## Non-goals

- no firmware source change;
- no new Chatter firmware command, wire flag or scheduler mode;
- no LoRa SACK;
- no MISSING pagination;
- no persistent resume after SerialTerminal process death;
- no change to the user's normal output-mode choice outside explicit user commands.

## Invariants

- generic `ManagedSession` and generic transports must not learn Chatter commands or
  Chatter delivery semantics;
- controller-specific settlement/presentation logic remains profile-owned;
- `tx_state=unknown` is not blindly retried by generic session code;
- TODO_029 idempotency is preserved: same transfer/message identity is replayed where
  recovery explicitly permits replay;
- sender `completed` still means remote `RESULT OK`, never merely local write or first TX;
- TUI may suppress file-transfer base64/protocol noise from scrollback, but that UI policy
  must be independent of controller output-mode mutation;
- forensic logging/redaction behavior remains intact.

## Design requirements

1. Separate three concepts that are currently conflated:
   - local transport write/submission outcome;
   - local Chatter BINARY presentation / bounded backpressure;
   - remote FT1 application completion.
2. Do not use human TELEMETRY mode as a hidden machine side channel.
3. Remove the transfer-mode lease state (`_transfer_restore_mode` and equivalent behavior)
   from the file-transfer path. If the generic `BinaryUserTransferLifecycle` hook becomes
   dead after this, simplify/remove it rather than retaining a no-op abstraction solely for
   historical compatibility.
4. Preserve reconnect repair. A connection-generation change may trigger idempotent FT1
   replay/recovery, but must not trigger `/both`.
5. Keep DATA fast path free of a new application ACK. Gaps are detected by receiver chunk
   identity and repaired after control settlement using existing FT1 mechanisms.

## Implementation

- [ ] remove mandatory parsing/waiting on `DELIVERY WAIT_ACK/ACK/FAILED` from ordinary FT1
      send progression;
- [ ] remove `/both` acquisition, reconnect reassertion and prior-mode restoration from
      file-transfer lifecycle;
- [ ] define and document the replacement binary-send settlement/backpressure contract;
- [ ] preserve bounded handling of local write failure / unknown outcome without blind
      duplicate side effects;
- [ ] preserve META/DATA/END/MISSING/RESULT reconnect repair from TODO_029;
- [ ] decouple TUI transfer-output muting from any controller output-mode lease;
- [ ] update `ARCHITECTURE.md`, `FILE_TRANSFER.md`, `AGENT_API.md` and the agent skill if
      their documented contracts change;
- [ ] remove or update tests that currently require temporary `BOTH` and mode restoration;
- [ ] add regressions proving no transfer-owned output-mode commands are emitted.

## Validation

Automated:

- [ ] TX file transfer succeeds in a fixture where no `DELIVERY ...` telemetry lines are
      ever produced;
- [ ] RX file transfer and final RESULT path succeed without telemetry settlement lines;
- [ ] starting, completing, failing and cancelling a transfer emits no `/both`, `/chat` or
      `/tele` commands;
- [ ] reconnect during an active transfer emits no output-mode command and still reaches
      deterministic repair/completion or bounded failure;
- [ ] CHAT/BOTH/TELEMETRY tracked mode values are unchanged by the transfer lifecycle;
- [ ] TELEMETRY-only/no-BINARY-visibility case has explicit deterministic behavior and does
      not silently mutate mode;
- [ ] TODO_029 selective MISSING repair, duplicate handling, RESULT semantics and
      `repair_too_large` regressions remain green;
- [ ] full pytest suite passes because the change touches profile, session-facing binary
      transport and file-transfer behavior.

Physical:

- [ ] two-node USB file transfer with controller left in ordinary CHAT mode and no automatic
      `/both` transition;
- [ ] same transfer with forensic log proving no transfer-generated output-mode command;
- [ ] local reconnect scenario still repairs missing chunks and verifies final SHA-256;
- [ ] repeat after TODO_031 so throughput validation is not contaminated by the known
      Serial `read(512)` / 200 ms receive-batching bug.

## Findings

Operator decision on 2026-09-30: TELEMETRY is diagnostic output and must not be a required
control plane for ordinary file transfer. The current `BOTH` lease/restore behavior is
therefore a follow-up defect, not the desired long-term contract.

## Known limitations

The existing firmware exposes BINARY payload presentation through the human CHAT path.
This TODO does not authorize a firmware change. If a user selects a mode where that payload
is not observable and no independent existing stream carries it, SerialTerminal must expose
that limitation honestly instead of changing the mode behind the user's back.

## Result

Implemented: `OPEN`
Validated: `OPEN`
Status: `OPEN`
