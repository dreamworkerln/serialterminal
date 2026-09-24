# Reliable USER / ACK hardware validation

Read this only for USER reliability, ACK, retry, duplicate, queue or cancellation scenarios.

Current ACK-capable Chatter uses bounded stop-and-wait USER delivery.

Logical identity:

```text
(sender_session_id, user_seq)
```

A retry reuses the same logical identity and payload.

Current implementation policy for the checkpoint family is typically:

```text
maximum physical USER attempts = 5
reliable USER queue depth = 8
```

Treat these as maintained executor policy, not eternal wire constants. A task that depends on changed implementation semantics must supply the updated contract explicitly; the hardware executor does not inspect firmware source/docs to discover it.

## Normal delivery

Strong PASS evidence for normal USER requires both sides:

```text
sender physical USER transaction
peer received/presented the intended USER
sender received matching ACK for the same logical identity
```

SerialTerminal queued/written and a local TxDone marker are not peer delivery.

Use unique payloads for independent directions/scenarios.

## Duplicate and lost ACK

NEW USER:
- present in peer CHAT once;
- create ACK obligation.

DUPLICATE USER:
- suppress duplicate CHAT presentation;
- send ACK again.

STALE USER:
- do not re-present as a fresh chat message;
- current contract does not require an ACK.

A lost-ACK acceptance scenario must prove, together:

```text
peer CHAT showed USER exactly once
peer classified retry as duplicate
peer sent repeated ACK
sender later matched ACK
```

Do not claim ACK loss merely because the sender retried. Fault creation must be physically or instrumentally demonstrated by the scenario.

If the available setup cannot deterministically create the requested lost USER/ACK/wrong ACK condition, report BLOCKED or INCONCLUSIVE. Never fabricate the fault.

## ACK matching

Wrong-session, wrong-seq, stale or unrelated ACK must not complete the current pending USER.

ACK itself is not ACKed.

Heartbeat and ECHO are best-effort traffic outside the reliable USER state machine.

## Queue

While one USER waits for ACK/retry, later USER messages may wait in a bounded reliable queue.

Queue full must be explicit, for example:

```text
[SYS] SEND QUEUE FULL: message not accepted
```

Do not treat queue rejection as accepted delivery.

## Cancellation

/cancel:

```text
in-flight USER already physically transmitted
    -> stop future retries
    -> delivery status remains unknown

no in-flight USER; queued unsent USER exists
    -> remove one queued USER
    -> it was not transmitted
```

/cancel all stops the current reliable retry and clears queued reliable USER messages.

For cancellation validation, verify that no further retry TX occurs for the cancelled logical USER. Do not claim cancellation proves a previously transmitted USER was not received.

## Concurrency and peer-off

Simultaneous half-duplex USER transmissions may collide. A reliability scenario accepts collision as an intermediate event only if bounded randomized retries later separate delivery or produce the explicit bounded failure required by the contract.

Peer-off validation requires bounded retry exhaustion and no endless retry after final failure.

Peer-return validation requires evidence that the pending logical USER can complete after the peer becomes available within the retry window.

## Focused reliability checklist

When the task is the full reliability gate, cover separately as requested:

```text
normal USER -> ACK
lost USER -> retry -> ACK
lost ACK -> duplicate suppression -> repeated ACK -> delivery
simultaneous USER
peer off bounded failure
peer returns during retry window
new USER while another waits
queue full explicit rejection
/cancel in-flight
/cancel queued
/cancel all
wrong-session ACK
wrong-seq ACK
stale/duplicate ACK
```

Do not expand a narrow task into the full checklist unless asked.
