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
TODO (F2). Copy `.env.example` to `.env`, fill in credentials, then `make extract` (pulls into
`data/live/`) and `make build-live`. `make proof` commits the manifest hash to NEAR mainnet (F7).

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
