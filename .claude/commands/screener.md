---
description: Simulate the hackathon AI screener on a clean clone of the repo
---
Act as the NEAR HACKATHON AI screener (Claude Code / Codex). Your job is a reproducibility check, feature verification, a structured report and a preliminary score. You have NO credentials: no .env, no GCP, no JWT.

1. Clone the public repo URL from README (or `git clone .` into a fresh temp dir if not pushed yet). Do not reuse any local caches or node_modules.
2. Follow README.md literally, step by step, "do X -> see Y". Record every step that fails or is ambiguous.
3. Run `make all`. It must succeed offline from data/snapshot/.
4. For each feature claimed in README, check it exists and behaves as described (open the built site/out/index.html data files, run the CLI commands shown).
5. Check the track requirements: SQL queries filtered on block_date, Intents Explorer pull (with JWT documented in .env.example), one command rebuilding every chart, static dashboard showing chart + query + one sentence, THESIS.md with claim / supporting evidence / contrary evidence / what would change my mind.
6. Check submission rules: LICENSE present, AI-generated code and libraries disclosed, pre-hackathon / hackathon-submission tags or branch documented.

Output: a report with sections Reproducibility, Feature verification, Track requirements, Rules, Issues (severity-ranked), and a preliminary score out of 10 with one-line justification. Do not edit the repo.
