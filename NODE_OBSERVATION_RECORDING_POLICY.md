# Node Run / Observation Recording Policy

## Purpose

This is the canonical happy-path evidence policy for the hardware executor working from the serialterminal-observations clone.

The executor creates and interprets hardware evidence. Guarded publication helpers validate and publish already prepared artifacts; they never invent evidence.

Recovery from publication failures is intentionally not described in full here. If a guarded helper fails or branch state is unusual, read:

```text
.agents/skills/lora-chatter-hardware/references/evidence-recovery.md
```

## Role boundary

During a hardware task:

```text
serialterminal-observations                 writable only for canonical evidence
../serialterminal                          read-only runtime/source
firmware source checkout                   outside executor boundary; do not inspect
REVIEW_STATE.md                            read-only
```

The hardware executor never resolves or reads a firmware source checkout. Required implementation facts must be supplied through maintained executor references/task input or established from physical-node output. Missing implementation facts are an evidence boundary, not a reason to inspect source.

Do not modify source, tests, CI, TODOs, docs, skills or reviewer state. Do not fix a discovered bug inside the measured hardware task.

## Storage

The local evidence repository is an independent clone on branch:

```text
node_observations
```

It is the hardware executor working directory.

Committed observations and RUN bundles are append-only historical evidence. If a committed record is wrong, publish a new correction record/run; do not edit or delete the old one.

Tracked executor infrastructure such as AGENTS.md and .agents/ is maintained only by an explicit infrastructure/source-maintenance task, never by a hardware run.

## Canonical layout

```text
observations/
    OBS_YYYYMMDDTHHMMSSZ_<topic>.md

runs/
    RUN_YYYYMMDDTHHMMSSZ_<topic>/
        MANIFEST.json
        REPORT.md
        serialterminal.log
        serialterminal.console.log
```

Optional diagnostic files are governed by NODE_RUN_AUXILIARY_ARTIFACTS.md and are not part of ordinary runs.

REVIEW_STATE.md belongs to the reviewer and is never changed by the executor.

## Run identity

Use one UTC identity:

```text
<stamp>_<topic>

stamp = YYYYMMDDTHHMMSSZ in real UTC
topic = [a-z0-9][a-z0-9-]*
```

Do not append Z to local wall-clock time. Convert to UTC first.

Canonical shell timestamp:

```bash
date -u +%Y%m%dT%H%M%SZ
```

If an OBS belongs to a RUN, both basenames use the same stamp/topic.

## Artifact roles

serialterminal.log
: exact forensic log from the one SerialTerminal process used for the run. Copy it byte-for-byte; never reconstruct it.

serialterminal.console.log
: exact companion human-console log produced by the same process. It is presentation/audit evidence, not delivery proof.

REPORT.md
: complete curated executor report: task, known revisions, actual setup, actions, verdicts, anomalies/limitations, final state and evidence pointers.

OBS_*.md
: short factual reusable finding for reviewer/learning. It is not a second REPORT.

Do not dump chain-of-thought or the whole JSON transcript into REPORT/OBS.

## When OBS is required

Create an OBS for:

- FAIL or BLOCKED after hardware interaction;
- INCONCLUSIVE with a reusable reason;
- unexpected behavior or regression candidate;
- intentional fault injection;
- a new reusable hardware finding/scenario useful to later review.

A routine PASS may be RUN-only when it has no reusable finding beyond its report/logs. MANIFEST.json must then explicitly use observation.state = not-required with a short reason.

A small factual observation may be published without a RUN only when the task genuinely does not require a full run bundle.

## Observation format

A run-bound observation should contain:

```markdown
# Node observation

Observed: YYYY-MM-DDTHH:MM:SSZ
Task: <short task>
Result: PASS | FAIL | BLOCKED | INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@<exact SHA>
Firmware: dreamworkerln/lora-sack-protocol@<exact SHA or unknown>

Run bundle: runs/RUN_YYYYMMDDTHHMMSSZ_<topic>/

## Setup
...

## Actions
...

## Evidence
...

## Anomalies / conflicts
...

## Final state
...
```

Use exactly one canonical Run bundle line for a run-bound observation.

Do not guess firmware provenance. Detailed node provenance rules are in:

```text
.agents/skills/lora-chatter-hardware/references/provenance.md
```

## MANIFEST.json schema v1

```json
{
  "schema": 1,
  "observed_at": "YYYY-MM-DDTHH:MM:SSZ",
  "topic": "short-topic",
  "result": "PASS",
  "serialterminal": {
    "repo": "dreamworkerln/serialterminal",
    "sha": "<exact 40-hex SHA>"
  },
  "firmware": {
    "repo": "dreamworkerln/lora-sack-protocol",
    "sha": "<exact 40-hex SHA or unknown>"
  },
  "observation": {
    "state": "recorded",
    "path": "../../observations/OBS_YYYYMMDDTHHMMSSZ_short-topic.md"
  },
  "files": {
    "report": "REPORT.md",
    "console": "serialterminal.console.log",
    "serialterminal_log": "serialterminal.log"
  }
}
```

For a RUN without OBS:

```json
"observation": {
  "state": "not-required",
  "path": null,
  "reason": "<short explicit reason>"
}
```

Rules:

- observed_at and topic match the RUN basename;
- result is PASS, FAIL, BLOCKED or INCONCLUSIVE;
- SerialTerminal SHA is exact 40-hex;
- firmware.sha is exact 40-hex only when physical provenance establishes it, otherwise literal unknown;
- image/toolchain/full-file hashes never replace firmware.sha;
- files mapping names only the three canonical core files;
- recorded requires the matching OBS and reverse Run bundle pointer;
- not-required requires path null and a non-empty reason.

## Canonical RUN order

After measured interaction:

1. restore the required safe hardware state;
2. close sessions and terminate the SerialTerminal process so both logs are final;
3. create one UTC stamp/topic;
4. create runs/RUN_<stamp>_<topic>/ in this workspace;
5. write REPORT.md;
6. copy the exact forensic log as serialterminal.log;
7. copy the exact companion log as serialterminal.console.log;
8. decide whether OBS is required;
9. if required, create matching observations/OBS_<stamp>_<topic>.md;
10. write MANIFEST.json last;
11. invoke the guarded publication helper.

Do not stage hardware evidence in ../serialterminal.

## Guarded publication

From the serialterminal-observations workspace use the trusted sibling helper as a standalone command:

```bash
python3 -I ../serialterminal/scripts/commit-node-run
```

For an eligible standalone observation:

```bash
python3 -I ../serialterminal/scripts/commit-node-observation
```

Do not prepend/append commands with &&, ;, pipes, subshells or command substitution.

The helper uses exact-path staging and normal push only. It never force-pushes.

If sandbox protection prevents Git metadata/network access, request only the minimum approval needed for the exact standalone helper command.

If the helper returns non-zero, stop normal publication reasoning and read evidence-recovery.md. Do not bypass the helper with raw git add/commit/push.

## Independent remote verification

After helper success, verify the actual remote ref with one standalone command:

```bash
git ls-remote origin refs/heads/node_observations
```

Compare the returned SHA with the helper commit SHA.

Report:

```text
remote verification: verified
remote verification: mismatch
remote verification: not verified
```

Do not replace this with a local origin/node_observations check.

## Final response

After successful publication keep the chat result short:

```text
Result: PASS
Observation: observations/OBS_...   # when recorded
Run bundle: runs/RUN_.../
Commit: <SHA>
Remote verification: verified
```

The detailed narrative belongs in REPORT.md.
