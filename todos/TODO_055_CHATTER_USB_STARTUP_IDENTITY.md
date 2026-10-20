# Chatter USB startup identity confirmation TODO

TODO-ID: TODO_055
Status: IMPLEMENTED / SOFTWARE VALIDATION PASS / HARDWARE VALIDATION OPEN
Recorded: 2026-10-16

## Purpose / operator report

При запуске `python3 serialterminal.py --profile chatter` с USB ID ноды иногда
не появляется, хотя ручной `/id` затем работает. Оператор уточнил: основной
сценарий — первоначальный запуск ST, F2 используется редко.

## Evidence / finding boundary

Read-only диагностика существующих human logs сохранена целиком отдельными
копиями с SHA256 manifest в
`/home/dream/coding/journal_of_experiments/20261016T171921Z_st_usb_identity_diagnostics/`.
Новых подключений к аппаратуре, чтения firmware, flashing или аппаратных прогонов
не было. Физическая firmware version в этих старых logs не установлена; их
source/runtime revision не выводится из текущего рабочего HEAD.

* `serialterminal-20261016-152457-698112-p84989.console.log`, строки 1, 10–11:
  первый ответ содержит `> gB/id`, canonical NODE отсутствует до ручного `/id`
  в 15:25:19.815; затем приходит LoRa-Chatter-1B44. Timing фиксирует первоначальный
  4-byte preamble write перед connected: transport write не означает исполнение.
* `serialterminal-20261016-165835-700313-p104161`: 4-byte preamble записан,
  `/config` отвечает, но canonical NODE при старте отсутствует. Точная физическая
  граница потери ответа по этим logs не устанавливается.
* Отдельная source-confirmed F2 race: `_change_device()` возобновлял RX перед
  `_sync_panel_transport_identity()`. Быстрый canonical NODE мог быть затёрт
  последующим USB hint `None`. Это дополнительная находка, не объяснение всех
  первоначальных запусков.

## Target / scope

Chatter TUI подтверждает identity по canonical NODE, не по успешному USB write.
При отсутствии ответа делает максимум 3 дополнительных read-only `/id` с
интервалом 1 s на connection generation; первый запрос остаётся в существующем
Serial connect preamble. Fast response до первого UI tick исключает повтор.
После NODE повторов нет. Disconnect прекращает polling; новая generation
получает новый ограниченный бюджет. Неизвестный ID не выдумывается.

Policy и parser принадлежат `ChatterTuiPanel.poll_actions`; generic TUI только
передаёт transport/lifecycle context и ставит profile actions в обычную очередь.
Существующий `/config` refresh сохраняется. F2 устанавливает transport seed
через callback `before_resume` при paused RX; только потом разрешает reconnect.
Callback failure снимает pause через finally и передаётся существующему UI error
handler. При source fix не добавляется новый reconnect loop, sleep или RF retry.

Non-goals: generic/BLE/SPP/classic/JSONL startup policy, firmware, TODO_015's broad
preamble ownership redesign, FT1 recovery/transfer semantics и исправление старых
Ruff findings. TODO_054 changes остаются отдельным ранее проверенным scope.

## Implementation

- [x] Profile-owned bounded USB identity confirmation/retry with monotonic clock.
- [x] Generic profile panel polling through the existing action queue.
- [x] Seed-before-resume ordering for F2; callback failure releases pause.
- [x] README/ARCHITECTURE/AGENT_API/runtime skill consistency review and updates.

## Validation

- [x] Детерминированный stale console input (`gB/id`) без ручного `/id`.
- [x] Потерянный первый USB запрос, затем automatic identity recovery.
- [x] Реальный TerminalSession TX/RX + TUI line observer на fake USB transport.
- [x] Быстрый начальный NODE до первого UI tick; последующих запросов нет.
- [x] Ограничение частоты/числа, reconnect generation и disconnected state.
- [x] BLE/прочие transports и generic не получают USB retries.
- [x] F2 fast-response race и paused seed callback/error cleanup.
- [x] Baseline: 8 FAIL / 2 PASS; fixed targeted subset: 93 PASS / 0.86 s.
- [x] Changed-file Ruff, compileall и diff/comment review PASS.
- [x] Полный software suite: 1118 PASS / 109.85 s, без skips.
- [ ] Операторский hardware startup/reconnect check нескольких USB запусков,
  с exact source/runtime checkpoint, физической firmware version и сохранёнными
  logs; если проверялся F2, отдельно отметить фактическое покрытие.

## Result

Validated checkpoint: base `3ba8e4bd09efefd34f5cab15d9cfdd46d5a2d545` плюс
`implementation-source-tests.patch.gz` в указанном journal directory. SHA256
распакованного patch:
`3ab9e9993c903817c3e3964af642f8a849253699cf318342b42fc54b0889d220`.
Patch содержит cumulative source/test changes TODO_054 и TODO_055; более ранний
точный checkpoint TODO_054 сохранён в его собственной записи. Последующие правки
inventory/report — docs-only.

Финальный full software run:

```bash
SERIALTERMINAL_CACHE_FILE=/tmp/serialterminal-todo054-venv/usb-identity-devices.json /tmp/serialterminal-todo054-venv/bin/python -m pytest -q
```

Результат: **1118 PASS / 109.85 s**, без skips. Full Ruff сохраняет те же 3 baseline F401 вне scope.
Новые tests входят в общий `pytest -q` локально и в GitHub, без новых skip/flags.
TODO_051 parity и TODO_015 не закрываются этим изменением.
Hardware: NOT RUN. Commit/push/CI: NOT RUN.
