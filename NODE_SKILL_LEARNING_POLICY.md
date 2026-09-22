# Node Skill Learning Policy

## Purpose

Этот документ предназначен reviewer-у, который периодически обрабатывает hardware observations из branch node_observations.

Reviewer отделён от local hardware executor-а. Executor только выполняет физический scenario и пишет evidence. Reviewer выполняет дорогую knowledge-processing часть и при необходимости:

- обновляет active hardware executor skill/references на node_observations;
- изменяет SerialTerminal source/API/docs на dev только когда evidence действительно требует source outcome;
- продвигает REVIEW_STATE.md после завершённого reviewer outcome.

Canonical executor policy находится на node_observations:

```text
NODE_OBSERVATION_RECORDING_POLICY.md
.agents/skills/lora-chatter-hardware/
```

Reviewer pipeline:

```text
raw observations
-> compare across runs
-> inspect authoritative source when needed
-> separate object state from class behavior
-> deduplicate / resolve conflicts
-> generalize reusable rules
-> update hardware skill/reference when justified
-> advance REVIEW_STATE.md
```

Local hardware executor не выполняет этот процесс.

## 1. Authority and branches

```text
dev
    SerialTerminal code/docs
    AGENT_API.md
    .agents/skills/serialterminal-agent/SKILL.md
    NODE_SKILL_LEARNING_POLICY.md

node_observations
    hardware executor AGENTS.md
    .agents/skills/lora-chatter-hardware/
    NODE_OBSERVATION_RECORDING_POLICY.md
    NODE_RUN_AUXILIARY_ARTIFACTS.md
    observations/*.md
    runs/*
    REVIEW_STATE.md

lora-sack-protocol
    firmware/protocol source authority
```

node_observations не merge-ится в dev. Historical observations/RUNs остаются append-only.

Отдельный reviewer/infrastructure task может менять tracked hardware skill/policy files и REVIEW_STATE.md на node_observations. Local hardware executor во время measured run этого не делает.

Перед любой записью refetch actual target branch HEAD и relevant files.

## 2. Reviewer bootstrap

Перед review:

1. refetch serialterminal/dev HEAD;
2. refetch serialterminal/node_observations HEAD;
3. прочитать dev root AGENTS.md и этот reviewer policy;
4. прочитать node_observations/AGENTS.md;
5. прочитать current .agents/skills/lora-chatter-hardware/SKILL.md и только relevant references;
6. прочитать REVIEW_STATE.md из node_observations;
7. определить exact set новых observation records;
8. читать AGENT_API.md/generic SerialTerminal skill только если observations затрагивают generic API/transport semantics;
9. inspect lora-sack-protocol source/docs, когда promotion/conflict resolution требует firmware authority.

Не начинай с memory или guessed last observation.

## 3. REVIEW_STATE.md

REVIEW_STATE.md живёт в корне node_observations и является mutable reviewer state. Local hardware executor его не меняет.

Рекомендуемый формат:

```markdown
# Node observation review state

last_reviewed_observation: observations/OBS_...
last_reviewed_observation_commit: <node_observations evidence boundary commit>
reviewed_against_dev: <exact dev SHA used after any required source outcome>
reviewed_by_commit: <node_observations hardware-skill/reference promotion commit, or none>
reviewed_at: YYYY-MM-DDTHH:MM:SSZ

unresolved:
  - observation: observations/OBS_...
    reason: <short reason>
```

Semantics:

- last_reviewed_observation — последний observation file в полностью обработанном диапазоне;
- last_reviewed_observation_commit — evidence commit boundary, до которого review выполнен;
- reviewed_against_dev — exact dev checkpoint, против которого закрыт review;
- reviewed_by_commit — отдельный node_observations infrastructure commit, который применил promoted hardware skill/reference changes; если таких changes не было, none;
- unresolved — уже рассмотренные, но не закрытые anomaly/conflict candidates.

Если reviewer меняет hardware skill/references, сначала создаётся и проверяется отдельный infrastructure commit, затем отдельным commit обновляется REVIEW_STATE.md. Это позволяет state ссылаться на уже существующий reviewed_by_commit.

REVIEW_STATE нельзя advance до завершения всех required dev/source outcomes и hardware-skill outcomes.

## 4. Как определить новые observations

Primary boundary — `last_reviewed_observation_commit`.

Reviewer должен обработать observation files, добавленные в `node_observations` после этого commit, в commit order.

Если `REVIEW_STATE.md` ещё отсутствует, это initial review: обработай все существующие `observations/OBS_*.md`.

