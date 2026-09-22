---
name: lora-chatter-nodes
description: Redirect for source-development sessions; physical LoRa-Chatter execution now uses the sibling serialterminal-observations workspace.
---

# Physical hardware skill moved

Do not execute a physical hardware run from this source-development workspace.

The active hardware executor starts from:

```text
../serialterminal-observations
branch: node_observations
```

Its operating skill is:

```text
.agents/skills/lora-chatter-hardware/SKILL.md
```

This dev workspace remains the source/runtime/API authority. AGENT_API.md and the
generic serialterminal-agent skill continue to describe the implemented machine
interface.

When a source change alters hardware operating semantics, review the sibling
hardware skill in a separate explicit executor-infrastructure maintenance task.
