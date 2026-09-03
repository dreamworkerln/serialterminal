# serialterminal

Обобщённый line-oriented терминал для USB Serial, Bluetooth LE / Nordic UART Service (NUS) и Classic Bluetooth SPP/RFCOMM.

`serialterminal` редактирует строку локально и отправляет её устройству только после `Enter`. Исходящие строки переживают временный disconnect/reboot и отправляются после reconnect к тому же выбранному физическому устройству.

## Запуск

```bash
python3 serialterminal.py
```

Session log по умолчанию:

```text
serialterminal.log
```

После запуска:

```text
Type /help or press Ctrl+T ? for full help.
```

Оба способа печатают локальные hotkeys `serialterminal`, затем ставят обычную Chatter-команду `/help` в reconnect-safe TX queue.

## Что поддержано

- USB Serial через `pyserial`;
- BLE NUS через `bleak`;
- Classic Bluetooth SPP/RFCOMM на Linux через BlueZ + Python Bluetooth sockets;
- unified device chooser;
- sticky reconnect по стабильной physical identity;
- BLE `0003` как human-console stream и optional `0004` как background machine-telemetry stream;
- локальные hotkeys `Ctrl+T ...`;
- локальное line editing через `prompt_toolkit`, включая Backspace/Delete и Unicode;
- Chatter device commands `/help`, `/id`, `/chat`, `/tele`, `/both`, `/echo`, `/reboot`;
- автоматический `/id` после USB Serial connect/reconnect;
- Chatter output/echo raw hotkeys `Ctrl+T 1/2/3`, `Ctrl+T c/t/b/e`;
- pending presentation для USER/ECHO: `>` остаётся только firmware-owned подтверждением успешного RF TX;
- полный help через `/help` или `Ctrl+T ?`;
- capability cache для найденных NUS/SPP устройств;
- Bluetooth scanner/prober;
- transcript с немедленным `flush()`;
- `LF`, `CRLF` или `CR` после `Enter`.

## Discovery и reconnect

Обычный запуск не подключается подряд ко всем неизвестным Bluetooth-устройствам. В chooser попадают:

- USB Serial;
- project BLE с именем `LoRa-*` как trusted hint;
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

## Hotkeys

Локальной пользовательской `VIEW=CHAT/TELEMETRY/BOTH` больше нет. Human console определяется самой Chatter-нодой; optional BLE `0004` остаётся background/transcript-only channel.

```text
Ctrl+C         quit immediately

Ctrl+T 1/c     Chatter human console: CHAT
Ctrl+T 2/t     Chatter human console: TELEMETRY
Ctrl+T 3/b     Chatter human console: BOTH
Ctrl+T e       Chatter echo mode toggle

Ctrl+T d       device chooser
Ctrl+T s       Bluetooth capability scanner
Ctrl+T i       connection/status
Ctrl+T ?       full help (local hotkeys + Chatter /help)
```

Обе семьи `1/2/3` и `c/t/b` временно эквивалентны и управляют самой Chatter-нодой через стабильный raw ABI:

```text
Ctrl+T 1/c -> bytes 14 31 -> Chatter OUTPUT_CHAT
Ctrl+T 2/t -> bytes 14 32 -> Chatter OUTPUT_TELEMETRY
Ctrl+T 3/b -> bytes 14 33 -> Chatter OUTPUT_BOTH
Ctrl+T e   -> bytes 14 65 -> Chatter ECHO toggle
```

`Ctrl+T d/s/i` полностью локальны. `Ctrl+T ?` сначала печатает local help, затем отправляет Chatter `/help`.

## Канонические Chatter-команды

Human-readable команды отправляются контроллеру обычными строками:

```text
/help     show Chatter help
/id       show canonical node identity
/chat     human console CHAT
/tele     human console TELEMETRY
/both     human console BOTH
/echo     toggle diagnostic echo mode
/reboot   reboot ESP32 controller
```

Canonical identity Chatter имеет вид:

