# Платформенный расчёт ширины TUI

TODO-ID: TODO_061
Status: OPEN
Severity: P2
Created: 2026-10-21
Source review: [REVIEW_004/F007](../reviews/REVIEW_004_IMPORTED_FIRMWARE_CLIENT_2026-10-21.md)
Finding checkpoint: `a34631e861d1477c48f5ad2bc15dad15564f73f6`.

## Current behavior и purpose

`src/serialterminal/tui_text.py` при импорте безусловно вызывает CDLL(None).wcwidth; Windows CPython 3.12 падает до запуска TUI.

## Target behavior и invariants

Импорт и штатный запуск Windows TUI работают; Linux и ASCII/combining/wide/Unicode width сохраняют semantics соответствующего terminal backend.

Отдельно от fcntl TODO_049; исправление TUI не означает готовность Windows FT1.

## Scope и constraints

Только SerialTerminal source/runtime; firmware read-only. Profile-specific semantics остаются в profile.
Решение ещё не реализовано. Разбор TODO не запускает fixes, commit/push, flash
или hardware runs. RF protocol/SACK не расширяется.

## Implementation

- [ ] Выбрать платформенно корректный width backend с сохранением Linux/ncurses поведения.
- [ ] Проверить fit/wrap/ellipsis и документировать поддержку; размеры интерфейса не менять ради обхода ошибки.

## Validation / acceptance

- [ ] Реальный Windows import/startup в windows-curses окружении, включая CPython 3.12. Platform mocks не заменяют этот gate.
- [ ] Linux width/layout regressions: combining, wide/CJK, emoji/ZWJ и control escapes.
- [ ] Единый полный local/server CI и parity guards; targeted runs обозначать subset. Python tests вне sandbox по AGENTS.md; проверить README/ARCHITECTURE/AGENT_API и agent skill по применимости.
- [ ] Независимое повторное ревью exact fix checkpoint; implementation/software и необходимые platform/hardware gates фиксируются раздельно.

## Evidence и result

[Переданный repro/evidence](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/windows-tui.log). Результаты получены на другом Windows-хосте; локально repro не перезапускался.
SHA-256 сверка подтвердила совпадение inventory с working tree и указанным commit.
Implementation: NOT STARTED. Acceptance validation: OPEN.
