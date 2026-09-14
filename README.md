# serialterminal

Обобщённый line-oriented терминал для USB Serial, Bluetooth LE / Nordic UART Service (NUS) и Classic Bluetooth SPP/RFCOMM.

`serialterminal` редактирует строку локально и отправляет её устройству только после `Enter`. Исходящие строки переживают временный disconnect/reboot и отправляются после reconnect к тому же выбранному физическому устройству.

## Запуск

Обычный human terminal теперь по умолчанию использует **generic** controller profile:

```bash
python3 serialterminal.py
```

Generic profile не отправляет устройству controller-specific команды при connect/reconnect, не интерпретирует firmware output как Chatter и для BLE использует стандартный NUS layout `0002` write + `0003` receive (`main`).

Для bundled LoRa-Chatter conveniences выбери профиль явно:

```bash
python3 serialterminal.py --profile chatter
```

Human `chatter` profile сохраняет Chatter-aware presentation/hotkeys и для USB Serial отправляет `/id` как connect/reconnect preamble. Human BLE/SPP не получают автоматический `/id`, как и раньше.

По умолчанию каждый отдельный запуск human terminal создаёт отдельный session log:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
```

Явный `--log <path>` остаётся доступен для отладки/совместимости.

После запуска terminal показывает выбранный profile и предлагает локальный help:

```text
Press Ctrl+T ? for SerialTerminal help.
```

В generic profile `Ctrl+T ?` печатает только локальный help. В `chatter` profile тот же hotkey дополнительно ставит firmware `/help` в reconnect-safe TX queue.

## Profiles

Profile выбирает controller compatibility/configuration и convenience behavior. Transport/session mechanics остаются в generic core, а семантикой controller-команд владеет firmware.

Сейчас bundled два profile:

```text
generic
    default для human CLI и agent open
    no connect preamble
    no controller-specific hotkeys/presentation
    standard BLE NUS 0002 write + 0003 receive -> stream main

chatter
    explicit LoRa-Chatter compatibility profile
    /id connect preamble
    Chatter help/hotkeys/presentation
    BLE 0003 -> chat
    optional BLE 0004 -> telemetry
```

Normal CLI передаёт выбранный profile явно в terminal/session factory. Прямые `TerminalSession` и `DeviceSelector` constructors тоже используют `generic` по умолчанию; Chatter behavior включается только явным `profile=CHATTER_PROFILE` или `--profile chatter`.

## Что поддержано

- USB Serial через `pyserial`;
- BLE NUS через `bleak`;
- Classic Bluetooth SPP/RFCOMM на Linux через BlueZ + Python Bluetooth sockets;
- unified device chooser;
- sticky reconnect по стабильной physical identity;
- controller profiles (`generic`, `chatter`) поверх общего transport/session core;
- общий headless `ManagedSession` для reconnect/RX/TX logic;
- machine-facing `serialterminal agent` JSONL interface поверх той же session/transport logic;
- несколько независимых agent sessions к разным устройствам и с разными profiles в одном процессе;
- raw SessionEvent/chunk forensic receive view и session-level completed logical-line view через `observe`;
- paired forensic + human-console agent run logs;
- configurable BLE write/receive characteristic-to-stream layout;
- локальные hotkeys `Ctrl+T ...`;
- локальное line editing через `prompt_toolkit`, включая Backspace/Delete и Unicode;
- capability cache для найденных NUS/SPP устройств;
- Bluetooth scanner/prober;
- transcript с немедленным `flush()`;
- `LF`, `CRLF` или `CR` после `Enter`.

Chatter-specific возможности — `/id`, `/help`, output/echo shortcuts, `chat`/`telemetry`, pending USER/ECHO presentation и optional BLE `0004` — принадлежат bundled `chatter` profile, а не generic default.

## Agent / Codex JSONL interface

Agent mode запускается без TUI:

```bash
python3 serialterminal.py agent
```

stdin и stdout используются как request/response JSON Lines. Один request всегда даёт один machine-readable JSON response. `observe` может оставаться pending, пока agent принимает следующие команды, поэтому ответы сопоставляются по `id` и могут приходить не в порядке запросов.

Основные операции:

```text
discover
open
status
list_sessions
send_line
send_bytes
observe
close
```

`events` и `wait_events` больше не являются machine API operations; receive/cursor workflow унифицирован через `observe`.

### Generic/default open

```json
{"id":1,"op":"discover","scope":"auto"}
{"id":2,"op":"open","device_key":"ble-address:..."}
{"id":3,"op":"send_line","session":"s1","text":"status"}
{"id":4,"op":"observe","cursors":{"s1":0},"timeout_ms":5000}
{"id":5,"op":"close","session":"s1"}
```

`open` без `profile` эквивалентен:

```json
{"id":2,"op":"open","device_key":"...","profile":"generic"}
```

Generic agent session не отправляет controller-specific connect preamble. Для BLE используется standard NUS `0002` write + `0003` receive как stream `main`.

### Chatter open

Для LoRa-Chatter node workflow profile выбирается явно:

```json
{"id":2,"op":"open","device_key":"...","profile":"chatter"}
```

Chatter profile отправляет `/id` после каждого успешного transport connect/reconnect до публикации session как `connected` и задаёт BLE streams `chat` + optional `telemetry`.

Profile выбирается отдельно для каждой session, поэтому один agent process может одновременно держать generic и controller-specific sessions.

Legacy `auto_id` оставлен только как compatibility override для старых callers. Новому коду следует выбирать profile и не передавать `auto_id`:

```text
auto_id omitted
    использовать preamble выбранного profile

