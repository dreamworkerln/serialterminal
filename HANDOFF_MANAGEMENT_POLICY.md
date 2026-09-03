# Handoff Management Policy

## Purpose

Этот документ задаёт универсальные правила ведения инженерного handoff/recovery состояния проекта.

Цель системы:

- позволить новому разработчику, AI или новой chat/session восстановить рабочий контекст без скрытой памяти;
- отделять текущую незавершённую операцию от стабильных recovery checkpoints;
- сохранять точные historical states как immutable snapshots;
- иметь один маленький mutable указатель на актуальный snapshot;
- фиксировать exact revisions/checkpoints вместо формулировок вроде «текущая ветка» или «последняя версия»;
- не смешивать source-code authority, handoff state и long-lived research/evidence;
- безопасно переживать движение branch heads, смену chat/session и длительные экспериментальные ветки.

Политика не зависит от языка программирования, платформы, количества репозиториев, branching model, CI-системы или конкретного продукта.

---

## 1. Область действия и `<HANDOFF_ROOT>`

В этом документе:

```text
<HANDOFF_ROOT>
```

означает **каталог, в котором находится этот `HANDOFF_MANAGEMENT_POLICY.md` и authoritative handoff infrastructure данного workstream/project**.

Это может быть:

- корень репозитория;
- корень отдельного handoff/recovery branch;
- каталог самостоятельного подпроекта;
- отдельный documentation/recovery repository.

`<HANDOFF_ROOT>` — обозначение в документации, а не буквальное имя каталога.

Все относительные handoff-пути в этой политике считаются относительно `<HANDOFF_ROOT>`.

Например:

```text
<HANDOFF_ROOT>/HANDOFF_INDEX.md
<HANDOFF_ROOT>/HANDOFF_MANAGEMENT_POLICY.md
<HANDOFF_ROOT>/CONTEXT.md
<HANDOFF_ROOT>/HANDOFF_007.md
```

### Правило для AI / automation

Если AI, агент или другой автоматизированный инструмент читает этот файл, он должен:

1. считать каталог этого файла текущим `<HANDOFF_ROOT>`;
2. применять правила только к handoff-системе этого workstream/project;
3. не смешивать соседние handoff-системы только потому, что они находятся в одном repository/account;
4. разрешать относительные пути от фактического `<HANDOFF_ROOT>`;
5. не создавать каталог с буквальным именем `<HANDOFF_ROOT>`.

---

## 2. Основные сущности handoff-системы

Рекомендуемый набор:

```text
<HANDOFF_ROOT>/HANDOFF_MANAGEMENT_POLICY.md
<HANDOFF_ROOT>/HANDOFF_INDEX.md
<HANDOFF_ROOT>/CONTEXT.md                  optional
<HANDOFF_ROOT>/HANDOFF_001.md
<HANDOFF_ROOT>/HANDOFF_002.md
<HANDOFF_ROOT>/HANDOFF_003.md
...
<HANDOFF_ROOT>/KNOWLEDGE_BASE_POLICY.md   optional
```

Дополнительно project/workstream может иметь long-lived evidence/research directories:

```text
notes/
Researches/
docs/research/
measurements/
...
```

Роли принципиально различаются.

```text
HANDOFF_MANAGEMENT_POLICY.md
    правила ведения handoff-системы

HANDOFF_INDEX.md
    маленький mutable current-state pointer / recovery map

CONTEXT.md
    optional mutable write-ahead state для текущей незавершённой операции

HANDOFF_NNN.md
    immutable full recovery snapshot конкретного checkpoint

KNOWLEDGE_BASE_POLICY.md
    optional project-specific правила authority/promotion для long-lived knowledge

notes/ / Researches/ / ...
    подробные long-lived evidence, measurements, rationale и research

source repositories / branches
    authority для реально существующего кода
```

---

## 3. Главное разделение: process, current pointer, snapshot и source

Нельзя использовать один файл одновременно как mutable diary, latest-state pointer и historical snapshot.

Правильное разделение:

```text
HANDOFF_MANAGEMENT_POLICY.md
    как вести систему

CONTEXT.md
    что прямо сейчас делается и может быть прервано

HANDOFF_INDEX.md
    где находится последний verified stable recovery checkpoint

HANDOFF_NNN.md
    каким точно было состояние на checkpoint NNN

source
    что фактически реализовано сейчас
```

