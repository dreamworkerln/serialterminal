# serialterminal

Обобщённый line-oriented терминал для USB Serial и Bluetooth LE / Nordic UART Service (NUS).

Терминал редактирует строку локально и отправляет её в устройство только после `Enter`. Исходящие строки переживают временный disconnect/reboot и отправляются после reconnect к **тому же выбранному устройству**.

## Текущее поведение

Поддержаны:

- USB Serial через `pyserial`;
- BLE NUS через `bleak`;
- единый terminal core;
- numbered device chooser;
- sticky reconnect к выбранному physical target;
- отдельные BLE views `CHAT`, `TELEMETRY`, `BOTH` для Chatter;
- immediate `Ctrl+C` exit;
- локальные control hotkeys с префиксом `Ctrl+T`;
- лог с немедленным `flush()`;
- `LF`, `CRLF` или `CR`.

## Запуск и выбор устройства

Обычный запуск теперь делает unified discovery:

```bash
serialterminal
```

Ищутся одновременно:

- доступные USB serial devices;
- BLE devices с advertised name `LoRa-*` (если установлен BLE extra).

Правило выбора:

```text
0 devices
    -> продолжать scan/wait

1 device
    -> autoconnect
    -> lock target

2+ devices
    -> никакого autoconnect
    -> numbered menu
```

Пример:

```text
Detected devices:
  1. USB  USB JTAG/serial debug unit
     /dev/serial/by-id/usb-Espressif_...  VID:PID=303A:1001  serial=...
  2. BLE  LoRa-Chatter-72E0
     AA:BB:CC:11:22:33
  3. BLE  LoRa-Chatter-A193
     DD:EE:FF:44:55:66
Connect to [1-3]:
```

После выбора target фиксируется на всю текущую terminal session. Если он исчез:

```text
[disconnected: ...]
[waiting for selected device...]
```

другое видимое устройство **не используется как fallback**. Reconnect продолжает искать только выбранную identity. Сменить target можно только явно через `Ctrl+T d`.

### Sticky USB identity

При наличии `/dev/serial/by-id/...` используется именно этот стабильный путь. Если `by-id` отсутствует, terminal старается привязаться по USB serial number + VID/PID, затем по USB location + VID/PID. Только последний fallback — конкретный tty path.

Поэтому выбранный ESP32, который после reboot переехал с `/dev/ttyACM0` на `/dev/ttyACM1`, не должен автоматически заменяться другим первым портом.

### Sticky BLE identity

После initial selection BLE target фиксируется по BLE address, а advertised name используется для отображения. Reconnect сканирует только выбранный address и не перепрыгивает на другую `LoRa-*` ноду.

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

`Ctrl+T` hotkeys — локальные команды terminal. Они никогда не отправляются в устройство.

`Ctrl+T d` временно disconnect'ит текущий target, сканирует доступные устройства и показывает numbered menu. `Enter` отменяет смену и reconnect'ит прежний target. `Ctrl+C` даже внутри menu немедленно завершает программу.

## Chatter BLE streams

Chatter использует один NUS service и три characteristics:

```text
INPUT
6E400002-B5A3-F393-E0A9-E50E24DCCA9E

CHAT notify
6E400003-B5A3-F393-E0A9-E50E24DCCA9E

TELEMETRY notify
6E400004-B5A3-F393-E0A9-E50E24DCCA9E
```

При BLE connect terminal всегда подписывается на `0003 CHAT` и best-effort также на `0004 TELEMETRY`. Старые Echo firmware, у которых существует только стандартный NUS TX `0003`, продолжают работать.

Переключение `Ctrl+T 1/2/3` — это **локальный display filter**, а не BLE disconnect/reconnect:

```text
BLE connection
    +-- 0003 CHAT ---------+
    +-- 0004 TELEMETRY ----+--> local view: CHAT / TELEMETRY / BOTH
```

Оба потока продолжают приниматься и записываться в session log, даже если один из них сейчас скрыт с экрана.

USB Serial физически является одним combined stream, поэтому на USB `Ctrl+T 1/2/3` не может разделить CHAT и TELEMETRY; terminal сообщает, что filtering доступен только для BLE.

## Явные transport modes

Unified mode:

```bash
serialterminal
serialterminal auto
serialterminal auto --scan-seconds 5
```

Serial-only:

```bash
serialterminal serial
serialterminal serial /dev/ttyUSB0
serialterminal serial -b 9600 /dev/ttyUSB0
serialterminal serial --list
```

Старый explicit serial path по-прежнему работает:

```bash
serialterminal /dev/ttyUSB0
serialterminal -b 9600 /dev/ttyUSB0
```

BLE-only:

```bash
serialterminal ble
serialterminal ble pinger
serialterminal ble repeater
serialterminal ble LoRa-Chatter-72E0
```

`p`/`r` aliases сохранены.

Compatibility wrapper также сохранён:

```bash
python3 tools/nus_terminal.py
python3 tools/nus_terminal.py pinger
python3 tools/nus_terminal.py repeater
```

## Reconnect и очередь команд

Terminal input отделён от transport I/O. Если выбранная нода reboot'ится, уже набранные полные строки остаются в исходящей очереди и отправляются после восстановления **этого же locked target**.

Никакая клавиша не передаётся per-key; обычный текст уходит только после `Enter`.

## ESP32 / DTR / RTS

`SerialTransport` сохраняет best-effort no-reset последовательность:

1. перед `open()` выставляется безопасное промежуточное DTR/RTS состояние;
2. после открытия обе линии deassert;
3. на Linux отключается `HUPCL`.

## Установка для разработки

```bash
git clone https://github.com/dreamworkerln/serialterminal.git
cd serialterminal
git switch dev

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

BLE support:

```bash
pip install -e '.[ble]'
```

Tests:

```bash
pip install -e '.[dev]'
pytest -q
python3 -m compileall -q src tools serialterm.py
```
