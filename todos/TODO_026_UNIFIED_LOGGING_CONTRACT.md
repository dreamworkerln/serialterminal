# Unified logging contract TODO

TODO-ID: TODO_026
Status: OPEN

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

- [ ] перечислить все log paths/classes и точки записи в interactive/agent режимах;
- [ ] определить, почему interactive mode использует отдельный transcript writer вместо `RunLog`;
- [ ] определить текущих consumers каждого файла;
- [ ] проверить naming, rotation/creation, timestamps, timezone, direction и session/device identity;
- [ ] выбрать canonical contract и migration plan.

## Implementation

- [ ] реализовать выбранный общий logging contract;
- [ ] сохранить forensic/raw и human/presentation роли раздельными, если это требуется design;
- [ ] обновить CLI/help/API docs;
- [ ] обновить evidence/publication integrations при необходимости.

## Validation

- [ ] unit tests на создание/закрытие всех обязательных log files;
- [ ] unit tests на timestamp/session/direction semantics;
- [ ] agent regression tests, включая raw RX + logical console + forensic gap;
- [ ] interactive regression test;
- [ ] ручной interactive smoke с физической нодой;
- [ ] agent smoke с физической нодой;
- [ ] сравнить временную пригодность логов двух режимов на одном типе firmware событий.

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

Finding source checkpoint for current implementation: `dev@3c9140589f5664910178cbdfd89e29550c6118f2`.

## Result

Implemented: not yet.

Validated: not yet.

Status: OPEN.