```text
[SYS] CHATTER NODE LoRa-Chatter-XXXX
```

Это то же имя, которое нода рекламирует по BLE. `serialterminal` не строит собственный node ID.

После успешного `SerialTransport.connect()` terminal автоматически отправляет `/id` **до** открытия reconnect-safe user TX gate. Поэтому накопленная USER/command очередь не может обогнать identity request. Это делается на каждом USB Serial connect/reconnect.

BLE NUS и Bluetooth SPP не получают автоматический `/id`: при выборе BLE имя ноды уже видно пользователю, а лишний host-side запрос не нужен. Явный `/id` при этом работает через любой transport.

При классификации команды `serialterminal` использует ту же boundary-normalization, что и текущий Chatter firmware: ASCII control/space + DEL по краям игнорируются только для command matching. Поэтому, например, строка `  /id  ` распознаётся как команда. Если после такого trim строка не совпала с известной командой, она остаётся обычным payload и отправляется **в исходном виде**.

`/reboot` намеренно text-only: для него нет нового raw `0x14` opcode и нет отдельного hotkey.

`/help` дополнительно интерпретируется локально: terminal печатает свои hotkeys и отправляет canonical `/help` контроллеру. Остальные команды идут через обычную reconnect-safe очередь в том виде, как их ввёл пользователь.

## TX presentation: кто имеет право печатать `>`

`serialterminal` никогда не синтезирует RF marker.

```text
> hello
> [ECHO TX] hello
```

Эти строки принадлежат Chatter firmware. На совместимой firmware они появляются только после подтверждённого TX и успешного возврата радио в RX.

Interactive payload после `Enter` сначала хранится как pending presentation и сразу записывается в transcript, но не дублируется на экране.

Успешный USER:

```text
> hello
```

Успешный ECHO request:

```text
> [ECHO TX] hello
```

Payload появляется на экране один раз — в firmware-owned success line.

Если firmware отвергает payload до успешного RF TX, terminal сначала показывает исходный submit как plain local line, затем оставляет firmware failure неизменённым:

```text
hello
[SYS] RADIO UNAVAILABLE, message not sent
```

или:

```text
hello
[ECHO] RADIO UNAVAILABLE
```

Plain `hello` означает только «это было отправлено пользователем в controller», а не RF success.

Никакого ANSI cursor-rewrite/history editing нет. Background `0004` telemetry не печатается в normal console, поэтому она не вмешивается в presentation. Все transport chunks при этом сразу сохраняются в transcript.

Если связь пропала после transport write, но до firmware outcome, sent-but-unresolved payload раскрывается как plain local line. Payload, который ещё не был физически записан в transport, остаётся pending и может быть отправлен обычным reconnect retry.

## Очереди

Есть три разных понятия, их нельзя смешивать:

```text
serialterminal outgoing transport queue
    queue.Queue() без maxsize
    reconnect-safe, практически unbounded

serialterminal pending presentation queue
    limit = 4 payload
    отдельна от transport queue

Chatter firmware InputEvent queue
    depth = 4
```

Presentation limit намеренно совпадает с текущей firmware input queue depth и защищает UI от бесконечного числа неразрешённых submit. Если четыре payload уже ждут outcome, следующий payload локально показывается как plain line и **не отправляется**:

```text
[serialterminal] pending presentation queue full; line not sent
```

Commands при этом не занимают presentation queue.

Оставшийся protocol/UI edge: firmware telemetry `INPUT QUEUE FULL dropped=N` сообщает cumulative drop count, но не identity конкретной строки. `serialterminal` не пытается угадывать соответствие такой потери эвристикой. Если это станет практически важным, нужен отдельный явно спроектированный host-facing outcome, а не cursor trick.

## Android / Kai Morich

В Android Serial Bluetooth Terminal можно использовать тот же набор:

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

## BLE NUS streams

Chatter BLE layout:

