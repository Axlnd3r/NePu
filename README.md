# NEAR Capture Ledger

## What it is
A reproducible investment-thesis tool for NEAR, built for NEAR HACKATHON 2026 (track: Investment Thesis).
One command rebuilds every metric and chart from committed, hashed data. Every number traces back to a
file in `data/` listed in a manifest with its SHA-256, source query and block_date range.

## The question
Can NEAR Intents value capture (buybacks + gas burn) outgrow token issuance, and how far is the network
from that point?

- Coverage ratio: `CR = (buyback value + burn value) / gross issuance value`, per day / 30d / 90d, in USD and NEAR.
- Break-even daily Intents volume: `V* = (i * S * P - Burn_usd) / tau_eff`.

Results: TODO (F3+). See THESIS.md once written.

## Quickstart (offline)
No credentials needed. Builds from `data/snapshot/`.

Requirements: [uv](https://docs.astral.sh/uv/), Node 24, GNU make, git.

```sh
git clone https://github.com/Axlnd3r/NePu---NEAR-Pulse-.git && cd NePu---NEAR-Pulse-
make all
```

`make all` runs `setup` (installs Python 3.12 + Node deps; needs network for packages only), `build`
(writes `site/public/data/*.json`), `verify` (ruff, manifest hashes, pytest) and `site`
(static dashboard in `site/out/`).

| Command | What it does |
|---|---|
| `make setup` | install Python (uv) and Node deps |
| `make build` | rebuild every metric from `data/snapshot/` |
| `make verify` | lint, recompute manifest hashes, run tests |
| `make site` | build static dashboard into `site/out/` |
| `make all` | setup + build + verify + site |

## Live mode
Needs credentials, so it is optional; the offline quickstart above never uses it.

1. Copy `.env.example` to `.env` and fill in `GOOGLE_CLOUD_PROJECT` (and `BQ_MAX_BYTES`). Log in once
   with `gcloud auth application-default login`. `INTENTS_EXPLORER_JWT` and `COINGECKO_API_KEY` are
   optional; without the JWT the Explorer table is skipped.
2. `uv run capture extract --dry-run` estimates BigQuery bytes without pulling anything.
3. `make extract` pulls into `data/live/` (gitignored). It is incremental by date: a second run
   queries nothing that is already there. BigQuery bills the queries to your own project's quota.
4. `make build-live` rebuilds the metrics from `data/live/`.
5. `uv run capture snapshot --freeze <YYYY-MM-DD>` copies `data/live/` into `data/snapshot/` (rows up
   to that complete UTC day) and rewrites its manifest.

`make proof` commits the manifest hash to NEAR mainnet (F7).

## Methodology
See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Data sources
TODO (F1). Planned: BigQuery `bigquery-public-data.crypto_near_mainnet_us`, NEAR RPC, NEAR Intents
Explorer API, DefiLlama, CoinGecko. Verification status of each source is tracked in
[DATA_AUDIT.md](DATA_AUDIT.md).

## Limitations
TODO.

## AI & libraries disclosure
- Code, tests and documentation in this repository were written with AI assistance (Claude Code,
  Anthropic) under human direction and review.
- Python: duckdb, pandas, pyarrow, google-cloud-bigquery, httpx, python-dotenv, numpy, scipy, typer,
  pytest, ruff (exact versions in `uv.lock`).
- Site: Next.js, React, Tailwind CSS, Recharts, TypeScript (exact versions in `site/package-lock.json`).

## Hackathon diff
Work done during the hackathon:
`https://github.com/Axlnd3r/NePu---NEAR-Pulse-/compare/pre-hackathon...hackathon-submission`

- Tag `pre-hackathon`: planning documents only (CLAUDE.md, PROGRESS.md, runbook commands).
- Tag `hackathon-submission`: the submitted state.

## License
MIT, see [LICENSE](LICENSE).
