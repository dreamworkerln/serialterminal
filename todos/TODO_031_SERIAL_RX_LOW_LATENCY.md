# Serial RX low-latency delivery TODO

TODO-ID: TODO_031
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN

## Purpose

Remove the fixed ~200 ms receive-batching latency currently introduced by the generic
`SerialTransport` read path. A serial timeout may bound idle waiting, but already-arrived
bytes must not be held until a large requested buffer fills or the full timeout expires.

This is a generic transport latency defect and is tracked separately from TODO_030 per the
TODO scope rule. TODO_030 removes the Chatter/telemetry dependency; TODO_031 fixes the
underlying Serial receive behavior that made the file-transfer throughput collapse obvious.

## Current behavior

`SerialTransport.connect()` configures:

```python
ser.timeout = 0.20
```

`ManagedSession.rx_loop()` asks for up to 512 bytes and the Serial transport currently calls:

```python
ser.read(512)
```

With pyserial timeout semantics, a short response can therefore remain blocked until either
512 bytes are collected or roughly 200 ms expires. This turns an idle-read timeout into
per-batch latency.

Operator-provided baseline:

```text
log: serialterminal-20260930-045442-141753-p62766.log
transport: USB Serial @ 115200
radio: SF7 / BW500 / CR 4/5
full Chatter BINARY USER: 243 B application / 255 B RF frame
FT1 file bytes per full DATA: 227 B
firmware TX USER duration: about 102 ms
firmware DELIVERY ACK elapsed: normally about 48..51 ms
host TX USER -> WAIT_ACK timestamp gap: median about 203 ms
full-DATA TX timestamp cadence: median about 384 ms
observed file-transfer rate: about 4.8 kbit/s
```

The ~200 ms plateau matches the configured serial timeout and is not LoRa airtime.

## Target behavior

Serial RX must wake promptly when any bytes are available and may then drain additional
immediately available bytes up to the caller's requested maximum.

Required properties:

- no requirement to fill the caller's 512-byte request before returning a short burst;
- no fixed ~200 ms coalescing delay after bytes have arrived;
- no busy-spin while the serial link is idle;
- preserve full-duplex RX/TX concurrency;
- preserve reconnect/disconnect/cancel-read behavior and existing write-outcome semantics;
- remain generic: no Chatter-aware logic in `SerialTransport` or `ManagedSession`.

A reasonable implementation shape is first-byte blocking followed by draining `in_waiting`
or an equivalent pyserial mechanism. The TODO intentionally does not mandate one exact API
sequence; correctness and latency behavior are the contract.

## Scope

- `src/serialterminal/transports/serial.py` read behavior;
- `ManagedSession` only if a generic read-loop change is actually required;
- deterministic transport/session tests;
- file-transfer performance validation as a consumer-level regression.

## Non-goals

- no firmware change;
- no BLE/SPP redesign;
- no Chatter command parsing in generic transport code;
- do not treat the physical `/bin <BASE64>` cost at 115200 as a software sleep;
- do not chase the firmware's radio USER/ACK airtime inside this host transport TODO.

## Invariants

- Serial reads remain bounded and interruptible enough for shutdown/reconnect;
- multiple readers remain serialized while TX remains concurrent with blocking RX;
- ordinary terminal input latency improves as well as FT1 latency;
- log/event ordering and canonical line assembly remain unchanged;
- a fix must not replace a 200 ms blocking wait with a CPU-burning zero-timeout polling loop.

## Performance budget

At 115200 8N1, a maximum `/bin` command containing 243 raw bytes expands to roughly 330
UART bytes and therefore costs about 28.6 ms on the wire. That is physical/local framing
overhead, not the 200 ms bug.

For the recorded SF7/BW500 case, current firmware reports about 102 ms USER TX and roughly
49 ms from TX completion to ACK handling. With the serial batching defect removed and no
new host pacing, a practical file-payload rate around 9..10 kbit/s is a reasonable
expectation for the present text/base64 @115200 path. The RF-only ceiling is higher and
must not be used as the host acceptance threshold.

## Implementation

- [x] change Serial RX so a short available burst is returned promptly instead of waiting
      for `read(512)` to fill or hit 0.20 s;
- [x] preserve an efficient blocking idle path; no high-frequency spin loop;
- [x] preserve full-duplex write concurrency and disconnect lifecycle;
- [x] audit `ManagedSession` TX queue waits and Chatter adapter condition waits to confirm
      they are event-woken and do not add fixed per-chunk sleeps/poll intervals;
- [x] do not add compensating sleeps, pacing constants or arbitrary debounce delays;
- [x] add focused regression tests for short serial bursts smaller than 512 bytes;
- [x] run the full test suite because the generic Serial transport is shared behavior.

## Validation

Automated:

- [x] deterministic fake/PTY test: a short burst much smaller than 512 bytes becomes a
      session RX event promptly without waiting the configured 0.20 s idle timeout;
- [x] idle read still blocks efficiently and shutdown/reconnect can wake it;
- [x] RX and TX remain concurrent;
- [x] fragmented and multi-line serial input retains exact bytes/order;
- [x] existing reconnect and forensic logging tests remain green.

Physical regression using the same topology/file as the 2026-09-30 baseline:

- [ ] no recurring ~200 ms host receive plateau in the log;
- [ ] full-DATA chunk cadence is materially below the ~384 ms baseline; target <= 230 ms
      median under the same SF7/BW500/115200 conditions;
- [ ] displayed sustained file rate is materially above 4.8 kbit/s; expected approximately
      9..10 kbit/s with the current text/base64 path when RF is clean;
- [ ] final file SHA-256 matches and no new retries/failures are introduced;
- [ ] record exact implementation SHA and exact physical validation run/checkpoint.

## Findings

The 200 ms value is valid as a coarse idle-read bound, but using it through
`read(512)` couples latency to requested buffer size. The defect is semantic batching,
not simply that the numeric timeout is 'too large'.

## Known limitations

Even after this fix, 115200 baud plus base64 framing consumes real time. Raising baud or
introducing a different local binary framing is a separate optimization and must be
measured/justified separately rather than hidden inside this latency fix.

## Result

Implemented: `a6581f0655a5c15d538b7511ec6b2a67fc9bb693`
Validated automated: GitHub Actions `36665201283` SUCCESS
Physical throughput regression: NOT RUN
Status: `IMPLEMENTED / PHYSICAL VALIDATION OPEN`
