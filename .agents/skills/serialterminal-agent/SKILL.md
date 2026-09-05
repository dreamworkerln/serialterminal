---
name: serialterminal-agent
description: Работа с machine-facing SerialTerminal JSONL agent API для discovery, long-lived sessions, send и canonical observe.
---

# SerialTerminal agent

Это repo-local operational skill для `serialterminal agent`.

## Сначала прочитай API contract

Полный и канонический контракт находится в [AGENT_API.md](../../../AGENT_API.md).

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
5. использовать `observe` с `cursors` для получения новых raw events и completed logical lines;
6. после каждого ответа `observe` продолжать с возвращёнными `cursors`;
7. для protocol/human-readable reasoning использовать `result.lines`, а для forensic transport/session verification — `result.events`;
8. `close` завершает конкретную session; завершение agent process закрывает оставшиеся sessions.

Предпочитай переиспользовать один agent process и уже открытые sessions вместо повторного запуска discovery/open для каждой команды.

## Observe и cursors

`observe` — единственный receive/cursor workflow. Формат cursor всегда один:

```json
{"cursors":{"s1":42}}
```

Даже для одной session не используй отдельную форму `session + after_seq`.

Для нескольких sessions передавай отдельный raw cursor на каждую:

```json
{"cursors":{"s1":42,"s2":75}}
```

После ответа используй именно возвращённый объект `cursors`.

`observe` может оставаться pending, пока тот же agent process принимает обычные команды. Он требует непустой `id`; пока observation с этим ID не завершилась, ID нельзя переиспользовать. Ответы могут приходить не в порядке запросов, поэтому всегда коррелируй их по `id`.

`timeout_ms` — только максимальное время конкретного long-poll. Это не protocol constant и не требуемая задержка: `observe` возвращается сразу после появления нового raw event. После timeout или event при необходимости сразу запускай следующий `observe` с возвращёнными cursors.

Если пришли raw events, но нужная firmware line ещё не завершена LF, `result.lines` может быть пустым. Продолжай observation с новым cursor; session layer сам хранит незавершённый line state.

Не склеивай RX chunks вручную, если нужная completed logical line уже есть в `result.lines`. `seq_first` у такой line может быть меньше или равен входному cursor, а `seq_last` — новее него: это нормальный способ вернуть целую строку, которая началась в предыдущем observation.

SerialTerminal не пишет unsolicited event messages в JSONL stdout. Каждая stdout-строка является ответом на конкретный request.

## Два уровня receive evidence

`result.events` — forensic source of truth. Здесь сохраняются raw `SessionEvent` records, transport chunk boundaries, `data_b64`, incremental chunk-level `text`, state/TX metadata и точные raw `seq`.

`result.lines` — convenience/protocol view только для завершённых LF-terminated firmware lines. Line assembly выполняется один раз на session layer независимо для каждого stream и не меняет BLE/Serial transport chunk semantics.

Используй:

```text
firmware/protocol reasoning   -> result.lines
transport/chunk forensics     -> result.events
```

Если нужно доказать exact bytes или границу BLE notification, смотри `result.events`/`data_b64`, а не reconstructed line text.

## Run logs

Каждый запуск agent создаёт связанную пару файлов с одним timestamp/PID prefix:

```text
logs/serialterminal-...-pPID.log
logs/serialterminal-...-pPID.console.log
```

Основной `.log` — forensic/API/transport truth. Companion `.console.log` — presentation/audit view того, что примерно увидел бы человек: `send_line` записывается как `[sN] [I] ...`, completed human-console RX line — как `[sN] [O] ...`. `[I]` означает input, принятый через `send_line`; `[O]` — completed logical line из human-console RX stream.

Firmware-owned leading `>` / `<` остаются частью самой строки и не заменяются этими host-side markers. Например firmware output `> hello` записывается как `[sN] [O] > hello`.

BLE background machine telemetry не попадает в `.console.log` только потому, что SerialTerminal подписан на отдельный telemetry stream. Если та же telemetry semantics реально появилась в human-console `chat` stream, например при `/both`, она естественно попадает в companion log. Этот файл не является delivery evidence и не заменяет `result.events`/`result.lines`.

Startup metadata в forensic log содержит `log_path` и `console_log_path`, чтобы executor мог положить оба файла в один run bundle.

## Что считать подтверждением

`send_line`/`send_bytes` с `state=queued` подтверждает только принятие данных reconnect-safe TX queue.

Последующее raw event `tx_state=written` подтверждает успешный вызов transport `write()`, но не доставку peer-у и не выполнение higher-level protocol operation.

Подтверждение доставки или результата определяй по RX/telemetry/application-level данным конкретного устройства или протокола. Для line-oriented firmware output сначала смотри `observe.result.lines`; при необходимости forensic доказательства проверяй соответствующие `observe.result.events`.

Такие firmware-specific acceptance rules не относятся к этому generic skill.

## Ошибки и доступ к hardware

Не делай blind retry при structured error. Сначала прочитай `error.code`, `error.message`, при необходимости run log и соответствующий раздел [AGENT_API.md](../../../AGENT_API.md).

`cursor_expired` относится к raw SessionEvent retention window. Отдельного line cursor нет.

Если host Bluetooth/D-Bus или sandbox возвращает permission error, не интерпретируй это как отсутствие устройства. Используй разрешённый окружением способ запуска с необходимыми правами или сообщи о permission boundary.

## Граница ответственности

Этот skill описывает только generic SerialTerminal workflow. Не добавляй сюда конкретные MAC-адреса, LoRa/Chatter команды, RSSI/SNR/Q, echo/reboot semantics, radio collision rules или acceptance criteria конкретной прошивки. Такие знания принадлежат project-specific hardware/protocol skill.
