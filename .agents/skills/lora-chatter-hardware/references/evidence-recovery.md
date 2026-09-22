# Evidence publication recovery

Read this only after a publication/storage/Git helper failure or when the observation workspace is already in an unusual state.

Normal publication rules are in ../../../../NODE_OBSERVATION_RECORDING_POLICY.md.

## Core rule

Do not bypass guarded publication with raw git add/commit/push, merge, rebase, reset, amend or force-push.

Do not repair or rewrite historical RUN/OBS evidence.

Do not modify REVIEW_STATE.md.

## Pending backlog

The observation clone may legitimately contain:

- pending standalone observations;
- complete pending RUN bundles;
- incomplete RUN from an interrupted executor;
- run-bound OBS whose RUN is not complete.

A complete unrelated run may be publishable while an incomplete canonical run remains pending.

Do not delete stale/incomplete evidence-like paths automatically. Removal is a separate explicit maintenance task.

Unexpected untracked paths outside the allowed observation/run namespaces are a hard publication boundary.

## Push failure

A guarded helper can create a local commit and then fail to push.

Preserve the local commit and exact diagnostic.

The helper's safe retry logic may repush validated local-ahead append-only publication commits when remote is not ahead and history is not divergent.

Hard boundaries include:

```text
remote ahead with unpublished local work
branch divergence
local-ahead commit modifying/deleting historical evidence
local-ahead commit outside canonical publication namespaces
tracked/staged residue
```

Do not solve these with destructive Git operations inside a hardware task.

## Helper failures

Invalid invocation normally returns exit 2.

Guard/Git failures return non-zero with a concrete diagnostic such as RUN COMMIT FAILED or OBSERVATION COMMIT FAILED.

Report the exact diagnostic. Do not collapse it to a generic "publication failed".

If sandbox blocks Git metadata or network, request the minimum permission for the exact standalone guarded helper or read-only remote verification command. Do not use that approval for unrelated shell/source writes.

## Remote verification

After helper exit 0, verify remote independently:

```bash
git ls-remote origin refs/heads/node_observations
```

If the remote SHA matches the helper commit, verification is verified.

If it differs, report mismatch.

If network/permission prevents the independent read after a minimal retry/approval attempt, report not verified. Do not reinterpret a local origin ref as independent remote verification.

## Storage/config failure

If the hardware executor is not actually running from the independent serialterminal-observations clone on node_observations, do not improvise a new clone/worktree or rewrite sandbox config during the measured hardware task. Report the storage/config boundary.

Executor infrastructure changes belong to a separate maintenance task.
