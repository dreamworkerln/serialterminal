# Node Run / Observation Recording Policy

## Purpose

Этот документ задаёт canonical правила local executor agent после hardware-задачи: как сохранить complete run evidence и, когда нужно, короткий factual observation record в отдельной append-only branch.

Local executor — исполнитель и сборщик evidence. Он не выполняет reviewer/promotion работу и не изменяет `.agents/skills/node-agent/SKILL.md` на основании одного run.

Reviewer обрабатывает observations по [NODE_SKILL_LEARNING_POLICY.md](NODE_SKILL_LEARNING_POLICY.md).

---

## 1. Storage и branch model

Run bundles и observations хранятся в отдельной orphan branch того же репозитория:

```text
node_observations
```

Эта branch не является development branch SerialTerminal и не должна содержать copy/merge истории `dev`.

Для local storage используется отдельный independent clone:

```text
./serialterminal/
    main clone, branch dev

./serialterminal-observations/
    independent clone, branch node_observations
```

Если команды выполняются из корня main `serialterminal` clone, storage clone находится по пути:

```text
../serialterminal-observations
```

Main clone используется для SerialTerminal/agent API, policy, skills и guarded helpers. Sibling clone используется только для run/observation evidence и reviewer state.

Executor не переключает main clone с `dev` на `node_observations` и не создаёт linked worktree для evidence storage.

### Human-only initial setup

Одноразовая setup-команда человека:

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

`../serialterminal-observations/.git` должен быть directory собственного clone, а не pointer-файлом linked worktree.

Человек также настраивает writable access/sandbox для sibling clone. Executor не меняет Codex rules, `config.toml`, trust, sandbox mode или writable roots.

---

## 2. Target layout

Published и pending evidence используют только canonical namespaces:

```text
node_observations branch
├── REVIEW_STATE.md
├── observations/
│   ├── OBS_YYYYMMDDTHHMMSSZ_<short-topic>.md
│   └── ...
└── runs/
    ├── RUN_YYYYMMDDTHHMMSSZ_<short-topic>/
    │   ├── MANIFEST.json
    │   ├── REPORT.md
    │   ├── serialterminal.log
    │   └── serialterminal.console.log
    └── ...
```

`REVIEW_STATE.md` принадлежит reviewer-у. Executor его не изменяет.

Committed observations и run bundles являются append-only historical evidence. Если в committed artifact найдена ошибка, публикуй новый correction record/run; не редактируй и не удаляй старый.

---

## 3. Artifact roles

### `serialterminal.log`

Exact forensic SerialTerminal logfile этого process/run. Это source of truth для JSONL requests/responses, raw RX chunk boundaries, `data_b64`, session seq, TX/state/error records.

Bundle creation только копирует exact logfile. Не нормализуй и не реконструируй его.

### `serialterminal.console.log`

Exact companion human-console logfile того же SerialTerminal run. Это presentation/audit view (`[I]` input, `[O]` completed human-console output), а не delivery proof.

Bundle creation копирует файл, который создал SerialTerminal. Не восстанавливай console log из forensic log.

### `REPORT.md`

Complete curated executor report о выполненной hardware task.

Он отвечает:

- что было поручено;
- какие exact revisions реально известны;
- какой hardware/session context фактически использовался;
- что было выполнено;
- какой verdict получен по каждому requested scenario;
- какие anomalies/limitations обнаружены;
- в каком состоянии оставлены hardware/sessions;
- где лежат persistent evidence artifacts.

`REPORT.md` не является raw execution log, chain-of-thought или dump всего JSON. Он пишется до final user-facing response; final response кратко суммирует persisted report.

### `OBS_*.md`

Короткий factual reviewer/learning record. Он отвечает: **что этот run установил или наблюдал**, а не «как агент по шагам работал».

Observation не должен дублировать `REPORT.md` и logs.

---

## 4. Run identity и naming

Используй один UTC identity:

```text
<stamp>_<topic>
```

где:

```text
stamp = YYYYMMDDTHHMMSSZ
topic = lowercase slug: [a-z0-9][a-z0-9-]*
```

Если observation относится к run, basename должен совпадать:

```text
observations/OBS_20260908T181500Z_bidirectional-user-smoke.md
runs/RUN_20260908T181500Z_bidirectional-user-smoke/
```

