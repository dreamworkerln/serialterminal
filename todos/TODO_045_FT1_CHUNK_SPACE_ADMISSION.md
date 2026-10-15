# FT1: допустимость META в uint32 chunk space

TODO-ID: TODO_045
Status: IMPLEMENTED / LOCAL VALIDATION PASS / CI AND RE-REVIEW OPEN
Priority: HIGH
Created: 2026-10-14
Implementation: INTEGER CHUNK VALIDATION AND REGRESSIONS IMPLEMENTED
Validation: HOST SOFTWARE 748 PASS / CI AND RE-REVIEW OPEN
Source review: [REVIEW_001/F016](../reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md#f016--high-receiver-admits-meta-identities-that-cannot-be-represented-by-endresume-uint32-chunk-space)
Reviewed commit: [db740af94c700c7c4e6d96abef7e809dadfcaf1c](https://github.com/dreamworkerln/serialterminal/commit/db740af94c700c7c4e6d96abef7e809dadfcaf1c)
Regression attribution: pre-existing at `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd` по addendum ревью.

## Purpose

Не принимать identity передачи, которую невозможно завершить через END/RESUME
из-за несовместимости META-derived chunk count с uint32.

## Current behavior

META допускает uint64 `wire_size` и `chunk_size=1`, а DATA index, END `chunk_count`
и RESUME `next_chunk` имеют uint32 layout. В ревью META с
`wire_size=2^32+1`, `chunk_size=1` создал receiving record с 4,294,967,297 chunks;
протокольно допустимый END для такого count закодировать невозможно.

## Target behavior и Invariants

- Derived chunk count свыше `0xffffffff` отклоняется до allocation/claim/runtime
  publication receiver state; тот же предел проверяется при sender preparation.
- Cross-message arithmetic согласовано, включая последний DATA index, END,
  RESUME и missing-range representation.
- Отклонение не портит существующие transfers, lease, partial или journal.
- Не менять wire layouts и не вводить произвольный меньший лимит файлов.

## Scope и Design

Protocol validation, sender preparation и receiver admission. Требуемый предел
следует из текущего wire format, новый encoding не выбран и не требуется.
Историческое S2 в [TODO_043](TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md)
частично подтверждено этим finding; bounded memory/queue и LIST validation
остаются в TODO_043 и не закрываются одним representability check.

## Implementation

- [x] Проверить согласованную representability до изменения RX/TX state.
- [x] Закрепить error semantics, не обходя existing normalized API errors.
- [x] Согласовать FT1_RESUME.md, FILE_TRANSFER.md, AGENT_API.md и agent skill
  с admission contract.

## Validation / acceptance

- [x] Boundary cases `0xffffffff` и `0x100000000` derived chunks, а также больше:
  первый representable, остальные отклонены без resource admission.
- [x] Проверить rounding wire_size/chunk_size, zero-length и последний index.
- [x] Sender preparation и receiver META дают согласованный результат.
- [x] Большие synthetic identities тестируются без многогигабайтных allocations;
  отсутствие state/lease/files после rejected META проверяется явно.
- [ ] Existing ordinary/recursive/resume paths, relevant tests, full pytest,
  compileall, diff --check и numbered re-review на exact implementation SHA.

## История: evidence при создании задачи

Evidence/repro и ограничения сохранены в исходном finding ревью. При оформлении
TODO repro не запускался повторно, fixes и source/tests не изменялись.
Status: OPEN; implementation, regression validation и re-review остаются открыты.
Это task record; hardware, firmware changes, commit/push не выполнялись.

## Implementation checkpoint — 2026-10-15

Base4d732aa. One protocol helper computes exact integer ceiling division and
validates uint64 wire_size/uint16 chunk_size/uint32 derived chunk_count. META
encoding, RX admission, sender prepared-stream metadata and candidate validation
use the same arithmetic. Receiver rejects invalid count before recursive frame,
record, claim or filesystem allocation, while preserving an existing ROOT. The
decoder still exposes a structurally valid received META to admission, allowing
an explicit normalized invalid_metadata RESULT rather than silent packet loss.

Permanent synthetic tests cover zero, rounding, uint32 max and above for chunks
1/227/65535, uint64 max, largest valid RX without sparse allocation, last DATA
index and END/RESUME max cursor round trips. Raw invalid META bypasses the local
encoder to verify receiver rejection. Synthetic oversized prepared sender stream
fails before journal/META and removes its temporary wire while retaining source.
Targeted protocol/recursive/journal/boundary suite59 PASS/9.18s. Final full suite
in progress; independent re-review, CI and hardware remain OPEN. No firmware,
push or hardware run.

Final isolated-cache full suite748 PASS/85.11s; compileall and diff-check PASS.
Exact implementation trees: src `36d98807a5b63c5ab0df8890f47431359e888c42`; tests `61f5a3c0e4a7c9ec4800d2dd0bbe6a10d121ee95`.
