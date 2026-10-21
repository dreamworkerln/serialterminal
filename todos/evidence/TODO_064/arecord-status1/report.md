# F12 stop correction

Installed arecord 1.2.6 returns status 1 after requested SIGINT even on normal
quiet capture completion. Initial TODO_064 classification rejected this result.
The operator failure and virtual ALSA null reproduction are recorded in diagnosis.json
and null-probe-before.json. The correction accepts status 1 only for requested stop,
no forced fallback and empty stderr; error/forced/unrequested cases remain rejected.

Regression before: 1 FAIL / 9 PASS. After: voice subset 39 PASS; full pytest 1419 PASS
with 7 existing DeprecationWarning; compile/Ruff PASS; Lizard advisory WARNING.
No real microphone, speakers or nodes opened. Both operator ST processes need restart;
real F12 stop/send retest remains OPEN. No Git commit/push.

The original lifecycle evidence remains unchanged in the parent evidence directory.
Current-source-fix.patch applies to BASE 8a9d91d and includes the new test file;
status1-correction.patch applies to the saved pre-correction working source.
