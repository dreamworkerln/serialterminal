# Node Skill Learning Policy

## Purpose

Этот документ предназначен для reviewer-а, который периодически обрабатывает накопленные hardware observations из orphan branch `node_observations` и при необходимости обновляет `.agents/skills/node-agent/SKILL.md` в `dev`.

Local executor не должен выполнять этот процесс. Его отдельный контракт: [NODE_OBSERVATION_RECORDING_POLICY.md](NODE_OBSERVATION_RECORDING_POLICY.md).

Reviewer выполняет дорогую часть knowledge processing:

```text
raw observations
→ compare across runs
→ inspect authoritative source when needed
→ separate object state from class behavior
→ deduplicate / resolve conflicts
→ generalize reusable rules
→ update lora-chatter-nodes skill
→ advance REVIEW_STATE.md
```

---

## 1. Authority and branches

```text
dev
    SerialTerminal code/docs
    AGENT_API.md
    .agents/skills/serialterminal-agent/SKILL.md
    .agents/skills/node-agent/SKILL.md
    reviewer policies

node_observations
    orphan evidence branch
    observations/*.md
    REVIEW_STATE.md

lora-sack-protocol
    firmware/protocol source authority
```

`node_observations` не является source branch и не merge-ится в `dev`.

Observation records являются historical evidence. Reviewer не переписывает старые records, чтобы они соответствовали текущему пониманию. Correction/refinement делается reviewer output/skill update или новым observation record.

Перед любой записью refetch actual target branch HEAD и relevant files.

---

## 2. Reviewer bootstrap

Перед review:

1. refetch `serialterminal/dev` HEAD;
2. refetch `serialterminal/node_observations` HEAD;
3. прочитать root `AGENTS.md`;
4. прочитать этот policy;
5. прочитать текущий `.agents/skills/node-agent/SKILL.md`;
6. прочитать `REVIEW_STATE.md` из `node_observations`, если он существует;
7. определить exact set новых observation records;
8. читать `AGENT_API.md`/generic SerialTerminal skill только если observation затрагивает generic API/transport semantics;
9. inspect `lora-sack-protocol` source/docs, когда для promotion/conflict resolution требуется firmware authority.

Не начинай с memory или guessed last observation.

---

## 3. REVIEW_STATE.md

`REVIEW_STATE.md` живёт в корне orphan branch `node_observations` и является единственным mutable reviewer state в этой branch.

Local executor его не меняет.

Рекомендуемый формат:

```markdown
# Node observation review state

last_reviewed_observation: observations/OBS_20260903T203005Z_echo-timeout.md
last_reviewed_observation_commit: <node_observations commit SHA containing/ending processed range>
reviewed_against_dev: <dev SHA read during review>
reviewed_by_commit: <dev commit that applied skill/docs changes, or none>
reviewed_at: YYYY-MM-DDTHH:MM:SSZ

unresolved:
  - observation: observations/OBS_...
    reason: <short reason>
```

Semantics:

- `last_reviewed_observation` — последний observation file в полностью обработанном диапазоне;
- `last_reviewed_observation_commit` — commit observation branch, до которого review выполнен;
- `reviewed_against_dev` — exact `dev` checkpoint, с которым сравнивались observations/skill;
- `reviewed_by_commit` — exact `dev` commit, созданный review-ом для обновления skill/docs; если изменения в `dev` не требовались, `none`;
- `unresolved` — уже рассмотренные, но не закрытые anomaly/conflict candidates, которые надо сохранить видимыми для будущего evidence.

`REVIEW_STATE.md` обновляется только после того, как reviewer outcome в `dev` завершён и проверен.

---

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
4. сравнить observation с текущим node skill;
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

Только `CLASS_CANDIDATE` после promotion gate напрямую изменяет node skill.

`ANOMALY_CONFLICT` сначала требует resolution; он не является автоматическим новым contract.

---

## 7. Class-level abstraction rule

`.agents/skills/node-agent/SKILL.md` описывает класс LoRa-Chatter node, а не лабораторные экземпляры.

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

Новое/изменённое правило попадает в `node-agent/SKILL.md` только если:

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

## 12. Обновление lora-chatter-nodes skill

Target:

```text
serialterminal/dev:.agents/skills/node-agent/SKILL.md
```

Перед write:

1. refetch actual `dev` HEAD;
2. refetch current skill blob;
3. re-check that observations still относятся к актуальному behavior/source;
4. внести минимальные class-level changes;
5. не переносить raw logs/IDs/measurements в skill;
6. review diff for accidental weakening/duplication;
7. commit normal docs change to `dev`;
8. read back commit and updated skill.

Если review затронул generic SerialTerminal API, следовать `AGENTS.md`: отдельно проверить `AGENT_API.md` и generic SerialTerminal skill. Не переписывать generic contract из Chatter-specific observation без source evidence.

---

## 13. Порядок обновления REVIEW_STATE.md

После processing диапазона:

1. сначала закончить все необходимые изменения в `dev`;
2. получить exact resulting `dev` commit SHA;
3. read back updated skill/docs;
4. определить последний полностью обработанный observation и observation-branch commit boundary;
5. refetch actual `node_observations` HEAD и current `REVIEW_STATE.md`;
6. update `REVIEW_STATE.md`;
7. сохранить unresolved entries;
8. commit state update в `node_observations`;
9. read back state.

Нельзя advance `REVIEW_STATE.md`, если reviewer ещё не закончил соответствующий dev outcome.

Если `dev` change не требовался:

```text
reviewed_by_commit: none
reviewed_against_dev: <exact dev SHA used for review>
```

Это означает: observations обработаны, но skill/docs уже были корректны или promotion не прошла.

---

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
skill changes: <summary or none>
unresolved: <count/list>
dev commit: <SHA or none>
REVIEW_STATE commit: <SHA>
next observation boundary: <last_reviewed_observation>
```

---

## Authority summary

```text
NODE_OBSERVATION_RECORDING_POLICY.md
    local executor -> raw evidence

node_observations/observations/*.md
    immutable run-specific observations

NODE_SKILL_LEARNING_POLICY.md
    reviewer processing/promotion rules

node_observations:REVIEW_STATE.md
    mutable review cursor/state

.agents/skills/node-agent/SKILL.md
    current class-level LoRa-Chatter instructions

lora-sack-protocol source/docs
    firmware/protocol implementation authority

AGENT_API.md
    generic SerialTerminal API authority
```
