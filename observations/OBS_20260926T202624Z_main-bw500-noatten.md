# Node observation

Observed: 2026-09-26T20:26:24Z
Task: MAIN MATRIX BW500 no-attenuator shard startup
Result: BLOCKED
SerialTerminal: dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9
Firmware: dreamworkerln/lora-sack-protocol@unknown

Run bundle: runs/RUN_20260926T202624Z_main-bw500-noatten/

## Setup

Operator specified no inline RF attenuators on either node. No distance, orientation, or room topology was supplied. BLE was used.

## Actions

One fresh long-lived SerialTerminal agent process performed BLE discovery. It returned an empty device list. The machine API exposes no capability scanner/prober operation; the documented interactive scanner cannot be used while keeping this JSONL agent as the sole process owning the complete hardware interaction. No nodes were opened and no RF traffic or configuration command was sent.

## Evidence

The discovery response and event order are in the exact process log in the run bundle. No node identity, `/version`, `/config`, or RF measurement was obtained.

## Anomalies / conflicts

No RF anomaly was measured. The run is blocked at BLE capability discovery. The companion log's prelaunch nonexistence was not verified because the wrong companion filename was checked; this evidence gap is documented in REPORT.md.

## Final state

No sessions opened; no node state changed by this attempt. Nodes' actual final configuration remains unknown.
