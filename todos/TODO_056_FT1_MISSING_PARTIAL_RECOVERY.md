# FT1 missing-part recovery without manual journal cleanup

TODO-ID: TODO_056
Status: IMPLEMENTED / SOFTWARE VALIDATION PASS / HARDWARE VALIDATION OPEN
Recorded: 2026-10-16

## Operator request / evidence

Не ограничиваться ручной очисткой после одного отказа: ST должен самостоятельно
выходить из воспроизводимого broken-resume состояния при следующей передаче.

Два одновременно запущенных оператором ST по BLE остановили 2.png на META:
TX p24926 восстановил старый journal ID 5670acd3be78b0f7, RX p24954 вернул
storage_failed: stale/corrupt durable resume state already exists for transfer_id.
Sender записал failed при 0 bytes, окно terminal error оставалось до Esc по TODO_053.
RX manifest suspended от 15:22:49.870 MSK утверждал 180 received chunks, но его
.part отсутствовал. Причина/время исчезновения именно этого файла не установлены.

Raw logs, console/timing/application snapshots, manifests, hashes и исходный
read-only отчёт сохранены в
`/home/dream/coding/journal_of_experiments/20261016T175104Z_two_st_file_transfer_stall/`.
Старое состояние пользователя вручную не переносилось и не очищалось.

## Scope / target

При точно совпадающем valid META и receiving/suspended manifest без .part:

1. Получить incoming lease; не обходить live owner.
2. Сохранить нулевой durable proof до создания пустого .part через exclusive xb.
3. Fsync/checkpoint нового файла, опубликовать новый runtime state, вернуть RESUME 0.
4. Сохранить ID; sender отправляет файл заново с chunk 0 и проходит обычные hashes.
5. Записать resume_state_reset(reason=missing_partial, previous_chunks, next_chunk=0)
   и понятный ROOT lifecycle текст в TUI.

На rollback запрещено возвращать старые ranges рядом с новым пустым .part.
Suspended runtime incoming context и его progress также сбрасываются: close после
checkpoint failure не должен заново опубликовать старый proof.

Existing useful partials, conflicting/corrupt identities, publishing intent,
quarantine, symlink paths и чужие owners не сбрасываются этим механизмом.
Persistent I/O failure остаётся явным bounded failure. Wire/firmware, UI error
autoclose policy, runtime/provenance выбор и новое автоматическое background send
не входят в задачу. Явный F5/file_send_start по-прежнему запускает отправку.

## Additional source finding

ResumeStateStore._cleanup_part_budget удалял .part до manifest. Прерывание на
следующем unlink оставляло manifest без данных. Теперь proof удаляется первым;
процессное прерывание оставляет orphan .part. Другие retention paths уже удаляют
proof перед данными. Это доказанная software interruption window, а не установленная
причина исчезновения файла в старом аппаратном запуске.

## Implementation / validation

- [x] Same-ID missing-part reset с честным RESUME 0 и durable ordering.
- [x] Нулевой rollback и invalidation старого suspended incoming cache/progress.
- [x] Manifest-before-part в byte-budget cleanup.
- [x] Наблюдаемый reset event и TUI lifecycle text.
- [x] Actual paired sender/receiver software transfers: same-process и sender restart,
  receiver restart, потеря .part, полный повтор с chunk 0 и проверка final bytes.
- [x] Fault injection: zero-proof write до/после atomic replace, xb creation,
  checkpoint, затем повтор; отдельный checkpoint failure → close → restart.
- [x] Защита live owner, useful partial, mismatching META, quarantine/publishing.
- [x] Interrupted manifest unlink при cleanup не удаляет данные раньше proof.
- [x] 13 новых tests: baseline 9 FAIL / 4 PASS; fixed relevant subset 212 PASS / 16.32 s.
- [x] Changed-file Ruff/diff check PASS.
- [x] Полный repository software suite: 1131 PASS / 110.48 s, без skips; compileall PASS.
- [ ] Аппаратное повторение операторского сценария двумя ST на нодах при exact
  source/runtime checkpoint и физически подтверждённой firmware version; сохранить
  META/RESUME 0/DATA/RESULT logs и совпадение итогового файла. До этого TODO не CLOSED.

## Result

Runtime changes: resumable.py, resume_store.py, tui_file_transfer.py; regressions:
tests/test_ft1_missing_partial_recovery.py. FT1_RESUME/FILE_TRANSFER/README/AGENT_API
и runtime skill согласованы. Архитектура проверена: восстановление остаётся FT1
host behavior; generic transports/session/profile и firmware не узнают file state.
Tests входят в общий локальный/GitHub pytest -q без flags/skips; TODO_051 остаётся
отдельным scope. Hardware: NOT RUN. Commit/push/merge/CI: NOT RUN.

Validated checkpoint: `3ba8e4bd09efefd34f5cab15d9cfdd46d5a2d545` плюс cumulative
`software-fix56-source-tests.patch.gz` в указанном journal directory (TODO_054–056).
SHA256 распакованного patch:
`c22404a2bd39718ef3f75e09f6bef2e6bb74500d943c1190dcd0609d8a69df0e`.
Исторические checkpoint TODO_054/055 сохранены отдельно. Последующие правки
TODO/inventory/report — docs-only.

Точный baseline output: `software-fix56-baseline-regressions.txt` (9 FAIL / 4 PASS).
Full software output: `software-fix56-full-pytest.txt` (1131 PASS / 110.48 s).
Команда full run:

```bash
SERIALTERMINAL_CACHE_FILE=/tmp/serialterminal-todo054-venv/missing-part-devices.json /tmp/serialterminal-todo054-venv/bin/python -m pytest -q
```

Changed-file Ruff/diff/comment review PASS. Full Ruff: прежние 3 F401 в
pipeline_manager.py, recursive.py, test_ft1_outbox.py; эти файлы в задаче не менялись.
Operator action для проверки: перезапустить оба ST, чтобы загрузить новый code,
выбрать тот же исходный файл через F5. Ручная чистка старого resume state не нужна.
Hardware acceptance остаётся OPEN до фактического прогона с evidence.
