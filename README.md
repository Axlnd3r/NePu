# NEAR Capture Ledger

**Live dashboard:** https://axlnd3r.github.io/NePu/ (built by `.github/workflows/pages.yml`
from `data/snapshot/` after `make verify` passes; the footer shows the commit and the manifest hash)
· **Argument:** [THESIS.md](THESIS.md) · **Method:** [docs/METHODOLOGY.md](docs/METHODOLOGY.md) ·
**Sources checked:** [DATA_AUDIT.md](DATA_AUDIT.md)

## What it is
A reproducible investment-thesis tool for NEAR, built for NEAR HACKATHON 2026 (track: Investment
Thesis, judged on evidence rather than conviction). One command rebuilds every metric, chart and the
thesis text from committed, hashed data. Every number traces back to a file in `data/` listed in a
manifest with its SHA-256, source query and `block_date` range, and a test recomputes the published
numbers independently of the code that produced them.

For tools and agents: `make build` writes machine-readable outputs to `site/public/data/*.json`
(summary, coverage, distribution, valuation, developer, markers, provenance, queries) and
regenerates `THESIS.md` and the results block below; `data/snapshot/manifest.json` is the index of
the inputs; the `capture` command (`uv run capture --help`) is the entry point.

## The problem
NEAR Intents routes large cross-chain swap volume, and part of its fees is used to buy NEAR, while
new NEAR is issued every epoch. Whether that capture can outgrow issuance is a falsifiable question.
This project measures it and reports how far the network is from that point:

- Coverage ratio: `CR = (buyback value + burn value) / gross issuance value`, per day and over rolling
  `30d` and `90d` windows, in USD and in NEAR units.
- Break-even daily Intents volume: `V* = (i * S * P - Burn_usd) / tau_eff`, with `i` the daily
  issuance rate, `S` total supply, `P` the NEAR price and `tau_eff` the take rate.
- Buybacks are not burns: the NEAR bought back is held in a wallet, so the float view and the
  total-supply view are kept apart.

## Results
<!-- results:start -->
**Latest build**, generated from `site/public/data/*.json` (the full argument, with the evidence against it, is in [THESIS.md](THESIS.md)):

