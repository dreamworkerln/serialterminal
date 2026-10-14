# Timing: однозначные event identities при append и замене session

TODO-ID: TODO_047
Status: OPEN
Priority: MEDIUM
Created: 2026-10-14
Implementation: NOT STARTED
Validation: REVIEW FINDING RECORDED / FIX VALIDATION OPEN
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

- [ ] Закрепить correlation identity и append/reopen contract.
- [ ] Реализовать выбранный вариант, сохранив предыдущие events.
- [ ] Проверить consumers и синхронизировать LOGGING.md, AGENT_API.md и
  repo-local serialterminal-agent skill.

## Validation / acceptance

- [ ] Reopen того же path для нескольких sessions: все события сохранены,
  correlation keys уникальны и ordering однозначен.
- [ ] TUI session/profile replacement проверяет тот же контракт.
- [ ] Existing timing/flush/close и readers/analyzers корректны для выбранной схемы;
  обработка existing trace согласована с документированной compatibility policy.
- [ ] Relevant timing/TUI/logging tests, full pytest для shared terminal behavior,
  compileall, diff --check и numbered re-review на exact implementation SHA.

## Evidence и Result

Evidence/repro и ограничения сохранены в исходном finding ревью. При оформлении
TODO repro не запускался повторно, fixes и source/tests не изменялись.
Status: OPEN; implementation, regression validation и re-review остаются открыты.
Это task record; hardware, firmware changes, commit/push не выполнялись.
