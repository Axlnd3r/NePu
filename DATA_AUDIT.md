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
| 8 | Explorer API | params, fields, one JWT call | Spec read and saved. No JWT available, so no call made. `appFees.fee` unit undocumented | `intents_explorer_openapi.yaml` | **PARTIAL** | DefiLlama for fees/volume; Distribution Map degraded |
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
- There is no separate chain field: chain is encoded in the asset id. The unit of `appFees.fee` is not documented (example value 50, plausibly basis points); unverified.
- Only 1Click transactions are covered (CLAUDE.md); coverage of non-1Click flow is unknown.
- **No JWT was available** (not in `.env`, not in the environment), so no call was made and no sample saved.

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
| `explorer_1click_daily` | not pulled | - | needs `INTENTS_EXPLORER_JWT` |

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
- The Explorer client is implemented and tested against mocks only (throttle 1 request per 5 s, on-disk cache, pagination, 429 retry). Not exercised against the real API: no JWT. `fee_usd` is left empty because the unit of `appFees[].fee` is undocumented, and the chain derived from asset ids is an unverified heuristic.

## Original open questions

| # | Question | Status | Where answered |
|---|---|---|---|
| Q1 | BigQuery freshness after NEAR Lake deprecation | Closed: fresh to 2026-11-02 | Check 1 |
| Q2 | Full ids of revenue wallets | Closed (1csfundsadmin only confirmed via revenue.near.org and chain state) | Check 4 |
| Q3 | How Intents fees move | Closed: native NEAR TRANSFER after `native_withdraw` | Check 4 |
| Q4 | Explorer API access | Open: needs a JWT | Check 8 |
| Q5 | DefiLlama endpoints | Closed | Check 7 |

## Gate 1 decision (recommendation, needs your confirmation)

Overall: **GO-WITH-FALLBACK**. The gate box in `PROGRESS.md` is left unticked until you confirm.

| Source | Decision | Scope and fallback |
|---|---|---|
| BigQuery | **GO-WITH-FALLBACK** | Fresh. Use `ft_balances_daily` for wallet balances (net out internal transfers), `blocks`/`circulating_supply` for supply, chunked `execution_outcomes` + `transactions` for burn. Developer indicator over a shortened window. Budget about 0.5 TiB per full extract |
| NEAR RPC (archival) | **GO** | Net supply and account state, no key. Gross issuance not available from `total_supply` alone |
| DefiLlama | **GO** | Independent cross-check for fees and revenue (matched on-chain within 1.6 % over 30 days); fees, volume and TVL history is 540 days or less. `dexs` as Intents volume must be confirmed before using it for tau_eff |
| Explorer API | **GO-WITH-FALLBACK** | Blocked on a JWT. Without it, fees by channel/affiliate (Distribution Map: fees by channel, HHI, near.com share) is not computable beyond the wallet split, and the module is reported "unavailable" for the missing part |
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

