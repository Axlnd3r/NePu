---
description: Audit that every number in README, THESIS.md and the site traces back to data with a manifest
---
Audit every numeric claim in README.md, THESIS.md, docs/METHODOLOGY.md and site/public/data/*.json.

For each number:
- find the file in data/ and the column/row it comes from,
- confirm that file is listed in the relevant manifest.json with a matching SHA-256,
- recompute it from that file (DuckDB or pandas) and compare.

Output a table: location | value shown | recomputed value | source file | status (OK / MISMATCH / UNTRACEABLE).
Do not fix anything yet. List the fixes you propose, then wait for my approval.
