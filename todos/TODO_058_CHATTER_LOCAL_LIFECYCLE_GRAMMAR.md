# Достоверный разбор локального lifecycle Chatter

TODO-ID: TODO_058
Status: IMPLEMENTED / SOFTWARE VALIDATION PASS / INDEPENDENT RE-REVIEW OPEN
Severity: P1
Created: 2026-10-21
Source review: [REVIEW_004/F001](../reviews/REVIEW_004_IMPORTED_FIRMWARE_CLIENT_2026-10-21.md)
Finding checkpoint: `a34631e861d1477c48f5ad2bc15dad15564f73f6`.

## Исходное поведение и purpose (reviewed base)

`profiles/chatter/machine_client.py::feed_line` ищет reset-маркеры как подстроки. USER `first:` вызывает local_controller_reset; `discard_binary_pipeline` удаляет pending при неизменном node epoch/outstanding. Legacy `binary_user.py` также разбирает маркеры без границы USER presentation.

## Target behavior и invariants

Chat/echo с first:, rst:0x…, ESP-ROM:, [SYS] CHATTER READY не меняет mode/epoch и не освобождает pending. Истинные локальные boot/reset события распознаются. Identity сохраняется до terminal outcome или достоверного reset/new-epoch proof.

Связанные TODO_034/035 recovery гарантии сохраняются; прежние software PASS не доказывают устранение этого finding.

## Scope и constraints

Только SerialTerminal source/runtime; firmware read-only. Profile-specific semantics остаются в profile.
Реализована единая грамматика локальных lifecycle-строк в Chatter profile.
Generic session/transport, FT1 protocol и firmware не изменяются. Commit/push,
прошивка и аппаратные прогоны в этой задаче не выполнялись.

## Implementation

- [x] Определить единую profile-owned грамматику lifecycle с исключением USER presentation; generic core/transports не узнают Chatter-маркеры.
- [x] Согласовать machine/legacy lifecycle и discard proof; сохранить reconnect/FT1 recovery и текущий recursive multi missing.

## Validation / acceptance

- [x] Production adapter + node model: все перечисленные chat/echo маркеры, настоящие boot/reset строки, accepted pending при неизменном epoch, fresh epoch и terminal outcome.
- [x] Agent/TUI forwarding и FT1 recovery/settlement regressions; одного усиления rst: до rst:0x недостаточно.
- [x] Все software check-команды существующего CI workflow выполнены локально без второго списка команд; новые tests включены в полный pytest, collection guard защищает это включение. Targeted runs обозначены subset. Python tests вне sandbox; README/ARCHITECTURE/AGENT_API/agent reference проверены и обновлены. Общая инфраструктурная задача TODO_051 этим не объявляется закрытой.
- [ ] Независимое повторное ревью exact fix checkpoint; implementation/software и необходимые platform/hardware gates фиксируются раздельно.

## Evidence и result

[Переданный repro/evidence](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_false_reset.py). Результаты получены на другом Windows-хосте; локально repro не перезапускался.
SHA-256 сверка подтвердила совпадение inventory с working tree и указанным commit.
Implementation: IMPLEMENTED. Software validation: PASS.
Independent acceptance re-review: OPEN.

## Implementation checkpoint — 2026-10-21 UTC

Base: `a34631e861d1477c48f5ad2bc15dad15564f73f6`.
Working-tree checkpoint: [BASE + exact task patch](evidence/TODO_058/implementation.patch),
[SHA-256 manifest и snapshots](evidence/TODO_058/checkpoint.json).
Это не новый commit; прежние локальные изменения импорта ревью в task patch
не входят. Исходный REVIEW_004/F001 сохраняет исторический RED.

`profiles/chatter/controller_lifecycle.py` классифицирует полную локальную строку:
ROM banner, полную rst/boot запись, RADIO FATAL и точный CHATTER READY.
Удаляются только terminal CR/LF; USER/echo префиксы и leading whitespace
не снимаются. Machine, legacy, PHY cache и human presentation используют один
parser. RADIO FATAL теперь согласованно распознаётся всеми четырьмя consumers.
Local output-mode readiness требует `[SYS]` в начале строки, поэтому цитата
current/OUTPUT не завершает reset и не меняет cached output mode.

Pipeline discard, fresh-epoch negotiation, terminal outcomes и reconnect guards
не переписаны: исправлена достоверность входного lifecycle proof. Actor/JSONL
schema не менялась; generic agent и TUI продолжают только forwarding строк.

## Validation и evidence

Все Python проверки выполнялись вне ограничивающего sandbox, без аппаратуры.

| Проверка | Результат | Evidence |
| --- | --- | --- |
| Окончательный regression suite против BASE source (git archive в temp) | 83 cases: 72 FAIL / 11 PASS, 0 errors/skip; false lifecycle воспроизведён | [regression-results.json](evidence/TODO_058/regression-results.json), [baseline JUnit](evidence/TODO_058/baseline-complete.xml) |
| Тот же suite против fixed source | 83 PASS, 0 skip | [fixed JUnit](evidence/TODO_058/fixed-complete.xml) |
| Предварительный соседний targeted subset | 155 PASS; machine/legacy/recovery/PHY/presentation | [targeted JUnit](evidence/TODO_058/targeted.xml) |
| Все named software checks текущего `.github/workflows/ci.yml` | Compile PASS, Ruff PASS, полный `pytest -q`: 1374 PASS / 0 skip; advisory Lizard WARNING exit 1 сохранён как в workflow | [workflow-checks.json](evidence/TODO_058/workflow-checks.json), [runner, читающий workflow](evidence/TODO_058/run_workflow_checks.py) |
| Lizard delta against BASE | CC уменьшается у всех четырёх изменённых функций; новый parser CC3/NLOC7/1 parameter, новых threshold violations нет | [complexity-delta.json](evidence/TODO_058/complexity-delta.json) |
| Semantic diff / definition inventory / comments | PASS, существующие definitions и comments сохранены; dependency direction profile-owned | [source-review.json](evidence/TODO_058/source-review.json), [author self-review](evidence/TODO_058/semantic-review.md) |
| GitHub / physical USB/BLE/RF | NOT RUN; software parser/fake-node proof не выдаётся за hardware evidence | Существующие hardware gates TODO_034/035 остаются отдельно |

Локальная среда: Python 3.10.12; workflow серверной подготовки указывает Python
3.12, remote run не выполнялся. Для полного local software coverage отсутствующие
Ruff/pyte подготовлены в изолированном `/tmp/serialterminal-todo058-qa`;
обязательные pytest/Bleak/dbus_fast/pyte проверены до запуска. Pyproject и системные
зависимости не изменялись. Старые и промежуточные результаты сохранены отдельно;
итог — workflow-checks.json и regression-results.json. Инфраструктурный CI parity
TODO_051 остаётся отдельной задачей, этот fix его общий scope не реализует.

## Remaining acceptance

- [ ] Независимое повторное ревью exact checkpoint/patch. Выполненный author
  self-review не считается независимым.

Status: IMPLEMENTED / SOFTWARE VALIDATION PASS, не CLOSED. Нового обязательного
physical gate для этой line-classification логики не вводилось; gates связанного
FT1 controller recovery не закрывались. Commit/push не выполнялись.