```text
NUS service             6E400001-B5A3-F393-E0A9-E50E24DCCA9E
INPUT / RX              6E400002-B5A3-F393-E0A9-E50E24DCCA9E
PRIMARY / human TX      6E400003-B5A3-F393-E0A9-E50E24DCCA9E
MACHINE TELEMETRY       6E400004-B5A3-F393-E0A9-E50E24DCCA9E
```

`serialterminal` подписывается на `0003`, затем best-effort на `0004` при наличии.

Human console на `0003` следует режиму Chatter:

```text
/chat  -> CHAT + SYSTEM
/tele  -> TELEMETRY + SYSTEM
/both  -> CHAT + TELEMETRY + SYSTEM
```

Если клиент подписан на `0004`, firmware отправляет туда TELEMETRY независимо от `/chat`, `/tele` или `/both`:

```text
0003 = human console
0004 = background machine telemetry
```

`serialterminal` не показывает `0004` в normal console. Полученные `0004` bytes декодируются отдельным stream state и сохраняются в transcript, поэтому данные доступны для последующего анализа/collector logic без дублирования пользовательского экрана.

Для старой firmware без `0004` BLE соединение остаётся валидным через стандартный `0003`.

## Line editing и отправка

Interactive input работает через `prompt_toolkit.PromptSession`.

До Enter пользователь редактирует локальную Unicode-строку. Backspace/Delete не отправляются устройству как отдельные bytes. После Enter в transport уходит одна complete line:

```text
edited text + configured line ending
```

Это отличается от byte-stream terminal вроде `pio device monitor`, где управляющие клавиши могут физически попасть в UART. Chatter firmware поэтому дополнительно имеет собственный input sanitizer.

## Reconnect и transport queue

Input отделён от transport I/O. Полная строка попадает в TX queue только после `Enter`.

Если target disconnect/reboot происходит во время отправки, текущий transport-queue element удерживается и повторяется после reconnect к тому же locked target.

Reconnect-safe queue относится к:

```text
/id /chat /tele /both /echo /reboot
/help controller request
raw Ctrl+T 1/2/3/c/t/b/e controls
ordinary USER/ECHO text
```

Автоматический Serial `/id` не кладётся в эту очередь: он отправляется непосредственно после успешного connect и до `connected_event`, чтобы queued user input не мог его обогнать.

Важно: output/echo mode хранится в RAM Chatter и после reboot возвращается к firmware defaults. `serialterminal` не переотправляет последний device mode автоматически после reconnect.

## Bluetooth scanner

Запуск:

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

На время scanner текущий transport отключается и reconnect ставится на паузу. После выхода терминал снова пытается подключиться к тому же sticky target. Набранная, но ещё не отправленная строка сохраняется.

BLE scanner ищет NUS RX `0002`, primary TX `0003` и отдельно отмечает optional telemetry `0004`.

Classic scanner делает BR/EDR discovery через BlueZ (`bluetoothctl`, fallback `hcitool`), SDP browse через `sdptool` и ищет Serial Port Profile / UUID `0x1101` и RFCOMM channel.

## Capability cache

Scanner сохраняет результаты в:

```text
~/.cache/serialterminal/devices.json
```

или под `$XDG_CACHE_HOME`.

Cache хранит capability state, время probe, имя/address, NUS streams и RFCOMM channel. Обычный chooser использует подтверждённые capabilities.

## Sticky identity

USB priority:

```text
/dev/serial/by-id/...
-> VID/PID + USB serial number
-> VID/PID + USB location
-> concrete tty path
```

Это transport identity, используемая для reconnect. Chatter node identity (`LoRa-Chatter-XXXX`) — отдельная controller-owned capability, получаемая через `/id`.

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
pytest -q
```

Покрыты command trim, `/id`, auto-ID только на Serial, отсутствие auto-ID на Bluetooth transport, USER/ECHO presentation, rejection, background `0004` telemetry, BLE chunk boundaries, duplicate payloads, disconnect semantics и full-duplex Serial regression.

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