Не включай concrete MAC/node IDs в filename. Они разрешены внутри evidence конкретного run.

---

## 5. Когда observation required, optional или отсутствует

Complete hardware run всегда может иметь RUN bundle. Standalone observation — отдельный distilled artifact и нужен не всегда.

Observation особенно обязателен при:

- FAIL/BLOCKED после начала hardware interaction;
- unexpected behavior;
- anomaly/regression/bug candidate;
- расхождении с текущим node skill/expected contract;
- intentional fault injection;
- новом или reusable hardware scenario, полезном reviewer-у.

Routine PASS run может не иметь standalone observation, если нет reusable finding сверх полного report/log evidence. Это решение должно быть записано явно в `MANIFEST.json` и кратко в `REPORT.md`; отсутствие OBS нельзя оставлять двусмысленным.

Standalone observation без RUN остаётся допустимым для маленьких factual observation-only случаев, где полный hardware run bundle не требуется.

---

## 6. Observation format

Обычно достаточно 10–25 содержательных строк плюс короткие exact excerpts.

Template:

```markdown
# Node observation

Observed: YYYY-MM-DDTHH:MM:SSZ
Task: <short task>
Result: PASS | FAIL | BLOCKED | INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@<exact SHA>
Firmware: dreamworkerln/lora-sack-protocol@<exact SHA or unknown>

## Setup
- <relevant actual setup/fault state>

## Actions
- <minimal stimulus/order needed to understand evidence>

## Evidence
- <key exact observed facts>

## Anomalies / conflicts
- none

## Final state
- <cleanup/final hardware state>
```

Если observation относится к RUN bundle, добавь **ровно одну canonical machine-readable строку**:

```text
Run bundle: runs/RUN_YYYYMMDDTHHMMSSZ_<short-topic>/
```

Она должна использовать тот же `<stamp>_<topic>`, что и filename OBS. `commit-node-observation` считает такую запись run-bound и никогда не публикует её отдельно.

Если exact source SHA неизвестен, пиши `unknown`; не угадывай.

В observation разрешены run-specific IDs, MAC, USB path, session IDs, RSSI/SNR/Q, timing/counters, fault state, payload и exact excerpts. Не превращай эти значения в постоянные свойства класса/экземпляра.

---

## 7. `MANIFEST.json` schema v1

Canonical schema для `RUN_<stamp>_<topic>/MANIFEST.json`:

```json
{
  "schema": 1,
  "observed_at": "YYYY-MM-DDTHH:MM:SSZ",
  "topic": "short-topic",
  "result": "PASS",
  "serialterminal": {
    "repo": "dreamworkerln/serialterminal",
    "sha": "<exact 40-hex SHA>"
  },
  "firmware": {
    "repo": "dreamworkerln/lora-sack-protocol",
    "sha": "<exact 40-hex SHA or unknown>"
  },
  "observation": {
    "state": "recorded",
    "path": "../../observations/OBS_YYYYMMDDTHHMMSSZ_short-topic.md"
  },
  "files": {
    "report": "REPORT.md",
    "console": "serialterminal.console.log",
    "serialterminal_log": "serialterminal.log"
  }
}
```

Для run без observation:

```json
"observation": {
  "state": "not-required",
  "path": null,
  "reason": "<short explicit reason>"
}
```

Validation rules:

- `observed_at` и `topic` должны точно соответствовать `RUN_<stamp>_<topic>`;
- `result` только `PASS | FAIL | BLOCKED | INCONCLUSIVE`;
- SerialTerminal SHA всегда exact 40-hex;
- firmware SHA exact 40-hex или literal `unknown`;
- `files` mapping canonical и не содержит произвольных external paths;
- `recorded` требует matching OBS с тем же identity и обратной `Run bundle:` ссылкой;
- `not-required` требует `path: null` и non-empty `reason`.

Helper валидирует форму/связность, но не решает, семантически оправдан ли `not-required`; это ответственность executor/policy.

---

## 8. Executor создаёт artifacts; helpers только публикуют

Главный invariant:

```text
executor
    -> creates/interprets evidence

publication helper
    -> validates already prepared artifacts
    -> stages exact allowlist
    -> commits
    -> normal-pushes
    -> verifies local/remote state
```

Helpers никогда не должны:

