# Local / GitHub CI parity TODO

TODO-ID: TODO_051
Status: OPEN
Recorded: 2026-10-16

## Purpose

По запросу оператора обеспечить одинаковый полный CI локально и на GitHub:
один источник команд, аргументов, dependencies/feature flags и критериев PASS/FAIL.
Не поддерживать отдельные списки проверок в README, workflow и ручном запуске.

## Finding checkpoint and current behavior

Branch `dev_tui_exp_recursive_missing`, HEAD
`ee9e954339f37a541f303aeec98d560b09794758` + существующие local changes.
Задача создана после read-only проверки конфигурации, без запуска тестов.

* `.github/workflows/ci.yml` — единственный workflow; полный `pytest -q`
  собирает общий каталог `tests` по `pyproject.toml`. Отдельного скрытого pytest
  subset в workflow не найдено.
* Общего executable CI entrypoint нет. Workflow запускает compileall, ruff,
  advisory Lizard и pytest отдельными командами.
* README / INSTALL / AGENTS приводят более узкие compile/lint команды:
  в них не везде включены `usb_timing_logger.py` и `scripts`, которые есть в CI.
* Локальная установка для разработки в INSTALL использует `.[ble,dev]`,
  GitHub устанавливает `.[dev]`. BLE extra приносит зависимости Bleak/DBus,
  а dev extra их не гарантирует. В `test_ble_release.py` и `test_bluez_busy.py`
  есть `pytest.importorskip("dbus_fast...")`: при отсутствии зависимости эти
  software tests пропускаются, поэтому одинаковая команда pytest ещё не
  гарантирует одинаковое фактическое покрытие.

## Target behavior and invariants

* Один общий CI entrypoint, вызываемый локально и workflow; одинаковые scopes
  compile/lint/complexity/pytest, exit codes и nonblocking policy Lizard.
* Одинаковый обязательный набор зависимостей, включая необходимые для mock BLE/
  DBus software tests. Отсутствие обязательной зависимости — явная ошибка
  подготовки полного CI, а не незаметное уменьшение покрытия через skip.
* Обоснованные platform/optional skips имеют одинаковые явные условия в обоих
  окружениях и видны в отчёте. Обычный pytest/targeted run не называть полным CI.
* Правила не разрешают реальные serial/BLE connections, hardware runs или
  firmware changes. Mock DBus tests не требуют физического Bluetooth устройства.
* Не менять FT1/BLE runtime behavior и отложенную non-POSIX ownership задачу
  TODO_049 ради выравнивания CI.

## Implementation

- [ ] Ввести общий executable plan и подключить GitHub к нему без дублирования
  test/lint/build команд в YAML.
- [ ] Согласовать dev/test dependencies и обязательность BLE/DBus software tests.
- [ ] Зафиксировать правила допустимых skips и отчёт о пропущенном покрытии.
- [ ] Обновить README, INSTALL и AGENTS: одна команда полного CI и отдельное
  описание targeted pytest; scopes должны соответствовать общему плану.
- [ ] Добавить regression tests паритета workflow/entrypoint и полноты suite,
  включая контроль обязательных dependencies.

## Validation and acceptance

- [ ] На одной source revision полный локальный и GitHub CI вызывают общий
  план с одинаковыми аргументами и обязательными dependency/feature settings.
- [ ] Негативный тест: новый test/lint этап, отсутствующий в общем плане,
  или дублирующая workflow-команда обнаруживаются проверкой контракта.
- [ ] Контролируемое отсутствие обязательной DBus dependency не даёт ложный
  full PASS; в подготовленном окружении соответствующие tests выполняются.
- [ ] Compileall, ruff, advisory complexity и полный pytest пройдены по новому
  entrypoint; результаты/skip reasons и exact checkpoint записаны.
- [ ] Проверить diff на сохранение существующих tests/assertions и отсутствие
  source/runtime/hardware изменений вне CI scope; обновить inventory.

## Result

Implemented: NO. Validated: configuration inspection only.
Status: OPEN. Тесты, commit/push и аппаратные действия при создании TODO не выполнялись.
