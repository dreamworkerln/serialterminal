# Node Skill Learning Policy

## Purpose

Этот документ задаёт процесс накопления hardware observations и контролируемого обновления `.agents/skills/node-agent/SKILL.md`.

Цель — разделить две роли:

```text
local executor agent
    выполняет hardware-задачи и фиксирует наблюдения

reviewer
    периодически обрабатывает накопленные observations,
    обобщает их и обновляет class-level node skill
```

Local executor не должен тратить токены на полноценное knowledge-management рассуждение и не должен самостоятельно «обучать» node skill после каждого hardware run.

---

## 1. Node skill описывает класс, а не экземпляры

`.agents/skills/node-agent/SKILL.md` должен позволять агенту правильно работать с LoRa-Chatter node, которую он раньше не видел.

В skill допустимы class-level знания:

- команды и их semantics;
- transport/stream behavior;
- protocol behavior;
- validation criteria;
- fault/recovery scenarios;
- reusable hardware-operation rules;
- protocol constants и другие настоящие class-level identifiers, когда они являются частью контракта.

В skill не должны попадать instance-specific данные:

- конкретные node IDs;
- MAC/BLE addresses;
- конкретные USB device paths;
- session IDs;
- текущие cursors/seq;
- текущие RSSI/SNR/Q;
- текущая lab topology;
- текущая доступность конкретного transport;
- текущее питание/состояние конкретного экземпляра;
- результаты одного run, сформулированные как постоянное свойство устройства.

Ключевое правило:

```text
current state of an object != behavior of the class
```

Например, observation «в этом run USB endpoint отсутствовал» не означает, что LoRa-Chatter node не поддерживает USB. Observation «в этом run RF был недоступен» не означает, что конкретная node permanently имеет отключённый RF.

---

## 2. Local executor — простой исполнитель

Local executor должен:

1. прочитать `AGENTS.md`, `AGENT_API.md`, generic SerialTerminal skill и текущий node skill;
2. выполнить заданный hardware scenario;
3. собрать достаточное evidence для PASS/FAIL/BLOCKED;
4. не путать local queue/write confirmation с higher-level delivery;
5. явно сообщить неожиданное поведение, anomaly или bug candidate;
6. оставить hardware в требуемом безопасном финальном состоянии;
7. при включённом observation recording сохранить короткую фактическую запись о run.

Local executor не обязан:

- классифицировать каждое наблюдение как reusable knowledge;
- строить общую модель поведения;
- разрешать противоречия между skill, source и hardware;
- дедуплицировать накопленные знания;
- редактировать `node-agent/SKILL.md`;
- превращать единичное observation в постоянное правило.

Если обнаружено поведение, противоречащее текущему skill или expected result, executor должен рапортовать его как anomaly/conflict и сохранить evidence, а не переписывать skill под один run.

---

## 3. Observation records — сырьё, не skill

Для накопления наблюдений рекомендуется отдельная evidence area, например:

```text
node_observations/
    OBS_YYYYMMDD_<short-topic>.md
```

Если позже будет выделена отдельная Git branch для executor-generated observations, executor должен писать только observation records в эту branch. Создание/имя такой branch является отдельным repository decision и этой policy автоматически не выполняется.

Observation record должен быть коротким и фактическим. Минимальный шаблон:

```markdown
# Node observation

Observed: YYYY-MM-DDTHH:MM:SSZ
Task: <short task>
Firmware/source checkpoint: <repo/branch@SHA if known/relevant>
SerialTerminal checkpoint: <repo/branch@SHA>

## Setup
- transports actually discovered/used
- relevant intentional fault/setup conditions

## Actions
- concise ordered actions

## Observed evidence
- exact relevant outputs/events
- PASS/FAIL/BLOCKED facts

## Anomalies / conflicts
- expected vs observed, if any

## Final state
- cleanup/restored modes/sessions

## Evidence pointers
- log path / artifact / commit / external report when available
```

Не нужно копировать полный terminal transcript, если достаточно точных excerpts и ссылки на authoritative log/evidence.

Observation record может содержать concrete node IDs, addresses, measurements и topology, потому что это historical evidence конкретного run. Именно поэтому observation records отделены от class-level skill.

---

## 4. Bug/anomaly reporting имеет приоритет

Если executor обнаружил потенциальный баг, regression или расхождение с ожидаемым поведением, он должен явно выделить:

```text
expected
observed
evidence
reproduction steps, if known
current impact
```

Он не должен автоматически объявлять новое observed behavior правильным контрактом.

