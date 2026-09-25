# LoRa radio characterization program

Purpose: durable research plan for characterizing LoRa-Chatter radio operation across
supported SF/BW/payload combinations using two physical nodes and the hardware
executor.

This document defines the campaign structure and interpretation rules. The lower-level
execution contract for an individual sweep is
`references/phy-payload-sweep.md`.

## Research question

At fixed low TX power, determine which supported LoRa PHY combinations carry Chatter
USER traffic cleanly, which combinations are degraded but usable, and which fail or
show reproducible CRC/header/retry behavior.

The campaign is not a range test and is not a search for one monotonic maximum payload.
It is a stability/compatibility map across:

```text
spreading factor
bandwidth
USER payload size
direction
```

The primary fixed-power campaign uses:

```text
TX power = 2 dBm on both nodes
```

Keep frequency and physical setup constant within a campaign unless the operator
explicitly creates a separate frequency/topology experiment.

## Campaign stages

### Stage 1 — MAIN MATRIX

```text
SF = 7, 8, 9, 10, 11, 12
BW = 125, 250, 500 kHz
payload = 1, 8, 16, 32, 64, 96, 128, 160, 180, 200 user bytes
directions = A->B and B->A
```

This is the first required stage for a new full characterization campaign.

Normal point depth:

```text
3 logical USER requests A->B
3 logical USER requests B->A
```

If any CRC/HDR/retry/ACK-timeout/final-failure/correlation anomaly appears at the
point, extend that exact SF/BW/payload to:

```text
10 logical USER requests total A->B
10 logical USER requests total B->A
```

Do not stop scanning larger payloads after an anomaly.

### Stage 2 — SLOW

```text
SF = 7, 8, 9, 10, 11, 12
BW = 62.5 kHz
payload = 1, 8, 16, 32, 64, 96, 128, 160, 180, 200 user bytes
directions = A->B and B->A
```

Use the same normal 3+3 point depth and 10+10 anomaly-extension rule as MAIN.

Run this as a separate campaign stage because airtime is materially longer.

### Stage 3 — ULTRA-SLOW

```text
SF = 7, 8, 9, 10, 11, 12
BW = 41.7, 31.25, 20.8, 15.6, 10.4, 7.8 kHz
directions = A->B and B->A
```

Ultra-slow settings can make a single long USER transaction very expensive. Do not
apply the full MAIN repetition grid blindly.

Initial qualification for each SF/BW:

```text
payload = 1, 16, 64, 128, 200 user bytes
1 settled logical USER A->B
1 settled logical USER B->A
```

This is a coverage screen, not a high-confidence clean classification.

If all five payloads are clean in both directions, classify the combination as
`screened-clean` and move on.

If any anomaly occurs:

1. repeat the anomalous payload to at least 3 settled logical USER requests per
   direction;
2. add one or two neighboring/midpoint payload sizes around the anomaly;
3. preserve every retry/CRC/HDR/failure as evidence;
4. continue through the 200-byte endpoint even when an earlier payload was degraded;
5. if the evidence remains unstable or contradictory, schedule a focused follow-up
   instead of exploding the entire ultra-slow matrix to byte-by-byte coverage.

The operator may later promote selected ultra-slow combinations from
`screened-clean` to full 3+3 validation when they are operationally important.

## Canonical run sharding

Do not attempt the entire campaign in one hardware-agent RUN.

A canonical RUN should have a recoverable, reviewable boundary and should finish with
a complete report even if later stages remain open.

Default shards:

```text
MAIN:
    one BW per RUN
    RUN A: BW500, SF7..12, full sparse payload grid
    RUN B: BW250, SF7..12, full sparse payload grid
    RUN C: BW125, SF7..12, full sparse payload grid

SLOW:
    one RUN for BW62.5 when practical
    split SF7..9 and SF10..12 if duration/anomaly expansion becomes excessive

ULTRA-SLOW:
    one BW per RUN by default
    split further by SF when long-airtime retries make a complete BW shard impractical
```

A RUN may be split earlier when:

- anomaly extensions materially inflate duration;
- transport stability becomes questionable;
- forensic logs become unwieldy;
- the agent cannot complete the shard without risking evidence quality.

Do not combine partial results from an invalid/contaminated RUN into a later PASS
claim without explicitly identifying which points were repeated cleanly.

## Deterministic traversal order

Within a shard, use a declared deterministic order and record it in REPORT.md.

Default:

```text
SF ascending: 7 -> 8 -> 9 -> 10 -> 11 -> 12
payload ascending within SF
direction block: complete A->B repetitions, then B->A repetitions
```

The exact BW shard order for the MAIN campaign is:

```text
500 -> 250 -> 125 kHz
```

The order is an orchestration convention, not a statement that one PHY is better.

Record the previous and target PHY at each configuration transition so later analysis
can distinguish a steady-state RF anomaly from a possible runtime-reconfiguration
history effect.

## Baseline and preflight

Every canonical shard starts from a clean executor/hardware state.

Required facts before measured USER traffic:

```text
identify both nodes
record exact /version when provenance is part of the campaign
record /config on both nodes
heartbeat OFF
diagnostic OFF
echo-loop OFF
reliable USER work settled / cancelled
power = 2 dBm on both nodes
same campaign frequency on both nodes
target SF/BW applied and confirmed on both nodes
```

BLE is the default controller transport. BLE output/transport failures are not LoRa
RF failures.

Do not flash, reboot, toggle unrelated settings or modify source as part of a baseline
sweep unless the operator explicitly creates a separate control experiment.

## Point execution

