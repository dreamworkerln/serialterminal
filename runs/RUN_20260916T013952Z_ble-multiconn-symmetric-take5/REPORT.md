# BLE multi-connection symmetric diagnostic — take5

Result: INCONCLUSIVE

Observed UTC: 2026-09-16T01:39:52Z
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Run shape

One long-lived agent process was used for both passes. Capability-based discovery found:

| Node | device_key | session(s) | BLE streams |
|---|---|---|---|
| LoRa-Chatter-1B44 | `ble-address:44:1b:f6:8d:b7:a9` | `s1` pass 1, `s4` peer pass 2 | `chat`, `telemetry` |
| LoRa-Chatter-72E0 | `ble-address:e0:72:a1:d5:4c:15` | `s2` peer pass 1, `s3` pass 2 | `chat`, `telemetry` |

The Chatter profile-owned `/id` preamble confirmed both canonical identities. `/chat` produced `OUTPUT CHAT`; help output showed `echo=OFF`. Human console was the `chat` stream (NUS 0003); machine telemetry remained the independent `telemetry` stream (NUS 0004).

## Pass 1 — target LoRa-Chatter-1B44, peer LoRa-Chatter-72E0

| Phase | Complete | Malformed | Inconclusive |
|---|---:|---:|---:|
| A target alone | 3/3 | 0/3 | 0/3 |
| B peer connected idle | 2/3 | 0/3 | 1/3 |
| C concurrent output | 0/3 | 3/3 | 0/3 |
| D peer closed | 3/3 | 0/3 | 0/3 |

Phase B has only two target `/help` sends in the recorded agent requests; the next target send was the first Phase C stimulus. This is a requested-workflow deviation and prevents a clean 3/3 matrix.

First malformed target evidence in Phase C is raw chat seq `634–698`, session `s1`. The neighbouring raw event at seq `701` starts another `[SYS] CHATTER HELP` before the preceding output has reached its `BLE CLIENT` terminator. Exact event bytes, decoded chunks, and subsequent continuation are preserved in `serialterminal.log`. Peer Phase C session `s2` had three complete help outputs (raw ranges `88–180`, `208–300`, `303–395`).

## Pass 2 — target LoRa-Chatter-72E0, peer LoRa-Chatter-1B44

| Phase | Complete | Malformed | Inconclusive |
|---|---:|---:|---:|
| A target alone | 3/3 | 0/3 | 0/3 |
| B peer connected idle | 3/3 | 0/3 | 0/3 |
| C concurrent output | 0/3 | 3/3 | 0/3 |
| D peer closed | 3/3 | 0/3 | 0/3 |

First malformed target evidence in Phase C is raw chat seq `702–764`, session `s3`. The neighbouring raw event at seq `817` starts another help output before the prior output segment has reached its terminator. Peer Phase C session `s4` had three complete help outputs (raw ranges `88–180`, `208–300`, `328–420`).

## Interpretation boundary

No `forensic_gap` event was recorded in the SerialTerminal forensic log. The malformed concurrent segments are reversible at the raw stream boundary in both target directions, while solo and post-peer-close outputs had complete same-node baselines. However, Pass 1 Phase B was short one iteration and the concurrent sends were not all separated by verified completed target output, so a clean idle-vs-concurrent discriminator is not established by this run. No root cause is assigned to firmware, BlueZ, controller, or transport.

Disconnect/lifecycle boundary: peer sessions `s2` and `s4` were closed normally before their corresponding Phase D. No target reconnect was used for the comparison. `s1` and `s3` remained connected through their Phase D and reported `queued_tx=0` before close.

## Final state

Both physical nodes were left powered on, in CHAT with echo OFF, no pending test sends/retries, and all sessions were closed normally. The single agent process exited cleanly. No flash, reboot, btmon, sudo, firmware inspection, or firmware SHA determination was performed.