auto_id=false
    подавить preamble выбранного profile

auto_id=true
    допустим только если profile определяет connect preamble

generic + auto_id=true
    structured invalid_profile_option
```

Полный контракт profiles/open/error semantics находится в `AGENT_API.md`.

### Observe

Receive/observation использует один `cursors` object и retained raw event buffer. Формат одинаков для одной и нескольких sessions.

`observe.result.events` сохраняет raw SessionEvent/chunk representation с transport stream tag, byte-accurate `data_b64` и incremental chunk-level UTF-8 `text`.

`observe.result.lines` одновременно возвращает завершённые LF-terminated logical firmware lines с `seq_first/seq_last`; line assembly живёт на session layer и не меняет transport chunk boundaries.

Один raw cursor управляет обеими views. Если logical line началась до входного cursor, а завершилась после него, следующий `observe` возвращает целую line, поэтому caller не обязан вручную хранить и склеивать RX fragments.

`send_line` и `send_bytes` используют одну reconnect-safe ordered TX queue. `tx_state=written` означает только успешное завершение transport `write()`, а не application/protocol/peer delivery.

Один agent process может держать несколько разных `device_key` одновременно. Повторный `open` того же `device_key` внутри одного manager возвращает structured `device_busy`.

## Agent run logs

Каждый agent run создаёт связанную пару файлов с одним timestamp/PID prefix:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
```

Основной `.log` — forensic/API/transport truth. В нём остаются точные chronological records:

```text
[RUN]
[AGENT]
[AGENT REQUEST]
[AGENT RESPONSE]
[STATE]
[TX]
[RX <stream>]
[ERROR]
```

Logical lines являются first-class частью `ManagedSession`/`observe.result.lines`, а raw `[RX <stream>]` сохраняет transport chunk boundaries и `data_b64`.

Companion `.console.log` — удобный человекочитаемый view одного run для всех sessions:

```text
2026-09-05T08:23:01.100+00:00 [s1] [I] status
2026-09-05T08:23:01.420+00:00 [s1] [O] READY
2026-09-05T08:23:05.100+00:00 [s2] [I] ping
2026-09-05T08:23:05.250+00:00 [s2] [O] pong
```

`[I]` означает text, принятый через `send_line`; `[O]` — completed logical line из human-console receive stream выбранного profile. Generic BLE console stream называется `main`; Chatter BLE console stream — `chat`.

Background profile streams, например Chatter `telemetry`, не пишутся в `.console.log` просто из-за подписки. Они остаются в forensic `.log` и `observe.result.events`.

Companion log — presentation/audit view, а не evidence доставки. `send_bytes` в нём как обычный human input не изображается. Startup `[AGENT]` metadata в forensic log содержит оба пути: `log_path` и `console_log_path`.

Полный контракт, raw/line cursor semantics, concurrent `observe`, out-of-order response rules, paired logging и ошибки: `AGENT_API.md`.

