# Chatter device chooser: NUS capability filtering TODO

TODO-ID: TODO_054
Status: CLOSED
Recorded: 2026-10-16

## Purpose

По запросу оператора убрать из выбора BLE-устройства для профиля `chatter`
наушники, телевизоры и прочие устройства без Nordic UART Service. Добавить
регрессионные тесты, чтобы неподходящие устройства не возвращались через
другой источник candidates. Эта задача оформляется после TODO_053; реализация
фильтра в текущий window fix не входит.

## Finding checkpoint / current behavior

Source inspection при HEAD
[`f70f1a8efff02f4b29e77782f50c18941596f890`](https://github.com/dreamworkerln/serialterminal/commit/f70f1a8efff02f4b29e77782f50c18941596f890)
(файлы discovery/selector этим заданием не менялись):

* `ble_discovery.py:21,115–121`: `SHOW_ALL_BLE_DEVICES=True` безусловно разрешает
  все scan results до проверки advertised NUS/cache capability.
* `ble_discovery.py:154–159`: connected BlueZ identities добавляются в candidates
  отдельно, без NUS eligibility check.
* `cli.py:92–101`: `DeviceSelector._discover_ble_candidates()` использует этот
  список без отдельной политики выбранного профиля.
* `cli.py:200–237`: F2 `known_candidates()` объединяет remembered candidates,
  confirmed cache и все connected BlueZ identities. Исправить только active
  scan недостаточно: неподходящие устройства останутся в известном списке.
* `tests/test_ble_discovery.py:test_default_visibility_includes_all_scanned_devices_regardless_of_nus`
  специально закрепляет прежний all-device prototype, включая Headphones
  с `nus=False`. Это существующая политика, которую новое требование меняет;
  нельзя объявлять старый тест доказательством нужного поведения Chatter.

## Target behavior / design constraints

1. Для `chatter` BLE chooser показывает targets с NUS capability evidence:
   NUS service в advertisement либо действующее confirmed NUS cache evidence.
   Имя устройства/слова Nordic/Chatter не являются доказательством capability.
2. Та же eligibility policy применяется после объединения scan, remembered,
   cache и connected BlueZ sources, включая F2 после смены профиля. `busy`
   не является доказательством NUS и не обходит фильтр.
3. Сохранить немедленный F2 по известным targets, без скрытого active scan,
   GATT connect/probe или отключения чужих устройств ради построения меню.
   Неизвестные capabilities исследует явный scanner/prober.
4. Истинный UNKNOWN после transient probe failure не стирает ранее подтверждённый
   NUS факт; definitive NO не становится YES по имени. Проверить TODO_012 cache
   semantics и существующие `test_ble_cache_unknown.py` regressions.
5. Generic discovery остаётся controller-agnostic. Требования выбранного профиля
   задаются capability-based profile/selector policy, без `profile.name == chatter`
   в transports/discovery и без проверки vendor/name aliases.
6. Сохранить generic all-device discovery/scanner там, где оно предусмотрено
   явным workflow; не менять USB serial/SPP eligibility как побочный эффект.
   Зафиксировать точный контракт profile selection в документации.

## Implementation

- [x] Выбрать минимальный profile-owned capability contract для chooser.
- [x] Применить eligibility ко всем candidate sources и повторному F2/profile switch.
- [x] Убрать/сузить действие all-device prototype для Chatter, сохранив discovery boundary.
- [x] Согласовать README/ARCHITECTURE/AGENT_API/runtime skill с итоговым scope.

## Validation / acceptance

- [x] Mock advertisement: настоящий NUS остаётся; headphones/TV без NUS исчезают.
- [x] Device без имени и без Chatter prefix с NUS допускается; названный Nordic
  или Chatter без NUS evidence не получает автоматический допуск.
- [x] Проверить remembered/cache/connected-only пути и duplicates одного адреса;
  connected non-NUS/busy headphones не появляются в F2.
- [x] Проверить known confirmed NUS без текущего advertisement; UNKNOWN/NO cases.
- [x] Проверить переключение generic → chatter на одном selector с накопленными
  candidates: старый all-device cache не обходит новую eligibility.
- [x] F2 regression доказывает отсутствие scan/connect/disconnect/probe side effects.
- [x] Полный pytest при изменении shared scanner/selector behavior по AGENTS.md.

## Implementation / software evidence — 2026-10-16

`BleProfileConfig.chooser_requires_nus` включён только у Chatter. Selector
проверяет advertised NUS или confirmed cache capability после объединения
candidates, при discovery и каждом F2. Generic discovery/scanner остаются
all-device; JSONL discover использует generic selector и сохраняет свой контракт.
USB Serial/SPP eligibility не меняется. `BleDeviceIdentity.advertised_services`
сохраняет advertisement evidence при scan/BlueZ deduplication и F2 busy refresh;
metadata не меняет физическое equality/key адреса. Имена и busy не дают допуск.
Generic core не импортирует Chatter profile и не сравнивает имена профилей.

Новый `tests/test_chatter_chooser.py`: 27 cases, включая modern/legacy Bleak,
UNKNOWN/NO, cache-only/remembered/connected sources, повторный F2 и round-trip
смену профиля, сохранение Serial/SPP. На исходном HEAD эти tests: 15 FAIL /
12 PASS; на изменённом source: все 27 PASS. Совместный discovery/selector/profile
subset: 95 PASS / 1.00 s. Software tests используют fake scanner/BlueZ/client;
запрещённые connect/probe вызывают явный test failure.

Первый полный запуск остановился на отсутствующей объявленной dev-зависимости
pyte; она и Ruff установлены в отдельный `/tmp/serialterminal-todo054-venv`.
Первый полный выполненный suite: 1107 PASS / 1 FAIL / 102.00 s — ранее записанная
в TODO_052 гонка `test_observe_default_avoids_raw_event_payload_amplification`
(66 events вместо 65). Isolated rerun: 1 PASS / 0.29 s. Этот тест и agent code
не изменялись. Финальный full rerun с отдельным device cache:
**1108 PASS / 143.69 s, без skips**.

Команды финальной проверки:

```bash
SERIALTERMINAL_CACHE_FILE=/tmp/serialterminal-todo054-venv/devices.json /tmp/serialterminal-todo054-venv/bin/python -m pytest -q
/tmp/serialterminal-todo054-venv/bin/python -m pytest -q tests/test_chatter_chooser.py tests/test_ble_discovery.py tests/test_ble_discovery_generic.py tests/test_ble_cache_unknown.py tests/test_bluez_busy.py tests/test_cli.py tests/test_profiles.py tests/test_generic_profile.py
```

Offline replay списка оператора из 13 устройств при смоделированном NUS
advertisement двух нод оставляет только LoRa-Chatter-1B44 и LoRa-Chatter-72E0.
Это проверка chooser/render path на fake input, не подтверждение advertising
реальных устройств.

Changed-file Ruff, compileall (`src serialterminal.py usb_timing_logger.py tools
scripts`) и diff/comment review PASS. Full Ruff: те же 3 baseline F401 в
`pipeline_manager.py`, `recursive.py`, `test_ft1_outbox.py`; эти файлы не изменялись.
Новые tests входят в общий локальный/GitHub `pytest -q` без feature flags/skips.
TODO_051 CI parity остаётся отдельным открытым scope.

Implementation / validation checkpoint: base
`3ba8e4bd09efefd34f5cab15d9cfdd46d5a2d545` плюс следующие SHA256 source/test:

```text
30dc55fd5543e1cf5eb4f831b25a2f5a9794825567c318c5ed6af1da59fe5714  src/serialterminal/ble_discovery.py
0f067bacd9209a996e392da6eca1faaf8c8e1bc0cf659e4084b7e43b524f2bd1  src/serialterminal/cli.py
7515ba88f4539bf77794c601d677a84d3af1bd59cd7da1d4b91560145e7ab6b2  src/serialterminal/profiles/base.py
8a93e6010f6c25dfdef3bfce5b32b39350083d2f06506adcc119b29ac6fdd33b  src/serialterminal/profiles/chatter/profile.py
1252e88803f532eefbd26ad5d8ad0e043ba42c4f0fd23a057891f55e746fcf81  src/serialterminal/transports/ble_nus.py
0e6a667e0153bffa89592d072888f14bf9da07e9672cb15950e63aae21699b6d  tests/test_chatter_chooser.py
```

AGENT_API и runtime skill проверены и уточняют только human chooser policy;
machine schema/open semantics сохранены. Observation executor работает через
generic JSONL discovery, поэтому его operating policy не требует изменения.
Hardware: NOT RUN; эта offline capability-filter задача не устанавливает physical
gate и не закрывает аппаратные gates других TODO. Commit/push/CI: NOT RUN.
Remaining follow-ups in this TODO: none. Status: CLOSED / software acceptance PASS.