The low-level serialization and ACK-correlation rules in
`phy-payload-sweep.md` are mandatory.

The central invariant is:

```text
one measured reliable USER transaction in flight across both nodes combined
```

For each logical USER:

```text
send
-> capture current USER identity/sequence
-> wait for matching ACK for that exact transaction
   OR explicit bounded terminal outcome
-> verify the transaction is settled
-> only then send the next USER
```

Never launch the opposite direction while the current transaction is unsettled.

Never treat an arbitrary/newest ACK as completion.

## Payload construction

Use deterministic single-byte ASCII so requested USER byte length equals actual USER
byte length.

Each logical request should have a unique point/request marker when the payload length
allows it. The rest of the payload is deterministic padding.

Uniqueness is for forensic correlation only; it must not change the requested total
USER byte length.

## What to measure

Per point, retain:

```text
SF
BW
power
frequency
payload user bytes
direction
logical requests
matching-ACK deliveries
physical USER attempts
retry count
ACK timeout count
final delivery failures
CRC count
HDR count
RSSI/SNR observations
queue/correlation/transport anomalies
validity status
```

Also preserve frame length when firmware telemetry exposes it. Chatter USER RF frame
length is larger than USER payload length because protocol overhead exists; do not
confuse the two.

## Classification

Use these point labels:

```text
CLEAN
    all requested logical deliveries completed on first physical attempt and no
    CRC/HDR/correlation anomaly was observed

DEGRADED
    logical delivery succeeded, but retry/CRC/HDR/ACK-timeout evidence occurred

FAILED
    at least one requested logical delivery reached bounded final failure

INVALID
    overlap, lost correlation, mismatched PHY, transport forensic gap or other
    orchestration defect prevents an RF conclusion

UNMEASURED
    requested point was not executed
```

For ULTRA-SLOW initial one-request-per-direction qualification, use:

```text
SCREENED-CLEAN
SCREENED-DEGRADED
SCREENED-FAILED
SCREENED-INVALID
```

Do not present a screening result as equivalent to a 3+3 validated point.

## CRC/HDR interpretation

CRC/header events are RF evidence but do not carry trustworthy USER protocol identity.

Attribute them to the active serialized measurement window and event order. Do not
invent an exact USER sequence from the CRC/HDR line itself.

A CRC event followed by successful retry/ACK means `DEGRADED`, not `CLEAN`.

A short-payload anomaly does not prove that longer packets fail. A long-payload
success does not erase a shorter-payload CRC anomaly.

## Contamination rule

Any cross-node measured USER overlap invalidates the affected sample.

The first detected overlap/lost-correlation point defines a contamination boundary.
From that boundary until clean state is explicitly re-established:

```text
do not use samples for RF conclusions
```

Recovery:

```text
stop new USER submission
-> settle/cancel reliable work on both nodes
-> verify queues/retries quiet
-> re-confirm 2 dBm and target PHY on both nodes
-> repeat the contaminated point from scratch
```

If a canonical shard cannot be fully repaired during the run, publish it as
INCONCLUSIVE with exact unmeasured/invalid points rather than fabricating completion.

## Adaptive anomaly follow-up

The main campaign maps the space. It does not try to prove root cause inside every
shard.

After a shard is published, the coordinator reviews anomalies and may schedule a
separate focused diagnostic RUN.

Useful follow-ups include:

```text
repeat exact anomalous SF/BW/payload with larger sample count
compare both directions
add nearby payload sizes
repeat same point without any config transition
controlled PHY re-apply A/B
controlled configuration-order A/B
repeat after reboot only as an explicit separate control
```

Do not inject these controls silently into the baseline matrix.

## Runtime PHY re-apply control

If the baseline campaign suggests a configuration-history effect, create a separate
A/B experiment.

Example structure:

```text
A: reach target PHY through normal campaign transition, measure focused point
B: explicitly move to another valid PHY and return to target, measure same point
```

Keep payload, power, frequency, direction and physical setup unchanged.

The re-apply experiment is evidence about runtime configuration behavior. It must not
retroactively rewrite the baseline sweep.

## Campaign completion

A stage is complete only when:

- every requested SF/BW/payload/direction point has a valid result under the stage's
  repetition policy;
- every contaminated point has been cleanly repeated or remains explicitly unresolved;
- anomaly extensions required by the contract are complete;
- all canonical RUNs are published and remotely verified;
- the coordinator has reviewed the reports/raw anomaly windows for consistency.

The full radio characterization campaign is complete only when MAIN, SLOW and
ULTRA-SLOW are all complete or the operator explicitly records a narrower accepted
scope.

## Agent/coordinator workflow

The hardware executor runs one shard at a time.

Coordinator responsibilities:

1. choose the next stage/shard;
2. give the agent the exact stage/BW/SF scope and campaign frequency;
3. state that TX power is fixed at 2 dBm;
4. require CANONICAL_RUN publication;
5. require the agent to load this program and `phy-payload-sweep.md`;
6. review the published RUN/OBS before starting the next shard;
7. schedule anomaly follow-ups separately.

Executor responsibilities:

1. follow its hardware skill and RF preflight;
2. enforce global USER serialization and exact ACK correlation;
3. execute the requested shard completely;
4. extend anomalous points according to the stage policy;
5. preserve CRC/HDR/retry evidence;
6. recover and repeat contaminated points instead of using them;
7. restore safe final state;
8. publish exact RUN/OBS evidence and report unmeasured points explicitly.

The coordinator should not send the entire multi-stage campaign as one giant prompt.
Each shard gets a concise run-specific prompt in chat; durable rules remain here and in
the sweep reference.
