# serialterminal

Обобщённый консольный терминал с подключаемыми transport-реализациями.

Сейчас реализован **Serial Port**. Архитектура отделяет терминал от транспорта, чтобы следующим шагом добавить Bluetooth без переписывания строкового ввода, логирования и reconnect.

## Что уже умеет

- Serial Port через `pyserial`;
- ввод команды целой строкой: символы не уходят в устройство по одной клавише, команда отправляется только после `Enter`;
- история команд и редактирование строки средствами `readline`, когда модуль доступен;
- автоматический reconnect после отключения/подключения USB;
- приоритет стабильных `/dev/serial/by-id/...`, затем `/dev/ttyUSB*` и `/dev/ttyACM*`;
- 8N1 и настраиваемый baud rate;
- `LF`, `CRLF` или `CR` после `Enter`;
- лог терминальной сессии;
- отсутствие собственного prompt, чтобы не конфликтовать с prompt прошивки;
- best-effort режим без нежелательного reset на ESP32: безопасная последовательность DTR/RTS и отключение `HUPCL` на Linux.

> Полностью исключить аппаратный reset при открытии порта программно можно не для каждого USB-UART/драйвера. Реализация старается не дёргать reset-линии и сохраняет подход из исходного рабочего примера.

## Структура

```text
serialterminal/
├── src/serialterminal/
│   ├── cli.py
│   ├── terminal.py
│   └── transports/
│       ├── base.py
│       └── serial.py
├── tests/
├── serialterm.py
├── pyproject.toml
└── .github/workflows/ci.yml
```

`Transport` — общий byte-stream интерфейс. `SerialTransport` — его первая реализация. Bluetooth будет добавлен отдельным transport-модулем.

## Установка для разработки

```bash
git clone https://github.com/dreamworkerln/serialterminal.git
cd serialterminal
git switch dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Для Debian / Ubuntu также можно установить системный `pyserial`:

```bash
sudo apt update
sudo apt install python3-serial
```

## Запуск

После `pip install -e .`:

```bash
serialterminal
```

или совместимым именем:

```bash
serialterm
```

Без установки пакета:

```bash
python3 serialterm.py
```

По умолчанию: `115200`, 8N1, окончание строки `LF`.

### Автопоиск Serial Port

```bash
serialterminal
```

### Список устройств

```bash
serialterminal --list
```

### Явный порт

```bash
serialterminal /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
```

или:

```bash
serialterminal /dev/ttyUSB0
```

### Baud rate

```bash
serialterminal -b 9600 /dev/ttyUSB0
```

### Окончание строки

```bash
serialterminal --eol lf
serialterminal --eol crlf
serialterminal --eol cr
```

## Строковый ввод

Терминал использует обычный line-oriented ввод: набираемая команда редактируется локально, а в transport попадает один пакет только после `Enter`.

То есть ввод:

```text
status<Enter>
```

передаёт в Serial Port:

```text
status\n
```

а не `s`, затем `t`, затем `a` и т.д.

## ESP32 / DTR / RTS

ESP32 DevKit часто использует DTR/RTS для auto-reset и входа в bootloader. При открытии порта некоторые драйверы и serial-библиотеки могут кратковременно менять эти линии.

`SerialTransport` перед `open()` задаёт безопасное промежуточное состояние, после открытия деактивирует DTR/RTS и на Linux отключает `HUPCL`. Это сделано специально для уменьшения вероятности нежелательного reset.

## Права доступа Linux

Если появляется `Permission denied`:

```bash
sudo usermod -aG dialout "$USER"
```

Затем нужно перелогиниться.

## Тесты

```bash
pip install -e . pytest
pytest -q
```

CI запускает compile-check и тесты на каждый push/PR.

## Следующий transport

Следующий этап — Bluetooth. Он должен реализовать тот же `Transport` (`connect`, `disconnect`, `read`, `write`, `is_connected`, `description`), после чего общий терминал останется без изменений.
