# PROGRESS

Living log. Claude updates this at the end of every session. Newest entry on top.

## Gates
- [x] Gate 1 (2026-11-03): data go/no-go — GO-WITH-FALLBACK, confirmed by user 2026-11-02, see DATA_AUDIT.md
- [x] Gate 2 (2026-11-07): first coverage ratio from pipeline, reconciliation tests passing — met 2026-11-02, see DATA_AUDIT.md F3
- [ ] Gate 3 (2026-11-13): `make all` succeeds from a clean clone with no credentials; /screener score >= 8

## Phase status
| Phase | Dates | Status | Notes |
|---|---|---|---|
| F0 Setup repo | 2 Nov | done | `make all` green locally; CI not yet run (no remote) |
| F1 Data verification | 2–3 Nov | done, awaiting Gate 1 confirmation | Recommendation GO-WITH-FALLBACK, see DATA_AUDIT.md |
| F2 Ingestion + snapshot | 3–5 Nov | done | Snapshot v1 frozen 2026-11-01; Explorer table not pulled (no JWT); price limited to 365 days |
| F3 Coverage ratio + tests | 5–7 Nov | done | CR_float, CR_supply, V*, sensitivity, 10/10 months reconcile within 15% |
| F4 Distribution Map | 7–9 Nov | done | Snapshot v3 (2026-11-01); distribution.json, developer.json; lead/lag verdict null |
| F5 Valuation Lab | 8–10 Nov | done | valuation.json: reverse table + Monte Carlo (3 scenarios x 2 inflation paths x 3 prices); historical/decay results rest on launch-phase growth |
| F6 Dashboard | 9–12 Nov | done, live at https://axlnd3r.github.io/NePu/ | 6 pages, ChartCard + evidence chips, Playwright QA, independent number audit; GitHub Pages workflow ready |
| F7 THESIS, README, offline, CI, proof | 11–13 Nov | done except the clean-clone `/screener` (user, new session) | proof on testnet + OpenTimestamps; THESIS.md and README generated; weekly workflow ready |
| F8 Demo + submission | 13–14 Nov | todo | |