Если старый state содержит только `last_reviewed_observation`, но не commit SHA, найди commit, который впервые добавил этот file, и используй его как recovery boundary.

Не полагайся только на timestamp filename: commit history является authoritative ordering при неоднозначности.

`REVIEW_STATE.md`-only commits не считаются observations.

---

## 5. Processing каждого observation

Для каждого нового record:

1. проверить, что это factual observation, а не уже выполненная generalization;
2. сохранить concrete setup/identity/measurements как run evidence;
3. проверить exact SerialTerminal/firmware checkpoints, если они указаны;
4. сравнить observation с текущим hardware skill;
5. при необходимости сравнить с другими observations того же scenario;
6. при semantic conflict inspect authoritative firmware/source или generic API;
7. классифицировать reviewer outcome;
8. решить: ignore as transient, retain as evidence, mark unresolved, report bug candidate, refine existing skill rule или promote new class-level rule.

Reviewer не обязан превращать каждый PASS в новое знание.

---

## 6. Classification

Минимальные классы:

```text
CONFIRMS_EXISTING
    observation подтверждает уже правильный class-level rule

CLASS_CANDIDATE
    reusable behavior, потенциально достойное skill

INSTANCE_STATE
    состояние/config одного экземпляра

ENVIRONMENT_TOPOLOGY
    текущие transports/devices/permissions/lab setup

MEASUREMENT
    RSSI/SNR/Q/timing/counters/current values

EVIDENCE_ONLY
    полезное историческое подтверждение без изменения skill

ANOMALY_CONFLICT
    расходится с skill/source/expected behavior

BUG_CANDIDATE
    evidence указывает на возможный regression/implementation defect

INSUFFICIENT
    evidence недостаточно для вывода
```

Только `CLASS_CANDIDATE` после promotion gate напрямую изменяет hardware skill.

`ANOMALY_CONFLICT` сначала требует resolution; он не является автоматическим новым contract.

---

## 7. Class-level abstraction rule

`.agents/skills/lora-chatter-hardware/SKILL.md` описывает класс LoRa-Chatter node, а не лабораторные экземпляры.

Reviewer должен суметь сформулировать promoted rule без случайной привязки к:

- concrete node ID;
- MAC/BLE address;
- USB device path;
- session ID/cursor/seq;
- current RSSI/SNR/Q;
- current topology;
- current transport availability;
- current power state конкретного экземпляра;
- exact payload/date одного run.

Главный тест:

```text
Would this instruction help an agent operate a LoRa-Chatter node it has never seen before?
```

Если нет — это почти наверняка evidence/state, а не skill knowledge.

Ключевое правило:

```text
current state of an object != behavior of the class
```

---

## 8. Generalization examples

Не promote:

```text
node <id> had RF disabled
```

Можно promote после подтверждения:

```text
If controller power remains available while radio-module power is absent,
controller transport may remain reachable while RF is unavailable.
```

Не promote:

```text
USB endpoint was absent/present in this run
```

Можно promote:

```text
Discovery reflects currently available transports, not a permanent node inventory.
Multiple transports reporting the same node identity are transport paths to one physical node.
```

Не promote:

```text
RSSI was -29 dBm
```

Можно использовать как evidence успешного peer RX, но не как class-level expected RSSI.

---

## 9. Promotion gate

Новое/изменённое правило попадает в `lora-chatter-hardware/SKILL.md` только если:

- оно class-level;
- повторно полезно будущему executor-у;
- не является transient state/measurement/topology;
- подтверждено достаточным hardware evidence, authoritative source или их сочетанием;
- формулировка не сильнее имеющегося evidence/source;
- это не догадка;
- оно не противоречит authoritative source;
- оно не дублирует уже существующий rule;
- оно уменьшает вероятность будущей ошибки executor-а;
- skill остаётся компактной instruction manual, а не test log.

Один run может быть достаточен для хорошо определённого fault scenario, если intentional setup известен и source/behavior согласованы. Один случайный outcome не должен превращаться в универсальный contract.

Если confidence недостаточен, leave unresolved/evidence-only.

---

## 10. Conflict resolution

Если observation противоречит skill, reviewer должен сначала определить наиболее вероятный тип:

```text
skill wording too absolute
skill stale after behavior/source change
intentional alternate hardware state
instance/environment-specific outcome
measurement variance
SerialTerminal/tool artifact
firmware regression/bug
insufficient evidence
```

Дальше:

