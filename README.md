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
Ctrl+T 1       CHAT view
Ctrl+T 2       TELEMETRY view
Ctrl+T 3       BOTH views
Ctrl+T d       device chooser
Ctrl+T s       Bluetooth capability scanner
Ctrl+T i       connection/status
Ctrl+T ?       help
```

Hotkeys локальные и никогда не отправляются в устройство.

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

USB Serial и Bluetooth SPP имеют один физический stream `main`, поэтому CHAT/TELEMETRY filtering для них не применяется.

BLE Chatter может иметь два независимых notify streams:

```text
CHAT       0003
TELEMETRY  0004
```

Оба всегда пишутся в log, даже если один скрыт на экране.

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

и затем локальные hotkeys, включая `Ctrl+T s`.

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
