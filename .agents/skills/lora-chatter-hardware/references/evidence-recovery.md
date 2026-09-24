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
true branch divergence (ahead>0 and behind>0)
local-ahead commit modifying/deleting historical evidence
local-ahead commit outside canonical publication namespaces
tracked/staged residue
remote changes that touch or collide with the pending RUN/OBS paths
```

A strictly behind-only workspace is recoverable when ALL of the following are true:

- `ahead=0` and `behind>0`;
- the pending hardware evidence exists only as untracked canonical `runs/RUN_...` and optional `observations/OBS_...` paths;
- there are no staged or tracked modifications;
- inspection of `HEAD..origin/node_observations` shows no change to any pending RUN/OBS path and no rewrite/deletion of historical evidence;
- the remote commits are ordinary fast-forward additions such as executor-skill/policy maintenance or unrelated immutable evidence.

In that case, after a successful fetch, advance the local branch only with:

```bash
git merge --ff-only origin/node_observations
```

Request elevated permission for that exact Git operation if the sandbox requires it. Then re-check `git status --short`, confirm the pending evidence files are still the only untracked paths, and retry the guarded publication helper.

Do not use rebase, non-fast-forward merge, reset, checkout-overwrite, stash, clean, amend, force-push, or raw `git add/commit/push` as recovery.

If the remote diff touches a pending evidence path or any condition above is false, stop and report the boundary instead of attempting automatic recovery.

## Helper failures

Invalid invocation normally returns exit 2.

Guard/Git failures return non-zero with a concrete diagnostic such as RUN COMMIT FAILED or OBSERVATION COMMIT FAILED.

Report the exact diagnostic. Do not collapse it to a generic "publication failed".

If sandbox blocks Git metadata or network, do not stop at the first permission error. Request the minimum elevated permission for the exact standalone guarded helper or exact read-only Git/remote-verification command, then retry that operation. Typical recoverable environment failures include inability to create `.git/index.lock` or `.git/worktrees/.../index.lock`, read-only Git metadata, `Permission denied`/`Operation not permitted`, and sandboxed network access.

Git metadata access, guarded publication, and independent remote verification may be separate permission classes. Request narrowly scoped elevation for each required operation when encountered. Report `BLOCKED` only when elevation is unavailable/denied or the approved retry still cannot perform the required Git operation. Do not use any approval for unrelated shell/source writes, destructive Git operations, or to bypass the guarded helper with raw `git add/commit/push`.

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
