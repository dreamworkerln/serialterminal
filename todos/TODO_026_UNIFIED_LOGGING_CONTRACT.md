# Unified logging contract TODO

TODO-ID: TODO_026
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN

## Purpose

Разобраться с текущим расхождением форматов логирования между интерактивным SerialTerminal и machine-facing `serialterminal agent`, затем определить и реализовать единый устойчивый контракт логов без потери существующей forensic ценности.

## Current behavior

На текущем `dev` два режима имеют разные logging semantics.

Интерактивный SerialTerminal создаёт один human transcript:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
```

В нём есть timestamp сессии в заголовке, но обычные firmware/input строки не получают отдельный host timestamp.

Machine-facing `serialterminal agent` использует `RunLog` и создаёт пару:

```text
<name>.log
<name>.console.log
```

Основной файл содержит timestamped forensic/API/transport records, а companion `.console.log` содержит timestamped logical human-console records с session id и направлением `[I]/[O]`.

Операторское наблюдение 2026-09-22 подтвердило, что при обычном ручном запуске рядом с transcript-файлом companion `.console.log` не создаётся.

## Problem

Различающиеся форматы затрудняют одинаковый анализ ручных и agent-driven прогонов, особенно когда требуется общая временная шкала нескольких устройств или точное сравнение событий по host timestamps.

Нельзя просто переименовать существующие файлы или заменить forensic log human transcript-ом: у режимов разные потребители и разные гарантии.

## Target behavior

Выбрать и документировать единый logging contract для SerialTerminal, в котором:

- роли forensic/raw и human-console/presentation логов однозначны;
- timestamps имеют одинаково определённую семантику;
- interactive и agent режимы дают сопоставимый материал для временного анализа;
- session/device/direction identity представлена там, где она необходима;
- существующие agent forensic guarantees, включая `forensic_gap`, не ослабляются;
- обычный human UX не ухудшается.

Конкретное решение о том, должен ли interactive mode создавать отдельный `.console.log`, timestamp-ить текущий transcript или использовать общий logging layer другим способом, принимается после анализа. Этот TODO не предрешает формат.

## Scope

- инвентаризация всех текущих log writers и consumers;
- сравнение interactive transcript, agent forensic log и agent companion console log;
- определение canonical timestamps / direction / session identity;
- единая naming/lifecycle policy;
- backward-compatibility для scripts/tests/evidence publication;
- документация формата;
- automated tests для выбранного контракта;
- ручная проверка interactive mode и agent mode.

## Non-goals

- изменение BLE/Serial/SPP transport semantics;
- изменение firmware output format;
- изменение Chatter protocol;
- удаление forensic raw evidence ради более красивого human log.

## Invariants

- agent forensic log остаётся byte/event-accurate и не теряет `forensic_gap` semantics;
- human-console normalization не должна подменять raw evidence;
- логирование не должно менять порядок TX/RX или session lifecycle;
- существующие RUN publication consumers должны либо продолжить работать, либо получить явную совместимую миграцию.

## Investigation

- [x] перечислить все log paths/classes и точки записи в interactive/agent режимах;
- [x] определить, почему interactive mode использует отдельный transcript writer вместо `RunLog`;
- [x] определить текущих consumers каждого файла;
- [x] проверить naming, rotation/creation, timestamps, timezone, direction и session/device identity;
- [x] выбрать canonical contract и migration plan.

Selected contract:

```text
primary .log
    human -> compatibility transcript
    agent -> forensic/API/transport truth

companion .console.log
    shared format for both frontends
    offset-aware ISO-8601 timestamp, millisecond precision
    process-local session token
    [I] queued line
    [O] completed ManagedSession logical line from a human-console stream
```

Interactive mode uses process-local `s1`. Agent mode keeps its normal `s1`, `s2`, ... identifiers.

The historical human transcript is intentionally preserved instead of being silently replaced by the agent forensic format. This keeps existing operator workflows compatible while giving both frontends the same timestamped logical timeline.

## Implementation

- [x] реализовать выбранный общий logging contract;
- [x] сохранить forensic/raw и human/presentation роли раздельными;
- [x] обновить CLI/help/API docs;
- [x] review evidence/publication integrations: no schema or publisher change required because canonical agent `.log/.console.log` names and semantics remain compatible.

Implementation checkpoint:

```text
dev@5965d576c3bb124d85adf7842282684e755894c7
GitHub Actions 35733796357 -> SUCCESS
156 pytest tests passed
```

Changed contract documentation:

```text
LOGGING.md
README.md
AGENT_API.md
```

## Validation

- [x] unit tests на создание обязательного human companion log;
- [x] unit tests на timestamp/session/direction semantics;
- [x] existing agent regression suite, including raw RX/logical console/forensic-gap behavior, PASS in full CI;
- [x] interactive regression test for queued input, canonical completed output, background-stream exclusion and CR/LF escaping;
- [x] ручной interactive smoke с физической нодой, включая `--profile chatter`;
- [ ] agent smoke с физической нодой;
- [ ] физически сравнить временную пригодность логов двух режимов на одном типе firmware событий.

Software regression gate:

```text
accepted base: 84f78aa1054eab8a95320410c34036f3f803f0e0
source change: 5965d576c3bb124d85adf7842282684e755894c7
BASE..HEAD diff reviewed
all deletions reviewed
function/method definition comparison: no definitions removed
compile: PASS
ruff: PASS
pytest: 156 PASS
full GitHub Actions: 35733796357 SUCCESS
```

## Findings

Initial finding:

```text
interactive mode:
    one transcript .log
    session timestamp in header
    firmware lines are not individually host-timestamped
    no observed companion .console.log

agent mode:
    forensic .log with per-record timestamps
    companion .console.log with per-line timestamps + session + direction
```

Finding source checkpoint for original behavior: `dev@3c9140589f5664910178cbdfd89e29550c6118f2`.

Implemented finding:

```text
interactive now creates:
    <name>.log
    <name>.console.log

agent remains:
    <name>.log
    <name>.console.log
```

The shared companion renderer is `format_console_record()`. Interactive receive records are fed from the existing canonical `ManagedSession` line notifier, so companion output uses the same logical-line boundary/timestamp model as agent output without changing the existing human presentation parser in this TODO.

## Result

Implemented: `dev@5965d576c3bb124d85adf7842282684e755894c7`.

Software validated: GitHub Actions `35733796357` SUCCESS; 156 tests PASS.

Physical manual smoke: PASS on 2026-09-22 with physical LoRa-Chatter-1B44 using `Profile: chatter`.

Observed files:

```text
serialterminal-20260922-165233-281847-p52949.log
serialterminal-20260922-165233-281847-p52949.console.log
```

The companion log showed millisecond offset-aware timestamps, `[s1]`, `[I]` for manual commands and one `[O]` record per canonical human-console logical line.

Additional non-blocking observation: the compatibility transcript contained duplicate telemetry text while Chatter machine telemetry was subscribed in background and the firmware human output mode was TELEMETRY. The companion `.console.log` did not duplicate those records because it correctly includes only profile human-console streams. This does not invalidate the shared companion contract; investigate transcript stream attribution/duplication separately if desired.

Physical agent smoke: OPEN.

Status: IMPLEMENTED / AGENT PHYSICAL VALIDATION OPEN.
