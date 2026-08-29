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

## Что поддержано

- USB Serial через `pyserial`;
- BLE NUS через `bleak`;
- Classic Bluetooth SPP/RFCOMM на Linux через BlueZ + Python Bluetooth sockets;
- unified device chooser;
- sticky reconnect по стабильной identity;
- отдельные BLE streams `CHAT`, `TELEMETRY`, `BOTH`;
- локальные hotkeys `Ctrl+T ...`;
- Chatter output-mode control через `Ctrl+T 1/2/3` независимо от USB/BLE/SPP transport;
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
Ctrl+T 1       CHAT view + Chatter CHAT output
Ctrl+T 2       TELEMETRY view + Chatter TELEMETRY output
Ctrl+T 3       BOTH views + Chatter BOTH output
Ctrl+T d       device chooser
Ctrl+T s       Bluetooth capability scanner
Ctrl+T e       Chatter echo mode toggle
Ctrl+T i       connection/status
Ctrl+T ?       help
```

`Ctrl+T d/s/i/?` — чисто локальные команды `serialterminal`; они никогда не отправляются устройству.

Для Chatter четыре hotkey являются одновременно локальными UI-действиями и firmware-командами:

```text
Ctrl+T 1 -> локальный CHAT view      + bytes 14 31
Ctrl+T 2 -> локальный TELEMETRY view + bytes 14 32
Ctrl+T 3 -> локальный BOTH view      + bytes 14 33
Ctrl+T e ->                            bytes 14 65
```

Служебные байты идут через ту же reconnect-safe TX queue, что и обычные строки. Поэтому одинаковое управление работает через USB Serial, BLE NUS и Bluetooth SPP. Добавляемый терминалом line ending после control bytes для Chatter безвреден.

В Chatter `1/2/3` меняют уже **сам firmware output**, а не только экранный фильтр терминала. Это особенно важно для USB Serial/SPP, где физически есть один stream `main`: ненужная TELEMETRY действительно перестаёт выводиться нодой в режиме CHAT.

Chatter сам сообщает применённое состояние (`[SYS] OUTPUT ...`, telemetry `OUTPUT MODE ...`, `[SYS] ECHO MODE ON/OFF`), поэтому terminal не пытается угадывать состояние ноды.

### Те же команды в Android

Для Android Serial Bluetooth Terminal от Kai Morich удобно создать HEX macro-кнопки:

```text
CHAT       14 31
TELEMETRY  14 32
BOTH       14 33
ECHO       14 65
```

То есть Android-клавиатуре вообще не нужна физическая клавиша Ctrl: macro посылает те же байты, которые `serialterminal` формирует из `Ctrl+T ...`.

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

CHAT / TX
6E400003-B5A3-F393-E0A9-E50E24DCCA9E

TELEMETRY (optional)
6E400004-B5A3-F393-E0A9-E50E24DCCA9E
```

Практическая граница совместимости терминала — наличие RX `0002` и CHAT/TX `0003`. `0004` помечается отдельно как telemetry capability.

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

BLE Chatter может иметь два независимых notify streams:

```text
CHAT       0003
TELEMETRY  0004
```

`serialterminal` по-прежнему умеет фильтровать их локально по `view_mode`, но для нового Chatter `Ctrl+T 1/2/3` дополнительно переключает генерацию stream на самой ноде.

USB Serial и Bluetooth SPP имеют один физический stream `main`; локально разделить его на CHAT/TELEMETRY невозможно, поэтому firmware-side output mode как раз даёт настоящее переключение и для этих transports.

## Reconnect и очередь команд

Input отделён от transport I/O. Полная строка попадает в TX queue только после `Enter`. Если target reboot'ится во время отправки, текущая строка остаётся в очереди и будет повторно отправлена после reconnect к тому же locked target.

Chatter control hotkeys `Ctrl+T 1/2/3/e` используют ту же очередь, поэтому сама команда не теряется только из-за краткого disconnect между нажатием hotkey и фактической отправкой.

Важно: output/echo mode живёт в RAM самой Chatter-ноды и после reboot возвращается к firmware default (`BOTH`, echo OFF). `serialterminal` пока не переотправляет последний режим автоматически после каждого reconnect; hotkey можно нажать снова после reboot.

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

и затем hotkeys `Ctrl+T 1/2/3/e/d/s/i/?`.

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
