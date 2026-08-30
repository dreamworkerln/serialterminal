# serialterminal

Обобщённый line-oriented терминал для USB Serial, Bluetooth LE / Nordic UART Service (NUS) и Classic Bluetooth Serial Port Profile (SPP/RFCOMM).

Терминал редактирует строку локально и отправляет её в устройство только после `Enter`. Исходящие строки переживают временный disconnect/reboot и отправляются после reconnect к **тому же выбранному физическому устройству**.

## Обычный запуск

Основной пользовательский вход один:

```bash
python3 serialterminal.py
```

По умолчанию session log:

```text
serialterminal.log
```

То есть имя launcher и основного log теперь одинаковое по базе:

```text
serialterminal.py
serialterminal.log
```

Внутренние `src/serialterminal/...` модули — только устройство проекта. Для обычной работы их руками запускать не требуется.

После запуска терминал сразу напоминает:

```text
Type /help or press Ctrl+T ? for full help.
```

Оба способа эквивалентны: сначала `serialterminal` печатает свои hotkeys, затем отправляет контроллеру обычную строку `/help` через reconnect-safe очередь.

## Что поддержано

- USB Serial через `pyserial`;
- BLE NUS через `bleak`;
- Classic Bluetooth SPP/RFCOMM на Linux через BlueZ + Python Bluetooth sockets;
- unified device chooser;
- sticky reconnect по стабильной identity;
- отдельные BLE streams `CHAT`, `TELEMETRY`, `BOTH`;
- локальные hotkeys `Ctrl+T ...`;
- полный help через `/help` или `Ctrl+T ?`;
- отдельное управление локальным BLE view через `Ctrl+T 1/2/3`;
- отдельное управление Chatter firmware output через `Ctrl+T c/t/b`;
- Chatter echo-mode toggle через `Ctrl+T e` независимо от USB/BLE/SPP transport;
- capability cache для найденных NUS/SPP устройств;
- aggressive Bluetooth scanner/prober из самого терминала;
- лог с немедленным `flush()`;
- `LF`, `CRLF` или `CR` после `Enter`.

## Обычный discovery

После запуска:

```bash
python3 serialterminal.py
```

обычный режим **не подключается подряд ко всем неизвестным Bluetooth-устройствам**. В chooser попадают:

- USB Serial;
- project BLE с именем `LoRa-*` как trusted hint;
- BLE, рекламирующие NUS service UUID;
- BLE с ранее подтверждённым scanner'ом NUS;
- Classic Bluetooth устройства с ранее подтверждённым scanner'ом SPP.

Неизвестный BLE по умолчанию скрыт. Это задаётся константой в коде:

```python
SHOW_ALL_BLE_DEVICES = False
```

Runtime-переключателя этого флага пока нет.

Правило выбора:

```text
0 devices  -> scan/wait
1 device   -> autoconnect + lock target
2+ devices -> numbered menu
```

После выбора reconnect идёт только к той же physical identity. Другой доступный target не используется как fallback. Сменить устройство можно через `Ctrl+T d`.

## Hotkeys

```text
Ctrl+C         quit immediately

Ctrl+T 1       local CHAT view (BLE only)
Ctrl+T 2       local TELEMETRY view (BLE only)
Ctrl+T 3       local BOTH view (BLE only)

Ctrl+T c       Chatter device output: CHAT
Ctrl+T t       Chatter device output: TELEMETRY
Ctrl+T b       Chatter device output: BOTH
Ctrl+T e       Chatter echo mode toggle

Ctrl+T d       device chooser
Ctrl+T s       Bluetooth capability scanner
Ctrl+T i       connection/status
Ctrl+T ?       full help (local hotkeys + Chatter /help)
```

### Полный help

Два пользовательских способа полностью эквивалентны:

```text
/help
Ctrl+T ?
```

Порядок вывода намеренно такой:

```text
1. serialterminal печатает свои hotkeys локально
2. serialterminal ставит /help в обычную TX queue
3. Chatter controller печатает свою часть help
```

Никакого специального end-marker или отдельного help-протокола между Python и firmware нет. `/help` — обычная текстовая локальная команда Chatter.

### VIEW и DEVICE OUTPUT — разные вещи

`Ctrl+T 1/2/3` — **только локальный view терминала**. Они ничего не отправляют Chatter-нode.

Для BLE это позволяет, например, оставить firmware в `BOTH`, показывать на экране только CHAT, но продолжать получать TELEMETRY в отдельном notify stream и сохранять её в `serialterminal.log`.

```text
Ctrl+T 1 -> показать только BLE CHAT
Ctrl+T 2 -> показать только BLE TELEMETRY
Ctrl+T 3 -> показать оба BLE stream
```

USB Serial и Bluetooth SPP физически имеют один stream `main`, поэтому локально разделить его на CHAT/TELEMETRY нельзя. На этих transports `Ctrl+T 1/2/3` не могут отфильтровать уже смешанный поток; для реального отключения одного типа вывода используются device-команды `Ctrl+T c/t/b`.

