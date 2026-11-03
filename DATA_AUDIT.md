# DATA_AUDIT

Phase F1 data verification, run 2026-11-02 (UTC). One row per check; details and evidence below.
All raw evidence is in `docs/audit/` (hashes in `docs/audit/SHA256SUMS`). No analysis code was written:
the checks were run with throwaway scripts outside the repo. Every BigQuery query was dry-run first and
executed with `maximum_bytes_billed = BQ_MAX_BYTES = 10737418240`; the SQL of each is stored in the
evidence JSON next to its dry-run and billed bytes.

## Summary

| # | Item | Expected | Found | Evidence | Status | Fallback |
|---|---|---|---|---|---|---|
| 1 | BigQuery freshness | Possibly stale after NEAR Lake deprecation (2026-03-24) | Not stale. `blocks`, `transactions`, `receipt_actions` all reach 2026-11-02 (today, partial day). History starts 2020-07-21 / 2020-07-23 | `bq_freshness_schema.json` | **OK** | none needed |
| 2 | Schema | total supply, tokens burnt, logs, gas fields | All present (details below). CLAUDE.md's `receipts` view does not exist | `bq_freshness_schema.json` | **OK** | use `receipt_actions` + `receipt_details` |
| 3 | Intents verifier | `intents.near` | `intents.near` in docs and on chain; rank 2 FUNCTION_CALL receiver over 7 days | `bq_q3_q2_q4a.json`, `onchain_accounts.json` | **OK** | none needed |
| 4 | Revenue wallets and fee path | Full ids; NEP-141 or NEP-245 transfers | Ids found. Fees leave `intents.near` as **native NEAR TRANSFER** after `native_withdraw` + `wrap.near near_withdraw`. No NEP-141/NEP-245 transfer event reaches the wallets | `bq_q4_*.json`, `bq_q4g_trace_detail.json` | **OK** | none needed |
| 5 | Buyback destination | "permanent capital vehicle" | Wallet `buybacks.multisignature.near` (single source: revenue.near.org). The phrase "permanent capital vehicle" is **not found** in any source. Account did not exist on 2026-03-01, so the 2026-02-23 to ~April destination is unknown. NEAR is held, not burned | `buybacks_account_creation.json`, `onchain_accounts.json` | **PARTIAL** (vehicle label: FAIL) | scope buyback series to >= 2026-04-26; earlier period "unavailable" |
| 6 | Issuance | ~2.5 % per year | Net `total_supply` growth 2.467 % to 2.479 % annualised over 28 to 365 days | `rpc_total_supply.json` | **OK** | none needed |
| 7 | DefiLlama | fees/revenue, daily | Daily from 2025-05-10 (fees, revenue) and 2024-12-10 (volume) | `defillama_evidence.json` | **OK** | none needed |
| 8 | Explorer API | params, fields, one JWT call | JWT works (updated 2026-11-02). Fields match the spec; `appFees.fee` is basis points of `amountIn`. 30-day pull done: 89,210 rows. Covers about 27 % of DefiLlama's Intents volume (1Click only). The cursor parameter is unreliable (see Check 8) | `intents_explorer_openapi.yaml`, `explorer_sample.json`, `explorer_checks.json` | **OK** (scope: 1Click only) | time-window pagination; non-1Click flow stays "unavailable" |
| 9 | CoinGecko | daily range call with key | No key. Keyless works only for the **past 365 days** (error 10012 beyond that, found in F2). Keyed call untested | `sanity_onchain_vs_defillama.json`, F2 notes | **PARTIAL** | price_daily limited to the last 365 days; earlier days need a paid key or another source (user decision) |
| 10 | Cost | 3 largest queries under limit | All three exceed 10 GB per query (3.1 TB, 315 GB, 181 GB). Cheaper designs found for the flows (see Check 10) | `bq_cost_dryruns.json` | **PARTIAL** | cheaper query designs, chunked pulls |

## Check 1: freshness

- `SELECT MAX(block_date) FROM blocks WHERE block_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)` returned 2026-11-02 (dry-run 0.069 GB).
- Same 60-day MAX for `transactions` (0.367 GB) and `receipt_actions` (2.419 GB): both 2026-11-02.
- MIN/MAX partition per table from `INFORMATION_SCHEMA.PARTITIONS` (metadata, scans no table data). All tables end 2026-11-02 except `ft_balances_daily` (2026-11-01). Starts: `blocks` 2020-07-21, `transactions` and `receipt_actions` 2020-07-23.
- Today's partition is partial. Use complete days only (`block_date < CURRENT_DATE()`).
- NEAR Lake deprecation did not stop the dataset. Why the dataset still updates was not investigated.

## Check 2: schema

Exact names (type), from `INFORMATION_SCHEMA.COLUMNS` (191 columns, 16 tables):

| Need | Table.column | Notes |
|---|---|---|
| Total supply | `blocks.total_supply` (FLOAT64) | yoctoNEAR. Matches RPC within block-height offset. FLOAT64 loses digits beyond ~15 significant figures; fine for aggregates, not for exact reconciliation |
| Float | `circulating_supply.circulating_tokens_supply`, `total_tokens_supply` (FLOAT64), daily | Useful for the separate "float" view (rule 6). Latest row 2026-11-01 |
| Tokens burnt | `execution_outcomes.tokens_burnt` (FLOAT64), also `transactions.receipt_conversion_tokens_burnt` | yoctoNEAR, verified: 6.87e26 yocto (687 NEAR) summed for 2026-10-31. Total burn needs both tables |
| Logs / events | `execution_outcomes.logs` (STRUCT<list ARRAY<STRUCT<element STRING>>>) | `EVENT_JSON:` lines present (seen: `native_withdraw`, `intents_executed`). Unnest with `l.element` |
| Gas | `execution_outcomes.gas_burnt`, `blocks.gas_price`, `transactions.receipt_conversion_gas_burnt` | |
| Receipt action args | `receipt_actions.args` (STRING JSON) | TRANSFER: `{"deposit":"<yocto>"}`. Very expensive column (Check 10) |

