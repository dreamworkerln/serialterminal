# Node Observation Recording Policy

## Purpose

Этот документ описывает только работу local executor agent после hardware-задачи: как сохранить короткий factual observation record без анализа и без изменения `.agents/skills/node-agent/SKILL.md`.

Local executor — исполнитель и сборщик evidence. Он не выполняет reviewer/promotion работу.

Reviewer обрабатывает накопленные observations по [NODE_SKILL_LEARNING_POLICY.md](NODE_SKILL_LEARNING_POLICY.md).

---

## 1. Где хранить observations

Observation records хранятся в отдельной orphan branch того же репозитория:

```text
node_observations
```

Эта branch не является development branch SerialTerminal и не должна содержать копию/merge истории `dev`.

Для local storage используется **отдельный independent clone**, а не Git worktree.

Рекомендуемый local layout относительно общей parent directory:

```text
./serialterminal/
    main clone, branch dev

./serialterminal-observations/
    independent clone, branch node_observations
```

Если команды выполняются из корня main `serialterminal` clone, observation clone находится по относительному пути:

```text
../serialterminal-observations
```

Main `serialterminal` clone используется для запуска SerialTerminal/agent API и чтения policy/skills. `serialterminal-observations` используется только для raw observation evidence и reviewer state.

Executor не должен переключать main clone с `dev` на `node_observations` и не должен создавать linked Git worktree для observations.

### Human-only initial setup

Следующие команды — **одноразовая setup-инструкция для человека**, а не задача local executor agent.

Из корня main `serialterminal` clone:

```bash
git clone \
  --single-branch \
  --branch node_observations \
  "$(git remote get-url origin)" \
  ../serialterminal-observations
```

Проверка:

```bash
git -C ../serialterminal-observations status --short --branch
git -C ../serialterminal-observations branch --show-current
git -C ../serialterminal-observations rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
```

Ожидается:

```text
branch: node_observations
upstream: origin/node_observations
```

`../serialterminal-observations/.git` должен быть обычной directory собственного clone, а не pointer-файлом linked worktree.

После clone человек должен убедиться, что local Codex/sandbox configuration позволяет executor-у создавать observation files внутри `../serialterminal-observations`. Если используется explicit writable-root configuration, sibling observation clone должен быть разрешён там.

Project trust и sandbox write access — разные настройки. Наличие trusted project само по себе не считается доказательством writable-доступа.

### Human-only permission setup для commit/push helper

В `workspace-write` Git metadata (`.git`) может оставаться read-only даже внутри writable clone. Поэтому executor не должен выполнять raw `git add` / `git commit` / `git push` для observation clone.

Repository содержит guarded helper:

```text
scripts/commit-node-observation
```

Executor вызывает его только из корня main `serialterminal` clone и только в таком виде:

```bash
python3 -I scripts/commit-node-observation observations/OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
```

Чтобы не подтверждать эту операцию вручную каждый run, человек может один раз добавить narrow Codex exec-policy rule для этого exact command prefix:

```python
prefix_rule(
    pattern = ["python3", "-I", "scripts/commit-node-observation"],
    decision = "allow",
    justification = "Allow the guarded SerialTerminal observation helper to commit and push one new raw observation.",
)
```

Это permission setup выполняет только человек/operator. Executor **не должен** изменять Codex rules, `config.toml`, project trust, sandbox mode, writable roots или другие permissions.

Helper специально ограничивает elevated Git workflow: он проверяет, что его собственная working-tree версия совпадает с current `HEAD`, main clone находится на `dev`, sibling является independent clone на `node_observations` с upstream `origin/node_observations`, local/remote refs синхронизированы, tracked state чистый и существует ровно один новый `OBS_*.md`. После этого helper добавляет только этот record, делает commit и normal push, затем проверяет clean/synced state.

Если observation clone отсутствует или настроен неправильно, executor не создаёт и не перенастраивает его. Рапортуй:

```text
OBSERVATION STORAGE NOT CONFIGURED
```

Если clone найден, но sandbox не позволяет создать observation file, не меняй permissions/configuration. Рапортуй:

```text
OBSERVATION STORAGE NOT WRITABLE
```

Если helper отказывается выполнять commit/push из-за dirty state, divergence, wrong branch/upstream или другой guard failure, не обходи guard raw Git-командами и не делай merge/rebase/reset/force push. Рапортуй ошибку пользователю.

---

## 2. Layout observation branch

Ожидаемый layout:

```text
node_observations branch
├── REVIEW_STATE.md
└── observations/
    ├── OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
    └── ...
```

`REVIEW_STATE.md` принадлежит reviewer-у. Local executor его не изменяет.

Observation files после commit являются append-only evidence: executor не редактирует и не удаляет старые records. Если старый record содержит ошибку, создай новый correction observation со ссылкой на старый.

---

## 3. Когда писать record

Для hardware validation/fault/recovery task обычно создавай один observation record на завершённый run, если было фактическое взаимодействие с SerialTerminal/hardware.

Record особенно обязателен при:

- FAIL/BLOCKED после начала hardware interaction;
- unexpected behavior;
- anomaly/regression/bug candidate;
- расхождении с текущим node skill;
- intentional fault injection;
- новом hardware scenario, которое может быть полезно reviewer-у.

Не создавай record только ради того, чтобы продублировать обычный textual answer без hardware evidence.

---

