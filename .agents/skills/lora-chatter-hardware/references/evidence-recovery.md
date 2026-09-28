# Evidence publication recovery

Read this only after a publication/storage/Git failure or when the observation workspace is already in an unusual state.

Normal publication rules are in ../../../../NODE_OBSERVATION_RECORDING_POLICY.md.

## Core rule

The hardware executor publishes directly from the current serialterminal-observations workspace.

Direct Git is allowed only for append-only canonical evidence under:

```text
runs/RUN_<UTC>_<topic>/
observations/OBS_<UTC>_<topic>.md
```

Do not repair or rewrite historical RUN/OBS evidence.

Do not modify REVIEW_STATE.md, executor skills/policies or source during a hardware run.

Never use:

```text
force-push
rebase
reset
amend
checkout-overwrite
stash
clean
history rewrite
```

Do not use sibling publication scripts as recovery:

```text
../serialterminal/scripts/commit-node-run
../serialterminal/scripts/commit-node-observation
../serialterminal/scripts/node-publication-common.py
```

## First inspection

Preserve the exact failing Git diagnostic, then inspect:

```bash
git branch --show-current
git status --short
git rev-parse HEAD
git fetch origin node_observations
git rev-list --left-right --count origin/node_observations...HEAD
```

The branch must be `node_observations`.

Classify the state before changing anything.

## Pending untracked evidence

The workspace may legitimately contain:

- one complete pending RUN bundle;
- its matching run-bound OBS;
- one eligible standalone OBS;
- an incomplete RUN from an interrupted executor.

Expected untracked canonical evidence is not itself an error.

Unexpected untracked paths outside the intended current RUN/OBS are a publication boundary. Do not delete them automatically.

Before staging, confirm the pending bundle identity and exact files. For a canonical RUN, verify:

```text
RUN_<UTC>_<topic>/
    MANIFEST.json
    REPORT.md
    serialterminal.log
    serialterminal.console.log
optional matching OBS_<UTC>_<topic>.md
```

and verify MANIFEST/OBS identity rules from the recording policy.

## Behind-only workspace before commit

A strictly behind-only workspace is recoverable when all of the following are true:

- local `ahead=0`;
- remote `behind>0`;
- there are no staged or tracked modifications;
- pending evidence exists only as intended untracked canonical RUN/OBS paths;
- `HEAD..origin/node_observations` does not add the same pending paths or rewrite/delete historical evidence.

Then advance only with:

```bash
git merge --ff-only origin/node_observations
```

Re-check `git status --short` and the branch counts before staging.

If remote changes collide with the pending RUN/OBS path, stop and report the boundary.

## Behind-only workspace after intended evidence was already staged

A failed publication attempt may leave the intended current RUN/OBS already staged when
`origin/node_observations` advances independently.

This state is recoverable only when all of the following are true:

- local `ahead=0` and remote `behind>0`;
- every staged entry is status `A`;
- every staged path belongs only to the one intended current RUN bundle and optional
  matching OBS;
- there are no unrelated staged, tracked-modified or unexpected untracked paths;
- `HEAD..origin/node_observations` does not add the same pending RUN/OBS paths and
  does not rewrite/delete historical evidence.

First preserve the staged-path diagnostic:

```bash
git diff --cached --name-status
```

Then remove **only those exact intended evidence paths from the index**, preserving
their worktree bytes:

```bash
git restore --staged -- runs/RUN_<stamp>_<topic>/ observations/OBS_<stamp>_<topic>.md
```

Omit the OBS path when none exists. Re-check that the evidence is now merely untracked
and no unrelated state changed:

```bash
git status --short
```

Advance only by fast-forward:

```bash
git merge --ff-only origin/node_observations
```

Then re-run the canonical bundle/manifest identity checks, stage the same exact paths
again, and use the scoped whitespace gate below.

Do not use this recovery for staged modifications/deletions, unrelated staged content,
local commits, divergence, or a remote collision with the pending evidence path.

## Staging recovery

Normal staging is exact-path only:

```bash
git add -- runs/RUN_<stamp>_<topic>/ observations/OBS_<stamp>_<topic>.md
```

or for a standalone observation:

```bash
git add -- observations/OBS_<stamp>_<topic>.md
```

After staging:

```bash
git diff --cached --name-status
git diff --cached --check -- . \
  ':(exclude)runs/**/serialterminal.log' \
  ':(exclude)runs/**/serialterminal.console.log'
git status --short
```

The exact copied `serialterminal.log` and `serialterminal.console.log` are excluded
from whitespace/style validation because their bytes are evidence. Do not remove
trailing whitespace, normalize line endings or otherwise change those logs to make an
unscoped `git diff --cached --check` pass.

If an unscoped whitespace check was run first and reported only those exact log paths,
preserve the diagnostic, run the scoped command above, and continue publication when
all other gates pass. If the scoped check reports any editable artifact, fix that
artifact only when doing so preserves its required semantics; do not waive the error.

Every staged entry must be `A` and must belong only to the intended current evidence.

If unrelated content is already staged, do not silently unstage or overwrite another actor's state. Stop and report it.

## Commit failure

If `git commit` fails because Git metadata is sandbox-protected, request the minimum elevation for that exact commit operation and retry it.

If it fails for identity/config/hook/content reasons, preserve the exact diagnostic. Do not bypass hooks or change global Git configuration unless the operator explicitly starts a maintenance task.

After a successful commit, record the exact local SHA:

```bash
git rev-parse HEAD
```

## Push failure

If `git push origin HEAD:node_observations` fails, preserve the local commit and exact diagnostic.

Fetch and classify:

```bash
git fetch origin node_observations
git rev-list --left-right --count origin/node_observations...HEAD
```

If remote is not ahead and local is only ahead by the append-only publication commit(s), retry the normal push.

If both sides are ahead, the branch diverged after the local commit. Stop. Do not rebase, merge, reset, amend or force-push during the hardware task.

The local commit remains valid local evidence and can be reconciled later in an explicit maintenance step.

## Local-ahead state discovered at startup

If a previous hardware run already created local commit(s) that are not on origin:

1. inspect each local-ahead commit with `git show --name-status --format=fuller <sha>`;
2. require only append-only `A` entries under canonical RUN/OBS paths;
3. require no historical modification/deletion and no executor/source changes;
4. require remote not to be ahead/divergent.

If all conditions hold, a normal push is allowed.

Otherwise stop and report the branch state.

## Sandbox / permission recovery

Sandbox failure is not a hardware FAIL.

For a required Git operation blocked by `Permission denied`, `Operation not permitted`, inability to create `.git/index.lock`, protected Git metadata or blocked network access:

1. request the minimum elevation for the exact Git operation;
2. retry the same operation;
3. re-check repository state afterward.

Git metadata, fetch/push and remote verification may be separate permission classes.

Report `BLOCKED` only when elevation is unavailable/denied or the approved retry still cannot perform the required operation.

## Remote verification

After successful push, verify independently:

```bash
git ls-remote origin refs/heads/node_observations
git rev-parse HEAD
```

The SHAs must match exactly.

Report:

```text
remote verification: verified
remote verification: mismatch
remote verification: not verified
```

Do not replace the independent remote read with a local `origin/node_observations` ref.

## Storage/config failure

If the hardware executor is not actually running from the independent serialterminal-observations clone on `node_observations`, do not improvise a new clone/worktree or rewrite sandbox config during the measured hardware task.

Report the storage/config boundary.

Executor infrastructure changes belong to a separate maintenance task.
