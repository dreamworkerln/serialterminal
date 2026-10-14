# Review Management Policy

## Purpose

Эта политика задаёт правила хранения инженерных ревью по аналогии с
[TODO Management Policy](TODO_MANAGEMENT_POLICY.md). Ревью фиксирует оценку
конкретного состояния проекта; TODO ведёт работу по исправлению findings.
Методика проверки SerialTerminal описана в [REVIEWER.md](REVIEWER.md), правила работы
с репозиторием — в [AGENTS.md](AGENTS.md).

## 1. Структура и точки входа

`<PROJECT_ROOT>` — каталог, содержащий эту политику; здесь это корень репозитория SerialTerminal.
Все пути ниже считаются относительно этого каталога.

```text
<PROJECT_ROOT>/
  REVIEW_MANAGEMENT_POLICY.md
  REVIEW_INVENTORY.md
  reviews/
    REVIEW_001_<SHORT_STABLE_NAME>.md
    REVIEW_002_<SHORT_STABLE_NAME>.md
    ...
```

Policy задаёт правила и шаблон. Inventory содержит компактный реестр ревью,
их targets, verdicts и связей. Подробные findings и evidence живут в `reviews/`.
Policy и inventory не получают REVIEW-ID.

## 2. Сквозной REVIEW-ID

Каждое отдельное ревью получает постоянный ID `REVIEW_<NNN>` и имя файла:

```text
reviews/REVIEW_<NNN>_<SHORT_STABLE_NAME>.md
```

Например: `reviews/REVIEW_001_FT1_RECOVERY.md`.

1. Новый номер — максимальный уже выделенный REVIEW-ID + 1; первый — `001`.
   Проверить inventory, файлы в `reviews/` и его архиве, а при расхождении —
   историю Git. Сверить поле `Next new review ID` перед созданием файла.
2. Нумерация независима от TODO-ID. Число содержит минимум три цифры;
   после `999` последовательность продолжается `1000`.
3. Номер не переиспользуется после завершения, отмены или архивирования.
   Пропуски не заполняются, старые файлы не перенумеровываются.
4. При создании файла одновременно добавить запись в inventory и увеличить
   `Next new review ID`. Это правило выделения номера, а не отдельный генератор.
5. При конфликте номеров из параллельных изменений сохранить существующий ID,
   новому ревью выделить следующий свободный и исправить его ссылки до commit.

## 3. Точный target и ссылки на commits

До начала проверки зафиксировать:

- репозиторий, ветку, дату UTC и автора/агента ревью;
- полный 40-hex SHA reviewed commit и Markdown-ссылку на этот commit;
- полный SHA base и ссылку на него для ревью изменения, диапазон `BASE..TARGET`;
- источник выбора base: accepted checkpoint, предыдущий review или условие задачи;
- состояние checkout при проверке: `clean` либо `dirty`;
- task/TODO/spec, scope проверки и существенные исключённые области.

Для этого репозитория ссылка имеет вид:
`https://github.com/dreamworkerln/serialterminal/commit/<FULL_SHA>`.
Ссылка на compare может дополнять SHA, но не заменять его. Для неопубликованного
commit сохранить полный SHA и указать, что ссылка станет доступна после публикации.
Не подменять target веткой, `HEAD`, сокращённым SHA или commit самого отчёта.

Для ревью всего snapshot base можно указать как `N/A — snapshot review`.
Если base нужен, но неизвестен, записать `UNKNOWN` и ограничение; не придумывать
accepted base. GREEN нельзя использовать для утверждения о непроверенном diff.

Dirty checkout обозначать как `HEAD + patch`, а не как ревью чистого HEAD.
Сохранить точный patch/snapshot с checksum и доступным evidence pointer; учесть
untracked файлы, если они входят в scope. Один SHA HEAD не идентифицирует dirty
source. Commit, созданный позже, можно добавить как transport checkpoint после
подтверждения идентичности; исходный reviewed target не переписывать.

## 4. Status и verdict

Status описывает выполнение самого ревью:

| Status | Значение |
| --- | --- |
| IN_PROGRESS | Проверка начата, итог ещё не сформирован. |
| COMPLETE | Запрошенный scope рассмотрен, итог и ограничения записаны. |
| BLOCKED | Проверку нельзя закончить из-за указанной внешней зависимости. |
| CANCELLED | Проверка отменена; причина сохранена. |

