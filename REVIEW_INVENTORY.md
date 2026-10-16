# SerialTerminal review inventory

Правила и шаблон: [REVIEW_MANAGEMENT_POLICY.md](REVIEW_MANAGEMENT_POLICY.md).
Методика проверки: [REVIEWER.md](REVIEWER.md).
Задачи по исправлениям: [TODO_INVENTORY.md](TODO_INVENTORY.md).

Next new review ID: `REVIEW_004`.

## Review registry

| REVIEW-ID / report | Date UTC | Scope | Reviewed commit | Base | Status | Verdict | TODO / previous / follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [REVIEW_003](reviews/REVIEW_003_TUI_TRANSFER_WINDOW_LIFECYCLE.md) | 2026-10-16 | TUI file-window lifecycle, F7/history eligibility, same-ID confirmation and recovery; original snapshot before fixes | [`f70f1a8efff02f4b29e77782f50c18941596f890`](https://github.com/dreamworkerln/serialterminal/commit/f70f1a8efff02f4b29e77782f50c18941596f890) | N/A — snapshot | COMPLETE | RED | F001–F004 → TODO_053; initial investigation, fixes/current validation tracked in TODO_053; no physical causal verdict |
| [REVIEW_001](reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md) | 2026-10-13 | Current `dev_tui_exp_recursive_missing` software snapshot; FT1 recursive/core/recovery/persistence + adjacent agent/session lifecycle; 2026-10-14 regression-attribution addendum | [`db740af94c700c7c4e6d96abef7e809dadfcaf1c`](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c) | `8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79` + snapshot; regression baseline `fd94bde` | COMPLETE | RED | `TODO_043` (F001–F014), `TODO_044` (F015), `TODO_045` (F016), `TODO_046` (F017), `TODO_047` (F018); разобрано в TODO 2026-10-14; previous numbered review: none |
| [REVIEW_002](reviews/REVIEW_002_DEV_TUI_EXP_RECURSIVE_MISSING_POST_FIX_IAR.md) | 2026-10-15 | Post-fix IAR of current `dev_tui_exp_recursive_missing`; REVIEW_001 recheck + current FT1 recovery/persistence/recursive/settings/timing/agent lifecycle | [`6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`](https://github.com/dreamworkerln/serialterminal/commit/6fdeb00c220b3e27219fb6b5bb34f078f3bb717a) | `db740af94c700c7c4e6d96abef7e809dadfcaf1c` | COMPLETE | RED | previous `REVIEW_001`; REVIEW_001/F001–F018 FIXED; F001 → `TODO_049`, F002 → `TODO_050` (related to `TODO_041`); разобрано в TODO 2026-10-15; follow-up re-review required |

Исторические результаты ревью, сохранённые внутри TODO, остаются историческим evidence и не становятся numbered review автоматически.