Deviations from CLAUDE.md: no `receipts` view exists. Extra tables not listed there: `ft_events`, `ft_balances_daily`, `transaction_actions`, `circulating_supply`, `accounts`, `nft_events`, `ft_events_contracts_by_account`, `nft_events_contracts_by_account`.
`accounts` is unusable here: even with a 30-day `block_date` filter a `LIKE` scan was estimated at 1,129 GB, so it was not run.
`account_changes` columns are `affected_account_id`, `update_reason`, `affected_account_nonstaked_balance` (not `account_id`); it is too expensive for wallet history (700 GB since 2025-05-10).

## Check 3: Intents verifier contract

- docs.near-intents.org (`integration/verifier-contract/introduction.md`): "The Verifier Smart Contract (`intents.near`)".
- `balances.md`: balances are NEP-245 with token ids such as `nep141:wrap.near`. `near-token.md`: native NEAR must be wrapped via `wrap.near` before deposit.
- On chain (`view_account`, block 222654348): `intents.near` exists, code hash `BtA1BEFNS619...`.
- Top FUNCTION_CALL receivers, `receipt_actions`, `block_date >= CURRENT_DATE - 7` (0.995 GB): 1. `token.sweat` 1,060,264; 2. **`intents.near` 914,323**; 3. `wrap.near` 673,943.

## Check 4: revenue wallets and how fees reach them

Ids (revenue.near.org "Wallet Breakdown", re-verified in the raw HTML, and confirmed on chain with `view_account`):
- `fefundsadmin.sputnik-dao.near`
- `1csfundsadmin.sputnik-dao.near`
- `buybacks.multisignature.near`

Search `receipt_receiver_account_id LIKE '%fundsadmin%'`, last 30 days: only `fefundsadmin.sputnik-dao.near` appears as receiver. `1csfundsadmin` received nothing in that window (balance static at 270.88 NEAR).

Fee path:
- `ft_events` has **0 rows** involving the three wallets in 30 days. Fees do not arrive as NEP-141 events.
- `receipt_actions` into the wallets, 30 days: 855 TRANSFER receipts to `buybacks.multisignature.near` and 392 to `fefundsadmin.sputnik-dao.near`, all with predecessor `intents.near`.
- Traced three receipts to their transactions (33 receipts, actions and logs saved in `bq_q4g_trace_detail.json`). Same path each time:
  1. `intents.near` executes a signed intent and logs `EVENT_JSON {"standard":"dip4","event":"native_withdraw",...}`.
  2. `intents.near` calls `wrap.near` (`near_withdraw`); log: `Withdraw <n> NEAR from intents.near`.
  3. A `withdraw` callback on `intents.near` sends a native NEAR TRANSFER to the wallet.

| Sample receipt | Tx | Time (UTC) | To | Amount (NEAR) |
|---|---|---|---|---|
| `HUY193r5L8c2zYxpdUM5PzegxD9svRrMbLz1LE5a5rGU` | `EXbQ3W9wLQZWbiBHwAgACAoL2aqzpVm7ebBCetJzUMd1` | 2026-10-31 23:46:53 | buybacks | 246.97 |
| `F98aDrq5zP8z3GrRty6KtwBR75PqyuxsopaUnGWUeCo7` | `Hbg8tYbHG9qqgiYurDXKVeUe4qDaQpHkrB8RtL3e1wam` | 2026-10-31 22:16:13 | fefundsadmin | 228.11 |
| `4PLSH6a5yUDhuWTNnm11GN1ZcNp8hjjsicS8hpnR1Q5p` | `9VtgWtqCj1ATjSJwWwrPLboLRbVsVodVRLYp66yz3Pwr` | 2026-10-31 22:08:23 | buybacks | 226.83 |

Consequences:
- The extractable signal is "native NEAR TRANSFER from `intents.near` to the wallets" (or the `native_withdraw` event), not `mt_transfer`.
- **Internal transfers must be netted out.** On 2026-09-09 `1csfundsadmin` fell 502,791.6 NEAR while `buybacks` rose 514,257.6 NEAR (same day, `bq_q4_balances.json`). Summing wallet inflows would double count; DefiLlama's methodology also excludes transfers between these wallets.
- The wallet receives NEAR from `intents.near`, not NEAR purchased on a DEX by the wallet. The "buyback" is therefore fee revenue collected in NEAR and parked; whether any further market purchase happens is not visible in this data.