Ключевой принцип:

```text
INDEX answers:     where should I look now?
SNAPSHOT answers:  what exactly was known at that checkpoint?
CONTEXT answers:   where did the currently running operation stop?
SOURCE answers:    what code actually exists now?
```

---

## 4. Recovery order

Обычный recovery начинается не с угадывания последнего snapshot filename и не со случайного старого note.

Рекомендуемый порядок:

```text
1. CONTEXT.md, if present and relevant
2. HANDOFF_INDEX.md
3. latest verified HANDOFF_NNN.md named by the index
4. project-specific knowledge-base policy, if present
5. relevant long-lived notes/research/evidence referenced by snapshot/index
6. refetch and inspect actual source revisions named by snapshot/context
7. inspect external repositories/dependencies only when they are part of recorded state
```

`HANDOFF_MANAGEMENT_POLICY.md` нужно читать перед созданием/изменением handoff infrastructure и при сомнении о recovery semantics. Для обычного восстановления рабочего состояния достаточно следовать `HANDOFF_INDEX.md` и latest snapshot.

Если `CONTEXT.md` отсутствует, recovery просто начинается с `HANDOFF_INDEX.md`.

Если `CONTEXT.md` старее latest published snapshot и явно описывает уже завершённую операцию, latest verified snapshot/index имеют приоритет.

---

## 5. `HANDOFF_INDEX.md` — mutable stable entry point

`HANDOFF_INDEX.md` является **единственным маленьким mutable указателем** на latest verified full snapshot.

Он должен быстро отвечать:

```text
какой snapshot последний
где он лежит
какой commit/checkpoint опубликовал snapshot
какие source/repository roles актуальны
какие exact source checkpoints зафиксированы latest snapshot
где находится authoritative knowledge base
есть ли standing reminders / deferred gates
какой recovery order использовать
```

Index не должен копировать весь snapshot.

Он может содержать короткие current-state summaries, но подробное состояние и историю нужно хранить в numbered snapshots и long-lived knowledge docs.

Если index и старый snapshot расходятся о том, что является latest checkpoint, pointer в index определяет latest **published recovery checkpoint**, а фактический current implementation всё равно нужно подтверждать refetch source.

---

## 6. Snapshot numbering

Каноническое имя нового snapshot:

```text
HANDOFF_<NNN>.md
```

где `<NNN>` — zero-padded последовательный номер:

```text
HANDOFF_001.md
HANDOFF_002.md
HANDOFF_003.md
...
```

Правила:

1. Новый meaningful recovery checkpoint получает `max(existing published snapshot numbers) + 1`.
2. Номер не переиспользуется.
3. Старые snapshots не перенумеровываются для устранения дырок.
4. Snapshot ID означает последовательность recovery checkpoints, а не TODO ID, release number, branch number или priority.
5. TODO/snapshot/release counters независимы друг от друга.

### Legacy `HANDOFF.md`

Если существующая система исторически начиналась с файла:

```text
HANDOFF.md
```

его можно формально считать snapshot `001` и оставить под историческим именем.

В этом случае следующий snapshot:

```text
HANDOFF_002.md
```

Не нужно переименовывать старый `HANDOFF.md` только ради нормализации.

Для новой системы предпочтительно сразу начинать с `HANDOFF_001.md`, чтобы имя `HANDOFF.md` не было двусмысленным.

---

## 7. Immutable snapshot rule

Полный snapshot становится immutable после публикации, то есть после того, как `HANDOFF_INDEX.md` начал указывать на него как на latest verified checkpoint.

После публикации нельзя:

- переписывать старый snapshot под новое состояние;
- исправлять исторический checkpoint так, будто ошибка никогда не существовала;
- заменять его содержимое новым handoff;
- менять старые exact SHAs на более свежие moving heads.

Если позже обнаружена ошибка или новое понимание:

```text
старый snapshot остаётся историческим фактом
новый snapshot фиксирует correction / supersession
```

До публикации snapshot можно исправить и повторно проверить. Если snapshot оказался непригоден и index на него не переводился, текущий known-good index должен оставаться на предыдущем snapshot.