Generic SerialTerminal API остаётся device-agnostic. Project-specific LoRa-Chatter node guidance хранится в `.agents/skills/node-agent/SKILL.md`; firmware/protocol source authority остаётся в соответствующем source state `lora-sack-protocol`.

### Historical live hardware/Codex smoke

2026-09-03 наблюдался live smoke с двумя физическими BLE LoRa-Chatter нодами в одном `serialterminal agent` process: Codex открыл две независимые sessions, использовал multi-session receive long-poll, продолжал обычные команды при pending observation и выполнил TX с обеих sessions близко по времени.

Это исторически подтверждает практическую работу multi-session agent workflow и независимых per-session TX paths. Сам по себе этот smoke не доказывает успешную peer-доставку обеих близких LoRa передач и не является physical validation текущего profile-refactor checkpoint.

## Discovery и reconnect

Обычный запуск не подключается подряд ко всем неизвестным Bluetooth-устройствам. В chooser попадают:

- USB Serial;
- project BLE с именем `LoRa-*` как trusted compatibility hint;
- BLE, рекламирующие NUS service UUID;
- BLE с ранее подтверждённым scanner'ом NUS;
- Classic Bluetooth устройства с ранее подтверждённым scanner'ом SPP.

Неизвестный BLE по умолчанию скрыт:

```python
SHOW_ALL_BLE_DEVICES = False
```

Выбор:

```text
0 devices  -> scan/wait
1 device   -> autoconnect + lock target
2+ devices -> numbered menu
```

После выбора reconnect идёт только к той же physical identity. Сменить target можно через `Ctrl+T d`.

Discovery сохраняет `LoRa-*` compatibility hint через Chatter compatibility layer; generic `BleNusTransport` больше не владеет project-specific name filtering/discovery. Physical identity и sticky reconnect semantics от этого не меняются. Legacy `normalize_ble_target()` в transport-модуле оставлен только как import compatibility shim для старых callers.

## Human hotkeys

Общие локальные hotkeys доступны в любом profile:

```text
Ctrl+C         quit immediately
Ctrl+T d       device chooser
Ctrl+T s       Bluetooth capability scanner
Ctrl+T i       connection/status
Ctrl+T ?       SerialTerminal help
```

В generic profile `Ctrl+T ?` остаётся только local help; controller-specific hotkeys отсутствуют.

В `chatter` profile дополнительно доступны:

```text
Ctrl+T 1/c     Chatter human console: CHAT
Ctrl+T 2/t     Chatter human console: TELEMETRY
Ctrl+T 3/b     Chatter human console: BOTH
Ctrl+T e       Chatter echo mode toggle
Ctrl+T ?       local help + Chatter /help
```

Chatter shortcut actions `Ctrl+T 1/2/3/e` (и aliases `c/t/b`) теперь используют `SendBytes` и отправляют exact two-byte raw ABI `14 31/32/33/65` без configured EOL. Human-readable `/chat`, `/tele`, `/both` и `/echo` остаются обычными line-oriented командами и отправляются после Enter с выбранным line ending.

## Chatter profile

Следующие разделы относятся к запуску с `--profile chatter` либо к agent session с `profile:"chatter"`.

### Канонические Chatter-команды

Human-readable команды отправляются контроллеру обычными строками:

```text
/help        show Chatter help
/id          show canonical node identity
/chat        human console CHAT
/tele        human console TELEMETRY
/both        human console BOTH
/echo        toggle diagnostic echo mode
/cancel      cancel reliable USER retry / one unsent queued USER
/cancel all  stop current retry and clear queued USER messages
/reboot      reboot ESP32 controller
```

Canonical identity Chatter имеет вид:

```text
[SYS] CHATTER NODE LoRa-Chatter-XXXX
```

Это controller-owned identity. `serialterminal` не строит собственный node ID.

Human `chatter` profile после успешного `SerialTransport.connect()` отправляет `/id` до открытия reconnect-safe user TX gate. Human BLE NUS и Bluetooth SPP автоматический `/id` не получают. Agent `profile:"chatter"`, напротив, применяет profile preamble при каждом transport connect/reconnect независимо от transport kind.

При классификации Chatter-команды profile использует ту же boundary-normalization, что и совместимая firmware: ASCII control/space + DEL по краям игнорируются только для command matching. Если после такого trim строка не совпала с известной командой, обычный payload отправляется в исходном виде.