Cheap wallet series: `ft_balances_daily` (`epoch_date`, `account_id`, `liquid`, in NEAR units) for the three wallets since 2025-05-10 costs 0.98 GB. Balance on 2026-11-01: buybacks 2,150,197.5; fefundsadmin 1,965,356.7; 1csfundsadmin 270.9 (matches on-chain `view_account` to within a day's flow).

Cross-check (not a reconciliation, see F3): positive daily balance deltas of buybacks + fefundsadmin over 2026-10-03..2026-11-01 sum to 431,566.9 NEAR, about 2.096 M USD at the daily mean CoinGecko price, versus DefiLlama `dailyRevenue` of 2.063 M USD for the same days (ratio 1.016). File: `sanity_onchain_vs_defillama.json`.

## Check 5: buyback destination

- revenue.near.org lists `buybacks.multisignature.near` (all-time 1,646,934 NEAR on the page). The page also says "Figures shown are illustrative" and that NEAR's share of fees feeds "buybacks that permanently remove NEAR from circulation".
- No NEAR blog, forum or X post found names the account or a "permanent capital vehicle". Official posts say only that the Intents fee switch went live 2026-02-23 and that revenue is used for buybacks (near_intents X posts, NEAR "State of NEAR Q2 2026"). One search, not exhaustive.
- On chain the wallet **holds** NEAR: 2,150,520 NEAR at block 222654348, only one daily decrease in 190 days (-6,264.6 NEAR on 2026-07-10). So buybacks are not burns (rule 6). This contradicts the page wording "permanently remove".
- `buybacks.multisignature.near` returned `UNKNOWN_ACCOUNT` at heights for 2026-02-23 and 2026-03-01 and existed (40 NEAR) on 2026-04-20. The destination between 2026-02-23 and about April is **unknown**.
- `fefundsadmin` (front-end revenue) is never drawn down (0 decreases), so DefiLlama's `HoldersRevenue` (equal to total `Revenue`) counts as "buyback" revenue that is only held in a collection wallet. Buyback value in the coverage ratio must therefore be defined explicitly (see Gate 1).

## Check 6: issuance

`header.total_supply` via `block` on `archival-rpc.mainnet.fastnear.com` (no key). Tip block 222654048. Annualised (simple) from actual timestamps:

| Window | Actual days | Annualised change |
|---|---|---|
| ~30d | 28.50 | 2.467 % |
| ~60d | 57.73 | 2.469 % |
| ~90d | 87.26 | 2.473 % |
| ~365d | 365.00 | 2.479 % |

Consistent with 2.5 % and stable across windows. Caveat: this is **net** of burn. Gross issuance is not read directly here. *Corrected in F2:* the F1 text said a burn of about 687 NEAR per day (one day, 2026-10-31) "accounts for the gap" to 2.5 %. Over the full 365 complete days to 2026-11-01 the burn is 615,669 NEAR (0.0481 % of starting supply), so net growth plus burn gives an implied gross issuance of 2.527 %, 0.027 percentage points above the nominal 2.5 %; that residual is not explained here. Burn also halved within the year (mean 2,412 NEAR/day in the first half, 966 in the second). Source: `data/snapshot/supply_daily.parquet`. My window search was loose (the "30d" block is 28.5 days back), so only the actual-day columns should be quoted.

## Check 7: DefiLlama

Endpoints in the table are HTTP 200 and need no key. Fields in `defillama_evidence.json`.

| Endpoint | Use | History | Notes |
|---|---|---|---|
| `/protocol/near-intents` | TVL | 2025-10-30 to 2026-11-01, 369 points, daily | `tvl[] {date, totalLiquidityUSD}`; last point is intraday |
| `/summary/fees/near-intents` | gross fees | 2025-05-10 to 2026-10-31, 540 daily points | `totalDataChart [[ts, usd]]` |
| `...?dataType=dailyRevenue` | captured revenue | same | 30d total 2,063,429 USD |
| `...?dataType=dailyHoldersRevenue` | "buyback" | same | 30d total 2,063,429 USD, identical to revenue |
| `...?dataType=dailyProtocolRevenue` | treasury before buyback | same | 0 over the last 30d |
| `/summary/dexs/near-intents` | volume | 2024-12-10 to 2026-10-31, 691 points | 30d total 3,736,467,599 USD; whether this equals Intents volume is not confirmed |

Quality flags: revenue exceeds fees on 5 of 540 days (2025-11-07, 2026-01-15, 2026-02-02, 2026-03-27, 2026-10-31). The last fees point (2026-10-31, 11,755 USD) is far below the preceding days (127k to 388k), so it looks incomplete. Failed endpoints: `/overview/fees/near-intents` 500, `/summary/dex-volumes/near-intents` 500, `/summary/bridge-aggregators/near-intents` 400. Their methodology says revenue is "NEAR/wNEAR swept into its revenue wallets", which matches Check 4. 540 daily points is a short history for a bootstrap Monte Carlo.

## Check 8: Intents Explorer API

- `https://explorer.near-intents.org/api/v0/openapi.yaml` read (HTTP 200). Endpoints: `GET /api/v0/transactions`, `GET /api/v0/partner-any-quotes`. Bearer JWT on all; 1 request per 5 s per partner (429 otherwise).
- `/transactions` params: `numberOfTransactions` (default 50, max 1000), `lastDepositAddress` + `lastDepositMemo` (cursor), `direction` (next/prev), `search`, `fromChainId`, `fromTokenId`, `toChainId`, `toTokenId`, `referral`, `affiliate`, `statuses`, `showTestTxs`, `minUsdPrice`, `maxUsdPrice`, `startTimestamp[Unix]`, `endTimestamp[Unix]` (both non-inclusive).
- Response fields: `originAsset`, `destinationAsset`, `amountIn`, `amountInFormatted`, `amountInUsd`, `amountOut`, `amountOutFormatted`, `amountOutUsd`, `appFees[{recipient, fee}]`, `referral`, `status`, `createdAt`, `createdAtTimestamp`, `nearTxHashes`, `originChainTxHashes`, `destinationChainTxHashes`, `depositType`, `recipientType`, `refundFee`, and others.
- There is no separate chain field: chain is encoded in the asset id.
- Only 1Click transactions are covered. Measured over the 30-day pull below, Explorer volume is 27 % of DefiLlama's volume for the same days (daily ratio 0.21 to 0.33), so the rest of Intents volume is not in this table.

*Update 2026-11-02, after the JWT was obtained (Partner Dashboard, key type "Explorer", `partners.near-intents.org`):*
- **JWT works.** One call returned HTTP 200 with a list; every field matched the OpenAPI schema. Sample in `docs/audit/explorer_sample.json` (token redacted). A page of 1,000 rows holds about 2 hours of traffic.
- **`appFees[].fee` is in basis points of `amountIn`.** Docs (`api-reference/oneclick/request-a-swap-quote.md`): "Fee for this recipient as part of amountIn in basis points". The data agrees: over 548 transactions of at least 20 USD with an app fee, the observed spread (1 - out/in) correlates 0.66 with the declared fee, and 90 % of them have a spread of at least the declared fee. With a partner key the fee is split 50/50 with 1Click (1Click keeps at least 20 bps; `resources/fees.md`), so the declared fee is the amount requested, not what the recipient nets.
- **Asset-id patterns** seen in real data: `nep141:<chain>-<address>.omft.near`, `nep141:<name>.omft.near`, other `nep141:...` (on NEAR), `nep245:v2_1.omni.hot.tg:<id>_<address>` and `1cs_v1:<chain>:<kind>:<id>`. My first parsing rule left 55 % of assets unknown; after handling all five patterns 0 % of the 30-day pull is unknown. HOT ids (for example `hot:56`) are left as raw ids, not mapped to chain names.
- **The cursor (`lastDepositAddress`) is unreliable.** On 2026-10-10, after ten correct pages, a request with the cursor returned the first page again (100 % overlap), and my loop repeated it from cache until I stopped it (CPU 913 s, 2.1 GB). The client now pages by moving the end timestamp back to the last row's second and dropping duplicates, stops with an error when a page adds nothing new, and caps a day at 200 pages. Checked with one real request at the stall point (998 new contiguous rows) and with a fake server in the tests.
- **Pull result** (`data/snapshot/explorer_1click_daily.parquet`): 89,210 rows for 2026-10-03 to 2026-11-01, 488,989 transactions (11,831 to 23,791 a day, median 15,960), 506 pages in about 57 minutes (about 7 s per request). The row count equals an independent recount of unique transactions from the cached pages, day by day.
- **Declared app fee** in the pull: 4.81 M USD on 1,051 M USD of volume (0.458 %). This is the requested fee summed over recipients, before the 50/50 split with 1Click.
- **Limitation of the table design:** `affiliate` joins all fee recipients of a transaction into one string and `fee_usd` is their sum, so fee per recipient cannot be recovered from this table. The raw pages are cached (685 MB for the 506 pages used, plus 178 MB of older unused pages from the cursor attempt, under `data/live/_cache/`, not committed), so F4 can rebuild the table at recipient level without new requests.

## Check 9: CoinGecko

No key. Keyless `GET /api/v3/coins/near/market_chart/range?vs_currency=usd&from=2026-10-01&to=2026-11-02` returned HTTP 200 with `prices`, `market_caps`, `total_volumes`: 769 hourly points. The keyed call and its rate limits are untested. **F2 finding:** a range starting 2025-05-10 returned HTTP 401, `error_code 10012`, "Public API users are limited to querying historical data within the past 365 days"; a range starting 2025-11-03 returned HTTP 200 and one starting 2025-10-31 returned the same 401.

## Check 10: cost

Sandbox project (no billing): the free quota is 1 TiB of queries per month, so no charge is possible and over-quota queries are rejected. List-price estimate at 6.25 USD per TB shown for scale only. About 43 GB billed so far across the 17 executed queries whose bytes were recorded (a few small early queries were not recorded).

| Planned query | Dry-run | List price | vs 10 GB limit |
|---|---|---|---|
| Wallet sweeps with deposit amounts from `receipt_actions.args`, since 2025-05-10 | 3,146 GB | 19.66 USD | over |
| Same, one 30-day chunk | 87 GB | 0.55 USD | over |
| `DEPLOY_CONTRACT` from `receipt_actions`, since 2025-05-10 (developer indicator) | 315 GB | 1.97 USD | over |
| `intents.near` FUNCTION_CALL per day from `receipt_actions`, since 2025-05-10 | 315 GB | 1.97 USD | over (same scan as the row above; run as one query) |
| Burn: `execution_outcomes` daily `tokens_burnt`, since 2025-05-10 | 181 GB | 1.13 USD | over |
| Burn: `transactions` daily `receipt_conversion_tokens_burnt`, since 2025-05-10 | 25 GB | 0.16 USD | over |
| `blocks` daily `total_supply`, since 2025-05-10 | 1.8 GB | 0.01 USD | ok |
| Wallet balances from `ft_balances_daily`, since 2025-05-10 | 0.98 GB | 0.01 USD | ok |

Takeaways:
- Do **not** read wallet flows from `receipt_actions.args`. Use `ft_balances_daily` (0.98 GB) and net out internal transfers. TRANSFER counts without amounts (no `args`) are still 432 GB for the same period.
- Burn needs about 206 GB (two tables) in chunks of at most ~10 GB, which means roughly monthly chunks and a per-query limit just above 10 GB, or fortnightly chunks.
- One full extract of burn plus the developer/activity scan is about 0.5 TiB, half the monthly sandbox quota. Re-running `make extract` more than once or twice in a month will hit the quota. Narrow the developer indicator window (for example the last 180 days) before F2.
- Dry-run sizes can differ from billed bytes (billed rounds up per table, minimum 10 MB).

## F2 ingestion (2026-11-02)

Run with `capture extract` (incremental by date, one parquet per table in `data/live/`), frozen with
`capture snapshot --freeze 2026-11-01` into `data/snapshot/` (snapshot v1). Windows follow the
Hybrid choice: activity tables from 2026-04-26, supply/burn from 2025-05-10, wallets from
2025-11-07. Only complete UTC days are stored.

| Table | Rows | block_date range | Source / SQL |
|---|---|---|---|
| `network_daily` | 190 | 2026-04-26..2026-11-01 | BigQuery, `sql/network_daily.sql` |
| `contracts_daily` | 211,845 | 2026-04-26..2026-11-01 | BigQuery, `sql/contracts_daily.sql` |
| `intents_onchain_daily` | 190 | 2026-04-26..2026-11-01 | BigQuery, `sql/intents_onchain_daily.sql` |
| `supply_daily` | 541 | 2025-05-10..2026-11-01 | BigQuery, `sql/supply_daily.sql` |
| `fee_wallet_inflows_daily` | 811 | 2025-11-07..2026-10-31 | BigQuery, `sql/fee_wallet_inflows_daily.sql` |
| `defillama_intents_daily` | 690 | 2024-12-10..2026-10-30 | DefiLlama (4 endpoints) |
| `price_daily` | 363 | 2025-11-04..2026-11-01 | CoinGecko (keyless) |
| `explorer_1click_daily` | 89,210 | 2026-10-03..2026-11-01 | Explorer API `/transactions` (added in snapshot v2) |

BigQuery cost of the extract: 37 queries, 258.57 GB billed (0.235 TiB; dry-run total 258.56 GB), largest
single query 10.36 GB against the 10.74 GB limit. Together with F1 (about 45 GB) roughly 0.3 TiB of the
1 TiB monthly sandbox quota is used. A second `capture extract` ran 0 queries and billed 0 bytes.

Definitions and limits (each is a property of the data, not a bug):
- `new_accounts` counts CREATE_ACCOUNT actions only. Implicit accounts are created by TRANSFER and are not counted, so the series undercounts new accounts.
- `unique_signers` (intents) is the distinct transaction signer of FUNCTION_CALL receipts to `intents.near`; `unique_callers` (contracts) is the distinct receipt predecessor. For relayed calls these are not end users.
- `fee_wallet_inflows_daily.amount` is the **net daily change** of the wallet's liquid balance (`ft_balances_daily`), not gross inflow. The first observed day of each wallet is empty (unknown). `amount_raw` is derived from a float64, accurate to about 15 significant digits. Transfers between the wallets are not netted yet (F3). Rule 2 exception: this table has no `block_date`; the filter is on its partition column `epoch_date`. It is held back one extra day (`lag_days=1`) because its partitions land later.
- `supply_daily.burnt_near` = receipts burn + transaction-conversion burn; both parts are kept as columns. `circulating_supply_near` is the float view (rule 6).
- DefiLlama: the last 3 days are dropped as not final (2026-10-31 showed 11,755 USD of fees against 127k to 388k on neighbouring days). The table is rebuilt from the full history each run; the second run revised 0 stored values. Revenue exceeds fees on 4 of the stored days.
- `price_daily.near_usd` is the price at 00:00 UTC of each day. Only NEAR is priced: no other token reaches the wallets.

Source gaps found (the data is missing at the source; nothing was filled in):
- `ft_balances_daily` has no rows for `fefundsadmin` and `1csfundsadmin` on 2026-04-17..2026-04-20. The change on 2026-04-21 for those two wallets spans 5 days (`days_since_prev` = 5).
- `circulating_supply` has no rows for 2026-04-18 and 2026-04-19 (`circulating_supply_near` empty).

Assumption that failed, fallback chosen (CLAUDE.md "stop and record"):
- **CoinGecko public API serves only the past 365 days.** Fallback: `price_daily` covers 363 days (2025-11-04 onward) and slides forward on later runs. Prices for 2025-05-10..2025-11-03 are unavailable, so USD values for supply, burn and DefiLlama days before 2025-11-04 cannot be computed from this source. Options for you: a paid CoinGecko key, or another price source (not adopted without your decision).

New or confirmed facts:
- BigQuery `INFORMATION_SCHEMA`-checked column names in the F2 SQL all executed without error.
- `receipt_actions` queries scale far less than the F1 extrapolation suggested: the 190-day activity window costs 43 to 47 GB per table; the 540-day equivalents are about 10 times more.
- The Explorer client (throttle 1 request per 5 s, on-disk cache, 429 retry, time-window pagination) was first tested against mocks only and then run against the real API after the JWT arrived; see Check 8. Snapshot v1 had no Explorer table; snapshot v2 adds it and leaves the other seven files byte-identical.

## F3 core model (2026-11-02)

Model in `src/capture/models/coverage.py` and `breakeven.py`, definitions in `docs/METHODOLOGY.md`,
output `site/public/data/coverage.json` (built from `data/snapshot/`, 66 offline tests).

**Transfers between revenue wallets** (needed so the buyback wallet's inflow is not counted twice).
A transfer into the buyback wallet is estimated from same-day moves and was checked against
receipts for every day on which a revenue wallet fell (`docs/audit/internal_transfers_validation.json`):

| Day | Estimate (NEAR) | Receipts |
|---|---|---|
| 2026-09-09 | 502,791.6 | `1csfundsadmin` to `buybacks`: 502,793.0 |
| 2026-07-14 | 7,274.2 | `1csfundsadmin` to `buybacks`: 7,274.0 |
| 2026-04-22 | not applicable (buyback wallet absent) | no transfer between the three wallets; 1cs paid an outside account |
| 2026-07-10 | not applicable (the buyback wallet fell) | no transfer between the three wallets; paid an outside account |

The estimator only treats a rise of the buyback wallet as a transfer in, never a fall. It can be wrong
if a wallet pays an outside account on the same day as an organic inflow; no such day exists in the
snapshot. It is not validated for future data.

**Monthly reconciliation** (on-chain wallet inflows x daily price vs DefiLlama `revenue_usd`,
tolerance 15%). All 10 complete months pass; none was excluded:

| Month | Deviation | Month | Deviation |
|---|---|---|---|
| 2025-12 | +11.0 % | 2026-05 | -2.5 % |
| 2026-01 | +3.5 % | 2026-06 | +5.1 % |
| 2026-02 | -2.0 % | 2026-07 | -4.6 % |
| 2026-03 | +0.8 % | 2026-08 | -1.6 % |
| 2026-04 | -6.7 % | 2026-09 | -4.8 % |

2025-11 (price starts 2025-11-04) and 2026-10 (DefiLlama ends 2026-10-30) are partial and not compared.
DefiLlama revenue also matches the wallets in 2026-02 to 2026-04, before the buyback wallet existed,
so that revenue was collected in `fefundsadmin` and `1csfundsadmin`. Whether any of it was used for
buybacks in that period is still unknown, so buyback value stays empty before 2026-04-27.

**Mutation checks** (the tests can fail): tolerance set to 5% makes the reconciliation test fail on
2025-12, 2026-04 and 2026-06 and print the table; removing the transfer netting fails two golden tests.

**Result for the 30 days ending 2026-10-06** (2026-09-07 to 2026-10-06), from `coverage.json`:

| Quantity | Value |
|---|---|
| CR_float 30d (NEAR) | 0.139 (buyback 335,408 + burn 34,338, over gross issuance 2,656,764 NEAR) |
| CR_float 30d (USD, daily prices) | 0.136 |
| CR_supply 30d (burn only) | 0.013 |
| CR_float 30d, DefiLlama proxy basis | 0.207 |
| Buyback only, wallet basis, no burn | 0.126 |
| Issuance in USD | 10.09 M at daily prices; 14.05 M at the 2026-10-06 price (5.29 USD) |
| Buyback in USD | 1.23 M (wallet, daily prices); 1.93 M (DefiLlama proxy) |

Comparison with the public reference you gave (issuance about 13 M USD, buybacks about 1.9 M USD,
ratio about 0.146; a Stocktwits post I could not verify, so it is a pointer, not a source, and none of
its numbers is used by the model or appears in the outputs). The model was not tuned to it. The
ratios are close, but three differences that roughly cancel explain why that is not a confirmation:
1. *Buyback basis.* The reference's 1.9 M USD matches DefiLlama's holders revenue (1.93 M), which is
   all captured revenue including `fefundsadmin`, a wallet that has never paid out. The wallet-only
   figure is 1.23 M. This is a hypothesis about how the reference was built, not something I can see.
2. *Valuation.* The price ranged from 2.30 to 5.39 USD inside the window (2.44 on its first day, 5.29
   on its last), so issuance is 10.1 M USD at daily prices and 14.1 M USD at the final price; the
   reference's 13 M lies between them.
3. *Definition.* CR_float includes burn (+0.013); the reference is buybacks over issuance.
Buyback only on the wallet basis is 0.126 against 0.146, 14% lower, and using DefiLlama's proxy at
the final price gives 0.137 (1.93 M over 14.05 M), 6% lower.

**Break-even volume** as of 2026-10-30: V* is 652 M USD per day against an actual 30-day average
Intents volume of 130 M USD per day (5.0x). tau_eff (30d) is 0.0548%. With only the buyback wallet's
inflow, tau falls to 0.0362% and V* rises to 986 M USD per day. The sensitivity grid is consistent with
that: inflation 2.5%, price 1x, tau 1x gives 654 M USD per day. Break-even scales linearly with price
because issuance is fixed in NEAR.

## F4 Distribution Map and developer indicator (2026-11-03)

Snapshot v3 frozen at 2026-11-01 (11 files, `data/snapshot/manifest.json`). Added: `contracts_daily`
(corrected SQL), `explorer_channels_daily`, `explorer_recipients_daily`, `token_assets`; refreshed
`explorer_1click_daily`. `make verify`: 114 passed. Outputs: `site/public/data/distribution.json`,
`developer.json`.

Facts relied on and how each was verified:
- **Explorer pull 2026-07-01..2026-11-01.** Same endpoint and pagination as Check 8 (time window, dedupe, stall
  guard, 1000 rows per page, 1 request per 5 s). Run to completion on the user's machine; the live table covers
  to 2026-11-02, the freeze trimmed it to 2026-11-01 (433,167 rows instead of 435,846). Verified by
  `capture verify-manifest data/live` and by the golden and integration tests that rebuild the three Explorer
  tables from the same cached pages.
- **Token list** `https://1click.chaindefuser.com/v0/tokens` (no key), stored as `token_assets` (210 assets,
  snapshot at pull time, no date column). Verified by use: `unmapped_share` is 0.0 in every month in
  `distribution.json`, so every origin asset in the window resolved to a symbol.
- **Stablecoin and ZEC groups** are a judgment on that list (`stablecoin_symbols` in `distribution.json`),
  not a source fact.
- **`contracts_daily.sql` correction:** deploy-only days are now kept. Re-pulled for 2025-09-22..2026-11-01
  (921,480 rows, 245 GB billed). The snapshot refreeze changed `query_sha256` to 70b53524...259c4.
- **near.com is not measurable.** No field identifies it, and the front-end wallet is almost never an app-fee
  recipient. `near_wallet_only_share` is a labelled proxy (volume of transactions whose fee recipients are only
  NEAR revenue wallets), not a near.com share.

Numbers (source: `distribution.json`, `developer.json`; Explorer covers 1Click only):

| Month | Explorer volume (M USD) | Share of DefiLlama volume | Channel HHI | Top-1 channel | Declared fee to NEAR wallets | Attributable share of on-chain revenue |
|---|---|---|---|---|---|---|
| 2026-07 | 1,073.5 | 48.7 % | 0.198 | 34.1 % | 9.5 % | 68.8 % |
| 2026-08 | 1,212.6 | 43.7 % | 0.201 | 35.8 % | 8.3 % | 47.1 % |
| 2026-09 | 1,513.8 | 31.5 % | 0.192 | 36.1 % | 5.6 % | 21.5 % |
| 2026-10 | 1,095.3 | 27.4 % | 0.214 | 40.1 % | 9.6 % | 21.9 % |

- Stablecoin share of volume 61.8 / 62.0 / 61.5 / 53.3 % (Jul to Oct). Asset HHI 0.237 / 0.249 / 0.235 / 0.199.
- `near_wallet_only_share` 7.7 / 6.5 / 17.1 / 22.3 %. The share of volume with no app fee fell from 34.8 % (Jul)
  to 7.7 % (Oct). I did not investigate why; no causal claim is made.
- Explorer coverage of DefiLlama volume keeps shrinking, so the Distribution Map describes a falling fraction
  of Intents volume. This is stated in `distribution.json` notes and must be repeated in THESIS.md.
- Developer indicator (window 2025-09-22..2026-11-01, 30-day burn-in): 3,791 deploying accounts, 494 dropped in
  the burn-in, 137 already existing. Cohort 2026-08: 85 new contracts, 45.9 % still called in month +1. Cohort
  2026-09: 467, 31.3 %, with parent `near` behind 17.6 % of it.
- **Lead/lag verdict: null.** Lag 0 was best in training (r = -0.72); in the test months r = +0.90 on 5 pairs,
  permutation p = 0.19, alpha 0.1. Lags 2 and 3 have fewer than 4 pairs and report no correlation. The signs flip
  between train and test, so the result cannot be told apart from chance (CLAUDE.md rule 5: reported as is).

Open limits: Explorer volumes are requested amounts and declared fees are split with 1Click under a partner
key; recipient volumes do not add up because a transaction with several recipients counts in each.
`gcloud-login.sh` in the repo root is an untracked local helper and is not part of F4.

## F5 Valuation Lab (2026-11-03)

Offline from `data/snapshot` (v3); no new external source and no BigQuery query. Output:
`site/public/data/valuation.json` (10,000 paths, 60 months, seed `config.RANDOM_SEED`).

Facts relied on and how each was handled:
- **Inflation 2.5 %.** Matches the observed net supply growth of 2.467 to 2.479 % (Check 6) and the derived
  gross issuance of the start window: 2,692,593 NEAR modelled against 2,691,996 NEAR measured over
  2026-10-01..10-30 (0.02 % apart; computed in this session from `supply_daily`).
- **Inflation 1.6 % ("proposal").** **Not verified.** It was supplied by the user, no source is recorded in the
  repo (it was already in the F3 sensitivity grid without one). `valuation.json` labels it "a scenario supplied by
  the user and not verified against a source". If a source is found, record the link here and drop the label.
- **Volume** is DefiLlama's `volume_usd` (Check 7, assumed to be Intents volume). Growth sample: monthly mean of
  daily volume, 2025-06..2026-10, 16 monthly changes (2026-10 has 30 of 31 days, so a mean is used, not a sum).
- **tau (buyback basis)** from `fee_wallet_inflows_daily` (buyback wallet from 2026-04-26) and `price_daily`;
  monthly values need 90 % of the month's days observed in both series, which leaves 2026-05..2026-10.

Numbers (source: `valuation.json`, as of 2026-10-30):
- Start: volume 130.4 M USD/day (30d), NEAR 4.05 USD, supply 1,310.4 M NEAR, burn 1,291 NEAR/day,
  tau buyback 0.0362 %, tau all revenue 0.0548 %.
- Month 0 CR at the latest price 0.144; measured CR_float (30d) 0.122; model at the window's mean price (4.92)
  0.121. The gap is the price: it fell from 5.34 to 4.05 inside the window, and buyback USD converted at a lower
  price buys more NEAR (349.6 K modelled at the latest price, 289.4 K bought in the window).
- tau monthly range 0.0150 % (2026-07) to 0.0362 % (2026-10): the current value is the maximum.
- Reverse break-even, required annual growth of 30d volume (V* in M USD/day; buyback basis / all-revenue basis):

| Inflation | V* buyback | V* revenue | 1 year | 3 years | 5 years |
|---|---|---|---|---|---|
| 2.5 % | 989.9 | 654.3 | +659 % / +402 % | +96.5 % / +71.2 % | +50.0 % / +38.1 % |
| 1.6 % | 628.3 | 415.3 | +382 % / +219 % | +68.9 % / +47.1 % | +37.0 % / +26.1 % |

- Monte Carlo at a constant price, inflation 2.5 %, P(CR >= 1) at months 12 / 36 / 60, median first month:
  - historical: 45 % / 96 % / 99.7 %, month 12; median volume 1.2 B / 132 B / 13.8 T USD per day.
  - decay: 33 % / 59 % / 61 %, month 15; median volume 0.65 B / 2.7 B / 3.9 B USD per day.
  - flat: 9 % / 21 % / 28 %, month 59; median volume about 120 / 136 / 145 M USD per day.
  - With the ramp to 1.6 %: flat 11 % / 26 % / 31 % (month 47); decay 37 % / 65 % / 66 %.
  - At 2x the price, flat is 5 % / 15 % / 22 % and "not reached" at 2.5 %; at 0.5x it is 16 % / 28 % / 34 %.

How to read them (also in `valuation.json` notes and METHODOLOGY.md):
- The historical and decay scenarios inherit a mean growth of +0.191 per month (std 0.442) that is set by the
  launch phase; the mean from 2025-12 (11 months) is +0.006. The historical scenario's volumes after 36 months are
  not credible, so its probabilities near 1 are a consequence of them and are not evidence. The flat scenario is
  the only one that does not depend on the launch regime.
- The sample is 16 monthly changes (14 overlapping blocks of 3) and 6 months of tau, which was rising.
- The drawn tau is below the current one on average, so the flat median CR starts below the measured CR.
- A variant of the historical scenario that starts after the launch phase was offered and not added (outside the
  spec): it would be the natural next step if a less launch-driven upside case is wanted.

## F6 dashboard data layer (2026-11-03)

New outputs from `make build`: `summary.json` (hero, week-on-week CR, ledger, levers, conditions),
`queries.json` (SQL text or API request per input table), `provenance.json` (hashes, ranges,
reconciliation, proof slot), `markers.json` (dated events). New reference data: `data/reference/events.csv`
with its own `manifest.json` (checked by `make verify`).

Facts relied on and how each was verified:
- **Issuance step 2025-10-30 (data).** `issuance_gross_near` from `supply_daily`: 14-day mean about 176,237 NEAR/day
  before and 88,823 after; 2025-10-28 159,697, **2025-10-29 140,649 (transition day)**, 2025-10-30 84,444. The
  30-day annualised net supply growth is 5.00 % up to 2025-10-29 and about 2.45 % from 2025-11-29. Crypto Briefing
  (2026-10-02) mentions an earlier governance change from 5 % to 2.5 %; its date is not stated there, so the
  marker is dated from the data only.
- **HSP-029 (resolves the F5 "1.6 % not verified" label).** The Defiant names HSP-029 and says it "would lower
  issuance over 24 months after a 90-day grace period", target 1.6 %; Crypto Briefing (2026-10-02) gives 2.5 % to
  1.6 %, 24 months, a 90-day grace period, steps "every epoch". Both read with web fetch on 2026-11-03. **The vote
  result was not found**, so the ramp stays a scenario. The Valuation Lab ramp now waits 3 months before falling
  (`INFLATION_GRACE_MONTHS`); with the grace period the ramp results change by at most about 1 point (decay at
  month 12: 37 % to 36 %; flat 11 / 26 / 31 %, median month 47, unchanged).
- **Fee switch 2026-02-23 (reported).** Several secondary reports agree on the date; no primary NEAR Foundation
  post was found. URLs in `events.csv`.
- **Intents exploit 2026-10-01 (reported).** Several outlets and a status-page "1Click API incident"; 1Click
  services were halted. No technical post-mortem was read. URLs in `events.csv`. The label carries no amount.
- **Not drawn:** nearcore 2.14 (only 2.14.0-rc.1 found, no mainnet activation date); HSP-029 outcome (vote result
  not found).

Numbers (source: `summary.json`, 30 days 2026-10-01..2026-10-30):
- Per 10,000 USD of Intents volume: fees 16.01, revenue 5.48 (DefiLlama), 5.53 reaching NEAR wallets
  (on-chain), **3.62 reaching the buyback wallet**, burn 0.49, against issuance worth 33.91.
- Kept at each step: fees 0.160 % of volume; revenue 34.2 % of fees; on-chain 100.9 % of DefiLlama revenue;
  **65.5 % of on-chain revenue reaches the buyback wallet**.
- Lever bridge: volume must grow 7.59x today; inflation to 1.6 % closes 1.575x (to 4.82x); all revenue to buybacks
  closes 1.513x (to 3.18x). V* 989.9, 628.3, 415.3 M USD/day.
- Conditions: volume 13.2 % of V*; routing 65.5 % of 1.0; reconciliation worst 11.0 % against 15 % (not triggered).
- Hero: 12 cents per USD of new NEAR (CR_float in USD 0.1196, 30 days to 2026-10-31); this week 0.120, prev 0.118.

## Original open questions

| # | Question | Status | Where answered |
|---|---|---|---|
| Q1 | BigQuery freshness after NEAR Lake deprecation | Closed: fresh to 2026-11-02 | Check 1 |
| Q2 | Full ids of revenue wallets | Closed (1csfundsadmin only confirmed via revenue.near.org and chain state) | Check 4 |
| Q3 | How Intents fees move | Closed: native NEAR TRANSFER after `native_withdraw` | Check 4 |
| Q4 | Explorer API access | Closed 2026-11-02: JWT works, 30 days pulled | Check 8 |
| Q5 | DefiLlama endpoints | Closed | Check 7 |

## Gate 1 decision (recommendation, needs your confirmation)

Overall: **GO-WITH-FALLBACK**. The gate box in `PROGRESS.md` is left unticked until you confirm.

| Source | Decision | Scope and fallback |
|---|---|---|
| BigQuery | **GO-WITH-FALLBACK** | Fresh. Use `ft_balances_daily` for wallet balances (net out internal transfers), `blocks`/`circulating_supply` for supply, chunked `execution_outcomes` + `transactions` for burn. Developer indicator over a shortened window. Budget about 0.5 TiB per full extract |
| NEAR RPC (archival) | **GO** | Net supply and account state, no key. Gross issuance not available from `total_supply` alone |
| DefiLlama | **GO** | Independent cross-check for fees and revenue (matched on-chain within 1.6 % over 30 days); fees, volume and TVL history is 540 days or less. `dexs` as Intents volume must be confirmed before using it for tau_eff |
| Explorer API | **GO-WITH-FALLBACK** (update 2026-11-02: JWT obtained, now GO for 1Click only, see Check 8) | Blocked on a JWT. Without it, fees by channel/affiliate (Distribution Map: fees by channel, HHI, near.com share) is not computable beyond the wallet split, and the module is reported "unavailable" for the missing part |
| CoinGecko | **GO** | Keyless works; key optional |
| Buyback destination | **GO-WITH-FALLBACK** | Define buyback value as inflow to `buybacks.multisignature.near` from 2026-04-26. Before that: "unavailable, destination unknown". Report captured revenue (all three wallets, internal transfers netted) separately, and keep it distinct from NEAR actually held in the buyback wallet. No burn is observed, so burn value in the coverage ratio is gas burn only |

Resulting scope:
- Coverage ratio CR = (buyback value + burn value) / gross issuance value: computable from 2026-04-26 for buybacks and from 2025-05-10 for gas burn; gross issuance needs a source other than net `total_supply` or must be reported as net issuance with that label.
- Break-even volume V*: needs `tau_eff` = revenue / volume from DefiLlama (volume definition to confirm).
- Not computable without more input: channel-level fee distribution (needs a JWT) and the buyback series before 2026-04-26.

## Facts worth correcting in CLAUDE.md (not edited, your call)

- Revenue wallets are `fefundsadmin.sputnik-dao.near`, `1csfundsadmin.sputnik-dao.near`, plus `buybacks.multisignature.near`.
- Intents fees reach them as native NEAR transfers from `intents.near`, not NEP-245 balances moving to the wallets.
- No `receipts` view; extra tables `ft_balances_daily`, `circulating_supply`, `ft_events`, `transaction_actions`.
- `INTENTS_JWT` in the F1 prompt is `INTENTS_EXPLORER_JWT` in `.env.example`; `COINGECKO_API_KEY` was added.

## Log

### 2026-11-02, F1
- Ran checks 1 to 10. BigQuery access: ADC login on the user's Google account, sandbox project, `BQ_MAX_BYTES` 10 GiB.
- Tooling: uv 0.13.6, GNU make 4.4.1, Google Cloud SDK (for ADC only).
- Mistakes made and fixed during the run: a wrong column name in one `account_changes` dry-run (fixed, see Check 2), a loose block-height search for the 30-day supply point (actual days reported instead), and a BigQuery `accounts` scan that was rejected for cost before execution.

### 2026-11-02, F2
- Ingestion implemented and run; see "F2 ingestion". Snapshot v1 frozen at 2026-11-01. Manifests now carry `query_sha256`, and a test fails if a SQL file changes after its snapshot was taken.
- Corrected the F1 burn statement in Check 6 (it rested on a single day).
- Mistakes made and fixed: a missing `DATASET` constant (caught by a test), an over-strict test for missing values, and a 91-day request padding for CoinGecko that would have broken at the 365-day boundary (removed).

### 2026-11-02, F2 follow-up (Explorer)
- JWT obtained and verified; 30-day pull completed after fixing a pagination loop (Check 8). Snapshot v2 frozen at 2026-11-01.
- Mistake made and fixed: I trusted the API's cursor without a stall check, so a repeated page looped from cache for about 25 minutes before I noticed. The pagination, its guards and tests were replaced.

### 2026-11-03, F4
- Explorer back-pull completed after a PC shutdown interrupted it; snapshot v3 frozen at 2026-11-01; see "F4 Distribution Map and developer indicator".
- Mistake made and fixed: I estimated the remaining pull time from an early page rate (17 pages per day) that had almost doubled by September, so the estimate was too low. Estimates of this kind are unreliable because the volume per day keeps changing.

### 2026-11-03, F5
- Valuation Lab implemented test-first; see "F5 Valuation Lab".
- Mistake made and fixed: my first month-0 test asked for a 15 % match between the model and the measured CR_float and failed at 18 %. I checked before loosening it: the gap was the price (fell 5.34 to 4.05 in the window) and issuance matched to 0.02 %, so the test now compares at the window's mean price and the output states the gap.
- Mistake made and fixed: a first run showed a historical-scenario median CR of about 9,500 at month 60. That is the launch-phase growth extrapolated, so the output now carries the implied median volume and the notes say what the probabilities rest on.

### 2026-11-03, F6
- Data layer for the dashboard; see "F6 dashboard data layer".
- Mistake made and fixed: my first "what would change our mind" design had a volume condition and a take-rate condition. They are the same ratio (V0 / V* = tau / tau-needed), so the second was replaced by revenue routing, which moves independently. A test now guards against the duplicate.
- Mistake made and fixed: I expected the issuance marker on 2025-10-30 (from the phase prompt). The detector first returned 2025-10-29, a transition day; the marker is now dated to the first day closer to the new level and names the transition day.
- Bug found and fixed (existing since F4): on Windows the manifest lock failed with PermissionError when a previous lock file was still being deleted, losing manifest entries under concurrent upserts (the concurrency test failed 2 times in 5). The lock now retries on PermissionError; a deterministic test reproduces the case, and the concurrency test passed 12 times in 12.