Git/VCS history не заменяет эту semantic immutability: published snapshot сам по себе должен оставаться стабильной recovery точкой.

---

## 8. Safe snapshot publication order

Index никогда не должен указывать на snapshot, который ещё не существует или не был проверен.

Обязательный порядок:

```text
1. refetch actual source / dependency heads
2. определить next unused snapshot number
3. создать HANDOFF_NNN.md
4. read-back / verify snapshot content
5. убедиться, что recovery данных достаточно
6. только после этого обновить HANDOFF_INDEX.md -> HANDOFF_NNN.md
7. оставить все older published snapshots unchanged
```

Если шаг 3, 4 или 5 не прошёл:

```text
DO NOT advance HANDOFF_INDEX.md
```

Предпочтительная VCS публикация:

```text
commit A: create verified snapshot
commit B: advance index
```

Это делает failure mode безопасным: pointer всегда остаётся на существующем known-good snapshot.

Если инфраструктура поддерживает атомарную multi-file transaction и проект явно выбрал её, можно использовать её только при сохранении того же semantic invariant: index не должен стать видимым раньше verified snapshot target.

---

## 9. Exact revision / provenance discipline

Immutable snapshot должен позволять реконструировать historical state после движения branches/tags.

Moving branch name недостаточен.

Если используется Git/VCS, source checkpoint записывается как минимум так:

```text
<repository>/<branch>@<full commit SHA>
```

или, когда repository очевиден:

```text
<branch>@<full commit SHA>
```

Для внешних artifacts допустимы другие exact identifiers:

```text
tag
release ID
build ID
artifact digest
package version + checksum
snapshot ID
test-run ID
```

Нельзя считать provenance формулировки:

```text
latest
current branch
current dev
working version
last good build
```

без exact checkpoint.

---

## 10. Универсальный provenance header snapshot

Количество source roles различается между проектами, поэтому policy не навязывает фиксированные имена вроде `Accepted baseline` или `ACK branch`.

Каждый snapshot должен начинаться с compact provenance block, содержащего минимум:

```text
Snapshot: HANDOFF_00N.md
Previous: HANDOFF_00(N-1).md
Created:  YYYY-MM-DDTHH:MM:SSZ
Handoff authority: <repository/ref/path + exact checkpoint when applicable>
Source checkpoints:
  <role A>: <repo/branch>@<full revision>
  <role B>: <repo/branch>@<full revision>
Knowledge base:
  <authority/path + exact revision when applicable>
Transfer / promotion boundary:
  <short description or none>
```

Проект может использовать более конкретные role labels, например:

```text
Accepted baseline
Active work branch
Historical split point
Hardware reference
Reliability branch
UI/client repository
Release branch
Production deployment
```

Главное правило: role label должен описывать **семантическую роль**, а exact revision — конкретное состояние.

Если одна роль не существует, её не нужно выдумывать.

Если source repositories несколько, перечислить все, без которых recovery будет неоднозначным.

Полезно дополнительно записывать handoff-branch/root checkpoint **before snapshot creation**, чтобы snapshot мог показать, от какого recovery state он создавался.

---

## 11. Что обязан содержать full snapshot

Snapshot не должен быть просто длинным журналом коммитов.

Он должен обеспечивать восстановление engineering state.

Обычно включать:

```text
provenance header
recovery / authority rules
source/repository/branch roles
material changes since previous snapshot
accepted architecture / invariants
important do-not-change boundaries
current implementation state
what is explicitly NOT implemented
validation actually run
validation still pending
hardware / environment findings when relevant
known limitations / risks
important knowledge-base documents
promotion / selective-transfer boundary
immediate continuation steps
standing reminders / deferred gates when they matter
```

Глубокие подробности, измерения и длинные design rationale лучше держать в long-lived knowledge docs и ссылаться на них из snapshot.

Snapshot должен быть достаточно самодостаточным, чтобы reader понял текущую форму системы и смог найти подробности, но не обязан дублировать всю project documentation.

---

## 12. Implementation и validation должны быть разделены

Handoff обязан отличать:

```text
implemented
built
statically checked
automated tests passed
integration tested
hardware tested
accepted
promoted/released
```

Не писать:

```text
works
validated
ready
```

если фактически был выполнен только более узкий gate.

Полезные формулировки:

```text
IMPLEMENTED / full validation OPEN
build PASS / hardware validation PENDING
unit tests PASS / integration test NOT RUN
hardware-tested checkpoint: <exact revision>
```

Snapshot должен явно различать доказательства, реально полученные на exact checkpoint, и validation, который ещё только требуется.

Нельзя приписывать новому docs-only/source-only HEAD validation, выполненный на старом checkpoint, если релевантные изменения могли повлиять на результат.

---

## 13. `CONTEXT.md` — optional mutable write-ahead state

`CONTEXT.md` нужен не как второй snapshot, а как восстановление **текущей незавершённой операции**.

Использовать его для substantial multi-step work, например:

```text
multi-file refactor
protocol migration
branch-to-branch structural port
series of dependent commits
long hardware-debug sequence
release/promotion procedure
work with critical DO-NOT-CHANGE invariants
```

Не обязательно обновлять `CONTEXT.md` для каждой trivial one-line edit.

Полезный `CONTEXT.md` содержит:

```text
Status
Current operation / goal
Source role + exact baseline checkpoint
Target role + exact baseline checkpoint, if applicable
Planned scope
Explicit invariants / do-not-change rules
Last completed action
Current/next action
Validation required
Known blockers
```

`CONTEXT.md` mutable и обычно **перезаписывается** новым write-ahead state, а не превращается в append-only diary.

История изменений сохраняется VCS.

Когда операция завершена:

- можно временно отметить её completed;
- затем overwrite при следующей substantial operation;
- если состояние стало material stable recovery checkpoint, создать новый immutable `HANDOFF_NNN.md`.

`CONTEXT.md` не заменяет snapshot.

---

## 14. Source authority и handoff authority — разные вещи

Handoff infrastructure не должна становиться копией production/source tree.

Если используется отдельный handoff branch/repository:

```text
handoff branch/repository
    recovery, snapshots, research pointers, context

source branch/repository
    actual implementation
```

По умолчанию не следует писать production code в dedicated handoff branch.

Snapshot фиксирует exact observed source state, но не становится source-code authority.

Правило при расхождении:

```text
snapshot
    authority for what was known/accepted at historical checkpoint

refetched source
    authority for what code actually exists now
```

Перед новым code work или утверждением о current implementation нужно refetch соответствующий moving source ref.

---

## 15. Long-lived knowledge / evidence

Подробные исследования не нужно копировать целиком в каждый handoff snapshot.

Проект может иметь long-lived knowledge location:

```text
notes/
Researches/
docs/research/
measurements/
```

Snapshot/index должны указывать, где находится authoritative knowledge и, когда важна reconstructability, на каком exact revision.

Пример:

```text
Knowledge base:
    <repo>/<branch>@<full SHA>:notes/
```

Historical notes могут содержать implementation-state statements, которые позже устарели.

Поэтому нужно различать:

```text
active source
    current implementation truth

latest snapshot/index
    current recovery map / accepted checkpoint state

historical notes
    evidence, measurements, rationale and accepted findings at their time
```

Если новое evidence supersedes старую интерпретацию, предпочтительно добавить новый note/snapshot с явным supersession, а не молча переписывать historical evidence.

---

## 16. Knowledge transfer / promotion / selective port

Не все workstreams используют обычный whole-branch merge.

Возможны:

```text
experimental -> accepted branch promotion
reference implementation -> selective port
old architecture -> structural migration
multi-repository release
prototype -> production rewrite
```

Snapshot должен явно записать соответствующую boundary.

Примеры generic формулировок:

```text
Promotion boundary:
    experiment -> accepted baseline

Transfer boundary:
    selective transfer only; no whole-tree overwrite

Release boundary:
    source checkpoint -> release artifact
```

При transfer/promotion нужно отдельно проверить long-lived knowledge:

1. какие архитектурные требования должны перейти в accepted docs/source;
2. какие research/evidence notes нужно сохранить;
3. какие intermediate findings уже superseded;
4. где после transfer находится canonical knowledge owner.

Не переносить только код, теряя важные hardware/design conclusions.

---

## 17. Source-side `HANDOFF.md` pointer — optional

