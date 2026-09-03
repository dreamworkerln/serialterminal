# TODO Management Policy

## Purpose

Этот документ задаёт универсальные правила ведения инженерных TODO внутри проекта.

Цель системы:

- иметь стабильные идентификаторы задач;
- отделять подробную историю задачи от текущей карты состояния проекта;
- явно различать implementation и validation;
- фиксировать точные revisions/checkpoints вместо формулировок вроде «последняя версия работает»;
- сохранять понятный порядок следующих действий;
- не превращать корень проекта в набор разрозненных временных checklist-файлов.

Политика не зависит от языка программирования, платформы, типа продукта, CI-системы или конкретной структуры исходного кода.

---

## 1. Область действия и `<PROJECT_ROOT>`

В этом документе:

```text
<PROJECT_ROOT>
```

означает **каталог проекта, в котором находится этот `TODO_MANAGEMENT_POLICY.md`**.

Если файл лежит в корне репозитория — `<PROJECT_ROOT>` является корнем репозитория.

Если репозиторий содержит несколько самостоятельных подпроектов и файл лежит внутри одного из них — `<PROJECT_ROOT>` является корнем именно этого подпроекта.

Все относительные пути в этой политике считаются относительно `<PROJECT_ROOT>`.

Например:

```text
<PROJECT_ROOT>/TODO_INVENTORY.md
<PROJECT_ROOT>/TODO_MANAGEMENT_POLICY.md
<PROJECT_ROOT>/todos/
```

`<PROJECT_ROOT>` — это обозначение в документации, **не буквальное имя каталога**. При применении политики нужно использовать реальный каталог, в котором находится этот файл.

### Правило для AI / automation

Если AI, агент или другой автоматизированный инструмент читает этот файл из проекта, он должен:

1. считать каталог этого файла текущим `<PROJECT_ROOT>`;
2. применять правила к TODO-системе этого проекта;
3. разрешать все относительные пути от этого каталога;
4. не требовать заранее знать имя проекта;
5. не создавать каталог с буквальным именем `<PROJECT_ROOT>`.

Таким образом один и тот же файл можно переносить между проектами без ручной замены имени проекта внутри политики.

---

## 2. Постоянные точки входа

Два файла являются постоянными точками входа TODO-системы и остаются непосредственно в `<PROJECT_ROOT>`:

```text
<PROJECT_ROOT>/TODO_INVENTORY.md
<PROJECT_ROOT>/TODO_MANAGEMENT_POLICY.md
```

Их роли различаются:

```text
TODO_INVENTORY.md
    текущая карта состояния проекта

TODO_MANAGEMENT_POLICY.md
    правила ведения TODO-системы
```

Тематические задачи хранятся отдельно:

```text
<PROJECT_ROOT>/todos/
```

Это позволяет быстро найти текущее состояние проекта, не смешивая его с подробными design/checklist/history-файлами отдельных задач.

---

## 3. Рекомендуемая структура

Минимальная структура:

```text
<PROJECT_ROOT>/
  TODO_INVENTORY.md
  TODO_MANAGEMENT_POLICY.md

  todos/
    TODO_001_<SHORT_STABLE_NAME>.md
    TODO_002_<SHORT_STABLE_NAME>.md
    TODO_003_<SHORT_STABLE_NAME>.md
    ...
```

Остальная структура проекта не регламентируется этой политикой.

Например, рядом могут существовать:

```text
README.md
ARCHITECTURE.md
docs/
src/
include/
tests/
scripts/
firmware/
backend/
frontend/
hardware/
...
```

`TODO_INVENTORY.md` и `TODO_MANAGEMENT_POLICY.md` не получают numeric TODO-ID и не переносятся в `todos/`: это инфраструктура системы, а не отдельные задачи.

---

## 4. Сквозной TODO-ID

Каждый тематический TODO получает постоянный auto-increment ID:

```text
TODO_001
TODO_002
TODO_003
...
```

Каноническое имя файла:

```text
todos/TODO_<NNN>_<SHORT_STABLE_NAME>.md
```

Примеры:

```text
todos/TODO_001_AUTH_FLOW.md
todos/TODO_002_CACHE_INVALIDATION.md
todos/TODO_003_RELEASE_AUTOMATION.md
```

Правила:

1. Новый TODO получает `max(existing TODO IDs) + 1`.
2. Номер никогда не переиспользуется, даже если TODO закрыт, архивирован или superseded.
3. TODO не перенумеровываются для устранения дырок.
4. При уточнении названия можно изменить descriptive suffix, но `TODO_<NNN>` остаётся прежним.
5. В ссылках желательно указывать минимум ID, а лучше canonical path.
6. ID означает идентичность задачи, а не приоритет, дату, ветку или статус.

При первой миграции старых ненумерованных TODO номера назначаются один раз и затем считаются постоянными. Они не обязаны отражать исторический порядок создания старых файлов.

---

## 5. Роль `TODO_INVENTORY.md`

`TODO_INVENTORY.md` — **authoritative current-state index**.

Он должен быстро отвечать:

```text
какие TODO существуют
где лежит каждый TODO
каков текущий статус каждой задачи
что уже реализовано
что ещё требует validation
что OPEN / PARTIAL / BLOCKED / DEFERRED / SUPERSEDED
какие exact revisions/checkpoints относятся к текущему состоянию
какой следующий порядок работ
```

Пример компактной записи:

```text
TODO_012 — todos/TODO_012_IMPORT_PIPELINE.md
    parser rewrite                 CLOSED / tests PASS
    large-file handling            IMPLEMENTED / integration validation OPEN
    retry policy                   OPEN
```

Inventory не должен копировать весь тематический TODO. Подробный design/history/checklist живёт в профильном файле.

Если старый checkbox внутри тематического TODO расходится с текущим inventory, сначала нужно установить фактическое состояние по коду, тестам и checkpoint-данным, затем синхронизировать оба документа.

---

## 6. Что хранит тематический TODO

Обычно тематический TODO содержит:

```text
problem statement
purpose
current behavior
target behavior
scope
non-goals
constraints / invariants
design decisions
implementation checklist
validation checklist
observed findings
known limitations
exact implementation revisions
exact validation checkpoints
follow-up work
```

TODO должен быть достаточно самодостаточным, чтобы другой разработчик или AI понял:

- что требуется сделать;
- зачем это требуется;
- какие решения уже приняты;
- что нельзя сломать;
- чем будет доказано завершение;
- что уже было проверено;
- что остаётся открытым.

---

## 7. Стандартные статусы

Использовать небольшой фиксированный набор статусов.

### `OPEN`

Работа ещё не реализована.

### `IMPLEMENTED`

Изменение уже существует, но обязательный validation ещё не завершён.

Например:

```text
IMPLEMENTED / integration validation OPEN
```

Такую задачу нельзя считать `CLOSED`.

### `PARTIAL`

Часть scope завершена, часть остаётся открытой.

В TODO и inventory необходимо явно разделять завершённые и незавершённые части.

### `CLOSED`

Implementation и все обязательные validation gates завершены.

Желательно фиксировать:

```text
Implemented: <revision/checkpoint>
Validated:   <revision/checkpoint + test result>
```

### `DEFERRED`

Работа намеренно отложена.

Нужно указать причину, зависимость или условие возвращения к задаче.

### `BLOCKED`

Продолжение невозможно из-за конкретной внешней зависимости.

Не использовать `BLOCKED` вместо обычного `OPEN` только потому, что задача пока не начата.

### `SUPERSEDED`

Задача или design заменены другим решением.

Старый TODO и его ID не удаляются и не переиспользуются. В документе должна быть ссылка на заменивший TODO или решение.

---

## 8. Implementation и validation — разные состояния

Наличие изменений само по себе не означает завершение задачи.

Общая модель:

```text
OPEN
  ↓
IMPLEMENTED
  ↓
REQUIRED VALIDATION GATES
  ↓
CLOSED
```

Конкретные validation gates определяются типом задачи.

Возможные gates:

```text
build / compile
unit tests
integration tests
static analysis
lint / typecheck
manual validation
hardware validation
performance benchmark
security review
compatibility/regression test
staging validation
production observation
documentation review
```

Не каждой задаче нужны все gates. Нужные gates должны быть перечислены явно в тематическом TODO.

Пример:

```text
Feature X
    IMPLEMENTED
    unit tests PASS
    integration tests PASS
    migration rehearsal PASS
    CLOSED
```

Другой пример:

```text
Documentation cleanup
    IMPLEMENTED
    technical review PASS
    link check PASS
    CLOSED
```

---

## 9. Exact revision discipline

Не использовать как доказательство завершения формулировки:

```text
latest works
current branch tested
current version OK
последний коммит проверен
```

Если проект использует version control, фиксировать точную revision идентичность:

```text
commit SHA
tag
release ID
build ID
artifact digest
PR merge commit
```

Если version control отсутствует, использовать другой однозначный checkpoint:

```text
release version
artifact checksum
snapshot ID
test-run ID
 dated immutable package
```

Полезно различать:

```text
implementation checkpoint
validation checkpoint
docs-only checkpoint
accepted checkpoint
release checkpoint
recovery/snapshot checkpoint
```

Они могут быть разными.

---

## 10. Что делать с полностью выполненным TODO

Закрытый TODO не удаляется автоматически.

В нём сохранить минимум:

```text
Status: CLOSED
Implemented: <revision/checkpoint>
Validated: <revision/checkpoint / tests>
Remaining follow-ups: none / TODO_<NNN>
```

В `TODO_INVENTORY.md` сохранить его ID и статус `CLOSED`.

Закрытые TODO могут оставаться в `todos/`, пока полезны для текущего engineering context.

При необходимости старые закрытые задачи можно архивировать:

```text
todos/archive/
```

При архивировании ID и filename сохраняются:

```text
todos/TODO_014_DATA_EXPORT.md
→ todos/archive/TODO_014_DATA_EXPORT.md
```

Архивирование не должно превращаться в перенумерацию.

---

## 11. Scope: не смешивать unrelated work

Новый TODO должен иметь понятную техническую или продуктовую область.

Плохо:

```text
TODO_021_API_UI_CACHE_RELEASE_EVERYTHING.md
```

Лучше:

```text
TODO_021_API_RETRY.md
TODO_022_UI_ERROR_STATE.md
TODO_023_CACHE_INVALIDATION.md
TODO_024_RELEASE_PIPELINE.md
```

Исторически смешанный TODO можно оставить под существующим ID, но новые независимые follow-ups желательно выделять в отдельные TODO с новыми ID и связывать через inventory.

---

## 12. TODO должен иметь критерий завершения

Недостаточно:

```text
[ ] implement feature
```

Нужно определить acceptance criteria.

Например:

```text
Implementation:
[ ] implement target behavior
[ ] preserve listed invariants
[ ] update affected interfaces/docs

Validation:
[ ] required automated tests
[ ] required integration/manual test
[ ] regression check
```

Или для другой задачи:

```text
Validation:
[ ] benchmark against baseline
[ ] memory limit satisfied
[ ] production-like dataset checked
```

Так переход `IMPLEMENTED → CLOSED` становится объективным.

---

## 13. Findings должны возвращаться в документацию

Существенные факты, обнаруженные во время implementation или validation, не должны оставаться только в чате, issue-комментарии или памяти разработчика.

Новый finding следует записать:

1. в профильный `TODO_<NNN>...md`;
2. кратко в `TODO_INVENTORY.md`, если он меняет текущий статус, риск или порядок работ;
3. в постоянную документацию проекта, если finding является долговременным свойством архитектуры, интерфейса, окружения или эксплуатации.

Пример:

```text
Finding:
External service accepts duplicate requests after client timeout.

Consequence:
Retry implementation requires an idempotency key.
```

Или:

```text
Finding:
Large input files trigger quadratic memory growth.

Consequence:
Streaming parser is required before closing the import TODO.
```

---

## 14. Authoritative next-action order

В `TODO_INVENTORY.md` должен быть один актуальный порядок следующих работ.

Например:

```text
1. finish validation for TODO_004
2. implement TODO_007
3. resolve TODO_009 blocker
4. run final regression gate
5. record accepted revision
6. publish release/snapshot if required
```

Если приоритет изменился — inventory обновляется.

Старый порядок не должен оставаться в документе как будто он всё ещё authoritative.

---

## 15. Snapshot / handoff документы — optional

Некоторые проекты используют отдельные immutable snapshots, handoff-документы, release notes или recovery checkpoints.

Эта политика не требует конкретной системы именования для них.

Если проект использует, например:

```text
HANDOFF_<NNN>.md
SNAPSHOT_<NNN>.md
RELEASE_<VERSION>.md
```

их нумерация должна быть независима от TODO-ID.

Пример:

```text
TODO_004
HANDOFF_011
```

— это нормально.

Snapshot/handoff может ссылаться на TODO по ID/path, но не должен менять их идентичность или перенумеровывать их.

TODO — живой task record.

Snapshot/handoff — снимок состояния в конкретный момент.

---

## 16. Шаблон нового TODO

```markdown
# <Feature / Work Area> TODO

TODO-ID: TODO_<NNN>
Status: OPEN

## Purpose
Почему задача существует.

## Current behavior
Что происходит сейчас.

## Target behavior
Что должно происходить.

## Scope
Что входит в задачу.

## Non-goals
Что намеренно не входит в задачу.

## Invariants
Что нельзя сломать.

## Design
Выбранная архитектура / формат / алгоритм / подход.

## Implementation
- [ ] step 1
- [ ] step 2

## Validation
- [ ] required validation gate 1
- [ ] required validation gate 2
- [ ] regression check

## Findings
Новые факты, обнаруженные во время работы.

## Known limitations
Что намеренно не решается.

## Result
Implemented: `<revision/checkpoint>`
Validated: `<revision/checkpoint / test result>`
Status: `CLOSED`
```

Имя файла создаётся сразу с новым постоянным ID:

```text
todos/TODO_<NNN>_<SHORT_STABLE_NAME>.md
```

---

## 17. Рекомендуемый рабочий цикл

Для существенного изменения:

```text
select/create TODO
→ confirm scope + acceptance criteria
→ implement
→ run required validation
→ record findings
→ update thematic TODO
→ update TODO_INVENTORY.md
→ record exact revision/checkpoint
→ close only when required gates pass
```

Если работа остановилась раньше:

```text
IMPLEMENTED + validation OPEN
```

лучше, чем преждевременный `CLOSED`.

---

## 18. Главное правило

```text
TODO_<NNN> file
    = постоянная идентичность задачи
      + подробная инженерная история
      + implementation/validation checklist

TODO_INVENTORY.md
    = authoritative current-state map всех TODO проекта

TODO_MANAGEMENT_POLICY.md
    = универсальные правила ведения этой системы

<PROJECT_ROOT>
    = реальный каталог, содержащий этот policy-файл
```

Коротко:

```text
implement
→ validate
→ document
→ update inventory
→ record exact checkpoint
```

Задача считается завершённой не тогда, когда изменения написаны, а тогда, когда выполнены её заранее определённые acceptance/validation criteria и это состояние зафиксировано в TODO-системе.