- придумывать/пересказывать evidence;
- писать или чинить `REPORT.md`;
- писать или чинить observation;
- выбирать, какой local logfile относится к run;
- copy/move source logs в bundle;
- угадывать source revisions;
- достраивать incomplete bundle.

### Canonical executor order для RUN

После hardware interaction:

1. восстанови требуемый final hardware state;
2. закрой sessions и заверши SerialTerminal process, чтобы оба logs были final;
3. выбери один UTC `<stamp>_<topic>`;
4. создай `runs/RUN_<stamp>_<topic>/`;
5. напиши `REPORT.md`;
6. скопируй exact forensic log как `serialterminal.log`;
7. скопируй exact companion log как `serialterminal.console.log`;
8. реши по policy, нужен ли OBS;
9. если нужен — создай matching `observations/OBS_<stamp>_<topic>.md` с canonical `Run bundle:` pointer;
10. напиши `MANIFEST.json` последним, когда остальные artifact paths уже определены;
11. вызови `commit-node-run`.

Можно сначала собирать bundle во временном local staging dir и только после completeness копировать в sibling clone. Это уменьшает incomplete staging, но не является correctness requirement.

---

## 9. Guarded publication helpers

Repository содержит два стабильных no-argument helpers:

```bash
python3 -I scripts/commit-node-observation
python3 -I scripts/commit-node-run
```

Оба вызываются только из корня main `serialterminal` clone отдельным standalone shell execution. Не добавляй `&&`, `;`, pipe, subshell, command substitution или другие команды до/после helper-а.

В `workspace-write` `.git` sibling clone может быть read-only, поэтому executor должен сразу запрашивать elevated execution для helper command, а не сначала получать ожидаемый sandbox failure.

Human/operator может один раз разрешить stable prefixes:

```python
prefix_rule(
    pattern = ["python3", "-I", "scripts/commit-node-observation"],
    decision = "allow",
    justification = "Allow guarded standalone observation publication.",
)

prefix_rule(
    pattern = ["python3", "-I", "scripts/commit-node-run"],
    decision = "allow",
    justification = "Allow guarded complete node run publication.",
)
```

Executor не модифицирует helpers/common publication module во время hardware task. Их изменение — отдельная code-maintenance задача.

### `commit-node-observation`

Публикует только eligible standalone observations.

Run-bound OBS с canonical `Run bundle:` pointer игнорируется и не может быть случайно опубликован отдельно.

### `commit-node-run`

Публикует только complete valid RUN bundles. Если manifest `observation.state=recorded`, matching OBS входит в тот же commit. Если `not-required`, commit содержит RUN без OBS.

Оба helpers используют exact-path staging, normal push only и никогда не force-push.

---

## 10. Pending backlog и coexistence

Sibling clone одновременно является append-only branch checkout и local staging area. Поэтому valid untracked artifacts могут законно пережить executor run.

Нормальные состояния:

- несколько pending standalone observations;
- несколько complete pending RUN bundles;
- incomplete RUN от interrupted/crashed executor;
- run-bound OBS, bundle которого ещё не complete;
- standalone OBS и RUN artifacts одновременно.

Rules:

```text
commit-node-observation
    -> публикует все eligible standalone OBS одним commit
    -> оставляет RUN/incomplete/run-bound artifacts pending

commit-node-run
    -> публикует все complete valid RUN bundles одним commit
    -> включает matching OBS для recorded runs
    -> оставляет standalone OBS и incomplete RUN pending
```

Incomplete/invalid-but-canonical run A не должен блокировать публикацию complete unrelated run B. Helper оставляет A pending и не чинит/не удаляет его.

Любой untracked path вне canonical `observations/OBS_...md` или разрешённых четырёх files внутри canonical `runs/RUN_.../` вызывает hard guard failure. Helpers не делают broad staging.

После successful publication storage clone может всё ещё иметь recognized untracked pending artifacts. Допустимый final state:

```text
no tracked modifications/deletions
no staged changes
published paths no longer pending
local/remote refs synchronized
remaining untracked paths only recognized pending artifacts
```

Stale/abandoned incomplete staging удаляется только отдельной явной maintenance-задачей; helper никогда не удаляет evidence-like files сам.

---

## 11. Push failure и retry-safe recovery

Network failure может произойти после local commit, но до push.

При push failure helper обязан:

- сохранить созданный local commit;
- вывести exact local commit SHA и Git diagnostic;
- не делать reset/amend/rebase/merge/force-push;
- оставить новые untracked backlog artifacts нетронутыми.

