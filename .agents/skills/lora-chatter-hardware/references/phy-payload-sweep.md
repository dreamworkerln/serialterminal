# PHY / payload sweep hardware validation

Read this only for LoRa SF/BW/payload characterization and stability sweeps.

The purpose is to map which radio configurations carry reliable USER traffic without
destroying evidence through orchestration overlap or premature "first failure"
assumptions.

## Controlled variables

A PHY/payload sweep changes only the variables named by the task.

Unless the task explicitly says otherwise, hold these constant for the measured phase:

```text
TX power      = 2 dBm on both nodes
frequency     = task baseline
heartbeat     = OFF
diagnostic    = OFF
echo-loop     = OFF
coding/sync   = current firmware defaults/config
transport     = BLE
```

Record the pre-run `/config` of both nodes and restore it at the end unless the task
specifies a different final state.

Before every measured PHY row, apply the intended SF/BW to **both** nodes and confirm
the exact effective values with `/config`. Do not start USER traffic while the nodes
report different measured PHY settings.

Do not insert an unrequested "fix", extra BW toggle/reapply, reboot, or other hidden
configuration experiment into the baseline sweep. A PHY re-apply A/B is a separate
control and must be reported as such.

## Full PHY characterization stages

When the operator asks to characterize **all supported SF/BW combinations**, treat the
campaign as three separately reported stages:

```text
MAIN MATRIX:
    SF = 7, 8, 9, 10, 11, 12
    BW = 125, 250, 500 kHz

SLOW:
    SF = 7, 8, 9, 10, 11, 12
    BW = 62.5 kHz

ULTRA-SLOW:
    SF = 7, 8, 9, 10, 11, 12
    BW = 41.7, 31.25, 20.8, 15.6, 10.4, 7.8 kHz
```

Run and publish these as distinct stages so a long ultra-slow campaign cannot obscure
which earlier matrix is already complete.

For a new full characterization campaign, start with **MAIN MATRIX** unless the
operator explicitly selects another stage.

A historical or partial sweep does not close a stage merely because it sampled some
of the same SF/BW/payload points. A stage is complete only when its requested matrix
was executed under the current serialization/correlation rules with no unresolved
contaminated points. Preserve earlier runs as historical evidence, but label them
partial/incomplete relative to the stricter campaign when appropriate.

The standard sparse payload grid below applies to MAIN MATRIX and SLOW.

For ULTRA-SLOW, airtime can become extremely large. Unless the operator requests the
full standard grid, begin each SF/BW point with this reduced coverage grid:

```text
1, 16, 64, 128, 200 user bytes
```

Still test both directions and obey the same one-global-transaction invariant. If an
ultra-slow point shows CRC/HDR/retry/timeout/failure, preserve it and add a few
neighboring/midpoint payload sizes around the anomaly. Do not silently skip 200 B and
do not switch automatically to a 1-byte exhaustive scan.

## Sparse payload scan

When the operator asks to scan the application range `1..200` bytes without a
byte-by-byte sweep and does not provide a different list, use this standard sparse
grid:

```text
1, 8, 16, 32, 64, 96, 128, 160, 180, 200 user bytes
```

This is a sparse coverage grid, not a monotonic-boundary assumption.

For every SF/BW combination requested by the task, test **all** payload points in the
grid. Do not stop at the first CRC, retry, timeout, or failed delivery, and do not skip
larger payloads because a smaller payload failed. RF anomalies may be non-monotonic.

Use deterministic ASCII payload bytes so "N bytes" means exactly N RF user bytes.
Avoid multibyte UTF-8 in a size sweep. Include a short run/point marker when the
payload length permits it, then pad deterministically to the exact requested byte
length.

## Global serialization invariant

During a measured sweep there may be **only one measured reliable USER transaction in
flight across both nodes combined**.

For one logical USER request:

```text
send one USER
-> observe sender TX USER identity/sequence
-> observe receiver result
-> wait for the matching DELIVERY ACK for that exact current USER identity
   OR explicit final delivery failure/cancellation settlement
-> confirm no retry/USER from that logical transaction remains active
-> only then start the next logical USER request
```

Never treat "some ACK appeared" as completion.

In particular:

- do not queue the next payload while the current USER is in WAIT_ACK/retry;
- do not begin the opposite direction while the current direction is unsettled;
- do not submit A->B and B->A together during a sweep;
- do not use reliable queue depth as sweep throughput;
- do not infer completion from local TxDone, `>`, SerialTerminal `queued`/`written`,
  or an unrelated DELIVERY ACK.

