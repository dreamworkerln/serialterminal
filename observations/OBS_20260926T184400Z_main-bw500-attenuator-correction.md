# Node observation — BW500 RF setup correction

Observed: 2026-09-26T18:44:00Z
Task: correct omitted RF-path setup metadata for RUN_20260925T105411Z_main_bw500
Result: PASS (original RUN outcome unchanged)
SerialTerminal: dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9
Firmware: dreamworkerln/lora-sack-protocol@b76ffa04ab47a3f344b8270159ab274256f6ff62

Corrects:
- runs/RUN_20260925T105411Z_main_bw500/
- observations/OBS_20260925T105411Z_main_bw500.md

## Correction

The original BW500 canonical RUN omitted an important physical RF setup fact from its REPORT/OBS metadata.

During the entire measured RUN, **each node had a nominal 30 dB inline RF attenuator installed immediately before its antenna**:

```text
LoRa-Chatter-1B44 radio -> 30 dB attenuator -> antenna
LoRa-Chatter-72E0 radio -> 30 dB attenuator -> antenna
```

Therefore every over-the-air direction included both endpoint attenuators in series with the radio path, for approximately **60 dB of additional nominal end-to-end path attenuation** beyond antennas/free-space/environmental loss.

## Interpretation impact

- All RSSI/SNR values in the original BW500 RUN were observed with those attenuators installed.
- The original logical-delivery counts, retries, ACK timeouts, CRC/HDR counts, point classifications and PASS outcome are not changed by this correction.
- The omitted attenuation materially affects RF-condition interpretation. The BW500 RUN must not be treated as a no-attenuator or ordinary near-field/tabletop baseline.
- Directional anomalies still do not isolate a specific node defect: an A->B USER failure can be A-TX, B-RX or channel related, while a B->A ACK loss can be B-TX, A-RX or channel related.
- Root-cause attribution to one node requires additional controlled measurements, ideally with a third known-good node and/or a separate no-attenuator topology run.

## Historical handling

The original committed RUN/OBS remain immutable evidence. This correction record is the durable amendment and should be considered together with the original RUN during review.