Verdict хранится отдельно:

| Verdict | Значение |
| --- | --- |
| NOT_ISSUED | Итог ещё не выдан. |
| RED | Найдены дефекты, препятствующие acceptance заявленного scope. |
| GREEN | В проверенном scope нет препятствий acceptance; обязательные для него gates подтверждены. |
| INCONCLUSIVE | Evidence недостаточно для вывода; перечислены недостающие проверки. |

`COMPLETE / RED` — завершённое ревью с отрицательным результатом. GREEN software
review не закрывает незавершённые CI/hardware/release gates TODO. Указать область
verdict явно; отсутствие findings не означает автоматически GREEN всего проекта.

## 5. Findings и validation

Нумеровать findings внутри отчёта: `F001`, `F002`, …; ссылаться полным сочетанием
`REVIEW_001/F001`. Не перенумеровывать и не удалять findings после исправления.
Расположить их по severity согласно `REVIEWER.md`, перед итоговой оценкой.

Каждый существенный finding содержит:

- severity и короткое название;
- exact path/function/lines в reviewed target;
- проверенное поведение и достижимый failure scenario;
- impact, evidence/repro и пробел существующих тестов, если применимо;
- явно отделённые hypotheses и непроверенные предположения;
- acceptance criteria и ссылку на TODO, если исправление уже заведено.

Validation записывать таблицей: команда/проверка, exact checkpoint, результат,
вид evidence и ограничения. Различать выполненные reviewer проверки, переданные
оператором результаты и выводы по source inspection. Для не выполненных проверок
писать `NOT RUN`, для недоступных — `BLOCKED` с причиной. Не считать подтверждение
дефекта в repro успешным acceptance test. Для CI сохранить run URL и exact SHA;
для physical evidence — RUN identity, evidence commit и report pointer.

Review report хранит исходный результат. Работа по fixes и их текущий статус живут
в профильном TODO. При необходимости создать TODO по TODO policy и связать его
с `REVIEW_<NNN>/Fxxx`; не дублировать весь отчёт в TODO или inventory. Существующий
TODO можно использовать для нескольких связанных findings.

### 5.1. Команда «разбери ревью на TODO»

Команда оператора «разбери ревью на TODO» означает: прочитать указанное ревью
или диапазон ревью, создать один или несколько профильных TODO либо дополнить
существующие задачи по замечаниям. После оформления задач и их записей в
TODO inventory добавить **в шапку того же файла ревью**, сразу после REVIEW-ID,
отдельную строку обычного текста с номерами созданных и дополненных TODO:

```text
REVIEW-ID: REVIEW_002
Разобрано в TODO: TODO_021, TODO_022
Status: COMPLETE
```

Отметка и номера находятся в шапке, не в нижнем итоговом отчёте (`Result`).
В этой служебной строке используются только plain-text TODO-ID, без гиперссылок.
Подробности разбора при необходимости можно сохранить внизу того же файла.

Для диапазона ревью обработать каждый файл отдельно и перечислить только TODO,
относящиеся к этому ревью. Полную отметку ставить после завершения всего
запрошенного разбора; при частичном результате писать «Частично разобрано в TODO:
TODO_…» и перечислять оставшиеся замечания в тексте. При повторном разборе
сначала проверить существующие задачи, дополнить список без дублей и сохранить
ранее оформленные связи. Отметка подтверждает оформление задач; исходные findings,
reviewed target, status и verdict ревью сохраняются. Сам разбор в TODO не является
новым проходом проверки и не получает новый REVIEW-ID.

## 6. Повторное ревью и история

Новый проход после fixes или на другом target получает новый REVIEW-ID, даже
если тема та же. В новом отчёте и inventory указать предыдущий review и результат
повторной проверки каждого relevant finding: FIXED, STILL_PRESENT, RETRACTED или
NOT_CHECKED, с evidence и точным checkpoint. Также искать новые дефекты.

