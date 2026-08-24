# serialterminal

Обобщённый консольный терминал с единым line-oriented интерфейсом и подключаемыми transport-реализациями.

Сейчас реализованы:

- **Serial Port** через `pyserial`;
- **Bluetooth LE / Nordic UART Service (NUS)** через `bleak`.

Терминал не отправляет клавиши по одной: строка редактируется локально и попадает в transport только после `Enter`.

## Основные свойства

- общий terminal core для Serial и BLE;
- отправка целой строки только после `Enter`;
- история и редактирование строки через `readline`, когда он доступен;
- очередь исходящих строк: команда, набранная во время disconnect/reboot, ждёт reconnect и не теряется;
- входящий поток сразу пишется в лог и `flush()`-ится;
- автоматический reconnect;
- `LF`, `CRLF` или `CR`;
- отсутствие собственного `>` prompt.

### Serial

- `/dev/serial/by-id/...` имеет приоритет перед `/dev/ttyUSB*` и `/dev/ttyACM*`;
- настраиваемый baud rate, 8N1;
- best-effort защита ESP32 от нежелательного reset: безопасная последовательность DTR/RTS и отключение `HUPCL` на Linux.

### BLE NUS

Поддержаны ноды:

```text
LoRa-Pinger
LoRa-Repeater
```

Поведение перенесено из `tools/nus_terminal.py`:

- виден только один Pinger/Repeater → он выбирается автоматически;
- видны оба → терминал спрашивает `P` или `R`;
- после выбора target фиксируется по имени;
- после reboot/disconnect reconnect идёт только к выбранному target;
- другая LoRa-нода не используется как fallback;
- BLE RX логируется в `nus-pinger-YYYYMMDD-HHMMSS.log` или `nus-repeater-YYYYMMDD-HHMMSS.log`;
- лог flush'ится сразу, поэтому строки перед reboot, включая `FATAL`, остаются на диске.

Для текущих прошивок Pinger/Repeater можно отправлять:

```text
LF   full logging
LC   compact logging
L    current logging mode
```

## Структура

```text
serialterminal/
├── src/serialterminal/
│   ├── cli.py
│   ├── terminal.py
│   └── transports/
│       ├── base.py
│       ├── serial.py
│       └── ble_nus.py
├── tools/
│   └── nus_terminal.py
├── tests/
├── serialterm.py
├── pyproject.toml
└── .github/workflows/ci.yml
```

`Transport` — общий byte-stream интерфейс. `SerialTransport` и `BleNusTransport` реализуют его независимо от terminal UI.

## Установка для разработки

```bash
git clone https://github.com/dreamworkerln/serialterminal.git
cd serialterminal
git switch dev

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Для BLE:

```bash
pip install -e '.[ble]'
```

Для разработки с pytest:

```bash
pip install -e '.[dev]'
```

## Serial Port

Старый CLI полностью сохранён:

```bash
serialterminal
serialterminal /dev/ttyUSB0
serialterminal -b 9600 /dev/ttyUSB0
serialterminal --list
```

Можно писать transport явно:

```bash
serialterminal serial
serialterminal serial /dev/ttyUSB0
serialterminal serial -b 115200 /dev/ttyUSB0
```

Без установки пакета:

```bash
python3 serialterm.py
python3 serialterm.py serial /dev/ttyUSB0
```

### Окончание строки

```bash
serialterminal --eol lf
serialterminal --eol crlf
serialterminal --eol cr
```

## Bluetooth NUS

Автовыбор/выбор между двумя видимыми нодами:

```bash
serialterminal ble
```

Сразу зафиксировать Pinger:

```bash
serialterminal ble pinger
```

Сразу зафиксировать Repeater:

```bash
serialterminal ble repeater
```

Короткие варианты тоже принимаются:

```bash
serialterminal ble p
serialterminal ble r
```

Старый путь запуска сохранён как compatibility wrapper:

```bash
python3 tools/nus_terminal.py
python3 tools/nus_terminal.py pinger
python3 tools/nus_terminal.py repeater
```

По умолчанию BLE использует `LF`. Изменить можно так:

```bash
serialterminal ble repeater --eol crlf
```

Свой файл лога:

```bash
serialterminal ble repeater --log repeater-debug.log
```

## Reconnect и очередь команд

Ввод пользователя отделён от передачи.

Например, если во время reboot Repeater набрать:

```text
LC<Enter>
L<Enter>
```

обе полные строки остаются в исходящей очереди. После восстановления выбранного BLE target они отправятся в том же порядке. К Pinger терминал при этом не переключится.

То же правило действует для Serial: временное исчезновение USB-порта не превращает ввод в per-key передачу и не выбрасывает уже введённую строку.

## ESP32 / DTR / RTS

`SerialTransport` старается не генерировать reset при открытии порта:

1. перед `open()` задаётся безопасное промежуточное состояние DTR/RTS;
2. после открытия обе линии деактивируются;
3. на Linux отключается `HUPCL`.

Это best-effort: поведение конкретного USB-UART и драйвера всё равно может отличаться.

## Права доступа Linux

При `Permission denied` для Serial:

```bash
sudo usermod -aG dialout "$USER"
```

После этого нужно перелогиниться.

## Тесты

```bash
pip install -e '.[dev]'
pytest -q
python3 -m compileall -q src tools
```