`/help` в human Chatter profile дополнительно печатает local help и ставит canonical `/help` контроллеру. Остальные команды идут через обычную reconnect-safe очередь.

### TX presentation: кто имеет право печатать `>`

SerialTerminal не синтезирует RF marker:

```text
> hello
> [ECHO TX] hello
```

Эти строки принадлежат Chatter firmware. На совместимой firmware они означают firmware-side TX outcome, но сами по себе не доказывают peer delivery.

Interactive USER/ECHO payload в Chatter human profile сначала хранится как pending presentation и сразу записывается в transcript, но не дублируется на экране. Firmware success line показывает payload один раз.

Если firmware отвергает payload до успешного RF TX, terminal сначала показывает исходный submit как plain local line, затем оставляет firmware failure неизменённым, например:

```text
hello
[SYS] RADIO UNAVAILABLE, message not sent
```

Plain `hello` означает только «это было отправлено пользователем в controller», а не RF success.

Background BLE `0004` telemetry не участвует в human pending-presentation resolution. Все transport chunks при этом сохраняются в transcript/forensic records.

Если связь пропала после transport write, но до firmware outcome, sent-but-unresolved payload раскрывается как plain local line. Payload, который ещё не был физически записан в transport, остаётся pending и может быть отправлен обычным reconnect retry.

### Очереди

Есть разные уровни очередей, их нельзя смешивать:

```text
serialterminal outgoing transport queue
    reconnect-safe
    shared ManagedSession mechanism for human/agent line/raw TX

serialterminal pending presentation queue
    human Chatter presentation only

Chatter firmware queues
    controller/protocol-owned state
```

Host-side presentation state не является доказательством RF delivery. Актуальные firmware queue/reliability limits и acceptance criteria смотри в `.agents/skills/node-agent/SKILL.md` и authoritative firmware/docs, а не выводи из SerialTerminal UI.

### Android / Kai Morich

В Android Serial Bluetooth Terminal можно использовать тот же controller command set, например:

```text
HELP       /help
ID         /id
CHAT       /chat       or HEX 14 31
TELEMETRY  /tele       or HEX 14 32
BOTH       /both       or HEX 14 33
ECHO       /echo       or HEX 14 65
REBOOT     /reboot
```

Raw controls не требуют newline. Text commands выполняются после Enter/newline.

## BLE NUS layouts

### Generic

Generic/default profile использует стандартный Nordic UART Service layout:

```text
NUS service             6E400001-B5A3-F393-E0A9-E50E24DCCA9E
INPUT / RX              6E400002-B5A3-F393-E0A9-E50E24DCCA9E
OUTPUT / TX             6E400003-B5A3-F393-E0A9-E50E24DCCA9E -> stream main
```

`BleNusTransport` получает write characteristic и receive UUID/stream mapping как конфигурацию; transport runtime не требует Chatter `0004` semantics.

### Chatter

Chatter profile задаёт:

```text
NUS service             6E400001-B5A3-F393-E0A9-E50E24DCCA9E
INPUT / RX              6E400002-B5A3-F393-E0A9-E50E24DCCA9E
PRIMARY / human TX      6E400003-B5A3-F393-E0A9-E50E24DCCA9E -> stream chat
MACHINE TELEMETRY       6E400004-B5A3-F393-E0A9-E50E24DCCA9E -> stream telemetry (optional)
```

Human console на `0003` следует режиму Chatter firmware. Если `0004` существует, profile подписывает transport на него best-effort как отдельный background stream. Отсутствие `0004` не делает BLE connection невалидным.

Human terminal не показывает background `telemetry` stream в normal console только из-за подписки. Agent и forensic log сохраняют его отдельно.

## Line editing и отправка

Interactive input работает через `prompt_toolkit.PromptSession`.

До Enter пользователь редактирует локальную Unicode-строку. Backspace/Delete не отправляются устройству как отдельные bytes. После Enter в transport уходит одна complete line:

```text
edited text + configured line ending
```

Это отличается от byte-stream terminal, где управляющие клавиши могут физически попасть в UART.

## Reconnect и transport queue

Input отделён от transport I/O. Полная строка попадает в TX queue только после `Enter`.