До reviewer/source inspection такой результат остаётся anomaly/bug candidate.

---

## 5. Reviewer выполняет обучение

Reviewer периодически читает накопленные observation records, текущий node skill, relevant firmware/source и generic SerialTerminal contract.

Именно reviewer выполняет дорогую часть процесса:

```text
collect observations
→ compare with current skill
→ inspect authoritative source when needed
→ separate instance state from class behavior
→ deduplicate
→ resolve/refine conflicts
→ generalize reusable rules
→ update node skill
→ preserve evidence separately
```

Reviewer может использовать Git/GitHub history, exact SHAs и накопленные observation files для cross-run анализа.

---

## 6. Reviewer classification

При обработке observation reviewer различает минимум:

```text
CLASS BEHAVIOR
    reusable behavior of LoRa-Chatter nodes

INSTANCE STATE
    current state/configuration of one physical node

ENVIRONMENT / TOPOLOGY
    what transports/devices were available in this run

MEASUREMENT
    RSSI/SNR/Q/timing/counters and similar run-specific values

EVIDENCE
    historical proof that a scenario was exercised

ANOMALY / CONFLICT
    observation that disagrees with skill/source/expected behavior
```

Только reusable class behavior является прямым кандидатом на promotion в node skill.

Instance state, topology, measurements и run history остаются evidence.

---

## 7. Generalization rule

Перед promotion reviewer должен суметь сформулировать знание без привязки к конкретному экземпляру или случайной лабораторной конфигурации.

Плохая формулировка:

```text
node 1B44 has RF disabled
```

Хорошая class-level формулировка:

```text
If the controller remains powered while radio-module power is absent,
controller transport may remain available while boot reports RF unavailable.
```

Плохая формулировка:

```text
USB device X is always present
```

Хорошая class-level формулировка:

```text
Discovery reflects currently available transports. If multiple transports
report the same node identity, treat them as transport paths to one physical node.
```

---

## 8. Promotion gate

Reviewer может добавить/изменить правило в `node-agent/SKILL.md` только если оно:

- class-level, а не instance-level;
- повторно полезно будущему агенту;
- не является transient measurement/state;
- не зависит без необходимости от concrete node IDs/addresses/topology;
- подтверждено source contract, hardware evidence или их сочетанием;
- не является простой догадкой;
- не противоречит authoritative source;
- не дублирует существующее правило;
- делает skill инструкцией, а не журналом экспериментов.

Если confidence недостаточен, knowledge остаётся в observations до следующего review/validation.

---

## 9. Conflict handling

Observation, противоречащее skill, не должно автоматически overwrite skill.

Reviewer сначала определяет одно из:

```text
skill wording was too absolute
skill is stale after source change
observation is an intentional alternate hardware state
observation is environment-specific
observation is a regression/bug
insufficient evidence
```

Только после этого меняется class-level guidance.

---

## 10. Skill не является test log

Датированные smoke runs, конкретные payloads, MAC addresses, exact RSSI/SNR/Q и аналогичные сведения должны жить в observation/evidence records, а не накапливаться в node skill.

Skill может сохранить обобщённый проверенный вывод, например:

```text
BLE notification boundaries are not guaranteed to match text-line boundaries.
```

но не обязан хранить каждую дату и каждый run, который этот факт подтвердил.

---

## 11. Recommended operational loop

```text
user/reviewer defines hardware task
        ↓
local executor runs task
        ↓
PASS/FAIL/BLOCKED + evidence
        ↓
optional observation file committed to evidence area/branch
        ↓
reviewer periodically processes accumulated observations
        ↓
reviewer updates node-agent/SKILL.md only when promotion gate passes
```

Local executor optimizes for reliable execution and evidence collection.
Reviewer optimizes for correctness, abstraction quality and long-term skill maintenance.

---

## 12. Authority

```text
AGENT_API.md
    generic SerialTerminal machine-facing API authority

.agents/skills/serialterminal-agent/SKILL.md
    concise generic operational guidance

.agents/skills/node-agent/SKILL.md
    class-level LoRa-Chatter operating/validation guidance

NODE_SKILL_LEARNING_POLICY.md
    rules for collecting evidence and promoting knowledge into node skill

node observation records
    historical run-specific evidence

lora-sack-protocol source/docs
    firmware/protocol implementation authority
```

При расхождении skill с source или новым hardware evidence skill не переписывается локальным executor автоматически. Расхождение передаётся reviewer-у для анализа и controlled promotion/correction.