## Session log
### 2026-11-03 — F7 (site restyle)
- Done: dashboard restyled to a dark "obsidian and champagne" theme (user's reference: a refero.design style page): black canvas, cream ink #fff7dd, champagne #c8ad86 as the only accent, 4px radius, 1px hairlines, no shadows. Hero now leads with a pixelated NEAR "N" (components/NearMark.tsx: 9 x 9 tile grid, SVG gradient + static noise texture, no image file), a centred headline and a "Read the thesis" link. Inter typeface self-hosted via @fontsource-variable/inter (OFL; Switzer from the reference was not used because its licence does not allow redistributing the files). Light mode removed.
- Numbers found: none new; no data, model or text figure changed. make verify 260 passed, 1 skipped; qa/check.mjs clean on all pages, desktop and mobile.
- Decisions: chart colours re-chosen for the black surface and checked with the dataviz validator (series-2 #b58a3a, series-3 #b374ad, neutral #66635f: all-pairs CVD worst 13.8, normal-vision worst 18.1; CR 7d/30d/90d as an ordinal gold ramp, light end 4.15:1). Status badges keep icon + label (good = champagne, critical = #c96f5a). The yardstick bar ("New NEAR issued") is drawn as an outline. README discloses the new font dependency.
- Blockers: none.
- Next: redeploy GitHub Pages so the live site shows the new theme; then the clean-clone /screener and F8.

### 2026-11-03 — F7 (7a, 7b, 7c up to the screener)
- Done:
  - **7a proof of analysis.** Contract `contracts/proof-of-analysis` (owner-only, write-once `commit`, `get`, NEP-297 event), tests written first (13), built and tested in CI, wasm committed with its checksum. Deployed to NEAR **testnet** (`nepu-ledger.testnet`, a dedicated account made with the faucet), code hash read back from the chain equals the CI build. First proof committed and verified three ways (local hash, `proof.json`, `get` on chain; event log; idempotent second run). `capture proof status|preflight|commit|ots-record`, `data/proof.json`, the Methodology page verifies it in the browser (QA also checks that a tampered manifest is rejected). OpenTimestamps stamp made in CI (`ots` does not run on Windows), status pending.
  - **7b documents and automation.** THESIS.md and the README results block generated from the JSON through a registry of facts; README rewritten (do/see quickstart, three ways to verify the proof, own checklist, AI and libraries disclosure, both diff links); `weekly-rebuild.yml` (does nothing until its secrets exist; not run against real secrets yet); `proof.yml` (OTS stamp or upgrade).
  - **7c number audit.** Every JSON path cited by THESIS.md or the README is now recomputed independently (55 paths, 3 descriptive texts) and a test fails if a new path is cited without a recomputation; found and fixed two ordering defects in the weekly workflow (proof before verify) and in `commit()` (a stamp of an older manifest was kept). `make verify`: all tests pass.
- Numbers found (source: THESIS.md / summary.json, as of 2026-10-31): 12 cents of buybacks and burn per dollar of new NEAR issued; volume must grow 7.6x ($989.9M against $130.4M a day) to break even; 65.5 % of on-chain revenue reaches the buyback wallet; reconciliation 10 of 10 months, worst 11.0 % against 15 %; Explorer coverage 48.7 % (2026-07) to 27.4 % (2026-10). Wasm 105,951 bytes, 1.062 NEAR locked on testnet (a faucet account with 10 NEAR).
- Decisions: testnet plus OpenTimestamps, no mainnet (no funds); dedicated account; CI holds only a function-call key limited to `commit` (not created yet); contract built non-reproducibly in CI with the hash published; repository renamed by the user to `Axlnd3r/NePu` (Pages URL changed, base path follows the name); `/screener` to be run in a fresh session.
- Blockers / pending: function-call key and GitHub secrets for the weekly workflow (user); the OpenTimestamps stamp is pending until a Bitcoin block attests it and the `BitcoinBlockHeaderAttestation` line format is assumed until the first upgrade; official track requirements not provided, the README checklist says it is the project's own; demo video (F8); `hackathon-submission` tag at submission; `/clear` then `/screener` by the user.
- Next: merge to `main` (redeploys the site under `/NePu`), run `/screener` in a new session and fix what it finds (Gate 3: `make all` from a clean clone with no credentials, score at least 8), then F8 (demo video, submission tag).

### 2026-11-03 — F6
- Done: data layer (summary.json with the capture ledger, lever bridge and three independent conditions; queries.json, provenance.json, markers.json; data/reference/events.csv and parameters.csv with their own manifest); six dashboard pages (Overview, Token economics, Intents & channels, Valuation Lab, Developer, Methodology & data) where every chart shows one sentence, its SQL or API request, the model function and provenance, and headline numbers open their evidence; `make qa` (Playwright, Chrome, desktop light/dark and phone); tests/test_numbers_audit.py recomputes every published number independently; GitHub Pages workflow (.github/workflows/pages.yml). `make verify`: 176 passed; `make qa`: all pages clean, also under the Pages base path.
- Numbers found (source: summary.json, 30 days to 2026-10-30 unless stated):
  - Hero: 12 cents of buybacks and burn per USD of new NEAR (CR_float in USD 0.1196, 30 days to 2026-10-31); this week 0.120, prev 0.118.
  - Per 10,000 USD of Intents volume: fees 16.01, revenue 5.48, 3.62 reaching the buyback wallet, against 33.91 of issuance; 65.5 % of on-chain revenue reaches the buyback wallet.
  - Lever bridge: volume must grow 7.59x; the HSP-029 cut closes 1.575x (to 4.82x); all revenue to buybacks closes 1.513x (to 3.18x).
  - Issuance step dated from the data: 2025-10-30 (2025-10-29 is a transition day), 14-day means about 176,237 to 88,823 NEAR/day.
  - Number audit: 158 independent checks, 0 mismatches; now 11 permanent tests.
- Decisions: hero in USD (CR_float in NEAR shown beside it); conditions are volume vs V*, revenue routing to the buyback wallet and the reconciliation guard (a take-rate condition was the volume condition restated); reported events and policy parameters live in data/reference with sources; HSP-029 ramp starts after its 90-day grace period; markers on weekly charts are drawn at the week and listed with the event's own date; GitHub Pages under /NePu---NEAR-Pulse-.
- Bugs fixed: Windows race in the manifest lock (lost entries); Next.js 16.4.3 export nests prefetch files on Windows (404s); invalid popover markup broke hydration; stale summary.json after a model change (always rebuild with `make site`); bar lengths not proportional on phones; 99.7 % rounded to 100 %.
- Blockers: the first push needs the user's GitHub credentials, and Pages must be set to "GitHub Actions" in the repository settings; `.env.example` held the Google Cloud project id in history (removed now, history not rewritten, not a credential); HSP-029 vote result not found.
- Deployed: GitHub Pages enabled by the user (source: GitHub Actions); run re-deployed green; `QA_URL=https://axlnd3r.github.io/NePu---NEAR-Pulse- make qa` passed on all 18 page/viewport combinations; live footer shows commit 82f5597 and the same snapshot manifest hash.
- Next: F7 (THESIS.md quoting summary.json, README results, proof-of-analysis, /screener).

### 2026-11-03 — F5
- Done: models/valuation.py (reverse break-even, block bootstrap, scenarios historical / decay / flat, Monte Carlo with common random numbers), build.py writes site/public/data/valuation.json, config constants (10,000 paths, 60 months, 3-month blocks, seed `RANDOM_SEED`), docs/METHODOLOGY.md "Valuation Lab", DATA_AUDIT.md "F5 Valuation Lab". Tests written first: 27 new (hand-computed CR 0.8 and 0.425, equality with the F3 sensitivity grid, probabilities in [0, 1], same seed identical and another seed different, flat <= decay <= historical, price and inflation monotonic, month-0 check, no price target). `make verify`: 141 passed.
- Numbers found (source: site/public/data/valuation.json, as of 2026-10-30; price held constant at 4.05 USD):
  - Required annual growth of 30d volume (130.4 M USD/day) to reach CR_float = 1, buyback basis: inflation 2.5 %: +659 % (1 y), +96.5 % (3 y), +50.0 % (5 y), V* 989.9 M USD/day; inflation 1.6 %: +382 %, +68.9 %, +37.0 %, V* 628.3 M. All-revenue basis: +402 / +71.2 / +38.1 % at 2.5 %.
  - P(CR >= 1) at months 12 / 36 / 60, constant price, inflation 2.5 %: flat 9 / 21 / 28 % (median first crossing month 59); decay 33 / 59 / 61 %; historical 45 / 96 / 99.7 %. Ramp to 1.6 %: flat 11 / 26 / 31 %. At 2x price flat is 5 / 15 / 22 % and the median is "not reached".
  - Historical scenario median volume 1.2 B / 132 B / 13.8 T USD per day at months 12 / 36 / 60: not credible, so its probabilities near 1 are an artifact of launch-phase growth (mean +0.191 a month; +0.006 from 2025-12).
  - Model month 0 CR 0.144 at the latest price against measured CR_float 0.122; 0.121 at the window's mean price. The NEAR price fell 5.34 to 4.05 inside the window.
- Decisions: tau on the buyback basis (CR_float's), drawn once per path uniformly between the lowest and highest complete monthly value (0.0150 to 0.0362 %), the all-revenue basis only in the reverse table; supply held constant (as V*); decay keeps volatility and halves only the drift; month-0 test compared at the window's mean price, not loosened; no A2 scenario added (outside the spec); the 1.6 % inflation is labelled "supplied by the user, not verified".
- Blockers: the 1.6 % proposal has no recorded source; the growth sample is 16 monthly changes and tau has 6 months, so no scenario can support a strong claim; THESIS.md must present the flat scenario as the one independent of the launch regime and state the price assumption.
- Next: F6 Dashboard (site/): charts for coverage, Distribution Map, Valuation Lab and developer indicator, each with its query, one sentence and provenance. The fan chart should show the implied volume next to CR. Then F7 THESIS, README, offline build, CI, proof.

### 2026-11-03 — F4
- Done: Distribution Map (models/distribution.py: channel and asset concentration, HHI, stablecoin and ZEC shares, attributable share of on-chain revenue, take rates, near.com proxy) and developer indicator (models/developer.py: new contracts that stay used, cohorts, train/test lead/lag). Explorer tables rebuilt at recipient level from the cached pages (daily, channels, recipients), token_assets from the 1Click token list, `contracts_daily.sql` corrected (deploy-only days kept) and re-pulled. Explorer pulled 2026-07-01..2026-11-01. Snapshot v3 frozen at 2026-11-01 (11 files). `make verify`: 114 passed, ruff clean. `make build` writes distribution.json and developer.json.
- Numbers found (source: site/public/data/distribution.json, developer.json; Explorer is 1Click only):
  - Channel HHI 0.198 / 0.201 / 0.192 / 0.214 for Jul / Aug / Sep / Oct; top channel 34.1 % to 40.1 %; stablecoin share of volume 61.8 % to 53.3 %.
  - Explorer volume as a share of DefiLlama volume: 48.7 / 43.7 / 31.5 / 27.4 % (Jul to Oct), so the map covers a shrinking fraction of Intents volume.
  - Attributable share of on-chain revenue (declared fees to NEAR wallets) 68.8 / 47.1 / 21.5 / 21.9 %. near.com is not measurable; `near_wallet_only_share` 7.7 / 6.5 / 17.1 / 22.3 % is a labelled proxy.
  - Developer cohorts: 2026-08 85 new contracts, 45.9 % still called in month +1; 2026-09 467, 31.3 % (parent `near` behind 17.6 % of it).
  - Lead/lag verdict: **null** (lag 0 best in training, r = -0.72; test r = +0.90 on 5 pairs, permutation p = 0.19; lags 2 and 3 have fewer than 4 pairs). Reported as is, not as support for the thesis.
- Decisions: page Explorer by end timestamp, never by cursor; recipient volumes are not additive (a transaction counts in each recipient); stablecoin and ZEC groups are a labelled judgment; rows are trimmed to the frozen day (live table reached 2026-11-02, snapshot ends 2026-11-01); gcloud-login.sh is a local helper and was left out of the commit.
- Blockers: no field identifies near.com, so the near.com share the spec asks for is "unavailable" (reason in distribution.json) and THESIS.md must say so; Explorer coverage keeps falling, so every Distribution Map claim must carry its scope; developer lead/lag has too few monthly pairs for any positive claim.
- Next: F5 Valuation Lab (reverse valuation + bootstrap Monte Carlo, fixed seed in config). Reminder: price_daily only reaches back to 2025-11-04, which limits the bootstrap sample.

### 2026-11-02 — F2 follow-up (Explorer)
- Done: Explorer API verified with the JWT (fee unit = bps of amountIn, asset-id patterns, cursor unreliable); pagination rewritten (time window, dedupe, stall guard, page cap); 30-day pull complete: 89,210 rows, 488,989 transactions, 2026-10-03..2026-11-01; snapshot v2 frozen at 2026-11-01 (8 tables, the other 7 byte-identical).
- Numbers found (source: data/snapshot/explorer_1click_daily.parquet): Explorer volume is 27 % of DefiLlama's for the same days; declared app fee 0.458 % of volume; chain parsing 0 % unknown; row count equals an independent recount from the cache.
- Decisions: page by end timestamp, never by cursor; keep the table at transaction-group grain for now and rebuild at recipient level in F4 from the cache.
- Blockers: none new.
- Next: F4.

### 2026-11-02 — F3
- Done: models/coverage.py, models/breakeven.py, build.py writing site/public/data/coverage.json, docs/METHODOLOGY.md with every definition, tests (golden 3-day fixture, invariants, monthly reconciliation, build). 66 tests pass offline. Also normalised the repository to LF line endings (Python on Windows had written CRLF into 31 files) and verified the Explorer API against real data.
- Numbers found (source: data/snapshot via coverage.json):
  - CR_float 30d ending 2026-10-06 = 0.139 (buyback 335,408 NEAR + burn 34,338 NEAR over gross issuance 2,656,764 NEAR); CR_supply 30d = 0.013; DefiLlama-proxy basis 0.207.
  - Latest CR_float 30d (2026-10-31) 0.120, 90d 0.133. V* 652 M USD/day vs actual 130 M USD/day (5.0x) as of 2026-10-30; tau_eff 30d 0.0548 %.
  - Monthly on-chain vs DefiLlama revenue: 10 of 10 complete months within 15 %, largest +11.0 % (2025-12).
  - Transfer netting validated against receipts: 502,793.0 and 7,274.0 NEAR (estimates 502,791.6 and 7,274.2).
- Decisions: buyback_near = inflow to buybacks.multisignature.near net of estimated transfers from the other revenue wallets, from 2026-04-27; headline on wallet basis, DefiLlama proxy shown as a labelled secondary series; tau_eff keeps the spec definition (all revenue) with a labelled buyback-only variant; reconciliation tolerance 15 % is a documented constant guarded by a test; the public reference is not used by the model.
- Blockers: buyback value before 2026-04-27 is unknown (revenue reached fefundsadmin/1cs); the reference comparison cannot be confirmed (Stocktwits post unverifiable).
- Next: F4 Distribution Map. Prerequisite: rebuild the Explorer table at recipient level from the cached pages (the current table joins recipients and cannot split fee per recipient); Explorer covers 1Click only, about 27 % of DefiLlama volume.

### 2026-11-02 — F2
- Done: `capture extract` (incremental by date, retries with backoff, dry-run then run under maximum_bytes_billed, oversize ranges split automatically) and `capture snapshot --freeze`. Five SQL files in sql/, extractors for BigQuery, DefiLlama, CoinGecko and the Intents Explorer (mock-tested only). Manifests now store `query_sha256`. 33 tests pass offline. Snapshot v1 frozen at 2026-11-01.
- Numbers found (source: data/snapshot/*.parquet, manifest.json):
  - Rows: network_daily 190, contracts_daily 211,845, intents_onchain_daily 190, supply_daily 541, fee_wallet_inflows_daily 811, defillama_intents_daily 690, price_daily 363.
  - BigQuery: 37 queries, 258.57 GB billed (0.235 TiB), largest query 10.36 GB; a second extract billed 0 bytes.
  - Last 365 days: burn 615,669 NEAR, net supply growth 2.4788 %, implied gross issuance 2.527 % (corrects the F1 claim).
  - Wallet net change vs DefiLlama revenue, 2026-10-03..10-30: ratio 1.005 (sanity check, not the F3 reconciliation).
- Decisions: price_daily limited to the past 365 days (CoinGecko public API error 10012); fee_wallet_inflows_daily stores net daily change, not gross inflow; DefiLlama drops the last 3 days as not final; snapshot refuses a partial day.
- Blockers: no Intents Explorer JWT, so explorer_1click_daily is not pulled and the Distribution Map stays degraded; no USD price before 2025-11-04 (needs a paid CoinGecko key or another source, your call); source gaps 2026-04-17..20 (wallet balances) and 2026-04-18/19 (circulating supply).
- Next: F3 coverage ratio. Net out transfers between the three wallets (2026-09-09 case), define buyback value from 2026-04-26, label issuance as net or implied gross.

### 2026-11-02 — F1
- Done: checks 1-10 in DATA_AUDIT.md with evidence in docs/audit/ (SHA256SUMS). Statuses: 1, 2, 3, 4, 6, 7 OK; 5, 8, 9, 10 PARTIAL. Added git remote `origin` (not pushed), filled README links, added BQ_MAX_BYTES default and COINGECKO_API_KEY to .env.example, created local .env (gitignored).
- Numbers found (source file):
  - BigQuery fresh to 2026-11-02 for blocks/transactions/receipt_actions (docs/audit/bq_freshness_schema.json).
  - Net supply growth 2.467 % to 2.479 % annualised over 28 to 365 days (docs/audit/rpc_total_supply.json).
  - Fees reach wallets as native NEAR TRANSFER from intents.near: 855 receipts to buybacks.multisignature.near and 392 to fefundsadmin.sputnik-dao.near over 30 days (docs/audit/bq_q4c_actions.json).
  - On-chain wallet inflow 2026-10-03..11-01 is 1.016x DefiLlama dailyRevenue (docs/audit/sanity_onchain_vs_defillama.json). Sanity check only, not the F3 reconciliation.
- Decisions: wallet flows from ft_balances_daily (0.98 GB), not receipt_actions.args (3.1 TB); internal wallet transfers must be netted (2026-09-09: 1csfundsadmin -502,791.6 NEAR, buybacks +514,257.6 NEAR); buyback value defined from 2026-04-26.
- Blockers: no Intents Explorer JWT (Distribution Map degraded without it); buyback destination 2026-02-23 to ~April unknown (account created between 2026-03-01 and 2026-04-20); "permanent capital vehicle" not found in any source; BigQuery sandbox quota 1 TiB per month and one full extract is about 0.5 TiB.
- Next: you confirm Gate 1 (and supply a JWT, optionally a CoinGecko key); then F2 ingestion. Decide the developer-indicator window before F2 because of cost.

### 2026-11-02 — F0
- Done: git init + tag `pre-hackathon` on planning-docs commit (187cbf0). Scaffold per CLAUDE.md Layout:
  pyproject (uv, py3.12) + uv.lock, Makefile (setup/extract/build/build-live/verify/site/proof/all),
  typer CLI (extract, build, verify-manifest, proof), manifest.py (sha256, rows, source, query_file,
  date_range, pulled_at_utc), placeholder build -> site/public/data/meta.json, tests/test_manifest.py
  (5 tests), Next.js 16.4.3 static export page rendering meta.json, CI workflow, .env.example,
  .gitignore, LICENSE (MIT), README skeleton, DATA_AUDIT.md, docs/METHODOLOGY.md stub.
- Numbers found (with source file): none (no data yet).
- Decisions:
  - Removed next/font/google from the Next.js template: it downloads fonts at build time and would
    break offline builds. System font stack instead.
  - site/public/data/ is gitignored (generated by `make build`); `make site` depends on `build`.
  - `extract` and `proof` are stubs that exit 1 until F2 / F7; not part of `make all`.
  - verify_manifest stops at a hash mismatch (a changed parquet may not parse) instead of crashing.
  - Local git identity set repo-only: vibecodinggg <vibecodinggg@gmail.com>.
- Blockers:
  - No GitHub remote yet: README compare link uses `<owner>/<repo>` placeholder; CI unverified.
  - `make setup` needs network for packages (uv/npm); "offline" means no credentials.
- Next: F1 data verification (Gate 1, 2026-11-03): resolve Q1-Q5 in DATA_AUDIT.md.
<!-- template
### YYYY-MM-DD — F<n>
- Done:
- Numbers found (with source file):
- Decisions:
- Blockers:
- Next:
-->
