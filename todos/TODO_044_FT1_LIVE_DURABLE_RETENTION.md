# FT1: ограничения durable storage в долгоживущем процессе

TODO-ID: TODO_044
Status: IMPLEMENTED / LOCAL VALIDATION PASS / CI AND RE-REVIEW OPEN
Priority: HIGH
Created: 2026-10-14
Implementation: CYCLIC HOST RETENTION AND REGRESSIONS IMPLEMENTED
Validation: HOST SOFTWARE 775 PASS / CI AND RE-REVIEW OPEN
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

## Выбор оператора — 2026-10-15

Оператор выбрал циклическую очистку недокачанных данных: при нехватке места
старые неактивные partial-файлы автоматически уступают место новым, как записи
автомобильного регистратора. Простого отказа в новой передаче при наличии
доступных для удаления старых partial недостаточно.

Принятая policy:

- Очистка работает во время жизни manager: на admission/checkpoint/write
  boundaries, а не только при construction. Перед ростом partial проверяется
  бюджет; фактическая нехватка места при записи также запускает reclamation.
- Если превышается partial-byte budget или заканчивается свободное место на
  файловой системе, удалять самые старые неактивные служебные `.part` вместе
  с их incoming manifests, пока можно безопасно продолжать текущую запись.
  После освобождения места повторять запись; received map и durable cursor
  продвигаются только после успешного сохранения.
- Пока у передачи есть live owner, её state/partial/journal не удаляется,
  в том числе другим процессом. Если подходящих старых данных уже нет,
  завершать операцию явным storage failure, сохраняя последнее пригодное
  состояние текущей передачи. Не устраивать бесконечный retry без освобождения.
- Итоговые полностью скачанные пользовательские файлы и исходники отправки
  не являются содержимым этого циклического буфера и не удаляются.
- Действующие defaults сохраняются: TTL 7 суток; incoming 32, outgoing 32,
  completed tombstones 64; суммарные служебные partial 1 GiB. Completed limit
  относится только к служебным записям, а не к итоговым файлам пользователя.

Это согласование поведения для последующей реализации TODO_044 по порядку
после TODO_043. На момент согласования runtime ещё не менялся: startup cleanup не следовало выдавать
за уже реализованную циклическую очистку. Проверки должны покрыть реальную
ошибку ENOSPC/эквивалентный fault injection, продолжение записи после eviction,
отсутствие подходящих жертв и защиту active/final files.

## Implementation

- [x] Закрепить runtime bounds и active-owner contract, согласовать с F012.
- [x] Реализовать безопасное enforcement count/TTL/byte limits.
- [x] Согласовать FT1_RESUME.md, FILE_TRANSFER.md, AGENT_API.md и agent skill
  с реализованными boundaries и error semantics.

## Validation / acceptance

- [x] Один store без reconstruction: превысить каждый incoming/outgoing/completed
  count limit, TTL и total-part-byte budget; проверить документированные bounds.
- [x] Два managers/процесса с общим store: live state сохраняется, включая окно
  создания `.part` до первого manifest; expired/non-owned state очищается безопасно.
- [x] Fault injection cleanup/save и отсутствие свободного бюджета дают явную
  ошибку, сохраняют ownership и последнее пригодное durable state.
- [x] Retained resume и lost-RESULT tombstones продолжают работать.
- [ ] Relevant store/recovery tests, full pytest, compileall, diff --check и новое
  numbered re-review на exact implementation SHA.

## История: evidence при создании задачи

Evidence/repro и ограничения сохранены в исходном finding ревью. При оформлении
TODO repro не запускался повторно, fixes и source/tests не изменялись.
Status: OPEN; implementation, regression validation и re-review остаются открыты.
Это task record; hardware, firmware changes, commit/push не выполнялись.

## Implementation checkpoint — 2026-10-15

Base45f4042. Count/TTL are enforced during durable saves/checkpoints and release;
claim admission counts live pre-manifest leases as occupied slots. Namespace locks
serialize cross-process capacity checks with partial writes. Before growth, old
inactive partials are evicted to fit the byte budget/free space; ENOSPC/EDQUOT
triggers an idempotent retry only after an actual eviction. Part writes, manifest
replace, checkpoint fsync, materialization and exclusive publication use this path.
A failed partial write does not advance received ranges; unavailable victims or
cleanup failure preserve the last useful current state with explicit failure.
No final/source user file is evicted. Constructor cleanup remains crash fallback;
no timer, firmware behavior or new command is introduced.

Permanent tests cover count bounds for all three kinds without reconstruction,
TTL on a subsequent save, oldest-first budget eviction, disk free-space pressure,
partial ENOSPC/EDQUOT followed by exact-offset retry, failure with no victims,
manifest proof preservation, cleanup fault, live-owner protection, live-count
admission refusal, concurrent growth and another-process ownership. Exact-file
completion after rolling out old partial data is covered.
Targeted retention/atomic/publication/ownership suite63 PASS/14.93s before adding
the final two concurrency tests; full suite in progress. Re-review/CI/hardware OPEN;
no push, firmware or device run performed.

Full-run follow-up: first run735 PASS/3 FAIL exposed destructive cleanup on
low-level lease rollback for corrupt/symlinked incoming manifests; cleanup now
runs on settled manager release, not on temporary storage-lease rollback. A
permanent regression retains both untrusted manifest and partial until explicit
admission rejection. The third failure was the existing short control-META loss
scenario under full-run timing; it passed unchanged in the targeted54-test suite
(13.02s). Final full suite is rerunning on the corrected source.

Final isolated-cache full suite739 PASS/104.94s; compileall and diff-check PASS.
Exact implementation trees: src `4f816b3cbf2ab66c7d5f9b89e35602d0bd101e10`; tests `bc6dce72e7931e38a579450c915ff452b5b79b43`.

## Exact-repro verification follow-up — 2026-10-15

Final series verification repeated F015 directly: two8-byte parts followed by
save_incoming under max_part_bytes10 still retained16 bytes, bypassing the normal
DATA growth path. Checkpoint save now enforces the existing byte budget under
the same namespace lock, protecting the current part and evicting inactive older
parts before advancing proof. An over-budget set of live-owned parts explicitly
refuses checkpoint without replacing its last manifest. Sender candidate lookup
also excludes expired journals before admission can protect/revive them.
Permanent regressions include the exact8+8/10 repro, all-live checkpoint refusal
and expired candidate selection. These refine the accepted runtime boundaries;
no retention setting, wire limit or final-file policy changes.

A short control-META regression intermittently consumed its synthetic0.08s budget
in real fsync latency before the first retried child META was admitted. A40-run
diagnostic reproduced this at iteration19 (ROOT timeout before child admission).
Its fsync is now isolated as a no-op for that protocol-budget test; real file/flush,
retry counts, completion/failure assertions and <1s bounds remain. Actual durability
ordering/fault injection remains covered by separate storage/atomic tests.

Follow-up targeted store/atomic/journal/peer/interval/ownership suite92 PASS/16.08s.
The isolated control-META loss scenario then passed40 consecutive repetitions
with unchanged replay limits and assertions. Final cumulative full suite pending;
its working tree also includes the pending TODO_047 timing change.

Final cumulative working-tree suite:775 PASS/97.88s; compileall and diff-check PASS.
Log SHA256 `86409ba193076ec7a3600b59895700859cb4d93fa1b4f81d465b63c6c50f473f`. This run includes the pending TODO_047 timing
implementation; its exact cumulative src/tests trees are recorded in TODO_047.
The checkpoint-budget/TTL follow-up is committed separately from timing.
