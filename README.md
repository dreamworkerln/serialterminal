# Node observations and hardware executor workspace

This orphan branch stores immutable LoRa-Chatter hardware evidence and the lightweight operating context for the dedicated hardware executor.

Local layout:

```text
coding/python/
├── serialterminal/               branch dev
│   └── SerialTerminal runtime/source; hardware executor treats it read-only
└── serialterminal-observations/  branch node_observations
    ├── AGENTS.md
    ├── .agents/skills/
    ├── observations/
    └── runs/
```

Start the hardware Codex session with serialterminal-observations as its working directory. The source-development Codex session continues to start from serialterminal/.

Executor rules:

- append new evidence only under observations/ and runs/;
- do not merge node_observations into dev;
- do not modify REVIEW_STATE.md during a hardware task;
- hardware operating guidance lives in .agents/skills/lora-chatter-hardware/;
- canonical evidence policy lives in NODE_OBSERVATION_RECORDING_POLICY.md;
- optional diagnostic capture rules live in NODE_RUN_AUXILIARY_ARTIFACTS.md;
- full generic SerialTerminal API remains authoritative in ../serialterminal/AGENT_API.md and is read only when the hardware skill says it is needed;
- reviewer/promotion rules remain on dev in NODE_SKILL_LEARNING_POLICY.md.

Historical observations and RUN bundles remain append-only.
