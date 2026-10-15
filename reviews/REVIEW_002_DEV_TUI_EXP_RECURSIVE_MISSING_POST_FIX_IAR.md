# dev_tui_exp_recursive_missing post-fix independent review

REVIEW-ID: REVIEW_002
Status: COMPLETE
Verdict: RED
Date UTC: 2026-10-15
Reviewer: ChatGPT / independent

## Reviewed state

Repository: https://github.com/dreamworkerln/serialterminal
Branch: `dev_tui_exp_recursive_missing`
Reviewed commit: [6fdeb00c220b3e27219fb6b5bb34f078f3bb717a](https://github.com/dreamworkerln/serialterminal/commit/6fdeb00c220b3e27219fb6b5bb34f078f3bb717a)
Base commit: [db740af94c700c7c4e6d96abef7e809dadfcaf1c](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c)
Base selection: exact target of previous numbered review [REVIEW_001](REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md), used for fix attribution and re-review. The verdict also covers the complete current software snapshot in the stated scope rather than only regressions introduced by `BASE..TARGET`.
Range: `db740af94c700c7c4e6d96abef7e809dadfcaf1c..6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`
Checkout: clean at review start. Reviewer-created files under `reviews/evidence/REVIEW_002/`, this report and the inventory update were added only after the target had been fixed; production source/TODO content was not modified by the review.
Previous review: [REVIEW_001](REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md) — `COMPLETE / RED`
Task / TODO / spec: `AGENTS.md`, `REVIEWER.md`, `REVIEW_MANAGEMENT_POLICY.md`, `FT1_RESUME.md`, `FILE_TRANSFER.md`, `AGENT_API.md`, `README.md`; fix attribution also references `TODO_041`, `TODO_043`, `TODO_044`, `TODO_045`, `TODO_046`, `TODO_047`.

## Scope

Independent engineering audit of the current `dev_tui_exp_recursive_missing` software snapshot. The pass covered the full production-source delta against the previous numbered review target and then re-evaluated the current composed behavior, with emphasis on:

- FT1 durable RX/TX ownership, publication, retention, restart and same-process resume;
- recursive ROOT/child lifecycle, MISSING repair, depth/progress/boundary behavior and bounded state;
- peer-scoped sender journals and transfer identity;
- machine negotiation/recovery, remote-failure interruption and RX worker failure paths;
- centralized defaults/profile-aware baud selection and session/device identity wiring;
- timing append/segment identity and concurrent writers;
- cancellation, cleanup, timeout, rollback and error paths rather than success-only execution.

The exact `BASE..TARGET` production delta is 25 source files, 1127 insertions and 233 deletions; the combined source+tests diff is recorded in `reviews/evidence/REVIEW_002/diff-gate.txt`. Deletions and changed state/failure/retry/ownership paths were inspected semantically; prior findings were not considered fixed merely because a named regression test existed.

A repository-wide pytest result is unavailable in this runtime because the installed Python environment lacks `pyserial`. That prevents a complete GREEN software gate, but it does not make this review inconclusive: two deterministic current-target defects independently require RED. No physical serial/BLE device run, hardware fault injection, release acceptance or CI was requested or performed by this review.

## Findings

### F001 — BLOCKER: non-POSIX FT1 requires `fcntl`, so the documented Windows/best-effort transfer path cannot claim durable ownership

Where: `src/serialterminal/file_transfer/resume_store.py`, `ResumeStateStore.namespace_lock()` lines 63–86, `claim()` lines 97–115 and `_protected()` lines 131–146; mandatory ownership callers include `manager.py` lines 161 and 212, `recursive.py` lines 103 and 276, and `resumable.py` line 601.

Verified behavior: the durable store imports `fcntl` unconditionally inside namespace/lease operations. A real `FileTransferManager.start_send()` must call the outgoing durable `claim()` path before transfer admission. When `fcntl` is unavailable, that mandatory claim raises `ModuleNotFoundError` before the transfer can start. The same lease mechanism is used by incoming and recursive transfers. Store cleanup also enters the same namespace-lock mechanism when retained durable state must be handled.

Failure scenario: run SerialTerminal on a platform without the POSIX `fcntl` module; construct a normal FT1 manager; call `start_send()` for an ordinary source file. The first durable ownership claim imports `fcntl` and raises `ModuleNotFoundError`. Equivalent RX/recursive admissions reach the same ownership layer. If durable state is already present, cleanup can reach the same unavailable locking primitive even before new transfer work.

Impact: this is not merely loss of the stronger cross-process no-overwrite guarantee. Basic single-process FT1 admission is coupled to a POSIX-only primitive, so the documented non-POSIX/Windows file-transfer path is fundamentally unavailable. `README.md` lines 181–186 and `AGENT_API.md` lines 419–422 explicitly describe the receive directory on Linux/Windows, while `FT1_RESUME.md` lines 271–274 explicitly retains a non-POSIX best-effort durability fallback rather than declaring FT1 unsupported. `AGENT_API.md` lines 627–631 scopes POSIX specifically to concurrent final-publication coordination. The current implementation is stricter than those contracts.

Evidence / repro: `reviews/evidence/REVIEW_002/repro_non_posix_fcntl.py` installs an import hook that makes only `fcntl` unavailable, constructs a real `FileTransferManager`, and calls `start_send()`. At the reviewed target the captured output is `ModuleNotFoundError No module named 'fcntl'` in `reviews/evidence/REVIEW_002/repro_non_posix_fcntl.out`. The contrast is also visible in `src/serialterminal/timing.py` lines 13–16 and 75–80, where the same repository intentionally supports `fcntl is None` with a single-writer fallback.

Test gap: FT1 ownership/publication tests exercise POSIX locking and multi-process behavior, but there is no acceptance test that runs the FT1 TX/RX/cleanup contract with `fcntl` unavailable. Timing has an explicit non-`fcntl` fallback; FT1 does not.

Confidence / limitations: deterministic source-level and manager-level reproduction. The repro simulates absence of `fcntl` on the Linux review host rather than executing on a physical Windows host; the defect is the unconditional import and therefore does not depend on hardware or radio behavior.

Required acceptance: explicitly handle absence of `fcntl`. Preserve documented basic single-process FT1 and non-POSIX best-effort durable behavior, while either scoping cross-process namespace/lease guarantees to POSIX or implementing an equivalent Windows locking backend. Add deterministic no-`fcntl` regression coverage for at least outgoing admission, incoming admission and cleanup of retained state. A platform without `fcntl` must receive a supported single-process transfer path or an intentionally revised/documented unsupported-platform contract; it must not fail by an internal import exception.

Follow-up TODO: not yet assigned.

### F002 — HIGH: same-process timeout resume exposes terminal state before ownership release, so identical META can be rejected as terminal `invalid_metadata`

Where: `src/serialterminal/file_transfer/core.py`, `_terminal_record()` lines 728–744 and `_terminal_record_settled()` lines 751–779; `src/serialterminal/file_transfer/manager.py`, `_handle_meta()` lines 353–378, `_can_revive_timed_out_receiver()` lines 380–399 and `_expire_stale_incoming()` lines 401–428; `src/serialterminal/file_transfer/resumable.py`, `_handle_meta()` lines 517–557; sender terminal classification in `manager.py` lines 325–345.

Verified behavior: receiver idle timeout checkpoints the durable incoming state as suspended and asynchronously schedules terminal settlement. During `_terminal_record_settled()`, `record.terminal(...)` at line 768 makes `state="failed"` externally observable before `_release(...)` at line 770 and before `_active_id` is cleared at lines 772–774. A matching META arriving in this window sees the exact failed record, but `_can_revive_timed_out_receiver()` refuses revive while `_active_id` is still non-`None`. Control then falls through to `resumable._handle_meta()`, where the same failed record is treated as a conflicting identity and rejected with terminal code `invalid_metadata`. The sender classifies remote `invalid_metadata` as a terminal identity failure and durably marks the outgoing journal terminal.

Failure scenario: receiver has accepted META and at least one DATA chunk; its idle timeout fires; terminal state becomes visible; durable lease release is temporarily still in progress; the same sender immediately replays the same valid META for the same transfer ID. Instead of reopening retained state, the receiver emits negative RESULT `invalid_metadata: conflicting META for existing transfer_id`. The sender can then terminalize the old identity even though the only cause was the receiver's settlement interleaving.

Impact: the explicit same-process recovery contract can fail under an ordinary timeout/replay race. `FT1_RESUME.md` lines 192–193 says a matching META can reopen retained durable state after receiver-side same-process timeout, and lines 512–517 require same-transfer recovery. Here the receiver can instead convert a valid resume attempt into a terminal identity error, defeating same-ID recovery and forcing a fresh identity on a later explicit start.

Evidence / repro: `reviews/evidence/REVIEW_002/repro_terminal_release_race.py` blocks `_release()` exactly after terminal publication and before ownership clear, then feeds the identical META. Reviewed-target output in `repro_terminal_release_race.out` is:

```text
failed_code remote_sender_timeout
release_entered True active_id 20817
results [(False, 'invalid_metadata', 'conflicting META for existing transfer_id')]
final_state failed active_id None
```

A stock broad FT1 run also observed `tests/test_file_transfer_same_process_resume.py::test_timed_out_receiver_reopens_same_transfer_in_same_process` fail once in the same area; an isolated rerun passed, consistent with the timing-dependent mechanism. The deterministic synchronized repro is the authoritative evidence. Base attribution using the archived `db740af...` target is preserved in `repro_terminal_release_race_base.py/.out`: the terminal-before-release window already existed there and produced `protocol_error`; the current terminal `invalid_metadata` classification makes the race more destructive to sender identity. This finding therefore describes a current snapshot defect, not a claim that the ownership-ordering race was newly introduced by the reviewed delta.

Test gap: existing same-process resume coverage does not synchronize the interleaving between `record.terminal()` and lease/`_active_id` release. A non-deterministic test can pass or fail depending on outbox scheduling.

Confidence / limitations: deterministic at the state-machine boundary with the production manager/store paths; no serial device or firmware dependency. The exact real-world frequency depends on scheduling and replay timing, but reachability does not.

Required acceptance: make terminal observability and ownership/admission state coherent. A matching timeout META arriving during terminal settlement must either be deferred until release completes or be recognized as the same resumable transfer; it must never receive terminal `invalid_metadata` solely because release is still in flight. Add a synchronized regression that holds the terminal→release boundary, replays identical META, releases the gate, and proves that the same transfer ID reopens retained chunks/resume cursor without terminalizing the sender journal.

Follow-up TODO: [`TODO_041`](../todos/TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md) — its stage-4 same-ID revive/resume scope and still-open idle-timeout + matching-META gate cover this behavior.

## Previous findings recheck

All 18 findings from [REVIEW_001](REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md) were rechecked against the exact current target rather than inferred from commit messages. The selected acceptance/repro nodes produced `47 passed, 4 warnings in 4.88s`; detailed output is `reviews/evidence/REVIEW_002/previous-findings-recheck.txt`.

| Previous finding | Re-review result | Current evidence / reason |
| --- | --- | --- |
| REVIEW_001/F001 | FIXED | `test_rx_restore_post_checkpoint_failure_rolls_back_durable_and_runtime` plus source inspection of rollback-before-release semantics. |
| REVIEW_001/F002 | FIXED | `test_terminal_peer_identity_failure_allocates_fresh_id_on_explicit_retry`; terminal remote identity codes persist terminal sender journal state. |
| REVIEW_001/F003 | FIXED | `test_valid_root_end_is_deferred_before_child_result_arrives`; deferred END is replayed only after child settlement. |
| REVIEW_001/F004 | FIXED | `test_child_identity_collision_preserves_existing_context`; child/root identity collision is rejected before accepted frame mutation. |
| REVIEW_001/F005 | FIXED | `test_forty_sequential_root_settlements_leave_no_orphan_frames`; settled ROOT frames are retired. |
| REVIEW_001/F006 | FIXED | `test_live_root_replay_history_stays_one_entry_after_five_thousand_children`; processed-child replay history remains bounded. |
| REVIEW_001/F007 | FIXED | `test_rejected_root_meta_does_not_replace_live_frame`; rejected conflicting ROOT META is side-effect free for live recursive state. |
| REVIEW_001/F008 | FIXED | `test_parent_idle_clock_excludes_child_duration`; recursive child service no longer consumes the parent idle budget incorrectly. |
| REVIEW_001/F009 | FIXED | `test_failed_foreground_negotiation_releases_negotiating_state`; failed foreground machine negotiation publishes a recoverable failure state. |
| REVIEW_001/F010 | FIXED | `test_two_processes_publish_same_basename_without_overwrite_or_dual_path`; POSIX publication uses namespace coordination/reservation and exclusive publication. |
| REVIEW_001/F011 | FIXED | `test_concurrent_open_closes_all_workers_of_unadmitted_file_manager`; duplicate-open loser closes unadmitted manager/workers. |
| REVIEW_001/F012 | FIXED | `test_second_manager_cleanup_preserves_live_pre_manifest_part`; live pre-manifest partial is protected by durable ownership. |
| REVIEW_001/F013 | FIXED | `test_invalid_cancel_id_is_normalized_without_descendant_side_effects`; malformed cancel identity is normalized to the public error contract. |
| REVIEW_001/F014 | FIXED | `test_reopened_store_handles_bad_timestamp_without_deleting_recent_journal`; malformed durable timestamp falls back safely instead of destroying retained state. |
| REVIEW_001/F015 | FIXED | `test_counts_bounded_without_reconstructing_store`; count/TTL/part-byte limits are enforced during live operation, not only constructor cleanup. |
| REVIEW_001/F016 | FIXED | `test_raw_invalid_meta_rejected_before_any_resource_admission`; chunk count outside uint32 wire space is rejected before admission/resource creation. |
| REVIEW_001/F017 | FIXED | `test_two_peers_same_source_and_id_never_change_each_others_journal`; outgoing journals and leases are peer-scoped. |
| REVIEW_001/F018 | FIXED | timing reopen/concurrent/two-process tests; segment UUID + per-segment sequence prevents duplicate timing identity across appended sessions. |

The FIXED statuses above are scoped to the prior findings themselves. They do not override new `REVIEW_002/F001` or `REVIEW_002/F002`.

## Validation and evidence

| Check / command | Exact checkpoint | Result | Evidence type / pointer / limitations |
| --- | --- | --- | --- |
| Branch/target/base/worktree capture | target `6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`, base `db740af94c700c7c4e6d96abef7e809dadfcaf1c` | PASS | Executed; `reviews/evidence/REVIEW_002/target.txt`. Checkout was clean before reviewer evidence files were created. |
| `BASE..TARGET` stat/numstat/deletion-oriented semantic source review | same range | PASS | Executed/source inspection; `reviews/evidence/REVIEW_002/diff-gate.txt`; 25 production files, 1127+/233-. State/failure/recovery/concurrency paths inspected rather than accepting tests alone. |
| `git diff --check BASE..TARGET` | same range | PASS | Executed during diff gate; no whitespace error affecting reviewed patch. |
| `python -m compileall -q src serialterminal.py tools` | target | PASS | Executed; `reviews/evidence/REVIEW_002/compileall.txt`. Syntax/import compilation only. |
| Repository-wide `PYTHONPATH=src python -m pytest -q` | target | BLOCKED | Executed; collection stops with 15 `ModuleNotFoundError: No module named 'serial'`; `reviews/evidence/REVIEW_002/full-pytest-blocked.txt`. No network installation was available in the review runtime. |
| REVIEW_001 acceptance/regression recheck | target | PASS | Executed; 47 passed, 4 multiprocessing fork deprecation warnings; `previous-findings-recheck.txt`. |
| Recursive/machine/recovery targeted suite | target | PASS | Executed; 92 passed in 11.10 s; `recursive-machine-targeted.txt`. |
| Settings/profile wiring with minimal import-only fake `serial` | target | PASS | Executed; 33 passed; `settings-profile-stub.txt`. This proves settings/profile wiring only and explicitly does **not** validate real serial I/O. |
| Combined broad FT1 attempt | target | NOT RUN | The combined run was interrupted before completion; partial console provenance is retained in `ft1-broad-targeted.txt` and is explicitly **not** counted as evidence of PASS or FAIL. Deterministic F002 evidence is the synchronized repro below. |
| Deterministic no-`fcntl` manager repro | target | FAIL | Executed defect repro; `repro_non_posix_fcntl.py/.out` → `ModuleNotFoundError No module named 'fcntl'`. Confirms F001. |
| Deterministic terminal→release resume race repro | target | FAIL | Executed defect repro; `repro_terminal_release_race.py/.out` → matching META rejected as terminal `invalid_metadata`. Confirms F002. |
| Same terminal→release synchronized repro at REVIEW_001 target | base `db740af...` | FAIL | Executed attribution repro; `repro_terminal_release_race_base.py/.out` → same window returned `protocol_error`. Shows ordering race predates current range while current classification worsens sender identity handling. |
| Static `ruff` / `lizard` | target | BLOCKED | Tools are not installed in this runtime; no result claimed. |
| Physical serial/BLE/USB/RF and power-loss validation | target | NOT RUN | Outside requested software review; no hardware evidence inferred from automated tests. |
| CI | target | NOT RUN | User requested IAR + review commit/GDI publish, not CI. |

## Assessment

The post-fix work materially improves the branch: every finding from `REVIEW_001` has direct current-target acceptance evidence, and targeted recursive/machine/settings/timing behavior reviewed in this pass is consistent with its intended contracts. The review did not find a new material issue in the centralized defaults/profile baud wiring, recursive depth/progress accounting, peer-scoped journals, chunk-space admission or timing segment identity beyond the findings recorded above.

Acceptance of the current software snapshot is nevertheless blocked by two independent defects. `F001` is a platform-contract break: mandatory FT1 ownership now unconditionally requires a POSIX-only locking module even though the repository still documents Windows/non-POSIX best-effort operation. `F002` is a state-machine ordering defect: a reachable timeout/replay interleaving makes valid same-ID recovery look like a terminal metadata identity conflict. Either defect is sufficient to reject the relevant software contract; together they make RED conclusive despite the repository-wide pytest environment being incomplete.

No claim is made that the branch fails every platform or ordinary transfer, and no physical hardware conclusion is drawn. POSIX FT1 regression coverage is broad and the 18 previous review findings are considered fixed at this exact target. A new numbered re-review is required after the two current findings are addressed; the old `REVIEW_001` and this RED result should remain immutable history.

## Result

Status: COMPLETE
Verdict: RED
Verdict scope: current `dev_tui_exp_recursive_missing` software snapshot, focused on FT1/recovery/recursive/persistence/agent-session contracts at `6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`
Remaining gates: `REVIEW_002/F001`; `REVIEW_002/F002`; repository-wide pytest once a real `pyserial` dependency is available; physical serial/BLE/recovery/power-loss evidence as required by the relevant TODO/release gates; CI/release gates were not requested in this pass.
Follow-up: fix/link `REVIEW_002/F001`; complete the existing `TODO_041` same-process idle-timeout matching-META gate for `REVIEW_002/F002`; then create a new numbered re-review (`REVIEW_003` or the next free ID) against the exact fix target.
