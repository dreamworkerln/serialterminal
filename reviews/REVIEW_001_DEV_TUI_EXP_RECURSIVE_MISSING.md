# dev_tui_exp_recursive_missing independent review

REVIEW-ID: REVIEW_001
Status: COMPLETE
Verdict: RED
Date UTC: 2026-10-13
Reviewer: ChatGPT / independent

## Reviewed state

Repository: https://github.com/dreamworkerln/serialterminal
Branch: `dev_tui_exp_recursive_missing`
Reviewed commit: [db740af94c700c7c4e6d96abef7e809dadfcaf1c](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c)
Base commit: [8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79](https://github.com/dreamworkerln/serialterminal/commit/8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79)
Base selection: previous published checkpoint. The `8cf689e..db740af` delta only adds/changes review/TODO/documentation material; the `src` and `tests` tree object IDs are identical at base and target. Runtime findings therefore describe the complete current software snapshot, not regressions introduced by the review-documentation delta.
Range: `8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79..db740af94c700c7c4e6d96abef7e809dadfcaf1c` plus current-snapshot source review
Checkout: clean at review start; review output later modified only `REVIEW_INVENTORY.md` and this report
Previous review: none in the numbered review registry. Historical review evidence/leads are retained in `todos/TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md` and were not treated as authoritative.
Task / TODO / spec: `todos/TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md`, `FT1_RESUME.md`, `AGENT_API.md`, `ARCHITECTURE.md`, `REVIEWER.md`, `REVIEW_MANAGEMENT_POLICY.md`

## Scope

Independent software review of the current `dev_tui_exp_recursive_missing` snapshot, focused on FT1 recursive repair, persistent resume/publication, state-machine lifetime, durable-state ownership, machine negotiation and adjacent multi-session agent lifecycle. The pass included semantic source inspection, diff/deletion gate for the exact base/target, targeted stock tests, broader applicable stock suites and isolated reviewer repros.

Firmware behavior, RF performance, physical hardware evidence and release/hardware acceptance are out of scope. A full repository pytest result is unavailable in this runtime because `pyserial` is not installed; this limits a possible GREEN verdict but does not make the confirmed RED findings inconclusive.

## Findings

### F001 — BLOCKER: RX restore advances durable state before runtime publication and has no rollback

Where: `src/serialterminal/file_transfer/resumable.py`, `_restore_incoming()`, lines 267–359 (especially checkpoint at line 312 and runtime publication at lines 316–330); wrapper in `manager.py:_restore_incoming()`.

Verified behavior: a retained `suspended` RX manifest is rewritten as active `receiving` by `_checkpoint_incoming()` before `_restart_record()`, `_records[...]` and `_incoming` are committed. If an exception occurs after the checkpoint but before runtime publication, cleanup releases the lease and clears `_active_id` but does not restore the durable status.

Failure scenario: resume a suspended RX; checkpoint succeeds; inject failure at `_restart_record`; the manifest is now `receiving`, while `_incoming is None`, `_active_id is None`, and the existing runtime record remains failed.

Impact: persistent recovery truth and live ownership disagree. A crash/restart or another same-process resume can reason from a durable state that was never successfully published as a live receiver operation. This violates the resume atomicity contract and can misattribute recovery ownership.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f001_restore_checkpoint_can_advance_durable_state_before_runtime_publish` — PASS as a defect repro at the reviewed SHA.

Test gap: stock atomic-resume tests do not inject failure in the post-checkpoint/pre-runtime-publication window.

Confidence / limitations: confirmed deterministically in-process; no hardware dependency.

Required acceptance: make the restore transition atomic from the durable/runtime contract perspective. On any failure after changing durable status, either roll durable state back to the previous resumable state or publish a durable state that explicitly represents the failed/non-owned transition. Add fault-injection regression tests at each boundary between claim, checkpoint and runtime publication.

Follow-up TODO: `TODO_043`.

### F002 — BLOCKER: integrity failure automatically reuses a quarantined transfer ID and can enter a permanent retry trap

Where: `src/serialterminal/file_transfer/resumable.py`, receiver failure/quarantine path around lines 593–621 and sender candidate/start path lines 692–763; `manager.py:_sender_resume_candidate()` lines 69–105.

Verified behavior: terminal receiver integrity failure quarantines the RX identity, while the sender retains an active outgoing journal. A subsequent `file_send_start()` for the unchanged source automatically selects that journal and reuses the same transfer ID as a resume candidate.

Failure scenario: send transfer `X`; receiver reaches all DATA then fails END integrity verification and retains `X` as quarantined; sender fails but keeps outgoing journal; operator retries the same source; sender automatically starts `X` again with `resumed=true`; the peer rejects the quarantined identity again.

Impact: a normal operator retry cannot escape the terminal identity failure. The same logical transfer can be retried indefinitely without a new identity even though the peer has intentionally made the old identity non-resumable.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f002_remote_integrity_failure_is_automatically_reused_as_same_id_resume` — PASS as a defect repro.

Test gap: existing resume tests cover resumable transport/process failure, not terminal peer integrity rejection followed by a new user start.

Confidence / limitations: confirmed; exact peer rejection code can vary by retained failure, but the same-ID automatic reuse is deterministic.

Required acceptance: classify terminal integrity/protocol identities as non-resumable for automatic source lookup, or durably mark the sender journal terminal and allocate a fresh transfer ID on explicit new send. Regression test: terminal integrity failure -> explicit retry -> fresh identity -> no same-ID loop.

Follow-up TODO: `TODO_043`.

### F010 — BLOCKER: concurrent receivers can overwrite the same final file and both report completion

Where: `src/serialterminal/file_transfer/core.py:_unique_destination()` lines 174–188; `src/serialterminal/file_transfer/resumable.py:_publish_verified()` lines 642–663.

Verified behavior: destination selection and the later `destination.exists()` guard are check-then-act operations without a process-wide atomic reservation. Two managers sharing one receive directory can both select the same free path, both observe it absent, and then both call POSIX `os.replace()` on that path. `os.replace()` overwrites an existing destination atomically rather than failing. Both transfers can persist completed tombstones and reach `completed` for the same final path.

Failure scenario: two sessions receive different payloads with the same filename; synchronize both publication paths after their absence checks; both rename to `retained.bin`; final bytes are whichever rename wins, but both records/tombstones report success and the same `final_path`.

Impact: data corruption / loss with false success. One verified received file is silently overwritten by another while both peers may receive `RESULT OK`.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f010_two_managers_can_both_publish_ok_to_same_path` — PASS as a defect repro after synchronizing exactly at the final destination rename.

Test gap: publication tests exercise repeated/same-process publication, not two independent managers sharing a receive directory and racing the same filename.

Confidence / limitations: confirmed deterministically on POSIX semantics used by the implementation.

Required acceptance: introduce atomic cross-manager final-name reservation/publication semantics. The winner may publish exactly once; the loser must choose another reserved unique name or fail before any overwrite. Add a concurrent two-manager regression proving distinct outputs or one explicit failure, never dual OK to one path.

Follow-up TODO: `TODO_043`.

### F017 — BLOCKER: persistent sender journals are shared across sessions without peer identity

Where: `src/serialterminal/agent_core.py:open()` lines 687–714 (every per-session manager receives the same process `receive_dir`); `src/serialterminal/file_transfer/resume_store.py:save_outgoing()` lines 270–278 and `find_outgoing_for_source()` lines 283–295; `src/serialterminal/file_transfer/manager.py:_sender_resume_candidate()` lines 69–105.

Verified behavior: outgoing journals are keyed/stored by transfer ID and selected by resolved source path/content metadata, but contain no stable session/device/peer identity. All file managers in one agent process use the same durable store under `receive_dir`.

Failure scenario: session/device A starts source `same.bin` and leaves resumable outgoing transfer `A-ID`; independent session/device B starts the same source; B discovers A's journal, reuses `A-ID` with `resumed=true`, and after B completes it deletes the shared outgoing journal; A is still incomplete but its durable resume state is gone.

Impact: recovery identity is misattributed across independent peers. One device/session can consume and delete another device/session's durable logical work. This directly violates multi-session independence and can destroy resumability after a failure.

Evidence / repro: `/tmp/st-review-001/repros.py::test_new_sender_resume_journal_is_not_scoped_to_session_peer` — PASS as a defect repro; B reused `0000000000000515` created by A and completion by B removed A's journal while A remained non-completed.

Test gap: sender resume tests use one manager/peer namespace; agent tests prove multiple sessions are supported but do not test durable FT1 isolation between them.

Confidence / limitations: confirmed in-process with two managers sharing the real resume store. The correct stable peer key is a design decision, but the absence of any peer namespace is not.

Required acceptance: namespace or bind durable outgoing identity to a stable peer/device/session identity that survives only where resume is semantically valid; validate that identity before candidate selection and deletion. Regression: A and B sending the same local source must never select/delete each other's journals.

Follow-up TODO: not yet assigned; `TODO_043` should be extended or a dedicated persistent-state ownership TODO created.

### F003 — HIGH: valid ROOT END can be dropped solely because child RESULT presentation has not settled locally

Where: `src/serialterminal/file_transfer/recursive.py:_handle_end()` lines 236–254.

Verified behavior: while `frame.child_id` exists, an otherwise current END is saved as `deferred_end` only if the local child TX record already has `remote_result.ok`. If the peer sends the correct END after it has consumed the child transfer but before local RESULT presentation reaches the child record, the END is silently discarded.

Failure scenario: child missing-list transfer is accepted by the peer; peer immediately sends the expected ROOT END; local child RESULT has not yet been surfaced; `_handle_end()` returns without retaining END. With no control replay, the root can timeout despite having received the correct END.

Impact: correctness depends on duplicate/control replay rather than accepting a valid reordered event. Legal presentation ordering can produce a false transfer timeout.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f003_expected_root_end_before_child_result_is_dropped` — PASS as a defect repro.

Test gap: stock recursive tests do not force END-before-local-child-RESULT ordering with replay unavailable.

Confidence / limitations: confirmed state-machine ordering defect.

Required acceptance: retain/address the expected ROOT END based on recursive request identity even while local child settlement is pending, then process it once child ownership is safely released. Add an ordering regression with `max_control_replays=0`.

Follow-up TODO: `TODO_043`.

### F004 — HIGH: child transfer ID equal to its parent corrupts the ROOT recursive context before rejection

Where: `src/serialterminal/file_transfer/recursive.py:_handle_meta()` lines 153–199, especially frame insertion at line 172 and rollback pop lines 179/191.

Verified behavior: child META admission writes `_recursive_frames[meta.transfer_id] = frame` before underlying admission. If a child deliberately/corruptly uses the parent transfer ID, this overwrites the parent frame. When underlying admission rejects the duplicate, cleanup pops that key, removing the ROOT recursive frame while the core root record/lease can remain live.

Failure scenario: live ROOT ID `100`; receive child META with `transfer_id=100`, `parent_transfer_id=100`, valid depth; wrapper overwrites root frame; core rejects duplicate; wrapper removes key `100`; core record 100 remains active but no recursive ROOT frame exists.

Impact: malformed peer input can destroy local state-machine context and strand a live transfer/lease.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f004_child_id_equal_parent_destroys_root_recursive_context` — PASS as a defect repro.

Test gap: recursive protocol tests do not cover child/ancestor ID aliasing before wrapper mutation.

Confidence / limitations: confirmed.

Required acceptance: validate child identity against parent/ancestor/live frame IDs before mutating `_recursive_frames`, and make failed admission rollback restore the exact previous mapping. Add self-ID and ancestor-ID collision regressions.

Follow-up TODO: `TODO_043`.

### F005 — HIGH: completed ROOT recursive frames bypass core terminal retention and leak for process lifetime

Where: `src/serialterminal/file_transfer/recursive.py:_terminal_record_settled()` lines 318–361; compare core terminal eviction around `core.py` lines 743–745.

Verified behavior: child frames are popped at line 359; failed roots go through `_abort_recursive`; successfully completed root frames have no removal path. Core records are evicted according to `max_retained_terminal`, but `_recursive_frames` retains completed roots independently.

Failure scenario: complete 40 sequential roots with core terminal retention 16; core retains 16 records/terminal IDs while recursive mapping retains all 40, including 24 frames whose records are no longer retained by core.

Impact: long-lived SerialTerminal/agent processes accumulate recursive frame objects for every successful root transfer.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f005_terminal_root_frames_outlive_core_retention` — PASS as a defect repro; historical public-transfer observation in TODO_043 is consistent but was not used as proof.

Test gap: stock retention tests bound core records, not recursive wrapper state.

Confidence / limitations: confirmed lifecycle leak.

Required acceptance: retire completed root frames in lockstep with a defined lifecycle/retention policy, without breaking idempotent END/RESULT replay. Add long-run successful-transfer retention test that bounds both core and recursive structures.

Follow-up TODO: `TODO_043`.

### F007 — HIGH: rejected conflicting ROOT META overwrites live recursive repair state

Where: `src/serialterminal/file_transfer/recursive.py:_handle_meta()` lines 142–204, especially unconditional ROOT frame reconstruction lines 200–204 after manager handling.

Verified behavior: a conflicting META for a live root can be rejected by the underlying manager while the existing core record remains non-terminal. The wrapper then reconstructs `_recursive_frames[id]` from the rejected META and current `_incoming`, replacing the valid frame and resetting recursive request/progress/history fields.

Failure scenario: live root has request ID, previous-missing/no-progress counters and processed-child history; receive conflicting same-ID root META; underlying record still owns the original META; wrapper replaces the frame with one containing the conflicting META and zeroed recursive state.

Impact: rejected input still mutates accepted runtime state, losing repair identity/history and potentially invalidating subsequent END/child processing.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f007_rejected_root_meta_overwrites_live_recursive_frame` — PASS as a defect repro.

Test gap: duplicate-META tests cover matching identity, not conflicting same-ID ROOT input with active recursive state.

Confidence / limitations: confirmed.

Required acceptance: only create/replace the ROOT recursive frame when underlying META admission actually created/restored that exact META identity; rejection must be side-effect free for the existing frame. Add conflicting-root regression asserting full frame identity/state preservation.

Follow-up TODO: `TODO_043`.

### F008 — HIGH: ROOT idle timeout accounting pauses service but not the clock, and duplicate META does not refresh activity

Where: `src/serialterminal/file_transfer/recursive.py:_handle_meta()` lines 142–152 and `_expire_stale_incoming()` lines 455–461; manager idle expiry around `manager.py` lines 367–390.

Verified behavior: when a recursive child is active, `_expire_stale_incoming()` simply returns, but the root's `last_activity_monotonic` continues aging. The matching-META fast path may resend RESUME and return without touching root activity. As soon as child ownership clears, expiry can immediately declare the root timed out based on time intentionally spent servicing the child.

Failure scenario: root activity timestamp is older than idle budget; duplicate root META takes the fast path and leaves timestamp unchanged; active child suppresses expiry; child settles; next expiry immediately fails/suspends root with `remote_sender_timeout` even though the recursive repair cycle was active.

Impact: valid long repair work can consume the parent's idle budget and create a false sender timeout immediately after child completion.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f008_parent_idle_clock_includes_child_time_and_duplicate_meta_does_not_touch` — PASS as a defect repro.

Test gap: existing idle tests do not account for child-service duration plus duplicate control traffic.

Confidence / limitations: confirmed accounting defect; exact policy (pause clock vs update activity) is design freedom.

Required acceptance: define root-idle semantics during recursive child service and implement them monotonically (pause/exclude child duration or refresh on valid recursive activity). Add bounded child-duration and duplicate-META regressions.

Follow-up TODO: `TODO_043`.

### F009 — HIGH: failed foreground machine renegotiation can permanently strand the client in `negotiating`

Where: `src/serialterminal/profiles/chatter/machine_client.py`, `_negotiate()` lines 121–145 and `_ready()` lines 147–189; compare bootstrap/lifecycle exception rollback lines 65–94.

Verified behavior: `_negotiate()` sets `mode="negotiating"` and clears `error` before external HELLO work. Bootstrap/lifecycle callers catch `BinaryUserError` and restore `mode="failed"`; the foreground `_ready()` retry branches call `_negotiate()` without equivalent rollback. If a foreground retry fails, the client remains `negotiating` with `error=None`. Because `start_thread` exists, the next foreground `_ready()` waits for that existing negotiation instead of issuing a new HELLO, while the lifecycle loop also does not treat plain `negotiating` as a retry condition.

Failure scenario: bootstrap fails with temporary `machine_owner_busy`; explicit send triggers retry while owner is still busy; retry raises; mode remains `negotiating`; owner later becomes free; next send emits no HELLO and times out waiting for bootstrap state that no thread is servicing.

Impact: transient owner contention can create a permanently stuck local machine state until close/reopen, contrary to the documented recoverable HELLO path.

Evidence / repro: `/tmp/st-review-001/repro_f9.py::test_foreground_retry_failure_leaves_negotiating` — PASS as a defect repro.

Test gap: stock recovery tests cover failed bootstrap followed by a *successful* foreground retry, not a failed foreground retry followed by later recovery.

Confidence / limitations: confirmed deterministically with the existing machine-client test node.

Required acceptance: every `_negotiate()` caller must leave a serviced deterministic state on exception; either `_negotiate()` itself publishes `failed/error` or all callers do so consistently. Regression: busy bootstrap -> busy foreground retry -> owner frees -> next/idle retry succeeds and exactly the intended HELLOs are sent.

Follow-up TODO: `TODO_043`.

### F012 — HIGH: constructing another manager can delete a live receiver partial before its manifest exists

Where: `src/serialterminal/file_transfer/resume_store.py`, constructor cleanup line 43 and `_cleanup_part_budget()` lines 322–353; `src/serialterminal/file_transfer/resumable.py:_start_new_incoming()` lines 505–559.

Verified behavior: a new receiver creates/truncates the hidden `.part` before durable incoming manifest publication. `ResumeStateStore.__init__()` immediately calls cleanup. `_cleanup_part_budget()` treats every part without a manifest as orphaned and unlinks it, with no knowledge of another live manager's in-progress pre-manifest admission.

Failure scenario: manager A receives META and creates part, then blocks in claim/admission before checkpointing manifest; manager B using the same receive directory is constructed; B's store cleanup sees A's part without manifest and deletes it; A resumes and fails receiver processing.

Impact: simply opening another session/manager can destroy bytes owned by a live transfer in the same process.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f012_second_manager_cleanup_deletes_live_pre_manifest_part` — PASS; A's part was removed by B and A failed.

Test gap: cleanup tests treat no-manifest parts as abandoned filesystem artifacts, not as another manager's live pre-manifest state.

Confidence / limitations: confirmed. This shares a root cause family with F015/F017: one filesystem namespace has no live-owner coordination.

Required acceptance: eliminate the observable pre-manifest orphan window or coordinate cleanup with live ownership across managers. A store constructor must never delete another live manager's partial. Add concurrent construction/admission regression.

Follow-up TODO: `TODO_043`.

### F015 — HIGH: documented durable retention/storage bounds are enforced only at store construction

Where: `src/serialterminal/file_transfer/resume_store.py`, `__init__()` cleanup call line 43, write methods `save_incoming()` lines 197–220, `save_completed()` lines 244–268, `save_outgoing()` lines 270–278, and `cleanup()` lines 297–353.

Verified behavior: the documented count/TTL/partial-byte cleanup policy is invoked only when a `ResumeStateStore` is constructed. Normal manifest/part writes do not enforce those bounds. A long-running agent can accumulate more than `DEFAULT_MAX_INCOMING`, `DEFAULT_MAX_OUTGOING`, `DEFAULT_MAX_COMPLETED` and the configured part-byte budget until some later manager construction happens to run cleanup.

Failure scenario: construct a store with `max_part_bytes=10`; create two valid 8-byte retained parts/manifests -> 16 bytes remain; save 40 outgoing manifests -> all 40 remain, despite the default outgoing bound of 32.

Impact: the "bounded cleanup policy" is not actually a runtime bound. A long-lived process can grow durable state/disk use without the advertised limits, eventually causing storage pressure/failure.

Evidence / repro: `/tmp/st-review-001/repros.py::test_new_live_retention_limits_are_not_enforced_until_another_constructor` — PASS as a defect repro.

Test gap: existing cleanup tests invoke/trigger cleanup as a discrete operation; they do not prove the bounds remain true after ongoing writes in one long process.

Confidence / limitations: confirmed. Cleanup must also be fixed without reintroducing F012 by deleting live-owned state.

Required acceptance: enforce retention at safe lifecycle/write boundaries with cross-manager active-owner awareness. Add long-running tests that exceed each count/TTL/byte limit and prove bounded state without deleting live transfers.

Follow-up TODO: not yet assigned; `TODO_043` should be extended or durable-store lifecycle split into its own TODO.

### F016 — HIGH: receiver admits META identities that cannot be represented by END/RESUME uint32 chunk space

Where: `src/serialterminal/file_transfer/protocol.py` fixed layouts lines 11–18 and validation lines 257–300/356–360; `src/serialterminal/file_transfer/resumable.py:_chunk_count()` lines 258–260 and `_start_new_incoming()` lines 505–559.

Verified behavior: META carries `wire_size` as uint64 and `chunk_size` can be 1, while DATA index, END `chunk_count` and RESUME `next_chunk` are uint32. Receiver admission computes `ceil(wire_size/chunk_size)` but does not reject values above `0xffffffff`.

Failure scenario: valid META declares `wire_size=2^32+1`, `chunk_size=1`; META encodes and is accepted, creating an RX record with `chunks_total=4294967297`. No protocol-valid END can express that chunk count; `encode_message(EndMessage(...))` rejects it as out of range.

Impact: a protocol-valid META can create an inherently unfinishable transfer and hold session/storage/runtime resources until failure/timeout. Related loops/materialization over `chunks_total` also become pathological for malicious declarations.

Evidence / repro: `/tmp/st-review-001/repros.py::test_new_meta_can_admit_unfinishable_uint32_chunk_space` — PASS; receiver entered `receiving` with 4,294,967,297 chunks and END encoding for that count was impossible.

Test gap: protocol tests validate each field independently but do not validate cross-message representability of the META-derived chunk count.

Confidence / limitations: confirmed protocol-admission bug; ordinary file sizes/chunk sizes may not hit it, but remote META is an input boundary and must be coherent.

Required acceptance: reject META before allocating/claiming receiver state whenever derived chunk count exceeds uint32 (and enforce the same representability on sender preparation). Add boundary tests for exactly `0xffffffff` and `0x100000000` chunks.

Follow-up TODO: not yet assigned; candidate extension to `TODO_043` or protocol-boundary TODO.

### F006 — MEDIUM: one live ROOT can accumulate unbounded `processed` child history

Where: `src/serialterminal/file_transfer/recursive.py`, `_Frame.processed` line 40, replay lookup lines 155–160 and insertion in `_terminal_record_settled()` lines 340–342.

Verified behavior: every successfully serviced child transfer is retained in `parent.processed` until the root frame dies. Core terminal record retention does not bound this dict. Repair no-progress logic only limits consecutive no-progress cycles; continuing progress can create arbitrarily many child identities over a sufficiently large root.

Failure scenario: repeatedly settle 1,000 successful child requests under one still-live root while consuming `parent.requests`; `processed` reaches 1,000 while core terminal retention stays at 16.

Impact: memory use for a single long repair scales with total historical children rather than live/replay-needed state.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f006_processed_history_grows_while_core_records_are_bounded` — PASS as a defect repro.

Test gap: stock recursive tests cover small repair depths/cycles, not long progressive histories.

Confidence / limitations: confirmed growth mechanism; practical magnitude depends on file/repair pattern.

Required acceptance: define a bounded replay/dedup history strategy that retains enough identity for required idempotence without unbounded per-root growth. Add stress test proving the bound while valid late replay behavior remains correct.

Follow-up TODO: `TODO_043`.

### F011 — MEDIUM: losing concurrent `open()` leaks an already-started file manager/application worker

Where: `src/serialterminal/agent_core.py:open()` lines 600–755, especially binary/file manager construction lines 677–714 and second device-ownership check lines 719–729.

Verified behavior: two concurrent opens can both pass the initial `device_key` ownership check. Each creates its transport, `ManagedSession`, profile binary adapter and `FileTransferManager`; manager construction starts FT1 RX and profile lifecycle workers. At the second ownership check, the loser only calls `transport.close()` and raises `device_busy`; it does not close the already-created `file_manager`/binary adapter.

Failure scenario: synchronize two opens of the same `device_key` after the first check; one wins registration, one loses; the loser object is absent from `_file_managers` but its `_rx_thread` remains alive with `_stopping` unset.

Impact: repeated open races leak daemon workers/application state and can keep callbacks/store activity alive after an operation that reported `device_busy`.

Evidence / repro: `/tmp/st-review-001/repro_f11.py::test_duplicate_device_open_loser_leaks_file_manager` — PASS as a defect repro; reviewer retained the loser only to prove/clean it after the assertion.

Test gap: existing `device_busy` test is sequential and rejects at the first ownership check, before constructing application state.

Confidence / limitations: confirmed concurrent lifecycle leak.

Required acceptance: on the second-check loser path close all constructed application/session resources, not only raw transport, or atomically reserve device ownership before side-effectful construction. Add a two-thread open race regression asserting no loser FT1/machine threads survive.

Follow-up TODO: `TODO_043`.

### F013 — MEDIUM: malformed `file_transfer_cancel.transfer_id` escapes protocol normalization as `internal_error`

Where: `src/serialterminal/file_transfer/recursive.py:cancel()` lines 464–468; core normalized cancel path `core.py:cancel()` lines 1889–1909; `src/serialterminal/agent_core.py:file_transfer_cancel()` around lines 1074–1083.

Verified behavior: recursive `cancel()` calls `parse_transfer_id()` before delegating to the core method that normally converts `FileProtocolError` to `FileTransferError`. `SessionManager.file_transfer_cancel()` catches only `FileTransferError`. A malformed hex ID therefore escapes to the top-level generic exception handler and becomes `internal_error`.

Failure scenario: agent request `file_transfer_cancel` with `transfer_id="not-hex"`; response is `ok:false,error.code:"internal_error"` instead of the stable invalid-transfer/request error used by the file-transfer API.

Impact: caller input error is misclassified as an internal agent failure, breaking machine-facing error semantics and diagnostics.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f013_invalid_cancel_becomes_agent_internal_error` — PASS as a defect repro through `AgentProtocol.handle()`.

Test gap: malformed-ID coverage exists around other operations but not recursive cancel's pre-parse wrapper.

Confidence / limitations: confirmed.

Required acceptance: parse once inside the normalized FileTransferError boundary or explicitly normalize `FileProtocolError` in recursive/session cancel. Add malformed string, boolean and out-of-range ID tests at JSONL API level.

Follow-up TODO: `TODO_043`.

### F014 — MEDIUM: malformed durable `updated` value throws before sender-journal validation

Where: `src/serialterminal/file_transfer/resume_store.py:find_outgoing_for_source()` lines 283–295; candidate validation in `manager.py:_validated_sender_candidate()` lines 107–160.

Verified behavior: matching outgoing documents are sorted using `float(item.get("updated", 0))` before candidate validation. Unlike `cleanup()`, the sort has no `TypeError/ValueError` guard. A corrupt but readable JSON manifest with matching `source_path` and non-numeric `updated` raises `ValueError` before `_validated_sender_candidate()` can reject it.

Failure scenario: one malformed outgoing manifest for a source uses `"updated":"bad-timestamp"`; starting that source raises `ValueError` during candidate lookup.

Impact: one corrupt durable journal can block a new send/recovery path for that source rather than being ignored/quarantined as invalid state.

Evidence / repro: `/tmp/st-review-001/repros.py::test_f014_bad_updated_timestamp_escapes_candidate_validation` — PASS as a defect repro.

Test gap: durable-state validation tests do not cover malformed sort metadata before validation.

Confidence / limitations: confirmed local-corruption robustness defect.

Required acceptance: make ordering tolerant of invalid `updated` values and validate/quarantine malformed candidates before they participate in sort/selection. Add malformed type/string tests.

Follow-up TODO: `TODO_043`.

## Previous findings recheck

There is no previous numbered REVIEW-ID. The current target source is byte-identical to the previous published checkpoint, but historical TODO_043 review notes were treated only as leads and rechecked independently.

| Historical lead in `TODO_043` | Current finding | Recheck result at `db740af94c700c7c4e6d96abef7e809dadfcaf1c` |
| --- | --- | --- |
| RX restore durable/runtime atomicity | `REVIEW_001/F001` | STILL_PRESENT — isolated repro confirmed |
| quarantined same-ID automatic retry | `REVIEW_001/F002` | STILL_PRESENT — isolated repro confirmed |
| ROOT END ordering loss | `REVIEW_001/F003` | STILL_PRESENT — isolated repro confirmed |
| child ID/parent collision | `REVIEW_001/F004` | STILL_PRESENT — isolated repro confirmed |
| terminal ROOT frame retention leak | `REVIEW_001/F005` | STILL_PRESENT — isolated repro confirmed |
| unbounded `processed` history | `REVIEW_001/F006` | STILL_PRESENT — isolated repro confirmed |
| conflicting ROOT META overwrites frame | `REVIEW_001/F007` | STILL_PRESENT — isolated repro confirmed |
| recursive idle-accounting gap | `REVIEW_001/F008` | STILL_PRESENT — isolated repro confirmed |
| foreground HELLO retry stuck state | `REVIEW_001/F009` | STILL_PRESENT — dedicated repro confirmed |
| concurrent final publication race | `REVIEW_001/F010` | STILL_PRESENT — corrected barrier repro confirmed |
| duplicate-device open loser worker leak | `REVIEW_001/F011` | STILL_PRESENT — dedicated concurrent repro confirmed |
| constructor cleanup vs live pre-manifest part | `REVIEW_001/F012` | STILL_PRESENT — isolated repro confirmed |
| invalid recursive cancel error normalization | `REVIEW_001/F013` | STILL_PRESENT — JSONL-level repro confirmed |
| malformed sender journal timestamp | `REVIEW_001/F014` | STILL_PRESENT — isolated repro confirmed |

`REVIEW_001/F015`–`F017` are new findings from this pass, not merely carried forward from the historical TODO review text.

## Validation and evidence

| Check / command | Exact checkpoint | Result | Evidence type / pointer / limitations |
| --- | --- | --- | --- |
| Target/branch/worktree identity | `db740af94c700c7c4e6d96abef7e809dadfcaf1c` | PASS | executed; branch `dev_tui_exp_recursive_missing`; checkout clean before review-output files |
| `git diff --stat` + `git diff --name-status 8cf689e..db740af` | base → target | PASS | executed; 11 documentation/review/TODO paths only; no production/test files in delta |
| source/test tree object comparison | base → target | PASS | `src` tree `4f4e8c99b577c6cd874a9af2acad568910d4e9f9` at both commits; `tests` tree `b1b246853210cf4f81eae656ecc930d4fa953674` at both commits |
| `git diff --exit-code 8cf689e..db740af -- src tests serialterminal.py tools` | base → target | PASS | executed; empty diff |
| `git diff --check 8cf689e..db740af` | base → target | PASS | executed |
| `python3 -m compileall -q src serialterminal.py tools` | target | PASS | executed |
| targeted stock review subset: failure retention, resume atomic, recursive missing, machine recovery, agent | target | PASS | executed; `61 passed in 8.01s`; these tests do not cover the reproduced gaps above |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_file_transfer_*.py tests/test_ft1*.py` | target | PASS | executed; `145 passed in 28.25s` |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_chatter_machine*.py tests/test_agent.py` | target | PASS | executed; `73 passed in 3.61s` |
| reviewer repro set F001–F008, F010, F012–F017 | target | DEFECTS REPRODUCED | `/tmp/st-review-001/repros.py`; `15 passed in 1.74s`; PASS here means each test successfully demonstrated the asserted defect, not acceptance |
| reviewer repro F009 | target | DEFECT REPRODUCED | `/tmp/st-review-001/repro_f9.py`; `1 passed`; failed foreground retry leaves `negotiating` and later send emits no new HELLO |
| reviewer repro F011 | target | DEFECT REPRODUCED | `/tmp/st-review-001/repro_f11.py`; `1 passed`; losing concurrent open leaves unregistered FT1 worker alive |
| full `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q` | target | BLOCKED | collection stops with 14 import errors because runtime lacks `pyserial` (`ModuleNotFoundError: serial`); no full-suite PASS claimed |
| physical/hardware/RF validation | N/A | NOT RUN | outside requested software-review scope |

## Assessment

The reviewed snapshot is not acceptable for merging the recursive FT1 experiment into a production branch. The stock FT1/machine/agent tests are broadly green, but independent failure injection and concurrency repros expose four blocker-class defects: non-atomic resume truth, an automatic terminal same-ID retry trap, dual-success final-file overwrite, and cross-session theft/deletion of persistent sender identity. These are correctness/data/ownership failures, not style or test-only concerns.

The remaining HIGH findings show additional state corruption, dropped valid protocol events, false timeout behavior, persistent/live storage ownership races, unbounded runtime/durable growth and admission of an unfinishable protocol identity. MEDIUM findings still represent real lifecycle/API/robustness defects. Several are in code paths explicitly documented as bounded/recoverable/multi-session behavior.

The fact that `src` and `tests` are byte-identical to `8cf689e` means this RED verdict is not a regression verdict against the documentation-only delta: it is a current-snapshot verdict. The new review-management commit did not create these runtime bugs; it made the independent current-state review record possible.

Full repository pytest is unavailable in this environment because `pyserial` is absent. That prevents claiming comprehensive GREEN evidence but does not weaken the confirmed RED conclusion: the acceptance blockers reproduce without serial hardware or `pyserial`.

## Result

Status: COMPLETE
Verdict: RED
Verdict scope: current `dev_tui_exp_recursive_missing` software snapshot; FT1 recursive/core/recovery/persistence plus adjacent machine negotiation and agent multi-session lifecycle
Remaining gates: fix all blocker/high findings; assign/extend TODO coverage for F015–F017; add regressions matching each acceptance criterion; rerun applicable full software suite in an environment with `pyserial`; perform a new numbered re-review on the fixed exact SHA. Physical/RF validation remains separate where later required.
Follow-up: `todos/TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md` for existing findings; extend it or create dedicated TODO(s) for `REVIEW_001/F015`–`F017`; next review pass must allocate a new REVIEW-ID.

## Addendum 2026-10-14 — self-regression attribution against pre-implementation checkpoint

This addendum answers a narrower follow-up question: which current defects were introduced or newly exposed by the implementation written after the last pre-feature source checkpoint, rather than merely discovered while reviewing the branch.

Regression baseline: `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd` (`point 8 done`). Commit `991ff0e` changes only documentation, so the implementation delta is effectively `fd94bde..cb89154`, followed by the machine-recovery delta `8cf689e`. Reviewed target remains `db740af94c700c7c4e6d96abef7e809dadfcaf1c`; this addendum does not rewrite the original review target/base.

### Attribution

Confirmed defects introduced by the new recursive implementation:

- `REVIEW_001/F003` — new recursive END/child-result ordering logic drops a valid ROOT END.
- `REVIEW_001/F004` — new recursive child admission can overwrite the ROOT frame on child/parent ID collision.
- `REVIEW_001/F005` — new recursive wrapper retains terminal ROOT frames beyond the core record bound. This one is also a regression for ordinary successful ROOT transfers, not only an edge case inside repair.
- `REVIEW_001/F006` — new per-ROOT `processed` history is unbounded.
- `REVIEW_001/F007` — new ROOT META wrapper mutates recursive state after a core rejection path.
- `REVIEW_001/F008` — new child-aware idle suppression pauses the check, but not the ROOT activity clock.
- `REVIEW_001/F013` — new recursive `cancel()` pre-parses `transfer_id` outside the old normalized `FileTransferError` boundary, changing malformed-input API behavior to `internal_error`.

`REVIEW_001/F009` is a regression newly exposed by the `8cf689e` foreground negotiation-retry path. The lower-level `_negotiate()` failure behavior already left its transient mode as `negotiating`; before `8cf689e`, a failed background bootstrap remained `failed` and did not enter this new foreground retry branch. The added retry can now call `_negotiate()`, fail during that retry, and strand the production client in `negotiating` with no owner performing negotiation. Therefore the stuck-state mechanism is partly old, but the reachable failed-bootstrap -> foreground-retry -> permanently-negotiating production path is introduced by my recovery change.

The following confirmed findings are pre-existing at `fd94bde` and must not be misreported as regressions from the recursive implementation: `F001`, `F002`, `F010`, `F011`, `F012`, `F014`, `F015`, `F016`, `F017`. Exact source comparison confirmed the key F001/F002/F010 paths (`_restore_incoming`, `_fail_incoming`, `_publish_verified`, `_sender_resume_candidate`, `start_send`) are unchanged across the implementation boundary; the relevant agent/store ownership and retention behavior for F011/F012/F014-F017 also predates the recursive delta.

### F018 — MEDIUM: incremental timing append creates duplicate `seq` identities across session replacement

Where: `src/serialterminal/timing.py:TimingTrace.__init__()` and `record()`; TUI replacement reuses the same configured `log_path` through `tui_core.py:_make_session()` / `_replace_tui_session()`.

Verified behavior: the new timing writer opens an existing `.fttiming.jsonl` with append mode specifically to preserve earlier session segments, but every new `TimingTrace` initializes `_next_seq = 1`. Reopening the same path therefore creates one physical trace containing repeated sequence numbers.

Failure scenario: create a timing trace for `run.log`, record/close one event; create another `TimingTrace` for the same `run.log`, record/close one event. The resulting file contains `[(seq=1, session1), (seq=1, session2)]`. TUI F2/profile replacement follows this same path because a new `TerminalSession` is created with the existing `self.log_path`.

Impact: `seq` is no longer a unique ordering/correlation identity inside one timing companion file. Consumers that correlate or de-duplicate by trace sequence can merge unrelated events or infer the wrong ordering. `perf_ns` still provides a monotonic clock, so this is an observability/correlation defect rather than transfer-state corruption.

Evidence / repro: direct target-SHA repro on 2026-10-14 produced `[(1, 'session1'), (1, 'session2')]`. Existing `tests/test_timing.py::test_timing_reopened_path_preserves_previous_session` verifies the two events survive but does not assert sequence uniqueness/segment identity.

Confidence / limitations: confirmed local deterministic behavior. No claim is made that every current downstream analyzer keys solely on `seq`; the defect is the ambiguous file contract itself.

Required acceptance: either preserve a file-global monotonically increasing sequence when appending, or add an explicit stable trace/session segment identity and document that `(segment, seq)` is the correlation key. Add a reopen/session-replacement regression test that proves unambiguous identities.

Follow-up TODO: not yet assigned.

Adjacent documentation drift found during this audit: `AGENT_API.md` and the active skill describe incremental timing, while `LOGGING.md` still says timing is held in RAM and written only on clean shutdown. That text is stale relative to the implementation and should be reconciled, but it is not elevated to a separate runtime finding.

### Additional regression-audit validation

| Check / command | Exact checkpoint | Result | Evidence / limitation |
| --- | --- | --- | --- |
| Source regression range inspection `fd94bde..db740af` | base -> target | PASS | implementation commits and changed production paths reviewed; `991ff0e` confirmed docs-only |
| production definition/deletion comparison | base -> target | PASS | no production function/class definition disappears from the final source set; refactored names remain represented |
| reviewer repros F003-F009/F013 | target | DEFECTS REPRODUCED | 8 selected repros passed in 0.95 s; PASS means the asserted defects reproduced |
| reopened timing-path repro | target | DEFECT REPRODUCED | two appended events received duplicate `seq=1` |
| applicable file-transfer/FT1/machine/timing tests, run per file | target | PASS | all selected files completed green individually: 215 tests total; combined invocation exceeded the command harness timeout, so the timeout itself was not treated as a test failure |
| `tests/test_chatter_machine_client.py` | target | PASS | `26 passed in 1.40s` |
| `tests/test_chatter_machine_codec.py`, `test_chatter_machine_recovery.py`, `test_chatter_radio_timing.py`, `test_timing.py` | target | PASS | `21 + 7 + 12 + 4` passed |
| `git diff --check fd94bde..HEAD` | target | PASS | executed |
| `python -m compileall -q src serialterminal.py tools` | target | PASS | executed |
| full pytest | target | BLOCKED | runtime still lacks `pyserial`; no full-suite PASS claimed |

Regression verdict: RED. At least `F005`, `F009`, `F013` and `F018` are regressions in previously available/general behavior, while `F003`, `F004`, `F006`, `F007`, `F008` are correctness defects introduced with the new recursive feature itself. The pre-existing findings remain real blockers/high issues, but they are not attributed to this implementation delta.