- For every dollar of new NEAR issued, **12 cents** came back as buybacks or gas burn in the 30 days to 2026-10-31.
- **Not yet:** daily Intents volume would have to reach $989.9M, 7.6x its $130.4M average, for capture to cover issuance at today's rates.
- Proof: the SHA-256 of the snapshot manifest is committed on NEAR **testnet** (contract `nepu-ledger.testnet`, run id `capture-ledger-2026-11-01-48c59060cee3`, [transaction](https://explorer.testnet.near.org/transactions/2CsbDXKFmFPqUpBDvQxiamodirssdd9NT63E6dqeg76D), block 276,017,917). OpenTimestamps (Bitcoin): pending.
<!-- results:end -->

## Quickstart (offline)
No credentials are needed. Requirements: [uv](https://docs.astral.sh/uv/) (it installs the pinned
`Python 3.12` itself if that is missing), `Node 24`, GNU make, git.

1. **Do** `git clone https://github.com/Axlnd3r/NePu.git` and `cd NePu`.
   **See** the repository with `data/snapshot/` (the frozen inputs) and `data/snapshot/manifest.json`.
2. **Do** `make all`. **See** it install dependencies (the only step that needs a network), rebuild
   every metric into `site/public/data/`, run ruff, the manifest hash check and the tests, and
   export the dashboard to `site/out/`. It ends without errors.
3. **Do** `make serve` (it runs `uv run python -m http.server 8000 --directory site/out`) and open
   `http://localhost:8000`. **See** the hero sentence quoted under Results, the ledger of where
   Intents volume goes, the break-even meter and the other pages. (Opening `site/out/index.html`
   straight from the disk shows a broken page, with no styles and no charts: the export uses
   absolute asset paths, so it must be served.)
4. **Do** `uv run capture verify-manifest data/snapshot`. **See** `data/snapshot/manifest.json: OK`:
   every input file still has the hash recorded when it was frozen.

| Command | What it does |
|---|---|
| `make setup` | install Python (uv) and Node dependencies |
| `make build` | rebuild every metric from `data/snapshot/`, and `THESIS.md` and the results block |
| `make verify` | lint, recompute manifest hashes, run the tests (including the independent number audit) |
| `make site` | build the static dashboard into `site/out/` |
| `make serve` | serve `site/out` at `http://localhost:8000` (the export must be served, not opened from disk) |
| `make qa` | open every page in Chrome (desktop light and dark, phone) and fail on console errors, failed requests or overflow; screenshots go to `qa/screenshots/` |
| `make proof` | commit the manifest hash to NEAR (see Verify the proof) |
| `make all` | setup, build, verify and site; works from a clean clone, offline |

## Live mode
Needs credentials, so it is optional; the offline quickstart never uses it. Names only are listed in
`.env.example`; real values live in `.env`, which is git-ignored.

1. Copy `.env.example` to `.env` and fill in `GOOGLE_CLOUD_PROJECT` (and `BQ_MAX_BYTES`). Log in once
   with `gcloud auth application-default login`. `INTENTS_EXPLORER_JWT` and `COINGECKO_API_KEY` are
   optional; without the JWT the Explorer tables are skipped.
2. `uv run capture extract --dry-run` estimates BigQuery bytes without pulling anything.
3. `make extract` pulls into `data/live/` (git-ignored). It is incremental by date: a second run
   queries nothing that is already there. BigQuery bills your own project's quota.
4. `make build-live` rebuilds the metrics from `data/live/`.
5. `uv run capture snapshot --freeze <YYYY-MM-DD>` copies `data/live/` into `data/snapshot/` (rows up
   to that complete UTC day) and rewrites its manifest.

`.github/workflows/weekly-rebuild.yml` does these steps weekly when its repository secrets are set
(it does nothing without them).

## Verify the proof
The SHA-256 of `data/snapshot/manifest.json` (which lists the hash of every input file) is committed
to a NEAR contract, `contracts/proof-of-analysis`, so anyone can check that the published numbers
came from these files and that the hash existed no later than the transaction's block. **It does
not show that the data is correct**, and it is on **testnet**, which carries no economic security
and does not promise to keep its history; it was chosen because it costs nothing. The network is
named wherever the proof is shown. The result block above gives the contract, the run id and the
transaction.

- **On the dashboard:** the Methodology page hashes the served manifest in your browser, reads the
  contract's `get(run_id)` over JSON-RPC and compares the two.
- **With this repository:** `sha256sum data/snapshot/manifest.json`, then
  `PROOF_ACCOUNT_ID=nepu-ledger.testnet uv run capture proof status`, which prints `MATCH` when the
  contract holds that hash.
- **With nothing but curl:** call the contract's view method `get` with the run id; the reply holds
  the hash as JSON bytes:

```sh
ARGS=$(printf '{"run_id":"<run id from the results block>"}' | base64 -w0)
curl -s https://rpc.testnet.fastnear.com -H 'content-type: application/json' -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"query\",\"params\":{\"request_type\":\"call_function\",\"finality\":\"final\",\"account_id\":\"nepu-ledger.testnet\",\"method_name\":\"get\",\"args_base64\":\"$ARGS\"}}"
```

- **Second, independent timestamp:** the manifest is also stamped with OpenTimestamps (Bitcoin). The
  stamp is made by `.github/workflows/proof.yml`, because the `ots` client does not run on Windows.
  Save `data/proof/<run id>/manifest.json.ots` next to the manifest and run `ots verify`; the client
  needs a Bitcoin Core node. A fresh stamp is pending for a few hours.
- **The contract** is built and tested in CI (`.github/workflows/contract.yml`); the wasm and its
  checksum are committed in `contracts/proof-of-analysis/artifacts/`. To re-run the proof yourself you
  need `near-cli-rs`, a dedicated NEAR account and, for the weekly job, a function-call key limited
  to the `commit` method; see `.env.example`. Never use your own wallet, and never put a private key
  in the repository.

## Dashboard and demo video
- Dashboard: https://axlnd3r.github.io/NePu/ (six pages; every chart shows its query,
  one plain sentence and its provenance).
- Demo video: not published yet.

## Methodology
Formulas, definitions and limitations: [docs/METHODOLOGY.md](docs/METHODOLOGY.md). The thesis with the
contrary evidence, the numeric conditions that would change it and the metrics that are unavailable:
[THESIS.md](THESIS.md).

## Data sources
BigQuery public dataset `bigquery-public-data.crypto_near_mainnet_us`, the NEAR Intents Explorer API,
DefiLlama, CoinGecko and the 1Click token list. How each was checked, and where a source fell short, is
recorded in [DATA_AUDIT.md](DATA_AUDIT.md).

## Limitations
Stated in full in [THESIS.md](THESIS.md). In short: the channel data covers 1Click transactions only
and a shrinking share of Intents volume; the buyback wallet is observed only from the day it first
appears; the volume growth in the historical scenarios comes from the launch phase; the NEAR price is
held constant in every simulation, which is an assumption and not a forecast; correlation is not
causation; no price is predicted.

## Track checklist
Our own checklist, built from the track description (judged on evidence, not conviction). The
organisers' official requirement list was not available when this was written, so this is not it.

- [x] A falsifiable question and an explicit claim ([THESIS.md](THESIS.md), "Claim")
- [x] Evidence against the claim, and null results, reported
- [x] The conditions that would change the reading, as numeric triggers evaluated on every build
- [x] Every number traced to a hashed file, with an independent recomputation in the tests
- [x] Metrics that cannot be computed marked "unavailable" with the reason
- [x] Limitations stated; no price predictions
- [x] Sources listed and checked ([DATA_AUDIT.md](DATA_AUDIT.md))
- [x] Proof of analysis committed to NEAR testnet and timestamped with OpenTimestamps
- [x] `make all` from a fresh clone with no credentials, run by a separate AI screener session (a
  fresh agent that had not seen this project's history); it passed
- [ ] The same run by a human reviewer (pending)
- [x] BigQuery queries filter on `block_date`, except `sql/fee_wallet_inflows_daily.sql`, which filters
  on `epoch_date` because the `ft_balances_daily` table has no `block_date` column (stated in that
  file and in [DATA_AUDIT.md](DATA_AUDIT.md))
- [ ] Demo video (not published yet)

## AI & libraries disclosure
- The code, tests and documentation were written with Claude Code (Anthropic), using the Claude
  models named in the commit trailers (`Claude Sonnet 5.5` and `Claude Opus 5.5`), under the
  author's direction. The author made the decisions about scope and about anything involving
  money or public transactions, and ran those transactions.
- Python: duckdb, pandas, pyarrow, google-cloud-bigquery, httpx, python-dotenv, numpy, scipy, typer;
  development: pytest, ruff (exact versions in `uv.lock`).
- Site: next, react, react-dom, recharts, Tailwind CSS, TypeScript, and Playwright for the QA
  (exact versions in `site/package-lock.json`).
- Contract: near-sdk, built with cargo-near; deployed and called with near-cli-rs. The
  OpenTimestamps client (`opentimestamps-client`) runs in CI.
- Data providers are listed under Data sources.

## Hackathon diff
Work done during the hackathon, from the planning-only tag to the submission:
https://github.com/Axlnd3r/NePu/compare/pre-hackathon...hackathon-submission
(the `hackathon-submission` tag is created when the project is submitted; until then, the same
comparison against the current state is
https://github.com/Axlnd3r/NePu/compare/pre-hackathon...main).

- Tag `pre-hackathon`: planning documents only (`CLAUDE.md`, `PROGRESS.md`, runbook commands).

## Layout
- `sql/`: one parameterised query per BigQuery table; `src/capture/`: extractors, models
  (coverage, break-even, distribution, valuation, developer, ledger), build, thesis, proof, CLI.
- `data/snapshot/`: committed daily aggregates and `manifest.json`; `data/reference/`: dated events and
  policy parameters with sources; `data/proof.json` and `data/proof/`: the proof record.
- `site/`: Next.js and Recharts, static export, reads `site/public/data/*.json`.
- `contracts/proof-of-analysis/`: the NEAR contract.
- `tests/`: unit, golden, invariant, reconciliation, manifest and independent audit tests.

## License
MIT.