Если authoritative handoff живёт отдельно от active source, source branch/project может содержать маленький pointer/reminder файл, например:

```text
HANDOFF.md
```

Его задача только сказать:

```text
где находится authoritative handoff root
что первым читать HANDOFF_INDEX.md
что full snapshots живут только там
что current source HEAD нужно refetch перед code work
```

Такой source-side pointer **не должен превращаться во второй full mutable handoff**.

Это предотвращает две конкурирующие recovery histories.

Если source-side `HANDOFF.md` используется как pointer, authoritative snapshot series лучше именовать `HANDOFF_001.md`, `HANDOFF_002.md`, ... без двусмысленного mutable `HANDOFF.md`.

Legacy systems могут сохранять исторический `HANDOFF.md` snapshot 001 на authoritative handoff branch и одновременно tiny pointer `HANDOFF.md` на отдельных source branches, потому что это разные refs/locations.

---

## 18. `HANDOFF_INDEX.md` и long-lived reminders

Некоторые workstreams имеют deferred обязательство, которое легко потерять при длительном detour:

```text
run a pending validation gate
perform security review before release
recheck hardware before promotion
wait for external approval
```

Такой reminder можно хранить кратко в `HANDOFF_INDEX.md`, если он влияет на следующий material step.

Правила:

- reminder должен быть action-oriented;
- не заменять им TODO-систему;
- удалять/закрывать его только после выполнения или явного решения больше не требовать;
- если reminder является полноценной engineering task, лучше также иметь соответствующий TODO.

---

## 19. Взаимодействие с TODO-системой

Handoff и TODO решают разные задачи.

```text
TODO_<NNN>
    постоянная идентичность engineering task

HANDOFF_<NNN>
    последовательный recovery snapshot проекта/workstream
```

Их counters независимы.

Snapshot может ссылаться на TODO по ID/path:

```text
Open work:
- TODO_007 — ...
- TODO_011 — ...
```

Не нужно копировать весь thematic TODO внутрь handoff.

`TODO_INVENTORY.md` отвечает на вопрос «какие задачи и статусы сейчас существуют».

`HANDOFF_INDEX.md` отвечает на вопрос «какой recovery checkpoint latest и где искать состояние».

`HANDOFF_NNN.md` фиксирует exact cross-cutting state проекта в момент snapshot.

---

## 20. Failure / inconsistency handling

### Snapshot создан, но verification не прошёл

```text
не двигать index
исправить/пересоздать snapshot
повторить read-back verification
```

### Index случайно указывает на отсутствующий/невалидный snapshot

Это broken recovery state.

Исправить index на последний verified existing snapshot и зафиксировать correction.

### Snapshot содержит stale moving branch SHA

Если snapshot уже опубликован, не переписывать его.

Создать новый snapshot с актуальными exact refs и объяснить изменение.

### Historical note противоречит current source

Для current implementation refetch source.

Для historical rationale/evidence сохранить note и при необходимости добавить superseding document.

### `CONTEXT.md` противоречит latest snapshot

Определить, является ли context незавершённой более новой операцией.

Если нет — snapshot/index имеют приоритет; context нужно обновить.

---

## 21. Когда создавать новый full snapshot

Не нужен новый snapshot после каждого commit.

Он оправдан, когда состояние стало meaningful recovery checkpoint, например:

```text
закончена крупная phase
принято архитектурное решение с большим blast radius
завершена substantial validation
изменились branch/repository roles
изменился knowledge-base owner
выполнен promotion / selective port / release
перед длинным detour
после длинного detour перед сменой направления
перед передачей работы другому developer/AI/session
```

Мелкие code/doc edits могут жить между snapshots, если `CONTEXT.md`/source history достаточно для recovery.

---

## 22. Template: `HANDOFF_INDEX.md`

Минимальный generic шаблон:

```markdown
# Handoff index

This file is the mutable stable recovery entry point.

## Recovery order
1. CONTEXT.md, if present and relevant
2. HANDOFF_INDEX.md
3. latest snapshot named below
4. project-specific knowledge policy / long-lived notes
5. refetch actual source checkpoints

## Snapshot rules
- HANDOFF_NNN.md snapshots are append-only after publication.
- Create and verify snapshot before advancing this index.

## Current latest snapshot
Snapshot: <NNN>
File: HANDOFF_<NNN>.md
Snapshot publication checkpoint: <exact revision>

## Current source roles
<role>: <repo/branch>@<full revision>
...

## Knowledge base
<authority/path + exact revision when applicable>

## Immediate continuation
<short ordered actions>

## Standing reminders
<only material deferred gates, if any>
```

