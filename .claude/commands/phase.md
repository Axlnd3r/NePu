---
description: Start a runbook phase (F0-F8) with a plan, using the project memory files
argument-hint: F<number>
---
We are starting phase $ARGUMENTS of the NEAR Capture Ledger runbook.

1. Read CLAUDE.md, PROGRESS.md and DATA_AUDIT.md (if present). Summarise in 5 lines: what is done, open blockers, and decisions that affect $ARGUMENTS.
2. Check that the Definition of Done of the previous phase is met (run `make verify` if tests exist). If it is not met, stop and tell me what is missing.
3. Wait for me to paste the phase prompt. Then produce a step-by-step plan (files to create/change, commands to run, how each DoD item will be checked) before editing anything.
4. While working: follow the hard rules in CLAUDE.md. Record every external fact you rely on (endpoint, field name, account id) in DATA_AUDIT.md with how you verified it.
5. At the end: run `make verify`, update PROGRESS.md (done / numbers / decisions / blockers / next), and commit with message "$ARGUMENTS: <summary>".
