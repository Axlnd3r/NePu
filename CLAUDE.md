# NEAR Capture Ledger — instructions for Claude

## What this project is
A reproducible investment-thesis tool for NEAR, built for NEAR HACKATHON 2026, track "Investment Thesis" (judged on evidence, not conviction). Deadline: 2026-11-14 23:59 UTC.

Core question (falsifiable): can NEAR Intents value capture (buybacks + gas burn) outgrow token issuance, and how far is the network from that point?

Headline metric: coverage ratio CR = (buyback value + burn value) / gross issuance value, per day / 30d / 90d, in USD and in NEAR units.
Break-even daily Intents volume: V* = (i * S * P - Burn_usd) / tau_eff
  i = annual inflation / 365, S = total supply, P = NEAR price, tau_eff = protocol revenue / Intents volume.

Modules: (1) Capture Ledger core, (2) Distribution Map (fees by channel, HHI, near.com share), (3) Valuation Lab (reverse valuation + bootstrap Monte Carlo), (4) Developer indicator (new contracts that stay used), (5) proof-of-analysis (manifest hash committed to NEAR mainnet).

## Hard rules (never break)
1. Never invent numbers. Every number shown in README.md, THESIS.md or site/ must come from a file in data/ that is listed in a manifest. If a metric cannot be computed, write "unavailable" plus the reason in THESIS.md.
2. Every BigQuery query: filter on `block_date`, run with `--dry_run` first, then with `--maximum_bytes_billed=$BQ_MAX_BYTES`. Select only needed columns. Never `SELECT *` on large tables.
3. Never edit data/snapshot/ without regenerating data/snapshot/manifest.json (SHA-256 per file, query text, block_date range, pulled_at UTC).
4. Never commit secrets. Secrets live in .env (gitignored). .env.example lists names only.
5. Correlation is not causation. Lag tests report out-of-sample results, including null results.
6. Buybacks are not burns. Keep "total supply" and "float" views separate.
7. No new smart contracts except contracts/proof-of-analysis. No price predictions or price targets.
8. Repo text (code, comments, README, THESIS.md) is in English.

## Commands
- `make setup`   install Python (uv) and Node deps
- `make extract` pull fresh data (needs .env credentials) into data/live/
- `make build`   rebuild every metric from data/snapshot/ (offline, no credentials) -> site/public/data/*.json
- `make build-live` same, from data/live/
- `make verify`  pytest: reconciliation, invariants, manifest hashes
- `make site`    build static dashboard (Next.js export) into site/out/
- `make proof`   hash the manifest and commit it to NEAR mainnet (needs PROOF_ACCOUNT_ID)
- `make all`     setup + build + verify + site (must work from a clean clone, offline)

## Layout
- sql/                  one parameterised .sql per metric
- src/capture/extract/  bigquery.py, rpc.py, defillama.py, coingecko.py, intents_explorer.py
- src/capture/models/   coverage.py, breakeven.py, distribution.py, valuation.py, developer.py
- src/capture/manifest.py, build.py, cli.py
- tests/                test_reconciliation.py, test_invariants.py, test_manifest.py
- data/snapshot/        committed daily aggregates (parquet) + manifest.json
- data/live/            gitignored fresh pulls
- site/                 Next.js + Recharts, static export, reads site/public/data/*.json
- contracts/proof-of-analysis/  minimal Rust contract: commit(run_id, manifest_sha256)
- docs/METHODOLOGY.md   formulas, sources, limitations

## Conventions
- Python 3.12, uv, ruff, type hints, pure functions in models/ (input DataFrames -> output DataFrames).
- DuckDB for local SQL over parquet. Fixed random seed for Monte Carlo (seed in config).
- Every chart in site/ shows: the chart, the SQL/query that produced it, one plain sentence, and provenance (source, block_date range, pulled_at).
- Commit messages: `F<n>: <what>`. Do not rewrite history after tag `pre-hackathon`.

## Session protocol
- Start: read this file, PROGRESS.md and DATA_AUDIT.md. Propose a plan before editing.
- End: run `make verify`, update PROGRESS.md (done, numbers found, decisions, blockers, next step), commit.
- If a data assumption fails, stop and record it in DATA_AUDIT.md with the fallback chosen. Do not silently switch sources.

## Known data facts and open questions (keep updated in DATA_AUDIT.md)
- Dataset: bigquery-public-data.crypto_near_mainnet_us (tables: blocks, chunks, transactions, execution_outcomes, receipt_details, receipt_origin_transaction, receipt_actions, receipts view, account_changes). Partition column: block_date.
- NEAR Lake (the dataset's ingestion source) was deprecated 2026-03-24 per docs: freshness must be checked.
- Revenue wallets per revenue.near.org: fefundsadmin, 1csfundsadmin (full account IDs to confirm). Intents balances may live inside the intents verifier contract as NEP-245 balances: confirm how fees move.
- Explorer API: https://explorer.near-intents.org/api/v0, JWT required, 1 request / 5 s, 1Click transactions only.
- DefiLlama: https://api.llama.fi/protocol/near-intents (plus fees/revenue summary endpoints, confirm).
