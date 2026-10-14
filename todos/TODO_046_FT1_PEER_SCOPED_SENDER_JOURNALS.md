# FT1: изоляция sender journals по peer identity

TODO-ID: TODO_046
Status: OPEN
Priority: BLOCKER
Created: 2026-10-14
Implementation: NOT STARTED
Validation: REVIEW FINDING RECORDED / FIX VALIDATION OPEN
Source review: [REVIEW_001/F017](../reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md#f017--blocker-persistent-sender-journals-are-shared-across-sessions-without-peer-identity)
Reviewed commit: [db740af94c700c7c4e6d96abef7e809dadfcaf1c](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c)
Regression attribution: pre-existing at `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd` по addendum ревью.

## Purpose

Исключить выбор, завершение и удаление durable outgoing work другого peer/session
при отправке одного локального source через несколько независимых sessions.

## Current behavior

Agent sessions по умолчанию разделяют `.serialterminal-state`. Outgoing journals
и candidate selection не содержат peer identity. В repro два managers A/B с общим
store выбрали один transfer_id для того же source; completion B удалил journal A,
хотя A оставался non-completed. Теряется независимость sessions и resumability.

## Target behavior и Invariants

- Durable outgoing identity привязана к стабильной peer/device identity и
  проверяется до candidate selection, update и deletion.
- A/B для одного source не выбирают и не удаляют journals друг друга.
- Resume одного peer сохраняет identity там, где он семантически допустим,
  в том числе после reconnect/process restart.
- Generic discovery/session/transport остаются controller-agnostic; не вводить
  конкретные controller aliases, commands или profile-name branches.

## Scope и Design

Outgoing journal schema/namespace, передача identity в FT1 ownership boundary,
validation, completion/cancel cleanup и compatibility старого durable state.
Связано с [TODO_037](TODO_037_FT1_PERSISTENT_SENDER_AND_RESUME_HANDSHAKE.md),
[TODO_043](TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md) и
[TODO_044](TODO_044_FT1_LIVE_DURABLE_RETENTION.md).

Перед реализацией выбрать стабильный peer key и правила USB/BLE identity,
reconnect/process restart, старых journals без peer key и concurrent owners одного
peer. Ревью не выбрало key/migration policy; ephemeral session_id сам по себе
не доказывает допустимость persistent resume. Проверить dependency direction в
ARCHITECTURE.md. Не добавлять firmware/API flags для обхода profile segregation.

## Implementation

- [ ] Закрепить peer identity и backward-state policy без молчаливой атрибуции
  старого journal произвольному peer.
- [ ] Применить binding/namespace во всех outgoing candidate/write/delete paths.
- [ ] Согласовать cleanup ownership с TODO_043/F012 и TODO_044.
- [ ] Согласовать FT1_RESUME.md, FILE_TRANSFER.md, AGENT_API.md и agent skill
  с реализованными resume/identity semantics.

## Validation / acceptance

- [ ] Два managers A/B с общим store и одним source получают изолированный
  durable work; completion, failure, cancel и close B не затрагивают journal A.
- [ ] Concurrent sessions/processes сохраняют это свойство.
- [ ] Reconnect и process restart того же peer сохраняют корректный same-ID resume;
  другой peer и mismatched peer key не получают этот candidate.
- [ ] Проверить выбранную USB/BLE identity policy и старые journals без key.
- [ ] Existing lost-RESULT, source validation и integrity quarantine semantics
  сохраняются; relevant tests, full pytest, compileall, diff --check и independent
  numbered re-review на exact implementation SHA.

## Evidence и Result

Evidence/repro и ограничения сохранены в исходном finding ревью. При оформлении
TODO repro не запускался повторно, fixes и source/tests не изменялись.
Status: OPEN; implementation, regression validation и re-review остаются открыты.
Это task record; hardware, firmware changes, commit/push не выполнялись.