- если skill слишком абсолютный — сузить его до реально подтверждённого class-level rule;
- если source изменился — обновить skill по actual source + validation evidence;
- если alternate state — описать conditional scenario, а не свойство экземпляра;
- если environment/instance-specific — оставить только в evidence;
- если bug candidate — не нормализовать баг в skill; сохранить unresolved и рапортовать;
- если insufficient — не менять skill.

---

## 11. Cross-run processing

Reviewer должен использовать накопление observations для выводов, которые local executor делать не обязан:

- одинаковый pattern повторяется в разных runs;
- один observation опровергает слишком сильную старую формулировку;
- разные экземпляры показывают один class-level behavior;
- fault scenario воспроизводится при одинаковом intentional setup;
- старый anomaly исчез после source fix;
- measurement variation подтверждает, что значение не является constant.

Не нужно ждать искусственного числа повторов. Требуемая evidence strength зависит от типа claim.

---

## 12. Обновление hardware executor skill/references

Active target находится на node_observations:

```text
.agents/skills/lora-chatter-hardware/SKILL.md
.agents/skills/lora-chatter-hardware/references/
```

Перед write:

1. refetch actual node_observations HEAD;
2. refetch current skill и только затронутые reference files;
3. re-check observations against authoritative firmware/source/API;
4. внести минимальные class-level changes;
5. не переносить raw logs, concrete IDs, topology или measurements в reusable instructions;
6. review diff for accidental weakening/duplication;
7. commit normal reviewer/infrastructure change directly to node_observations;
8. read back commit and updated files.

Этот infrastructure commit не должен изменять observations/, runs/ или REVIEW_STATE.md.

Если review затронул generic SerialTerminal API/source behavior, соответствующие source/docs/tests changes выполняются отдельно на dev по dev/AGENTS.md. Не переписывай generic contract из одного Chatter observation без source evidence.

## 13. Порядок обновления REVIEW_STATE.md

После processing диапазона:

1. закончить все необходимые source/API/docs changes на dev и получить resulting dev SHA;
2. если promotion требует hardware skill/reference changes — закончить отдельный node_observations infrastructure commit и получить его exact SHA;
3. read back resulting source/skill state;
4. определить последний полностью обработанный observation и evidence commit boundary;
5. refetch actual node_observations HEAD и current REVIEW_STATE.md;
6. обновить REVIEW_STATE.md отдельным state-only commit;
7. reviewed_against_dev = exact resulting dev SHA;
8. reviewed_by_commit = exact hardware-skill/reference infrastructure commit или none;
9. сохранить unresolved entries;
10. read back state commit.

Нельзя advance REVIEW_STATE.md, если соответствующий source или skill outcome ещё не завершён.

State commit не должен менять historical observations/runs или executor infrastructure.

## 14. Partial review

Reviewer может обработать только часть новых observations.

В этом случае `last_reviewed_observation*` продвигается только до последнего **полностью обработанного** record в contiguous commit range.

Не перескакивай через неразобранный observation только потому, что более поздний файл проще.

Unresolved observation считается обработанным для cursor/state, если reviewer уже классифицировал его и сохранил в `unresolved`; будущие related observations могут закрыть его позднее.

---

## 15. What not to do

Reviewer не должен:

- удалять raw observations после promotion;
- переписывать history `node_observations` ради чистоты;
- переносить MAC/node IDs/measurements в class skill;
- считать PASS одного run обязательной class guarantee;
- нормализовать regression как новый contract без source decision;
- обновлять REVIEW_STATE до skill/docs outcome;
- заявлять hardware/source validation, которое не выполнялось.

---

## 16. Expected reviewer report

После review сообщить кратко:

```text
observations processed: <range/count>
hardware skill/reference changes: <summary or none>
unresolved: <count/list>
dev/source commit: <SHA or none>
hardware-skill commit: <node_observations SHA or none>
REVIEW_STATE commit: <node_observations SHA>
next observation boundary: <last_reviewed_observation>
```

## Authority summary

```text
node_observations:NODE_OBSERVATION_RECORDING_POLICY.md
    local hardware executor -> raw evidence policy

node_observations:observations/*.md + runs/*
    immutable run-specific evidence

NODE_SKILL_LEARNING_POLICY.md on dev
    reviewer processing/promotion rules

node_observations:REVIEW_STATE.md
    mutable reviewer cursor/state

node_observations:.agents/skills/lora-chatter-hardware/
    active reusable physical-executor instructions

lora-sack-protocol source/docs
    firmware/protocol implementation authority

AGENT_API.md on dev
    generic SerialTerminal API authority
```