Не превращать старый RED в GREEN задним числом. Исправление ошибки в самом отчёте
оформлять датированным дополнением с причиной; исходный вывод должен оставаться
прослеживаемым. Дополнение evidence к тому же проходу/target допускается в его
файле с датой. Архивирование в `reviews/archive/` сохраняет ID и имя; inventory
обновляет путь. Новое ревью не распространяет свой verdict на непроверенные scope.

Старые отчёты в TODO не переносить механически. При отдельном запросе на импорт
выделить REVIEW-ID, сохранить исходную дату, target, автора и evidence, пометить
`Imported`, дать ссылку на исходную запись. Импорт не означает новую проверку.

## 7. Что хранит inventory

Для каждого REVIEW-ID указать ссылку на файл, дату, scope, reviewed SHA/link,
base, status, verdict, связанные TODO и previous/follow-up review. Вверху хранить
`Next new review ID`. Не копировать findings целиком и не объявлять latest review
authoritative для всего проекта без соответствующего scope.

Пустой реестр прямо сообщает, что отдельные отчёты ещё не созданы; он не означает
отсутствие исторических ревью в TODO или других evidence.

## 8. Шаблон нового отчёта

После оформления TODO вставить в шапку шаблона, сразу после REVIEW-ID, строку
«Разобрано в TODO: TODO_…» по правилу раздела 5.1. Нижний итоговый раздел
сохраняет результаты самой проверки.

```markdown
# <Тема> review

REVIEW-ID: REVIEW_<NNN>
Status: IN_PROGRESS
Verdict: NOT_ISSUED
Date UTC: <YYYY-MM-DD>
Reviewer: <автор / агент; independent / self-review / imported>

## Reviewed state

Repository: <repository URL>
Branch: <branch>
Reviewed commit: [<FULL_SHA>](<commit URL>)
Base commit: [<FULL_SHA>](<commit URL>) / N/A / UNKNOWN
Base selection: <почему выбран этот checkpoint>
Range: <BASE..TARGET / snapshot>
Checkout: <clean / dirty + exact patch identity и evidence pointer>
Previous review: <ссылка / none>
Task / TODO / spec: <ссылки>

## Scope

<Проверенные области, ожидаемые invariants и существенные ограничения scope.>

## Findings

### F001 — <severity>: <название>

Where: <path, function, lines на reviewed target>
Verified behavior: <факт>
Failure scenario: <достижимая последовательность>
Impact: <последствие>
Evidence / repro: <ссылка или точная команда и результат>
Test gap: <что существующие tests не доказывают>
Confidence / limitations: <что подтверждено и что остаётся hypothesis>
Required acceptance: <критерии исправления>
Follow-up TODO: <ссылка / not yet assigned>

<Если findings нет, явно записать это вместо фиктивного F001.>

## Previous findings recheck

<Previous REVIEW-ID/Fxxx → FIXED / STILL_PRESENT / RETRACTED / NOT_CHECKED,
evidence; либо N/A для первого review.>

## Validation and evidence

| Check / command | Exact checkpoint | Result | Evidence type / pointer / limitations |
| --- | --- | --- | --- |
| <проверка> | <SHA / snapshot> | <PASS / FAIL / NOT RUN / BLOCKED> | <executed / supplied / source inspection; ссылка> |

## Assessment

<Обоснование verdict, что приемлемо, что мешает acceptance и какие gates открыты.>

## Result

Status: <COMPLETE / BLOCKED / CANCELLED>
Verdict: <GREEN / RED / INCONCLUSIVE / NOT_ISSUED>
Verdict scope: <software / конкретный contract / иная явно проверенная область>
Remaining gates: <перечень / none>
Follow-up: <TODO / новое ревью / evidence>
```

## 9. Рабочий цикл

```text
read AGENTS.md + REVIEWER.md + review policy/inventory
→ allocate next REVIEW-ID
→ record exact target/base/scope
→ review source and applicable evidence
→ record findings + validation + scoped verdict
→ link follow-up TODOs where needed
→ update REVIEW_INVENTORY.md
→ new REVIEW-ID for a new review pass
```

Сохранение review output не даёт разрешения исправлять source, закрывать TODO
без evidence, делать commit/push или запускать physical tests вне задания.
Run-specific hardware executor prompts остаются в чате согласно `AGENTS.md`.
