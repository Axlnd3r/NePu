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
| F4 Distribution Map | 7–9 Nov | todo | |
| F5 Valuation Lab | 8–10 Nov | todo | |
| F6 Dashboard | 9–12 Nov | todo | |
| F7 THESIS, README, offline, CI, proof | 11–13 Nov | todo | |
| F8 Demo + submission | 13–14 Nov | todo | |

## Session log
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
