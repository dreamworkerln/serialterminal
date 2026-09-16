# BLE burst RX completeness diagnostic with HCI correlation

Result: INCONCLUSIVE

Task: repeat the BLE burst RX diagnostic with an operator-owned HCI capture, then correlate HCI ATT notifications with SerialTerminal raw events.

Observed at: 2026-09-16T00:37:07Z
SerialTerminal exact SHA: 4f562062afd64750679a4d5562a29a022025a967
Firmware: unknown

## Hardware and sessions

- LoRa-Chatter-1B44 — `s1` — BLE `44:1B:F6:8D:B7:A9` — profile `chatter` — HCI handle `3585`.
- LoRa-Chatter-72E0 — `s2` — BLE `E0:72:A1:D5:4C:15` — profile `chatter` — HCI handle `3586`.
- Both sessions reached `connected`; the only `reconnecting` states were during initial open.
- No disconnect/reconnect occurred during the affected diagnostic intervals. The two HCI disconnects were the final normal session closes.

## Diagnostic phases

- Phase A isolated `/help`: both nodes produced complete late help markers. `s1` produced 33 chat lines and `s2` 34 chat lines.
- Phase B concurrent `/help`: 5 iterations. `s1` produced malformed/incomplete help output in all five iterations (23, 23, 24, 23, and 23 chat lines); `s2` produced the 34-line shape in all five.
- Phase C back-to-back `/help` + `/id`: 5 iterations on both sessions. `s1` showed malformed/interleaved help and identity output in every iteration; `s2` also varied from the isolated help shape and showed interleaving in the matrix.

Representative SerialTerminal raw evidence is `s1` chat seq 158–162, HCI handle 3585 packets 1659–1663 at btmon times 69.367337–69.411319. The completed logical line included:

```text
[SYS]   /cancel all stop current USER an[SYS]   HEX macro, n...
```

The corresponding HCI notification payloads contain the same truncated boundary. Another affected burst boundary is `s1` seq 544–545, HCI packets 2545–2546 at 119.314343–119.358363, where the logical output included `14 31=CHAT  l /reboot`.

## HCI correlation

The operator-provided captures were preserved unchanged under `artifacts/`.

Exact ordered payload comparison between HCI `ATT: Handle Value Notification` data and SerialTerminal `[RX ...]` event `data_b64` found equality for every captured stream:

| Node/session | HCI stream handle | Notifications | Bytes | Exact ordered match |
|---|---:|---:|---:|---|
| `s1` chat | `0x002a` / HCI 3585 | 819 | 13,878 | yes |
| `s2` chat | `0x002a` / HCI 3586 | 1,021 | 17,178 | yes |
| `s1` telemetry | `0x002d` / HCI 3585 | 54 | 976 | yes |
| `s2` telemetry | `0x002d` / HCI 3586 | 54 | 968 | yes |

The HCI capture therefore shows no byte loss or reordering between the recorded HCI notification stream and SerialTerminal raw session events for this run. SerialTerminal recorded no `forensic_gap`. The malformed burst content was already present in the HCI notification payload sequence; this run does not establish whether the deeper cause is peripheral/firmware generation, the BLE link before HCI delivery, or another boundary below the host callback.

## Final state and evidence

Both nodes were returned to `CHAT`; final status was `connected` with `queued_tx=0`. Both sessions were closed normally and the SerialTerminal agent exited with return code 0. No reboot, flash, btmon start, btmon stop, sudo, or capture management was performed by this executor.

Run-relative auxiliary captures:

- `artifacts/ble-burst-rx-hci-take3.btsnoop`
- `artifacts/ble-burst-rx-hci-take3.btmon.log`

The exact SerialTerminal forensic and console logs are the canonical files in this bundle.