Index может быть подробнее, если workstream сложный, но должен оставаться заметно компактнее full snapshot.

---

## 23. Template: `CONTEXT.md`

```markdown
# Current work context

Status: <IN PROGRESS / PAUSED / COMPLETED / BLOCKED>

## Current operation
<goal>

## Exact baselines
Source: <repo/branch>@<full revision>
Target: <repo/branch>@<full revision>  # if applicable

## Scope
<what is being changed>

## Invariants / do not change
- ...

## Last completed action
...

## Next action
...

## Required validation
- ...

## Blockers / findings
- ...
```

Этот файл mutable и предназначен для interrupted work, а не для long-term immutable history.

---

## 24. Template: `HANDOFF_NNN.md`

````markdown
# Handoff snapshot NNN

```text
Snapshot: HANDOFF_NNN.md
Previous: HANDOFF_MMM.md
Created: YYYY-MM-DDTHH:MM:SSZ
Handoff authority: <location + exact checkpoint>
Source checkpoints:
  <role A>: <repo/branch>@<full revision>
  <role B>: <repo/branch>@<full revision>
Knowledge base: <location + exact revision/path>
Transfer / promotion boundary: <description or none>
```

This snapshot becomes immutable after publication through HANDOFF_INDEX.md.

## 1. Recovery / authority
<roles, source authority, refetch rule>

## 2. Material changes since previous snapshot
- ...

## 3. Current implementation state
- implemented: ...
- not implemented: ...

## 4. Architecture / invariants
- ...

## 5. Validation evidence
Actually run / observed:
- ...

Still pending:
- ...

## 6. Findings / limitations / risks
- ...

## 7. Knowledge references
- <path / document>

## 8. Transfer / promotion notes
- ...

## 9. Immediate continuation
1. ...
2. ...
3. ...

## 10. Standing reminders
- ...
````

Sections that do not apply may be omitted, but provenance, implementation/validation distinction and continuation point should remain explicit.

---

## 25. AI / automation publication rules

При автоматизированном handoff агент должен:

1. refetch relevant source heads immediately before snapshot creation;
2. inspect `HANDOFF_INDEX.md` and existing snapshots to determine next unused number;
3. never guess the latest snapshot solely from memory;
4. never overwrite an already published snapshot;
5. record full exact revisions for all material source roles;
6. create snapshot before changing index;
7. read back the created snapshot from authoritative storage;
8. verify required provenance and recovery sections;
9. only then advance `HANDOFF_INDEX.md`;
10. read back the updated index;
11. never claim build/test/hardware validation that was not actually performed;
12. keep production/source modifications separate from handoff-only changes unless explicitly requested;
13. preserve project-specific branch/repository authority boundaries;
14. prefer incomplete-but-truthful state over invented certainty.

Если нужный exact source state нельзя подтвердить, snapshot должен явно сказать, что он не подтверждён, а не подставлять guessed SHA/state.

---

## 26. Главное правило

```text
HANDOFF_MANAGEMENT_POLICY.md
    = универсальные правила ведения recovery/handoff системы

CONTEXT.md
    = mutable write-ahead state незавершённой substantial operation

HANDOFF_INDEX.md
    = mutable pointer / current recovery map

HANDOFF_NNN.md
    = immutable exact recovery checkpoint after publication

long-lived notes / research
    = detailed evidence, measurements and rationale

source
    = authority for actual current implementation
```

Коротко:

```text
refetch
→ snapshot exact state
→ read/verify snapshot
→ advance index
→ preserve old snapshots
```

Handoff считается надёжным не тогда, когда существует длинный markdown-файл, а тогда, когда reader может однозначно восстановить:

```text
что было принято
что реально реализовано
что реально проверено
какие exact revisions относятся к этому состоянию
где лежит подробное evidence
что нельзя потерять
и что делать следующим
```
