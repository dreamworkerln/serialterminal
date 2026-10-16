# TUI transfer window lifecycle review

REVIEW-ID: REVIEW_003
Разобрано в TODO: TODO_053
Status: COMPLETE
Verdict: RED
Date UTC: 2026-10-16
Reviewer: Codex, source investigation before operator-authorized fixes

## Reviewed state

Repository: https://github.com/dreamworkerln/serialterminal
Branch: `dev_tui_exp_recursive_missing`
Reviewed commit: [f70f1a8efff02f4b29e77782f50c18941596f890](https://github.com/dreamworkerln/serialterminal/commit/f70f1a8efff02f4b29e77782f50c18941596f890)
Base: N/A — snapshot review; attribution to earlier accepted base not claimed.
Checkout at initial inspection: clean.
Task: operator report of phantom file window on F7 during node reboot; investigate
display/background/close transitions and create TODO. Later operator authorized
implementation and tests; fixes are tracked in TODO_053, not retroactively accepted here.
Previous related numbered review: none within this narrow TUI scope.

## Scope

`tui_file_transfer.py`, `tui_core.py`, public `tui.py` wrapper, ROOT snapshot selection,
FT1 cancel/timeout/recovery/same-ID readmission and existing TUI/PTY coverage.
No firmware inspection, hardware action, full protocol audit or regression-attribution claim.

## Findings

### F001 — Medium: старое подтверждение отменяет новую same-ID попытку

Where: `tui_file_transfer.py:59–119`; `tui_core.py:902–918`;
`file_transfer/manager.py:353–377`; `core.py:653–668,1997–2018`.
Verified: confirmation хранит только transfer_id; после failed RX и matching META
runtime record снова становится receiving с тем же ID. Старый Enter признаётся
активным подтверждением и устанавливает cancel_event новой попытки.
Impact: непреднамеренная отмена resumed RX; тот же ID также наследует закрытое UI.
Evidence: composed repro с реальным manager failure/settlement/restore, затем
production `_handle_key`. Existing tests проверяют terminal или другой ID,
но не завершённую и заново принятую попытку того же ID.
Required acceptance: отдельная runtime attempt identity, проверенная атомарно
при cancel admission; старая RX queue не отменяет следующую попытку.
Follow-up: [TODO_053](../todos/TODO_053_TUI_FILE_TRANSFER_WINDOW_LIFECYCLE.md).

### F002 — Medium: history/state используется как доказательство активной передачи

Where: `tui_file_transfer.py:89,99–110`; `tui_core.py:453–458`;
`file_transfer/recursive.py:381–390`; `resumable.py:658–672,1047–1057`.
Verified: проверка `state not in completed/failed/cancelled` допускает suspended
history. Closed real manager с suspended RX и `busy=False` проходит F7 и UI
action-admission checks, если snapshot продолжает передаваться в frontend.
Accepted asynchronous cancel до terminal также скрывает overlay, но сразу
возвращает прежний DATA header, а F7 снова показывает его.
Limit: normal TUI close отделяет manager от frontend; closed-manager repro —
проверка отсутствующего liveness guard, а не доказанный нормальный reboot path.
В clean idle manager F7 окно не создаёт. Причина конкретного физического эпизода
оператора не установлена; session logs не фиксируют F7/mode transitions.
Required acceptance: ROOT runtime ownership + positive phase eligibility,
отдельное pending-cancel представление, запрет превращать history в active UI.
Follow-up: TODO_053.

### F003 — Medium: recovery/resume не является определённым frontend transition

Where: `tui_file_transfer.py:59–79`; `file_transfer/resumable.py:141–184,363–376`.
Verified: видимость меняется по новому transfer_id, success и одному cancel-failure
пути. Same-ID resume после закрытого failed не открывает окно. Краткое recovery
может целиком пройти между redraw; текущая UI FSM его не замечает.
`sync(None)` при открытом confirmation скрывает отрисовку, но оставляет невидимый
перехват обычных клавиш. Это дополнительно проверенная boundary case;
достижимость при обычных клавишах session replacement отдельно не доказана.
Required acceptance: однозначные recovery/readmission transitions, сохраняемый
resume marker и видимый stale-input guard даже при исчезнувшем snapshot.
Follow-up: TODO_053.

### F004 — Low: свёрнутая форма повторяет подробное окно

Where: `tui_core.py:522–554,745–754,841–850`.
Verified: две строки, графическая полоса, chunks/bytes/rate; header и overlay
читают manager независимо. Два снимка одного redraw могут описывать разные
моменты lifecycle. Это структурный риск consistency, не воспроизведённый
физический экран с двумя окнами одновременно.
Required acceptance: одна краткая фоновая строка, одно чтение ROOT на кадр.
Follow-up: TODO_053.

## Validation and evidence

| Check | Exact checkpoint | Result | Evidence / limits |
| --- | --- | --- | --- |
| Source/transition inspection | f70f1a8efff02f4b29e77782f50c18941596f890 | findings confirmed within scope | Snapshot review |
| Six offline repro/control cases + original window/PTY tests | same source SHA | 131 PASS / 3.19 s | Repros assert observed old behavior, not corrected acceptance |
| New acceptance regressions against archived base source/tests | same source SHA | 12 FAIL / 7 PASS | [base-regressions.txt](evidence/REVIEW_003/base-regressions.txt); failures include missing runtime guard contract |
| Existing local session logs | runtime SHA UNKNOWN | inspected, no causal verdict | Cancel then reconnect and READY observed; no F7/visibility evidence |
| Physical reboot/F7 reproduction | same source SHA | NOT RUN | Devices were not opened |

[Evidence instructions](evidence/REVIEW_003/README.md).

## Assessment / result

COMPLETE / RED for the original TUI lifecycle snapshot. User-selected terminal
and recovery semantics are recorded in TODO_053. Baseline GREEN tests do not cover
the same-ID confirmation or liveness boundaries. This report preserves the original
findings; implementation and current validation belong to TODO_053. No claim of
physical repair, CI success or independent post-fix acceptance is made here.
