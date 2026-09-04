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

Этот helper является trusted repository infrastructure. **Local executor agent не должен модифицировать, переписывать, патчить или генерировать замену `scripts/commit-node-observation` во время hardware/observation task**, даже если helper завершился ошибкой. Изменять helper можно только в отдельной явно поставленной code-maintenance задаче с обычным review/validation.

Executor вызывает helper только из корня main `serialterminal` clone и **без аргументов**:

```bash
python3 -I scripts/commit-node-observation
```

Команда намеренно стабильная и не содержит filename/timestamp конкретного observation. Helper ожидаемо пишет в `.git` observation clone, поэтому executor должен **сразу запрашивать elevated execution для этой команды**, а не сначала запускать её в обычном `workspace-write` sandbox и получать ожидаемый read-only failure.

Человек может один раз разрешить именно этот стабильный command prefix для elevated execution и не подтверждать новый `OBS_*.md` вручную каждый run:

```python
prefix_rule(
    pattern = ["python3", "-I", "scripts/commit-node-observation"],
    decision = "allow",
    justification = "Allow the guarded SerialTerminal observation helper to commit and push pending raw observations.",
)
```

Это permission setup выполняет только человек/operator. Executor **не должен** изменять Codex rules, `config.toml`, project trust, sandbox mode, writable roots или другие permissions.

Helper специально ограничивает elevated Git workflow. Он проверяет, что:

- его собственная working-tree версия совпадает с current `HEAD`;
- main clone находится на `dev`;
- sibling является independent clone на `node_observations` с upstream `origin/node_observations`;
- local/remote refs синхронизированы;
- tracked state полностью чистый, поэтому старые observations, `REVIEW_STATE.md` и другие tracked files не могут быть изменены или удалены;
- все untracked files являются корректно названными новыми `observations/OBS_*.md`.

Helper принимает **один или несколько** pending new observation files. Если после предыдущего interrupted/failed run осталось несколько валидных новых `OBS_*.md`, helper добавляет их все и отправляет одним commit/push. Любой посторонний untracked file приводит к отказу вместо broad staging.

После commit/push helper проверяет final clean state и local-vs-origin synchronization.

### Helper result contract

Executor должен учитывать и **exit code**, и textual output helper-а.

Успех:

```text
exit code: 0
observations committed and pushed: <N>
observation: observations/OBS_....md
observation: observations/OBS_....md
commit: <SHA>
```

`exit 0` означает, что helper закоммитил все pending new observations, выполнил normal push и собственную final clean/local-vs-origin synchronization verification.

Обычная guard/Git failure:

```text
exit code: 1
OBSERVATION COMMIT FAILED: <concrete reason>
```

Invalid invocation, например переданы аргументы:

```text
exit code: 2
usage: python3 -I scripts/commit-node-observation
```

При non-zero exit executor не должен ограничиваться сообщением «helper failed». Он должен сохранить и передать пользователю **точный diagnostic text helper-а**, потому что helper сообщает конкретную причину: dirty tracked state, divergence, wrong branch/upstream, unexpected untracked files, invalid storage layout, Git/network failure и т.п.

После `exit 0` executor **обязан** выполнить независимую read-only проверку remote, не изменяя Git state:

```bash
local_sha="$(git -C ../serialterminal-observations rev-parse HEAD)"
remote_sha="$(git -C ../serialterminal-observations ls-remote origin refs/heads/node_observations | awk '{print $1}')"
test -n "$remote_sha" && test "$local_sha" = "$remote_sha"
```

Только если SHA совпали, commit считается независимо подтверждённым непосредственно на remote `node_observations`, и observation cycle считается полностью завершённым. Если SHA не совпали, executor должен сообщить mismatch и не заявлять remote success. Если read-only проверка не выполнилась из-за network/tool restrictions, не отменяй уже успешный helper result, но явно сообщи `remote verification: not verified`; не заявляй, что remote был независимо проверен.

Если observation clone отсутствует или настроен неправильно, executor не создаёт и не перенастраивает его. Рапортуй:

```text
OBSERVATION STORAGE NOT CONFIGURED
```

Если clone найден, но sandbox не позволяет создать observation file, не меняй permissions/configuration. Рапортуй:

```text
OBSERVATION STORAGE NOT WRITABLE
```

Если helper отказывается выполнять commit/push из-за dirty state, divergence, wrong branch/upstream или другой guard failure, не обходи guard raw Git-командами и не делай merge/rebase/reset/force push. Не модифицируй helper для обхода отказа. Рапортуй exact helper diagnostic пользователю.

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

4. Если есть tracked modifications/deletions, staged changes или изменение `REVIEW_STATE.md`, не исправляй и не перезаписывай их; сообщи проблему.
5. Создай новый record текущего run:

   ```text
   ../serialterminal-observations/observations/OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
   ```

   Если в clone уже лежат другие untracked валидные `OBS_*.md` от предыдущего interrupted/failed commit attempt, не удаляй и не переписывай их. Helper отправит весь pending batch одним commit.
6. Не изменяй `REVIEW_STATE.md`, предыдущие committed observation files **или `scripts/commit-node-observation`**.
7. Из корня main `serialterminal` clone сразу запроси **elevated execution** guarded helper без аргументов:

   ```bash
   python3 -I scripts/commit-node-observation
   ```

   Не запускай helper сначала в обычном sandbox: его нормальная работа включает запись Git metadata в observation clone.
8. Проверь exit code и сохрани stdout/stderr helper-а. При non-zero передай пользователю exact diagnostic; не пытайся исправлять helper в рамках hardware task.
9. Не выполняй вместо helper-а raw `git add`, `git commit`, `git push`, `git reset`, `git rebase`, merge или force-push в observation clone.
10. После `exit 0` **обязательно** независимо проверь remote SHA через read-only `git ls-remote` и сравни его с local `HEAD`. Только при совпадении SHA рапортуй `remote verification: verified`. При mismatch рапортуй mismatch и не заявляй remote success. Если независимая проверка невозможна из-за network/tool restrictions, рапортуй `remote verification: not verified`.

Commit message helper формирует автоматически:

```text
one pending observation:
    obs: <short topic>

multiple pending observations:
    obs: record node observations
```

Если helper завершился с `OBSERVATION COMMIT FAILED`, не обходи его guards. Сохрани factual hardware result в основном report и сообщи конкретную storage/Git проблему пользователю.

---

## 10. Что executor возвращает пользователю

В основном отчёте достаточно:

```text
hardware result: PASS/FAIL/BLOCKED/INCONCLUSIVE
observation: <filename or not recorded>
observation commit: <SHA if committed+pushed, otherwise not committed>
remote verification: <verified / not verified>
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
    guarded commit/push path for all pending new observations; executor must not modify it during hardware tasks

NODE_SKILL_LEARNING_POLICY.md
    reviewer rule for processing observations and updating node skill

node_observations branch
    run-specific historical evidence and REVIEW_STATE.md
```
