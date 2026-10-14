# FT1: ограничения durable storage в долгоживущем процессе

TODO-ID: TODO_044
Status: OPEN
Priority: HIGH
Created: 2026-10-14
Implementation: NOT STARTED
Validation: REVIEW FINDING RECORDED / FIX VALIDATION OPEN
Source review: [REVIEW_001/F015](../reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md#f015--high-documented-durable-retentionstorage-bounds-are-enforced-only-at-store-construction)
Reviewed commit: [db740af94c700c7c4e6d96abef7e809dadfcaf1c](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c)
Regression attribution: pre-existing at `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd` по addendum ревью.

## Purpose

Обеспечить действующие count/TTL/partial-byte bounds во время работы одного
долгоживущего агента, сохраняя live-owned state других managers.

## Current behavior

`ResumeStateStore.cleanup()` вызывается при construction, но обычные
`save_incoming/save_outgoing/save_completed` не поддерживают заявленные bounds.
В ревью после создания store с `max_part_bytes=10` сохранились два retained part
по 8 bytes; 40 outgoing journals остались при default count bound 32.
Это подтверждённый дефект enforcement; фактическое исчерпание диска не заявлено.

## Target behavior и Invariants

- Count/TTL/byte policy выполняется на документированных безопасных runtime
  lifecycle/write boundaries, без необходимости создавать новый manager.
- Cleanup не удаляет live admission, `.part`, manifest или journal другого owner.
- При нехватке места результат явный; durable proof не продвигается без сохранения.
- Не терять пригодные recovery state и completed tombstones через гонку cleanup.

## Scope и Design

В scope: resume store lifecycle, runtime enforcement и взаимодействие нескольких
managers, включая процессы, если они используют общий store. Связанный live-part
cleanup defect остаётся `REVIEW_001/F012` в
[TODO_043](TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md).
Историческое подозрение S1 той задачи теперь имеет подтверждение F015.

Перед реализацией определить ownership coordination, безопасные cleanup boundaries
и поведение бюджета при live state, превышающем лимит: admission/error/defer policy
и допустимые временные превышения должны быть явными. Ревью не выбрало механизм.
Не добавлять firmware/radio behavior и произвольные новые protocol limits.

## Implementation

- [ ] Закрепить runtime bounds и active-owner contract, согласовать с F012.
- [ ] Реализовать безопасное enforcement count/TTL/byte limits.
- [ ] Согласовать FT1_RESUME.md, FILE_TRANSFER.md, AGENT_API.md и agent skill
  с реализованными boundaries и error semantics.

## Validation / acceptance

- [ ] Один store без reconstruction: превысить каждый incoming/outgoing/completed
  count limit, TTL и total-part-byte budget; проверить документированные bounds.
- [ ] Два managers/процесса с общим store: live state сохраняется, включая окно
  создания `.part` до первого manifest; expired/non-owned state очищается безопасно.
- [ ] Fault injection cleanup/save и отсутствие свободного бюджета дают явную
  ошибку, сохраняют ownership и последнее пригодное durable state.
- [ ] Retained resume и lost-RESULT tombstones продолжают работать.
- [ ] Relevant store/recovery tests, full pytest, compileall, diff --check и новое
  numbered re-review на exact implementation SHA.

## Evidence и Result

Evidence/repro и ограничения сохранены в исходном finding ревью. При оформлении
TODO repro не запускался повторно, fixes и source/tests не изменялись.
Status: OPEN; implementation, regression validation и re-review остаются открыты.
Это task record; hardware, firmware changes, commit/push не выполнялись.
