# Node observation

Observed: 2026-09-16T03:44:42Z
Task: BLE human-console `/help` completeness with concurrent long output on two physical LoRa-Chatter nodes
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: unknown

## Setup
- Exact discovered BLE targets: LoRa-Chatter-1B44 and LoRa-Chatter-72E0.
- SerialTerminal profile: `chatter`; human output confirmed `OUTPUT CHAT`; `/help` output confirmed `echo=OFF`.

## Actions
- Performed 2 isolated solo `/help` iterations on each node.
- Performed 3 concurrent iterations: one `/help` on 1B44 followed immediately by one `/help` on 72E0, then waited for both completions and quiet interval.
- Performed 2 isolated recovery `/help` iterations on each node.

## Evidence
- All requested measured responses contained the complete raw chat output relative to the same-node solo baseline; no missing continuation or truncation was observed.
- Concurrent raw chat ranges were 1B44: `38-130`, `158-250`, `253-345`; 72E0: `13-105`, `133-225`, `253-345`.
- Recovery raw chat ranges were 1B44: `373-465`, `493-585`; 72E0: `13-105`, `133-225` in its recovery session.
- No forensic gap was recorded. No unexpected reconnect affected a measured comparison. No same-node command overlap occurred.

## Anomalies / conflicts
- Initial session state was `reconnecting` during normal profile connection preamble before each session became connected; no reconnect occurred during measured response comparisons.

## Final state
- Both SerialTerminal sessions were closed normally; `list_sessions` returned no sessions and the agent exited with code 0.
- No reboot or flash was performed; no pending test commands remained. Nodes remained in CHAT with echo OFF.

Run bundle: runs/RUN_20260916T034442Z_ble-concurrent-help-completeness-take6/
