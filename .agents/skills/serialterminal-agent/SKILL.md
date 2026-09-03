---
name: serialterminal-agent
description: Работа с machine-facing SerialTerminal JSONL agent API для discovery, long-lived sessions, send/receive и multi-session wait.
---

# SerialTerminal agent

Это repo-local operational skill для `serialterminal agent`.

## Сначала прочитай API contract

Полный и канонический контракт находится в:

`../../../AGENT_API.md`

Не дублируй и не переопределяй здесь schema, error codes или transport/session semantics. Если этот skill и `AGENT_API.md` расходятся, источником истины является `AGENT_API.md`.

## Базовый workflow

Запусти один долгоживущий процесс:

```bash
python3 serialterminal.py agent
```

Работай с ним по JSON Lines через stdin/stdout:

1. `discover` — получить текущие `device_key`;
2. `open` — открыть одну или несколько независимых sessions;
3. сохранить `latest_seq` каждой открытой session;
4. использовать `send_line` или `send_bytes` для передачи;
5. использовать `wait_events` для ожидания событий одной или нескольких sessions;
6. после каждого ответа `wait_events` продолжать с возвращёнными `cursors`;
7. `close` завершает конкретную session; завершение agent process закрывает оставшиеся sessions.

Предпочитай переиспользовать один agent process и уже открытые sessions вместо повторного запуска discovery/open для каждой команды.

## Ожидание событий

Для реактивной работы используй `wait_events`, а не частый polling через `events`.

`wait_events` может оставаться pending, пока тот же agent process принимает обычные команды. Он требует непустой `id`; пока wait с этим ID не завершился, ID нельзя переиспользовать. Ответы могут приходить не в порядке запросов, поэтому всегда коррелируй их по `id`.

Для нескольких sessions храни отдельный cursor на каждую session. После ответа используй именно возвращённый объект `cursors`, включая продвижение через события, исключённые фильтрами.

`timeout_ms` — только максимальное время конкретного long-poll. Это не protocol constant и не требуемая задержка: событие возвращается сразу после появления подходящего результата. После timeout или события при необходимости сразу запускай следующий `wait_events`.

SerialTerminal не пишет unsolicited event messages в JSONL stdout. Каждая stdout-строка является ответом на конкретный request.

## Что считать подтверждением

`send_line`/`send_bytes` с `state=queued` подтверждает только принятие данных reconnect-safe TX queue.

Последующее событие `tx_state=written` подтверждает успешный вызов transport `write()`, но не доставку peer-у и не выполнение higher-level protocol operation.

Подтверждение доставки или результата определяй по RX/telemetry/application-level данным конкретного устройства или протокола. Такие firmware-specific правила не относятся к этому generic skill.

## Ошибки и доступ к hardware

Не делай blind retry при structured error. Сначала прочитай `error.code`, `error.message`, при необходимости run log и соответствующий раздел `AGENT_API.md`.

Если host Bluetooth/D-Bus или sandbox возвращает permission error, не интерпретируй это как отсутствие устройства. Используй разрешённый окружением способ запуска с необходимыми правами или сообщи о permission boundary.

## Граница ответственности

Этот skill описывает только generic SerialTerminal workflow. Не добавляй сюда конкретные MAC-адреса, LoRa/Chatter команды, RSSI/SNR/Q, echo/reboot semantics, radio collision rules или acceptance criteria конкретной прошивки. Такие знания принадлежат project-specific hardware/protocol skill.
