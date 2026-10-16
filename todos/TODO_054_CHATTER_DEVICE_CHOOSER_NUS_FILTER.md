# Chatter device chooser: NUS capability filtering TODO

TODO-ID: TODO_054
Status: OPEN
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

- [ ] Выбрать минимальный profile-owned capability contract для chooser.
- [ ] Применить eligibility ко всем candidate sources и повторному F2/profile switch.
- [ ] Убрать/сузить действие all-device prototype для Chatter, сохранив discovery boundary.
- [ ] Согласовать README/ARCHITECTURE/AGENT_API/runtime skill с итоговым scope.

## Validation / acceptance

- [ ] Mock advertisement: настоящий NUS остаётся; headphones/TV без NUS исчезают.
- [ ] Device без имени и без Chatter prefix с NUS допускается; названный Nordic
  или Chatter без NUS evidence не получает автоматический допуск.
- [ ] Проверить remembered/cache/connected-only пути и duplicates одного адреса;
  connected non-NUS/busy headphones не появляются в F2.
- [ ] Проверить known confirmed NUS без текущего advertisement; UNKNOWN/NO cases.
- [ ] Проверить переключение generic → chatter на одном selector с накопленными
  candidates: старый all-device cache не обходит новую eligibility.
- [ ] F2 regression доказывает отсутствие scan/connect/disconnect/probe side effects.
- [ ] Полный pytest при изменении shared scanner/selector behavior по AGENTS.md.

Implementation: NOT STARTED. Tests for the new filter: NOT WRITTEN / NOT RUN.
Hardware: NOT RUN. Существующие all-device tests не закрывают этот TODO.
