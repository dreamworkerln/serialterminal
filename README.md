# serialterminal

Обобщённый line-oriented терминал для USB Serial, Bluetooth LE / Nordic UART Service (NUS) и Classic Bluetooth Serial Port Profile (SPP/RFCOMM).

Терминал редактирует строку локально и отправляет её в устройство только после `Enter`. Исходящие строки переживают временный disconnect/reboot и отправляются после reconnect к **тому же выбранному физическому устройству**.

## Что поддержано

- USB Serial через `pyserial`;
- BLE NUS через `bleak`;
- Classic Bluetooth SPP/RFCOMM на Linux через BlueZ + Python Bluetooth sockets;
- unified device chooser;
- sticky reconnect по стабильной identity;
- отдельные BLE streams `CHAT`, `TELEMETRY`, `BOTH`;
- локальные hotkeys `Ctrl+T ...`;
- capability cache для найденных NUS/SPP устройств;
- отдельный aggressive Bluetooth scanner/prober;
- лог с немедленным `flush()`;
- `LF`, `CRLF` или `CR` после `Enter`.

## Обычный режим: безопасный discovery

```bash
serialterminal
```

Обычный режим **не подключается подряд ко всем неизвестным Bluetooth-устройствам**. В chooser попадают:

- USB Serial;
- project BLE с именем `LoRa-*` как trusted hint;
- BLE, рекламирующие NUS service UUID;
- BLE с ранее подтверждённым scanner'ом NUS;
- Classic Bluetooth устройства с ранее подтверждённым scanner'ом SPP.

Неизвестный BLE по умолчанию скрыт. Это задаётся константой в коде:

```python
SHOW_ALL_BLE_DEVICES = False
```

Runtime-команды для переключения этого режима пока нет.

Правило выбора:

```text
0 devices  -> scan/wait
1 device   -> autoconnect + lock target
2+ devices -> numbered menu
```

После выбора reconnect идёт только к той же physical identity. Другой доступный target не используется как fallback. Сменить устройство можно через `Ctrl+T d`.

## Bluetooth scanner / capability probe

Scanner — отдельный агрессивный режим. Он намеренно смотрит **все** найденные Bluetooth-устройства и пытается определить terminal capability.

Интерактивное меню:

```bash
serialterminal scan
```

```text
Bluetooth scanner
  1. Probe all BLE devices for NUS
  2. Probe Classic Bluetooth devices for SPP
  3. Probe all Bluetooth
Scan [1-3]:
```

Без меню:

```bash
serialterminal scan ble
serialterminal scan spp
serialterminal scan all
```

Дополнительно:

```bash
serialterminal scan all --scan-seconds 8 --probe-timeout 10
serialterminal scan spp --no-rfcomm-test
```

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

Scanner сначала делает BR/EDR discovery через BlueZ (`bluetoothctl`, fallback `hcitool`), затем для каждой ноды делает SDP browse через `sdptool` и ищет Serial Port Profile / UUID `0x1101` и RFCOMM channel.

Если SPP найден, по умолчанию scanner также пытается кратко открыть RFCOMM connection. Неудачный connect test **не отменяет** подтверждённый по SDP SPP capability — например, устройство может требовать pairing/PIN.

Для отключения connect test:

```bash
serialterminal scan spp --no-rfcomm-test
```

## Capability cache

Результаты scanner сохраняются в:

```text
~/.cache/serialterminal/devices.json
```

или под `$XDG_CACHE_HOME`, если он задан.

Для тестов/отладки путь можно переопределить:

```bash
SERIALTERMINAL_CACHE_FILE=/tmp/serialterminal-devices.json serialterminal scan all
```

Cache хранит `YES / NO / UNKNOWN`, время probe, имя/address, NUS streams и RFCOMM channel. Обычный chooser использует только **подтверждённые** capabilities.

Именно поэтому устройство с произвольным именем вроде `Nordic_UART` или `ESP32-Terminal` после успешного NUS probe начинает появляться в обычном `serialterminal` независимо от префикса `LoRa-`.

## Явные transport modes

Unified:

```bash
serialterminal
serialterminal auto
serialterminal --list
```

Serial-only:

```bash
serialterminal serial
serialterminal serial /dev/ttyUSB0
serialterminal serial -b 9600 /dev/ttyUSB0
serialterminal serial --list
```

BLE NUS-only:

```bash
serialterminal ble
serialterminal ble pinger
serialterminal ble repeater
serialterminal ble LoRa-Chatter-72E0
serialterminal ble Nordic_UART
```

`p` / `r` aliases сохранены; произвольное значение воспринимается как точное advertised name.

SPP-only (показывает подтверждённые scanner'ом SPP targets):

```bash
serialterminal spp
```

Compatibility wrapper NUS также сохранён:

```bash
python3 tools/nus_terminal.py
python3 tools/nus_terminal.py pinger
python3 tools/nus_terminal.py repeater
```

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

После выбора target фиксируется по BLE address. Advertised name используется для отображения и explicit name filter.

### Bluetooth SPP

SPP target фиксируется по Bluetooth address + подтверждённому RFCOMM channel. Reconnect открывает RFCOMM только к этому address.

## Hotkeys

```text
Ctrl+C         quit immediately
Ctrl+T 1       CHAT view
Ctrl+T 2       TELEMETRY view
Ctrl+T 3       BOTH views
Ctrl+T d       device chooser
Ctrl+T i       connection/status
Ctrl+T ?       help
```

Hotkeys локальные и никогда не отправляются в устройство.

USB Serial и Bluetooth SPP имеют один физический stream `main`, поэтому CHAT/TELEMETRY filtering для них не применяется. BLE Chatter может иметь два независимых notify streams; оба всегда пишутся в log, даже если один скрыт на экране.

## Reconnect и очередь команд

Input отделён от transport I/O. Полная строка попадает в TX queue только после `Enter`. Если target reboot'ится во время отправки, текущая строка остаётся в очереди и будет повторно отправлена после reconnect к тому же locked target.

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

Для Classic Bluetooth scanner/SPP на Linux нужны BlueZ tools (`bluetoothctl`, `sdptool`; `hcitool` используется только как legacy fallback). RFCOMM transport использует встроенный Python `socket.AF_BLUETOOTH / BTPROTO_RFCOMM`.

Debian/Ubuntu:

```bash
sudo apt install bluez
```

## Установка для разработки

```bash
git clone https://github.com/dreamworkerln/serialterminal.git
cd serialterminal
git switch dev

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ble,dev]'
```

На старой системе можно поставить зависимости отдельно и запускать исходники без editable install:

```bash
pip install pyserial prompt-toolkit bleak pytest
PYTHONPATH=src python3 -m serialterminal
PYTHONPATH=src python3 -m serialterminal scan
```

Tests:

```bash
pytest -q
python3 -m compileall -q src tools serialterm.py
```