Если target disconnect/reboot происходит во время отправки, текущий transport-queue element удерживается и повторяется после reconnect к тому же locked target.

Reconnect-safe queue используется и human, и agent frontends. Profile connect preamble выполняется отдельно после transport connect и до публикации session как connected; queued user/agent TX не должен его обогнать.

Human frontend сохраняет historical behavior: profile preamble выполнялся только для USB Serial. Agent frontend применяет выбранный profile preamble на каждом supported transport connect/reconnect.

Controller state после reboot принадлежит самому устройству. SerialTerminal не обязан автоматически восстанавливать controller-specific mode, если profile явно этого не определяет.

## Bluetooth scanner

Запуск из human terminal:

```text
Ctrl+T s
```

Меню:

```text
Bluetooth scanner
  1. Probe all BLE devices for NUS
  2. Probe Classic Bluetooth devices for SPP
  3. Probe all Bluetooth
  Enter. Back to terminal
```

На время scanner текущий transport отключается и reconnect ставится на паузу. После выхода terminal снова пытается подключиться к тому же sticky target. Набранная, но ещё не отправленная строка сохраняется.

BLE scanner активно подтверждает только standard NUS compatibility: наличие RX `0002` и TX `0003`. Он не классифицирует Chatter `0004` и не хранит generic `CHAT`/`TELEMETRY` capabilities; optional `0004` остаётся runtime concern профиля `chatter` при реальном open.

Classic scanner делает BR/EDR discovery через BlueZ (`bluetoothctl`, fallback `hcitool`), SDP browse через `sdptool` и ищет Serial Port Profile / UUID `0x1101` и RFCOMM channel.

## Capability cache

Scanner сохраняет результаты в:

```text
~/.cache/serialterminal/devices.json
```

или под `$XDG_CACHE_HOME`.

Cache хранит NUS/SPP capability state, время probe, имя/address и RFCOMM channel. Обычный chooser использует подтверждённые capabilities.

## Sticky identity

USB priority:

```text
/dev/serial/by-id/...
-> VID/PID + USB serial number
-> VID/PID + USB location
-> concrete tty path
```

Это transport identity, используемая для reconnect. Controller/application identity — отдельное понятие и не заменяет transport key.

BLE target фиксируется по BLE address. SPP target — по Bluetooth address + подтверждённому RFCOMM channel.

## ESP32 / DTR / RTS

`SerialTransport` сохраняет best-effort no-reset последовательность:

1. безопасное промежуточное DTR/RTS перед `open()`;
2. deassert обеих линий после открытия;
3. отключение `HUPCL` на Linux.

USB Serial RX/TX остаются full-duplex: blocking read не держит общий mutex с write.

## Tests / CI

CI на каждый push/PR выполняет:

```text
python -m compileall -q src serialterminal.py tools
ruff check src tests serialterminal.py tools
lizard -l python -C 10 -L 80 -a 5 src serialterminal.py tools   # advisory
pytest -q
```

Покрыты generic profile zero-preamble behavior, Chatter profile compatibility, human profile selection, BLE injected receive layout, shared `ManagedSession` reconnect/order/stream events, multi-session agent manager, explicit per-session agent profiles, async `observe`, raw-event/logical-line correlation и paired forensic/console run logging.

Не фиксируйте в README число тестов как постоянную характеристику: authoritative результат — exact CI run для конкретного commit SHA.

## Зависимости

Python:

```text
pyserial
prompt-toolkit
bleak        # BLE
```

Установка:

```bash
pip install pyserial prompt-toolkit bleak
python3 serialterminal.py
```

Для Classic Bluetooth scanner/SPP:

```bash
sudo apt install bluez
```

Проверка:

```bash
which bluetoothctl
which sdptool
```

## Диагностика Bluetooth disconnect на Linux

Для link-level причин полезен `btmon`:

```bash
sudo btmon \
  | grep --line-buffered -Ei -A 6 \
      'Disconnect Complete|Device Disconnected'
```

Например `Reason: Connection Timeout` означает HCI/link supervision timeout и сам по себе не доказывает, что disconnect инициировал Python/Bleak.

При повторяющихся timeout на Debian/Ubuntu/Linux Mint:

```bash
sudo apt update
sudo apt install --only-upgrade bluez linux-firmware
sudo reboot
```