`Ctrl+T c/t/b/e` — **команды самой Chatter-ноды**. Они отправляются через ту же reconnect-safe TX queue, что и обычные строки, поэтому одинаково работают через USB Serial, BLE NUS и Bluetooth SPP.

Human-facing hotkeys `c/t/b` специально отделены от стабильных raw Chatter opcodes. На проводе сейчас остаются:

```text
Ctrl+T c -> bytes 14 31 -> Chatter OUTPUT_CHAT
Ctrl+T t -> bytes 14 32 -> Chatter OUTPUT_TELEMETRY
Ctrl+T b -> bytes 14 33 -> Chatter OUTPUT_BOTH
Ctrl+T e -> bytes 14 65 -> Chatter ECHO toggle
```

То есть `serialterminal` не меняет firmware command ABI: он только даёт более понятные отдельные hotkeys для device output.

`Ctrl+T d/s/i` остаются полностью локальными командами `serialterminal`. `Ctrl+T ?` сначала печатает local hotkeys, а затем отправляет Chatter обычную `/help`.

Chatter сам сообщает применённое состояние (`[SYS] OUTPUT ...`, telemetry `OUTPUT MODE ...`, `[SYS] ECHO MODE ON/OFF`), поэтому terminal не пытается угадывать состояние ноды.

### Те же команды в Android

Для Android Serial Bluetooth Terminal от Kai Morich удобно создать HEX macro-кнопки:

```text
CHAT       14 31
TELEMETRY  14 32
BOTH       14 33
ECHO       14 65
```

Android-клавиатуре физическая клавиша Ctrl не нужна: macro посылает непосредственно те же control bytes, которые ожидает Chatter firmware.

Новый `dev_chat` использует стандартный NUS TX `0003` как compatibility/primary output. Если клиент не подписан на дополнительный `0004`, telemetry автоматически идёт в `0003`. Поэтому обычный NUS Android-клиент видит все три device mode через один стандартный stream.

## Bluetooth scanner

Scanner запускается **из уже работающего терминала**:

```text
Ctrl+T s
```

Появится меню:

```text
Bluetooth scanner
  1. Probe all BLE devices for NUS
  2. Probe Classic Bluetooth devices for SPP
  3. Probe all Bluetooth
  Enter. Back to terminal
Scan [1-3, Enter=back]:
```

На время scanner текущий transport отключается и reconnect ставится на паузу. После выхода scanner терминал снова пытается подключиться к **тому же sticky target**. Набранная, но ещё не отправленная строка сохраняется в prompt.

### BLE probe

Для каждого BLE device scanner подключается, делает GATT service discovery и ищет:

```text
NUS service
6E400001-B5A3-F393-E0A9-E50E24DCCA9E

INPUT / RX
6E400002-B5A3-F393-E0A9-E50E24DCCA9E

PRIMARY / standard NUS TX
6E400003-B5A3-F393-E0A9-E50E24DCCA9E

DEDICATED TELEMETRY (optional)
6E400004-B5A3-F393-E0A9-E50E24DCCA9E
```

Практическая граница совместимости терминала — наличие RX `0002` и standard TX `0003`. `0004` помечается отдельно как telemetry capability.

Ошибки подключения/timeout записываются как `UNKNOWN`, а не как `NO`.

### Classic Bluetooth SPP probe

Scanner делает BR/EDR discovery через BlueZ (`bluetoothctl`, fallback `hcitool`), затем SDP browse через `sdptool` и ищет Serial Port Profile / UUID `0x1101` и RFCOMM channel.

Если SPP найден, scanner также пытается кратко открыть RFCOMM connection. Неудачный connect test **не отменяет** подтверждённый по SDP SPP capability: устройство может требовать pairing/PIN.

## Capability cache

Результаты scanner сохраняются в:

```text
~/.cache/serialterminal/devices.json
```

или под `$XDG_CACHE_HOME`, если он задан.

Cache хранит `YES / NO / UNKNOWN`, время probe, имя/address, NUS streams и RFCOMM channel. Обычный chooser использует только подтверждённые capabilities.

Поэтому устройство с произвольным именем вроде `Nordic_UART` или `ESP32-Terminal` после успешного NUS probe начинает появляться в обычном `python3 serialterminal.py` независимо от префикса `LoRa-`.

## Sticky identity

### USB

Приоритет identity:

```text
/dev/serial/by-id/...
-> VID/PID + USB serial number
-> VID/PID + USB location
-> concrete tty path
```

### BLE NUS

После выбора target фиксируется по BLE address.

### Bluetooth SPP

SPP target фиксируется по Bluetooth address + подтверждённому RFCOMM channel.

## BLE streams

Chatter BLE routing теперь выглядит так:

```text
0003  PRIMARY / standard NUS TX
0004  DEDICATED TELEMETRY
```

