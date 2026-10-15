# Timing: однозначные event identities при append и замене session

TODO-ID: TODO_047
Status: IMPLEMENTED / LOCAL VALIDATION PASS / CI AND RE-REVIEW OPEN
Priority: MEDIUM
Created: 2026-10-14
Implementation: SEGMENT IDENTITY, APPEND RECOVERY AND REGRESSIONS IMPLEMENTED
Validation: HOST SOFTWARE 775 PASS / CI AND RE-REVIEW OPEN
Source review: [REVIEW_001/F018](../reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md#f018--medium-incremental-timing-append-creates-duplicate-seq-identities-across-session-replacement)
Reviewed commit: [db740af94c700c7c4e6d96abef7e809dadfcaf1c](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c)
Regression attribution: introduced by implementation after `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd` по addendum ревью.

## Purpose

Сохранить однозначную корреляцию timing events внутри одного `.fttiming.jsonl`
при reopen и TUI session/profile replacement.

## Current behavior

`TimingTrace` открывает existing companion в append mode, но каждый instance
начинает `_next_seq=1`. Два successive traces для одного `run.log` записали
`[(1, session1), (1, session2)]`. TUI reuse того же log_path следует этому пути.
`perf_ns` сохраняет clock ordering, но `seq` неоднозначен внутри файла.
`test_timing_reopened_path_preserves_previous_session` проверяет сохранность
событий без проверки unambiguous correlation key.

## Target behavior и Design

Перед реализацией выбрать один контракт из вариантов review: file-global monotonic
sequence либо явный stable trace/session segment и correlation key `(segment, seq)`.
Не выбирать его молча; описать recovery/append и влияние на consumers.
Существующие события и session segments должны сохраняться, final transfer
semantics и clock meanings не меняются.

В scope: timing writer, reopened path, TUI replacement, consumers и logging docs.
Смежный documentation drift: LOGGING.md описывает RAM-only timing/clean-shutdown
write, хотя AGENT_API.md и active skill уже описывают incremental timing. Согласовать
это описание с фактическим writer и выбранным correlation contract.
Связано с [TODO_026](TODO_026_UNIFIED_LOGGING_CONTRACT.md).

## Implementation

- [x] Закрепить correlation identity и append/reopen contract.
- [x] Реализовать выбранный вариант, сохранив предыдущие events.
- [x] Проверить consumers и синхронизировать LOGGING.md, AGENT_API.md и
  repo-local serialterminal-agent skill.

## Validation / acceptance

- [x] Reopen того же path для нескольких sessions: все события сохранены,
  correlation keys уникальны и ordering однозначен.
- [x] TUI session/profile replacement проверяет тот же контракт.
- [x] Existing timing/flush/close и readers/analyzers корректны для выбранной схемы;
  обработка existing trace согласована с документированной compatibility policy.
- [ ] Relevant timing/TUI/logging tests, full pytest для shared terminal behavior,
  compileall, diff --check и numbered re-review на exact implementation SHA.

## История: evidence при создании задачи

Evidence/repro и ограничения сохранены в исходном finding ревью. При оформлении
TODO repro не запускался повторно, fixes и source/tests не изменялись.
Status: OPEN; implementation, regression validation и re-review остаются открыты.
Это task record; hardware, firmware changes, commit/push не выполнялись.

## Selected contract and implementation — 2026-10-15

Base5f35441. Proposed per-instance UUID segment_id + segment-local seq is used
after the operator's affirmative continuation. Every row carries the pair and
caller metadata cannot overwrite its identity/clocks. Append preserves old rows;
no global sequence scan or legacy-row rewriting is needed. Existing rows without
segment_id remain historical data without the new guarantee.

Each cooperating POSIX writer locks a batch through flush. Raw tail inspection
uses the existing append descriptor without decoding potentially truncated UTF-8;
a non-LF fragment is retained and separated before the next valid record. Such
fragments remain explicit evidence gaps. Capture clocks retain their meanings;
append order across segments is not treated as global capture ordering.

Permanent tests cover reopen with duplicate local seq but distinct pair keys,
reserved-field protection, legacy retention, truncated UTF-8 append, concurrent
threads/processes with large rows, and actual TerminalTui session/profile
replacement through fake transports. Existing worker-failure/backpressure/flush/
close assertions remain intact. Targeted timing/TUI/terminal/logging suite85 PASS
(0.58s). Full suite in progress. LOGGING.md corrected from obsolete RAM-only
shutdown-write prose to incremental256-event batches/8 queued batches and explicit
backpressure/incomplete-trace semantics. API and active skill agree.

Consumers in source/tools and the observation result-processing script were
inspected: no file-global timing-seq joins to migrate were found. Observation
files remain unchanged. No hardware, firmware changes, push or merge; CI and
independent post-fix review stay OPEN.

Portability audit found an unconditional POSIX import in the initial append-lock
change. It is now optional; descriptor-tail read has a portable binary fallback.
A subprocess regression imports/writes/closes with fcntl/pread unavailable and
preserves a truncated UTF-8 tail. Targeted suite86 PASS/1.33s. Initial full suite
771 PASS/104.36s preceded that correction; final full suite reruns below. New
regression-module imports were checked for unused names and cleaned before the
final run; existing unrelated imports are unchanged.

Final series verification also revisited F015 through the low-level checkpoint
repro, producing a dedicated TODO_044 follow-up before this commit. The control
regression's repeated full-run failure was traced to real fsync latency exceeding
its synthetic deadline; only that test isolates fsync, keeping real files/flush and
all retry/time/outcome assertions. Isolated scenario40/40 PASS and related suite92
PASS. The final cumulative full suite covers those refinements and timing together.

Final cumulative isolated-cache full suite:775 PASS/97.88s. Compileall using
/usr/bin/python3 and diff-check PASS. Log SHA256 `86409ba193076ec7a3600b59895700859cb4d93fa1b4f81d465b63c6c50f473f`.
The resumed run preserved its output in /tmp/st-series-resumed-YjmkAm/pytest.log;
no result is inferred from the interrupted earlier process.

Checkpoint/TTL follow-up commit:9f7dc68; timing commit base:9f7dc68.
Exact final cumulative implementation trees: src `3fb95df0fe1f46f89e4aa8569976774d4758f9d6`; tests `4b4105b4b31b93e0bc3dd9892b219d8555a5208b`.
