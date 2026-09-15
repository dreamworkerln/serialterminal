# TODO_020 — Make scanner recovery workflow executable from agent documentation

Status: OPEN

## Purpose

Turn the documented "use the Bluetooth capability scanner/prober" recovery advice into an exact non-interactive workflow that an autonomous agent can execute without guessing CLI syntax or entering a TUI prompt.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`AGENT_API.md` and `.agents/skills/serialterminal-agent/SKILL.md` tell machine users to run the Bluetooth capability scanner/prober when an expected BLE target is absent, then repeat discovery. They do not show the concrete non-interactive command.

The CLI already supports:

```text
python3 serialterminal.py scan ble|spp|all
--scan-seconds
--probe-timeout
--no-rfcomm-test
```

If scanner mode is omitted, the scanner path can become interactive. That distinction matters for agents using SerialTerminal as a tool.

The README's short agent summary also mentions `tx_state=written` but does not surface the newer high-impact `tx_state=unknown` and `forensic_gap` semantics that are already canonical in `AGENT_API.md` and the generic skill.

## Target behavior

- Generic agent skill gives an exact non-interactive scanner/prober command and a minimal `scan -> discover -> open returned device_key` recovery flow.
- Document when `ble`, `spp` or `all` is appropriate and how UNKNOWN differs from definitive NO.
- Avoid sending an autonomous machine client into the interactive scanner menu unless explicitly desired.
- README agent overview points readers to, or briefly flags, `tx_state=unknown` and `forensic_gap` without duplicating the full API contract.
- `AGENT_API.md` remains the source of truth for machine schema/semantics.

## Validation

- [ ] documented commands match current argparse entry points/options;
- [ ] generic skill contains enough procedure for a fresh agent to recover an absent BLE target;
- [ ] README/API/skill terminology agrees;
- [ ] no controller-specific discovery whitelist is introduced;
- [ ] documentation review PASS.