`serialterminal` при подключении подписывается сначала на `0003`, затем на `0004`. Если подписка на `0004` успешна, Chatter видит её через CCCD и оставляет логические потоки раздельными:

```text
CHAT       -> 0003
TELEMETRY  -> 0004
```

Поэтому в firmware mode `BOTH` `serialterminal` получает оба stream без дублей. Локальный `Ctrl+T 1/2/3` меняет только то, что видно на экране; скрытый BLE stream всё равно сохраняется в transcript.

Если `0004` отсутствует или клиент на него не подписался, Chatter отправляет TELEMETRY через `0003` как fallback. Это нужно обычным NUS-клиентам, включая Android terminal, которые работают только со стандартной парой RX/TX.

Если отправить device-команду `Ctrl+T c` или `Ctrl+T t`, соответствующий логический producer перестаёт генерироваться уже на самой ноде и, естественно, больше не попадёт ни на экран, ни в log.

USB Serial и Bluetooth SPP имеют один физический stream `main`. Там локальный view не может разложить смешанные bytes обратно по типам, поэтому для настоящего CHAT-only или TELEMETRY-only режима используются `Ctrl+T c/t/b`.

## Reconnect и очередь команд

Input отделён от transport I/O. Полная строка попадает в TX queue только после `Enter`. Если target reboot'ится во время отправки, текущая строка остаётся в очереди и будет повторно отправлена после reconnect к тому же locked target.

Chatter device controls `Ctrl+T c/t/b/e` и controller-часть полного help (`/help`) используют ту же очередь. Локальные view-команды `Ctrl+T 1/2/3` в outgoing queue не попадают.

Важно: output/echo mode живёт в RAM самой Chatter-ноды и после reboot возвращается к firmware default (`BOTH`, echo OFF). `serialterminal` пока не переотправляет последний device mode автоматически после каждого reconnect; при необходимости hotkey можно нажать снова после reboot.

## ESP32 / DTR / RTS

`SerialTransport` сохраняет best-effort no-reset последовательность:

1. безопасное промежуточное DTR/RTS перед `open()`;
2. deassert обеих линий после открытия;
3. отключение `HUPCL` на Linux.

## Зависимости

Python:

```text
pyserial
prompt-toolkit
bleak        # для BLE
```

На старом Linux можно поставить их отдельно, без editable install:

```bash
pip install pyserial prompt-toolkit bleak
python3 serialterminal.py
```

Для Classic Bluetooth scanner/SPP нужны BlueZ tools:

```bash
sudo apt install bluez
```

Проверка:

```bash
which bluetoothctl
which sdptool
```

## Диагностика Bluetooth disconnect на Linux

Если BLE/SPP начинает периодически disconnect/reconnect, полезно сначала посмотреть причину на уровне HCI/BlueZ, отдельно от `serialterminal`.

Короткая грепалка для `btmon`, которая показывает только события disconnect и несколько строк причины:

```bash
sudo btmon \
  | grep --line-buffered -Ei -A 6 \
      'Disconnect Complete|Device Disconnected'
```

Например, такой вывод:

```text
> HCI Event: Disconnect Complete
    Status: Success (0x00)
    Reason: Connection Timeout (0x08)
@ MGMT Event: Device Disconnected
    Reason: Connection timeout (0x01)
```

означает, что Bluetooth controller сообщил о link/supervision timeout. Это уже ниже уровня Python/Bleak и само по себе не означает, что disconnect инициировал `serialterminal`.

На Debian/Ubuntu/Linux Mint при повторяющихся Bluetooth timeout первым делом рекомендуется обновить BlueZ и firmware-пакеты системы, затем перезагрузиться и повторить тот же тест:

```bash
sudo apt update
sudo apt install --only-upgrade bluez linux-firmware
sudo reboot
```

Проверить установленные версии можно так:

```bash
dpkg -l bluez linux-firmware | grep '^ii'
uname -r
```

Если timeout сохраняется на старом Ubuntu 22.04-based stack, имеет смысл также проверить более новое поддерживаемое ядро/HWE. Для Ubuntu 22.04:

```bash
sudo apt install linux-generic-hwe-22.04
sudo reboot
```

После каждого изменения лучше менять только одну переменную и снова смотреть `btmon`, чтобы отличить проблему приложения от BlueZ/kernel/firmware/controller или RF-условий.

## Дополнительные CLI режимы

Они существуют для диагностики и автоматизации, но для обычной работы не нужны:

```bash
python3 serialterminal.py serial
python3 serialterminal.py ble
python3 serialterminal.py spp
python3 serialterminal.py scan
```

Основной сценарий остаётся:

```bash
python3 serialterminal.py
```

и затем hotkeys `Ctrl+T 1/2/3`, `Ctrl+T c/t/b/e`, `Ctrl+T d/s/i/?` или `/help`.

## Разработка

```bash
git clone https://github.com/dreamworkerln/serialterminal.git
cd serialterminal
git switch dev
```

Tests:

```bash
pytest -q
python3 -m compileall -q src tools serialterminal.py
```
