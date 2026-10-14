# SerialTerminal review inventory

Правила и шаблон: [REVIEW_MANAGEMENT_POLICY.md](REVIEW_MANAGEMENT_POLICY.md).
Методика проверки: [REVIEWER.md](REVIEWER.md).
Задачи по исправлениям: [TODO_INVENTORY.md](TODO_INVENTORY.md).

Next new review ID: `REVIEW_002`.

## Review registry

| REVIEW-ID / report | Date UTC | Scope | Reviewed commit | Base | Status | Verdict | TODO / previous / follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [REVIEW_001](reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md) | 2026-10-13 | Current `dev_tui_exp_recursive_missing` software snapshot; FT1 recursive/core/recovery/persistence + adjacent agent/session lifecycle; 2026-10-14 regression-attribution addendum | [`db740af94c700c7c4e6d96abef7e809dadfcaf1c`](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c) | `8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79` + snapshot; regression baseline `fd94bde` | COMPLETE | RED | `TODO_043` (F001–F014), `TODO_044` (F015), `TODO_045` (F016), `TODO_046` (F017), `TODO_047` (F018); разобрано в TODO 2026-10-14; previous numbered review: none |

Исторические результаты ревью, сохранённые внутри TODO, остаются историческим evidence и не становятся numbered review автоматически.
