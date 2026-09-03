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

Для неё используется отдельный permanent Git worktree. Main SerialTerminal worktree остаётся на `dev` и используется для запуска кода/agent API; observation worktree используется только для записи evidence.

Executor не должен переключать main worktree с `dev` на `node_observations`.

Чтобы найти observation worktree, используй:

```bash
git worktree list --porcelain
```

и найди worktree с:

```text
branch refs/heads/node_observations
```

Если такой branch/worktree не настроен, не создавай его автоматически и не переключай branches без отдельной setup-задачи. Рапортуй `OBSERVATION STORAGE NOT CONFIGURED` и продолжай hardware task без изменения skills/docs.

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

## 9. Git rules для executor

Перед записью:

1. основной worktree остаётся на `dev`;
2. найди permanent `node_observations` worktree через `git worktree list --porcelain`;
3. в observation worktree проверь `git status --short`;
4. если есть неожиданные local changes, не перезаписывай их и сообщи проблему;
5. создай ровно один новый observation file для текущего run;
6. не изменяй `REVIEW_STATE.md`;
7. не изменяй предыдущие observation files;
8. commit только новый record.

Рекомендуемый commit message:

```text
obs: <short topic>
```

Не merge/rebase/reset `node_observations` ради записи observation. Если push отклонён или branch разошлась, остановись и сообщи ситуацию вместо автоматического history manipulation.

---

## 10. Что executor возвращает пользователю

В основном отчёте достаточно:

```text
hardware result: PASS/FAIL/BLOCKED/INCONCLUSIVE
observation: <filename or not recorded>
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

NODE_SKILL_LEARNING_POLICY.md
    reviewer rule for processing observations and updating node skill

node_observations branch
    run-specific historical evidence and REVIEW_STATE.md
```
