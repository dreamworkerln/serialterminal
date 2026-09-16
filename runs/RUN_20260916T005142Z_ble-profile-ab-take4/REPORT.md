# BLE profile A/B diagnostic

Result: INCONCLUSIVE

Target: LoRa-Chatter-1B44
Device key: `ble-address:44:1b:f6:8d:b7:a9`
Observed address: `44:1B:F6:8D:B7:A9`
SerialTerminal: `dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967`
Firmware: unknown

One long-lived SerialTerminal agent process was used (`pid=8315`), with three sequential BLE sessions to the same device: `s1` Generic A, `s2` Chatter, `s3` Generic B. No second node session, flash, reboot, btmon, sudo, or source investigation was used.

## Observed profiles and streams

- GENERIC A: `profile=generic`, `streams=["main"]`; `/id` returned `LoRa-Chatter-1B44`; `/chat` returned `OUTPUT CHAT`; `/help` showed `echo=OFF`.
- CHATTER: `profile=chatter`, `streams=["chat","telemetry"]`; profile-owned identity preamble returned `LoRa-Chatter-1B44`; `/chat` returned `OUTPUT CHAT`; `/help` showed `echo=OFF`. Telemetry was retained separately and not mixed with chat bytes.
- GENERIC B: `profile=generic`, `streams=["main"]`; `/id` returned `LoRa-Chatter-1B44`; `/chat` returned `OUTPUT CHAT`; `/help` showed `echo=OFF`.

## Isolated controls

- GENERIC A: 2/2 `/help` outputs byte-complete.
- CHATTER: 2/2 `/help` outputs byte-complete on `chat`; telemetry remained a separate stream.
- GENERIC B: 2/2 `/help` outputs byte-complete.

## Burst results

Each iteration sent `/help` followed immediately by `/id`, then observed until completion and a quiet interval of approximately 1 s or more. Completion was judged from raw stream bytes/data_b64 and same-run complete output, not logical-line count alone. All five iterations in every block contained the expected complete help content, including `COMMANDS`, `/cancel all`, `/reboot`, `RAW CONTROLS`, `ANDROID BLE TERMINAL MACROS`, `Nordic UART`, and `BLE CLIENT`, followed by the identity line.

| Block | Raw human-console RX ranges | Iteration results |
|---|---|---|
| GENERIC A | main `296-389`, `394-487`, `492-585`, `590-683`, `688-781` | 1 COMPLETE; 2 COMPLETE; 3 COMPLETE; 4 COMPLETE; 5 COMPLETE |
| CHATTER | chat `350-444`, `474-568`, `573-667`, `697-791`, `796-915` | 1 COMPLETE; 2 COMPLETE; 3 COMPLETE; 4 COMPLETE; 5 COMPLETE |
| GENERIC B | main `202-295`, `300-393`, `398-491`, `496-589`, `594-687` | 1 COMPLETE; 2 COMPLETE; 3 COMPLETE; 4 COMPLETE; 5 COMPLETE |

| Block | COMPLETE | MALFORMED / INCOMPLETE | INCONCLUSIVE |
|---|---:|---:|---:|
| GENERIC A | 5/5 | 0/5 | 0/5 |
| CHATTER | 5/5 | 0/5 | 0/5 |
| GENERIC B | 5/5 | 0/5 | 0/5 |

First malformed raw example: not applicable; no affected block.

`forensic_gap`: no. No persisted `forensic_gap` event was found for `s1`, `s2`, or `s3`.

Disconnect/reconnect affecting comparison: no. Each open briefly recorded `state=reconnecting` before reaching `connected`; no disconnect/reconnect occurred during a comparison iteration. All three sessions closed normally. Final status before close reported `queued_tx=0`; `/chat` was confirmed.

There were a few overlapping observe requests during setup/cleanup before the comparison windows. Their responses duplicated already-returned event views, but the persisted session event sequence has no forensic gap and the burst ranges above are based on the raw event records, not duplicated response payloads.

## Factual comparison and finding

The previously observed corruption did not reproduce in this single-node profile A/B run: Generic A, Chatter, and Generic B were all byte-complete. Therefore profile selection did not produce a discriminator in this run. This correlation result does not assign root cause to SerialTerminal or firmware.

Final node state: powered on, output CHAT, echo OFF, queued TX 0; all sessions closed normally and the single agent process exited cleanly.

