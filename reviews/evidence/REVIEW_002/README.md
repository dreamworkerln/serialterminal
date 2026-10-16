# REVIEW_002 evidence index

Target: `6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`
Base: `db740af94c700c7c4e6d96abef7e809dadfcaf1c`

- `target.txt` — repository/branch/target/base capture.
- `diff-gate.txt` — exact `BASE..TARGET` diff stat/numstat used by the source-review gate.
- `compileall.txt` — Python compile result.
- `full-pytest-blocked.txt` — full pytest collection blocked by missing `pyserial` (`serial`).
- `previous-findings-recheck.txt` — selected acceptance/repro nodes for REVIEW_001/F001–F018: 47 PASS.
- `recursive-machine-targeted.txt` — recursive/machine/recovery targeted suite: 92 PASS.
- `settings-profile-stub.txt` — settings/profile wiring with a minimal import-only fake `serial`; not serial-I/O evidence.
- `repro_non_posix_fcntl.py/.out` — deterministic REVIEW_002/F001 repro.
- `repro_terminal_release_race.py/.out` — deterministic REVIEW_002/F002 target repro.
- `repro_terminal_release_race_base.py/.out` — same synchronized window at REVIEW_001 target for attribution.
- `ft1-broad-targeted.txt` — incomplete broad run stopped before completion; **not** a PASS result and retained only as provenance for the interrupted attempt.