На следующем invocation helper сначала fetch-ит `origin/node_observations`.

Автоматический retry разрешён только если:

```text
remote not ahead
local branch ahead only
all local-ahead commits are validated append-only publication commits
all changed paths are canonical observation/run additions
```

Тогда helper сначала normal-push-ит existing local-ahead commit(s), проверяет synchronization и только затем может опубликовать новый accumulated backlog.

Hard failure без destructive recovery:

- remote ahead при unpublished local work;
- divergence;
- local-ahead commit меняет/удаляет historical evidence;
- local-ahead commit содержит path вне publication namespaces;
- tracked/staged working-tree residue.

Executor не обходит этот guard raw Git-командами.

---

## 12. Helper result contract

Invalid invocation:

```text
exit code: 2
usage: python3 -I scripts/commit-node-observation
```

или:

```text
usage: python3 -I scripts/commit-node-run
```

Guard/Git failure:

```text
exit code: 1
OBSERVATION COMMIT FAILED: <concrete reason>
```

или:

```text
RUN COMMIT FAILED: <concrete reason>
```

Standalone observation success:

```text
exit code: 0
observations committed and pushed: <N>
observation: observations/OBS_....md
commit: <SHA>
```

Run success:

```text
exit code: 0
runs committed and pushed: <N>
run: runs/RUN_.../
observation: observations/OBS_....md   # only when recorded
commit: <SHA>
```

При non-zero передавай пользователю exact diagnostic text; не ограничивайся «helper failed».

---

## 13. Independent remote verification

После helper `exit 0` executor обязан отдельно подтвердить actual remote ref одной неизменной standalone-командой:

```bash
git -C ../serialterminal-observations ls-remote origin refs/heads/node_observations
```

Запрашивай elevated execution сразу. Не chaining-уй `grep`, `awk`, `test`, `&&`, pipe или другие команды.

Сравни первый SHA stdout с `commit: <SHA>` helper-а. Только при совпадении рапортуй:

```text
remote verification: verified
```

При mismatch:

```text
remote verification: mismatch
```

Если remote read невозможен из-за network/tool restriction, успешный helper result не отменяется, но рапортуй:

```text
remote verification: not verified
```

Не заменяй independent check локальным `origin/node_observations`.

---

## 14. Storage/config failures

Если sibling clone отсутствует/неверно настроен:

```text
OBSERVATION STORAGE NOT CONFIGURED
```

Если sandbox не позволяет executor создать run/observation files:

```text
OBSERVATION STORAGE NOT WRITABLE
```

Не создавай/перенастраивай clone и не меняй permissions в hardware task.

Если helper отказывается из-за dirty/diverged/unsafe state, не делай raw `git add/commit/push`, merge, rebase, reset или force-push для обхода guard.

---

## 15. Final user-facing report

После successful run publication final chat response — только completion/pointer layer; подробный narrative уже в `REPORT.md`.

Пример:

```text
Result: PASS
Observation: observations/OBS_...          # when recorded
Run bundle: runs/RUN_.../
Commit: <SHA>
Remote verification: verified
```

Для observation-only case:

```text
Result: PASS/FAIL/BLOCKED/INCONCLUSIVE
Observation: observations/OBS_...
Commit: <SHA>
Remote verification: verified
```

Не перепечатывай full `observe.result.lines`, весь console transcript или forensic JSON, если exact artifacts уже опубликованы в RUN bundle. Ключевые anomalies/limitations всё равно кратко сообщи пользователю.

---

## Authority

```text
AGENT_API.md
    generic SerialTerminal machine API + run-log semantics

.agents/skills/serialterminal-agent/SKILL.md
    concise generic SerialTerminal operation

.agents/skills/node-agent/SKILL.md
    concise LoRa-Chatter operation + pointer to this publication policy

NODE_OBSERVATION_RECORDING_POLICY.md
    canonical executor/storage/report/run/observation/publication/recovery policy

scripts/commit-node-observation
scripts/commit-node-run
scripts/node-publication-common.py
    guarded validation/publication implementation; never semantic evidence authoring

NODE_SKILL_LEARNING_POLICY.md
    reviewer processing/promotion rules

node_observations branch
    run-specific historical evidence + REVIEW_STATE.md
```
