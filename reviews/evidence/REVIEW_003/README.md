# REVIEW_003 evidence

Reviewed source: `f70f1a8efff02f4b29e77782f50c18941596f890`, clean at initial inspection.

`test_window_lifecycle_repro.py` сохраняет исходные шесть offline probes.
Они намеренно утверждают наблюдаемое старое поведение. Это forensic repro,
не regression suite, которую следует заставить проходить на исправленном source.
Использовать исходные `src/` **и** `tests/` указанного commit через PYTHONPATH.
Не запускать этот файл как acceptance текущего working tree.

Выполнено до edits, вне sandbox по AGENTS.md:

```text
PYTHONPATH=src:tests python -m pytest -q -s \
  reviews/evidence/REVIEW_003/test_window_lifecycle_repro.py \
  tests/test_tui_file_transfer_window.py tests/test_tui_transfer_pty.py
131 passed in 3.19s
```

`contract_cases_at_base.py` сохраняет точный файл первых 19 acceptance cases;
`base-regressions.txt` — фактический вывод этих cases против
неизменённых source/test helpers исходного commit, извлечённых через `git archive`
в `/tmp/serialterminal-review003-base`. Тестовый файл скопирован туда из нового
`tests/test_tui_transfer_lifecycle.py`; pytest использовал config archived проекта.
Результат: 12 FAILED / 7 PASSED. Это expected red baseline, не ошибка запуска.
Более ранний запуск с `-c /dev/null` остановился на import path и не используется
как behavioral evidence. Текущий рабочий файл тестов позже дополнен новыми cases;
не считать его побайтово тождественным первым 19 cases.

Временное окружение: `/tmp/serialterminal-review003-venv`, Python 3.12,
pytest 9.1.1, pyte 0.8.2, system-site-packages. Default platformio Python не имел
pytest; первый запуск остановился до collection. System Python также не имел
pytest/pyte. Зависимости установлены только в /tmp venv.

Это исключительно host evidence: настоящий FT1 manager + узкие transport/clock
boundaries, controller marker parser, Canvas и отдельный curses/PTY subprocess.
Реальные BLE/USB/RF устройства не использовались. Runtime identity существующих
локальных logs неизвестна; их нельзя выдавать за hardware validation нового кода.

## Implementation validation (отдельно от исходного RED review)

Exact source: исходный SHA + `implementation-source-tests.patch.gz` (gzip);
SHA256 распакованного patch записан в `.patch.sha256` и TODO_053. Patch включает tracked source/test
diff и новый `tests/test_tui_transfer_lifecycle.py`. Он сохранён до final полного
pytest и повторно сверяется перед commit; docs-only edits после него допустимы.

* `full-pytest.txt`: 1081 PASS / 103.18 s, 7 существующих fork warnings, без skips.
* `tui-targeted.txt`: 197 PASS / 5.16 s, включая TX/RX real curses/PTY.
* Compileall src/tests/serialterminal.py/usb_timing_logger.py/tools/scripts — PASS.
* `ruff-base.txt` и `ruff-final.txt`: один и тот же вывод — 3 baseline F401
  (`pipeline_manager.py`, `recursive.py`, `test_ft1_outbox.py`), без новых findings.
* `git diff --check` и проверка изменений существующих comments — PASS.

Эти результаты не меняют задним числом исходный RED verdict REVIEW_003 и
не доказывают физический reboot/RF scenario. GHA не объявляется зелёным по
локальному pytest; существующий full static CI gate всё ещё требует TODO_051.

Patch сохранён в gzip без изменения исходных bytes, чтобы context-only пробелы
unified diff не считались trailing whitespace самого evidence-файла.