## 4. Именование

Имя файла:

```text
observations/OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
```

Используй UTC timestamp и короткий slug без конкретных MAC/node IDs, например:

```text
OBS_20260903T201530Z_bidirectional-user-smoke.md
OBS_20260903T202410Z_radio-power-absent.md
OBS_20260903T203005Z_echo-timeout.md
```

Concrete identifiers можно писать внутри record как evidence конкретного run.

---

## 5. Record должен быть коротким

Цель — factual evidence, а не рассуждение. Обычно достаточно 10–25 содержательных строк плюс короткие exact excerpts.

Не выполняй здесь:

- generalization;
- promotion в skill;
- дедупликацию knowledge;
- длинный root-cause analysis;
- переписывание protocol contract;
- вывод о постоянных свойствах конкретного экземпляра.

Если увидел странность, зафиксируй expected/observed/evidence и остановись на уровне anomaly/bug candidate.

---

## 6. Обязательный формат

Используй этот шаблон:

```markdown
# Node observation

Observed: YYYY-MM-DDTHH:MM:SSZ
Task: <short task>
Result: PASS | FAIL | BLOCKED | INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@<exact SHA>
Firmware: dreamworkerln/lora-sack-protocol@<exact SHA or unknown>

## Setup
- <actually discovered/used transports and relevant intentional setup/fault state>

## Actions
- <short ordered actions>

## Evidence
- <exact relevant events/output and measured facts>

## Anomalies / conflicts
- none
```

Если anomaly есть:

```markdown
## Anomalies / conflicts
- Expected: <what was expected>
- Observed: <what actually happened>
- Impact: <current effect>
```

И завершение:

```markdown
## Final state
- <echo/output/session cleanup; hardware state if intentionally left changed>

## Evidence pointer
- <SerialTerminal log path / artifact / related report if available>
```

Если exact source SHA неизвестен, пиши `unknown`; не угадывай.

Record должен сам содержать ключевое evidence, достаточное для reviewer-а. Local log path является дополнительной ссылкой и не заменяет critical excerpts, потому что reviewer может работать только через Git/GitHub.

---

## 7. Что можно писать в observation

В raw observation разрешены run-specific данные:

- concrete node identity;
- MAC/BLE address;
- USB path;
- session IDs;
- current discovery result;
- RSSI/SNR/Q/timing/counters;
- intentional power/fault state;
- exact payload;
- exact relevant event excerpts.

Это historical evidence конкретного run, а не class-level skill.

Не формулируй такие данные как постоянные свойства класса или экземпляра.

Правильно:

```text
Observed in this run: USB endpoint was absent from discovery.
```

Неправильно:

```text
This node has no USB transport.
```

---

## 8. Anomaly / bug reporting

Если обнаружено потенциально неправильное поведение, record должен содержать минимум:

```text
expected
observed
evidence
short reproduction steps
current impact
```

Не исправляй `node-agent/SKILL.md` под единичный observation и не объявляй новое поведение правильным contract.

Если anomaly серьёзная, также явно сообщи о ней пользователю в основном task report.

---

## 9. Executor workflow: сохранить observation

После hardware interaction:

1. Main `serialterminal` clone оставь на `dev`.
2. Используй уже подготовленный sibling clone `../serialterminal-observations`; не создавай его сам.
3. Проверь:

   ```bash
   git -C ../serialterminal-observations status --short --branch
   git -C ../serialterminal-observations branch --show-current
   ```

4. Если есть unexpected local changes, старые modified/deleted observations или изменение `REVIEW_STATE.md`, не перезаписывай их и сообщи проблему.
5. Создай ровно один новый file:

   ```text
   ../serialterminal-observations/observations/OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
   ```

6. Не изменяй `REVIEW_STATE.md` и предыдущие observation files.
7. Из корня main `serialterminal` clone выполни только guarded helper:

   ```bash
   python3 -I scripts/commit-node-observation observations/OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
   ```

8. Не выполняй вместо helper-а raw `git add`, `git commit`, `git push`, `git reset`, `git rebase`, merge или force-push в observation clone.
9. Успехом считается только helper output с commit SHA после successful push и final clean/synced verification.

Commit message helper формирует автоматически из filename slug:

```text
obs: <short topic>
```

Если helper завершился с `OBSERVATION COMMIT FAILED`, не обходи его guards. Сохрани factual hardware result в основном report и сообщи конкретную storage/Git проблему пользователю.

---

## 10. Что executor возвращает пользователю

В основном отчёте достаточно:

```text
hardware result: PASS/FAIL/BLOCKED/INCONCLUSIVE
observation: <filename or not recorded>
observation commit: <SHA if committed+pushed, otherwise not committed>
anomaly: <none or one-line summary>
```

Не нужно пересказывать reviewer learning model.

---

## Authority

```text
AGENT_API.md
    generic SerialTerminal API

.agents/skills/serialterminal-agent/SKILL.md
    generic tool usage

.agents/skills/node-agent/SKILL.md
    current class-level LoRa-Chatter operating guidance

NODE_OBSERVATION_RECORDING_POLICY.md
    executor rule for raw observation recording

scripts/commit-node-observation
    guarded commit/push path for one new observation

NODE_SKILL_LEARNING_POLICY.md
    reviewer rule for processing observations and updating node skill

node_observations branch
    run-specific historical evidence and REVIEW_STATE.md
```