When the sender telemetry exposes the USER sequence, the completion ACK must match that
exact sequence under the established sender session. If exact correlation is lost or
ambiguous, the point is invalid and must be repeated from a clean settled state.

## Repetition policy

Normal sparse point:

```text
3 logical USER requests A->B
then 3 logical USER requests B->A
```

Every logical request must settle before the next begins.

If any anomaly appears at a point, including:

```text
RX CRC ERROR
header error
unexpected retry
ACK timeout
final delivery failure
unexpected queue growth
correlation ambiguity
```

then preserve the original evidence and extend that **same SF/BW/payload** to:

```text
10 logical USER requests total A->B
10 logical USER requests total B->A
```

This extension is for directionality/repeatability. Do not discard the first anomalous
attempts when counting the ten.

After the main sparse matrix, the task may request adaptive refinement around an
anomaly. Refine with a few neighboring/midpoint payload sizes; do not automatically
switch to a 1-byte exhaustive sweep.

## CRC and header-error attribution

SX127x CRC/header error telemetry does not contain a trusted protocol USER sequence.

Therefore record CRC/HDR evidence as:

```text
receiver
active SF/BW/payload measurement window
timestamp/order
RF frame length
RSSI/SNR when reported
surrounding TX/retry/ACK events
```

Do not claim that a CRC line itself identifies an exact USER sequence.

When the sweep is globally serialized, the active measurement window gives strong
context, but exact per-attempt association still comes from event ordering and must be
described as contextual when the corrupted frame has no protocol identity.

A CRC/HDR event is evidence to preserve, not a reason to throw away the row.

## Collision / contamination recovery

Cross-node USER overlap invalidates the affected radio sample.

If overlapping measured USER transmissions are detected, or if orchestration launches
a new USER before the previous logical transaction settles:

1. mark every affected point from the first overlap as contaminated until clean state
   is re-established;
2. do not use those samples for PHY reliability conclusions;
3. stop submitting new USER traffic;
4. settle or `/cancel all` as appropriate on both nodes and verify retries/queues are
   quiet;
5. re-confirm the intended power/SF/BW on both nodes;
6. repeat the contaminated point from scratch with global serialization.

Do not continue the matrix and later "average in" contaminated samples.

## Configuration-change boundary

Change SF/BW only when reliable USER work is fully settled.

For each new combination:

```text
settle previous USER transaction
-> apply requested PHY on node A
-> confirm
-> apply requested PHY on node B
-> confirm
-> /config on both
-> verify both report identical target SF/BW and 2 dBm
-> start measured USER traffic
```

If a config command reports BUSY, do not retry blindly while USER work may still be
active. Resolve the transaction state first.

## Per-point evidence

For every SF/BW/payload/direction point, retain enough evidence to report at least:

```text
logical USER requests attempted
logical deliveries with matching ACK
physical USER attempts / retries
final delivery failures
CRC count
HDR count when available
receiver RSSI/SNR observations
unexpected queue/collision/correlation events
valid / invalid / contaminated status
```

Do not collapse "eventually ACKed" into "clean": retries and CRC/HDR remain important
radio evidence even when logical delivery ultimately succeeds.

## Completion semantics

A completed sweep must distinguish:

```text
clean point
    all requested logical deliveries completed without observed RF anomaly/retry

degraded-but-delivered point
    logical delivery completed, but retry/CRC/HDR occurred

failed point
    one or more logical deliveries reached bounded final failure

invalid/contaminated point
    orchestration overlap, lost correlation, transport forensic gap or mismatched PHY
    prevents a radio conclusion

unmeasured point
    never executed
```

Do not infer a packet-size ceiling unless the measured data actually demonstrates one.
A smaller payload anomaly followed by larger clean payloads is evidence against a
simple monotonic size boundary.

## Canonical run reporting

For a canonical sweep, the RUN report must include:

- exact SF/BW matrix requested and actually completed;
- exact sparse payload grid;
- fixed TX power and frequency;
- direction and repetition counts;
- every CRC/HDR/retry/failure anomaly;
- every invalid/contaminated interval and why it was excluded;
- any point that was extended to 10+10 logical requests;
- all unmeasured combinations;
- whether a separate PHY re-apply control was performed;
- final restored node state.

Raw forensic logs remain the authority for exact event ordering.
