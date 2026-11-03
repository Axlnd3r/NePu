# Methodology

Formulas, sources and limitations of the NEAR Capture Ledger. Every result quoted anywhere in the
project is produced from the tables in `data/snapshot/` (listed in its `manifest.json`); this
document states definitions and never quotes results. Data checks behind these choices are in
`DATA_AUDIT.md`.

## Inputs

| Table | Source | Used for |
|---|---|---|
| `supply_daily` | BigQuery `blocks`, `execution_outcomes`, `transactions` | total supply, burn |
| `fee_wallet_inflows_daily` | BigQuery `ft_balances_daily` | revenue wallet balance changes |
| `defillama_intents_daily` | DefiLlama | volume, fees, revenue, holders revenue |
| `price_daily` | CoinGecko | NEAR/USD at 00:00 UTC |

Days are UTC days. Only complete days are stored. Supply and burn are in NEAR (yoctoNEAR / 1e24).

## Definitions

Let `d` be a day and `w` a window length in days.

- **Gross issuance**: `issuance_gross_near(d) = total_supply(d) - total_supply(d-1) + burnt_near(d)`.
  `total_supply(d)` is the supply at the last block of day `d`. `burnt_near(d)` is gas burnt that
  day (receipts plus transaction conversion). Supply growth is net of burn, so adding burn back
  gives what was minted.
- **Buyback (NEAR)**: `buyback_near(d)` is the NEAR that reached the buyback wallet
  `buybacks.multisignature.near` from outside the revenue wallets. It is the positive part of the
  wallet's net daily balance change minus the estimated transfer in from the other revenue
  wallets (see Transfers). The series starts the day after the wallet first appears in the data.
  Earlier days are empty, not zero: the buyback destination before that is unknown.
- **Buyback proxy**: `buyback_near_proxy(d) = holders_revenue_usd(d) / near_usd(d)`, from DefiLlama.
  It equals all captured revenue, including wallets that only hold NEAR, so it is an upper-side
  proxy and is always labelled as such.
- **CR_float(d, w)** `= sum(buyback_near + burnt_near) / sum(issuance_gross_near)` over days
  `d-w+1 .. d`, with `w` in 7, 30 and 90. The float view: buybacks take NEAR out of circulating
  float but not out of total supply.
- **CR_supply(d, w)** `= sum(burnt_near) / sum(issuance_gross_near)`. The total-supply view:
  buybacks do not reduce total supply, so only burn counts (CLAUDE.md rule 6).
- **CR_float in USD**: the same as CR_float with every day's flows valued at that day's price.
- **tau_eff(d, w)** `= sum(revenue_usd) / sum(volume_usd)` over the window, from DefiLlama. It is
  empty (not zero) where the window has no revenue.
- **V\*(d)** `= (avg_30(issuance_gross_near) * near_usd(d) - avg_30(burnt_near * near_usd)) / tau_eff(d, 30)`.
  The daily Intents volume, in USD, at which revenue at the current effective rate equals net
  issuance in USD. A negative numerator (burn above issuance) gives 0.
- **Sensitivity grid**: V\* for annual inflation `i` in 2.5% and 1.6%, a price of 0.5x, 1x and 2x
  the current price, and `tau_eff` of 0.5x, 1x and 1.5x the current value. Issuance per day is
  `i * total_supply / 365` NEAR. Burn is held constant in NEAR, so its USD value moves with the
  price multiple.
- **tau_eff_buyback**: a labelled variant using only the buyback wallet's inflow in USD instead of
  all captured revenue, because CR uses the buyback wallet only while `tau_eff` uses all revenue.

A rolling value needs every day of its window to have every input (`min_periods = w`); otherwise it
is empty. A missing input is never replaced by zero or by a shorter average.

## Transfers between revenue wallets

The revenue wallets are `fefundsadmin.sputnik-dao.near`, `1csfundsadmin.sputnik-dao.near` and
`buybacks.multisignature.near`. Moving NEAR from one to another is not new revenue and must not
be counted twice. The balance table shows only net daily changes, so a transfer into the buyback
wallet is estimated: when another revenue wallet falls by at least 1 NEAR and the buyback wallet
rises on the same day, the transfer is the smaller of the two moves. A fall of the buyback wallet
itself is never a transfer in. This was checked against receipts for every day on which a revenue
wallet fell (`docs/audit/internal_transfers_validation.json`). The estimate can be wrong if a
wallet pays out to an outside account on the same day as an organic inflow to the buyback wallet.

Source gaps: when the source skips days, the first change after the gap already contains the whole
gap, so days missing inside a wallet's observed span are set to 0 for the monthly reconciliation
(the sum is preserved). The buyback series does not use this.

## Reconciliation

For each complete calendar month in which every day has a price, a DefiLlama revenue and a wallet
change, on-chain revenue (NEAR that entered the three wallets from outside them, valued at each
day's price) is compared with DefiLlama's revenue.

Reconciliation tolerance: 15%

The tolerance is a starting value. If a month fails, the table is reported and the tolerance is not
loosened silently: changing it requires changing this line and the constant
`RECONCILIATION_TOLERANCE` in `src/capture/models/coverage.py` in the same commit, which a test
enforces.

## Invariants (tested in `tests/test_invariants.py`)

- Every coverage ratio is finite and not negative; CR_float is never below CR_supply.
- `tau_eff` is above 0 and below 1%.
- Annualised gross issuance after 2025-10-30 is between 1.5% and 3% of supply.
- A ratio is empty exactly when some day of its window lacks an input.
- Golden fixture: a 3-day hand-made example with the expected values worked out in the test.

## Distribution Map (`distribution.json`)

Who brings Intents volume and fees, and how concentrated it is. Built by
`src/capture/models/distribution.py` from the tables below.

| Table | Source | Used for |
|---|---|---|
| `explorer_1click_daily` | Explorer API `/transactions` | volume and fee by origin asset, fee recipients |
| `explorer_channels_daily` | same pages | volume, fee and transactions by channel |
| `explorer_recipients_daily` | same pages | declared fee by recipient |
| `token_assets` | public 1Click token list | asset id to symbol |
| `defillama_intents_daily` | DefiLlama | take rates; Explorer coverage |

**Scope.** The Explorer API only returns 1Click transactions, so every Explorer-based number
describes that part of Intents. `explorer_share_of_defillama_volume` states how large it is.
Only successful transactions are used. The three Explorer tables are built from the same raw
pages and always cover the same days.

**Definitions.** Periods are calendar months or weeks starting on Monday. A period is
`complete` only if every one of its days lies inside the Explorer date range; partial periods
are shown but flagged and are not comparable with complete ones.

- *Volume* of a transaction is `amountInUsd` (the origin amount valued by the API).
- *Channel* is the transaction's `referral` string; a transaction without one is `(none)`.
  Referral is a free-text label chosen by the integrator, so one partner can appear under
  several labels and a label does not prove who the end user's front end was.
- *Declared fee* of a recipient is `amountInUsd x fee / 10,000` (fee is in basis points of the
  input amount). It is the amount requested. With a partner key it is split 50/50 with 1Click,
  so it is not what the recipient nets.
- *Share* of a channel (or asset) is its volume divided by the period's total volume.
- *HHI* is the sum of squared shares, between 1/n and 1. *Top-5 share* is the sum of the five
  largest shares.
- *Asset* is the symbol of the origin asset from the token list. The same symbol on several
  chains is one asset. An asset id missing from the list is `(unmapped)` and its share is
  reported. *Stablecoins* are the USD-pegged symbols listed in `distribution.json`
  (`stablecoin_symbols`); yield-bearing vault shares and EUR/GBP tokens are not included. This
  list is a judgment.
- *Revenue attribution*: `declared_fee_share_to_near` is the declared fee whose recipient is one
  of the three NEAR revenue wallets divided by all declared fee. `attributable_share` divides the
  declared fee to those wallets by the on-chain revenue of the same days (NEAR entering the
  wallets from outside them, valued at each day's price, as in the reconciliation). What is left
  has no per-transaction source in this data and is not allocated to any channel.
- *near.com* cannot be measured: no field identifies it and the front-end wallet is hardly ever
  an app-fee recipient. `near_wallet_only_share` is a proxy for NEAR-run flow (volume whose fee
  recipients are only NEAR revenue wallets); `no_app_fee_share` is volume with no app fee. Neither
  is called near.com.
- *Take rate* (DefiLlama, per month): fees (or revenue) divided by volume, using only days where
  all three values exist. It covers the whole history and all of Intents, unlike the Explorer
  figures.

**Limitations.**
- 1Click only: the rest of Intents volume is not in the Explorer tables.
- A transaction with several fee recipients counts in each recipient's volume, so recipient
  volumes do not add up; channel and asset volumes do. Fee adds up in all tables.
- Most on-chain revenue is not explained by app fees to NEAR wallets; the unexplained part may
  come from flows this data does not contain, which is not tested here.
- The token list is a copy taken at pull time; symbols and the list can change.
- If the Explorer tables are absent (no JWT), the file contains only DefiLlama take rates and
  says so.

## Developer indicator (`developer.json`)

Whether newly deployed contracts stay in use, and how that moves with revenue. Built by
`src/capture/models/developer.py` from `contracts_daily` and `defillama_intents_daily`.

**Definitions.**
- A *new contract* is an account whose first observed `DEPLOY_CONTRACT` falls at least 30 days
  after the first day of data (burn-in) and which had no row, call or deploy, before that day.
  `contracts_daily` keeps deploy-only days, so a contract first called the day after it was
  deployed is still seen as new.
- A *cohort* is the calendar month of that first deploy. A cohort is `complete` only if its
  whole month lies after the burn-in and inside the data; the first and last cohorts are cut
  short and are shown but not used in the test.
- A contract is *active* in a month if it received at least one FUNCTION_CALL in it. *Retention
  at lag k* is the share of the cohort active in month +k, for k = 1, 2, 3. A month that is not
  complete in the data gives an empty value, never a share computed on part of a month. A
  stricter variant requires at least ten calls in the month.
- *top_parent_share* is the share of a cohort held by its most common parent account
  (`a.factory.near` has parent `factory.near`), to show when one deployer inflates a cohort.
- The series *retained new contracts* `x(t)` is the number of contracts first deployed in month
  t-1 that are active in month t, from complete cohorts. `y(t)` is DefiLlama revenue in USD for
  complete months.

**Lead/lag test.** For lags 0 to 3 months, pairs are `(x(t), y(t + lag))`, in levels and in
first differences. Training pairs have both months before 2026-05 and test pairs start on or
after it, so no test pair is used to look at the training sample. With fewer than 4 pairs no
correlation is reported and the row says why. For each correlation the p-value comes from
permuting `y`: all permutations when n is at most 8, otherwise 10,000 draws with a fixed seed.
The *verdict* takes the lag with the largest absolute training correlation (levels) and reports
its test correlation; it is `association` only if the test p-value is below 0.1 and the sign
matches training, `null` otherwise, and `insufficient_data` if a lag cannot be estimated.

**Limitations.**
- A deploy can be an upgrade of an older contract. The burn-in and the no-earlier-row rule
  reduce this but cannot remove it for a contract that was idle in the whole window.
- Calls made by the deployer count as activity.
- The test uses about a dozen monthly points, so it has little power; lags that need more pairs
  than exist are left empty. A null result is expected and says only that nothing can be told
  apart from chance with this data.
- Both series are trending and are affected by the same market conditions. A correlation, in
  either direction, describes how two short series moved together. It does not show cause or
  effect.

## Valuation Lab (`valuation.json`)

Two outputs, both conditional on stated assumptions and neither a forecast. No price is predicted
and no price target is given (CLAUDE.md rule 7).

**Model.** With V the 30-day average daily Intents volume (USD), tau the buyback take rate, P the
NEAR price, S the total supply, i the annual inflation and b the gas burn in NEAR per day:

    CR = (tau x V + b x P) / (i x S / 365 x P)        CR = 1  <=>  V = V*(i, tau)

V* here is the same break-even as in the sensitivity grid (a test checks they agree). The start
is measured at the last day where every input exists: V, b (30-day averages), tau (buyback wallet
inflow in USD / volume, 30 days), S and P.

**1. Reverse break-even.** Required compound annual growth of V to reach V* in 1, 3 and 5 years,
`(V* / V0)^(1/T) - 1`, with tau and P at their current values, for i = 2.5 % and 1.6 %, on two
bases of tau: the buyback wallet (the basis of CR_float, used in the Monte Carlo) and all protocol
revenue (the definition in CLAUDE.md, shown for comparison). A negative value means volume could
fall and still reach V*.

**2. Monte Carlo.** 10,000 paths, 60 monthly steps, seed `config.RANDOM_SEED`; every run uses the
same draws (common random numbers), so runs differ only in the assumption being varied.
- *Growth sample:* monthly log change of the monthly average of daily volume (DefiLlama) from
  2025-06, drawn as consecutive blocks of 3 months (moving blocks, no wrap-around, 14 blocks from
  16 monthly changes). `n_months`, mean and standard deviation are in the output.
- *Scenarios:* **historical** uses the draws as they are. **flat** subtracts the sample mean from
  every draw: zero drift, historical volatility. **decay** is flat plus the sample mean times
  `0.5^((t-1)/12)`, so the expected growth halves every 12 months and volatility does not decay.
  For a positive sample mean this orders the three paths one by one: flat <= decay <= historical.
- *tau:* one value per path, uniform between the lowest and highest observed monthly buyback take
  rate (months with at least 90 % of their days observed in both series).
- *Inflation:* 2.5 % constant, or linear from 2.5 % to 1.6 % over 24 months and then held.
  2.5 % is the observed net supply growth (DATA_AUDIT.md Check 6). **The 1.6 % figure is a
  scenario supplied by the user; no source for it is recorded, and it is labelled as such.**
- *Price:* **held constant in USD at its latest value in every run.** It is not simulated and not
  predicted. Runs at 0.5x and 2x of that value are sensitivities: the buyback is tau x V in USD,
  so a lower price buys more NEAR per issued NEAR and raises CR, while burn is in NEAR.
- *Supply and burn:* S at its latest value (as in V\*), b at its 30-day average.
- *Output per run:* P(CR >= 1) at months 12, 36 and 60 (the share of paths above 1 in that month,
  not "ever"); the share of paths that ever reach 1; the median month of the first CR >= 1 over
  all paths, or "not reached" when fewer than half of the paths get there; p10, p50 and p90 of CR
  per month; and the median volume the run implies (`volume_p50_usd_per_day`).

**Checks (`tests/test_valuation_golden.py`, `tests/test_valuation.py`).** Hand-computed CR (0.8,
and 0.425 at twice the price), the equality with the sensitivity grid, probabilities in [0, 1],
identical output for the same seed and different output for another, scenario C never more
optimistic than A on the median (and B between them), CR falling as the price multiple rises and
as inflation falls, and a month-0 check against the measured CR_float.

**Reading the results.**
- *The historical and decay scenarios inherit the launch phase.* The mean monthly log growth of the
  sample is far above its mean after 2025-12 (see `growth.mean_all` and `growth.mean_after_launch`).
  Extrapolated for 60 months it implies volumes far outside anything observed
  (`volume_p50_usd_per_day`), so a probability near 1 there is a consequence of that volume, not
  evidence about future behaviour. The flat scenario is the one that does not rely on it.
- *Month 0 versus the measurement.* The buyback is USD converted at the price used. At the latest
  price the model starts above the measured CR_float because the NEAR price fell during the 30-day
  window; at the window's mean price it reproduces it (`start.cr_model_month0_at_window_price`).
  Issuance at 2.5 % agrees with the derived gross issuance of the same window to within 0.1 %.
- *The tau range sits mostly below the current tau.* The latest month is its maximum, so the drawn
  tau is below the current one on average and the flat scenario's median CR starts below the
  measured one.

**Limitations.** Sixteen monthly growth observations, six months of buyback tau (rising) and a
price held constant are thin. Real supply grows with issuance (not modelled, mildly optimistic).
The growth sample is DefiLlama volume, a third-party definition. Nothing here is a statement about
what volume, tau, inflation or price will be.

## Limitations of the coverage ratio

- Wallet data is end-of-day balance (float64), so a day with an inflow and an outflow shows only
  the net change. Outflows of the buyback wallet are ignored, not subtracted.
- Buyback value is NEAR received by the wallet. The data does not show whether any NEAR was
  bought on a market afterwards; fees are collected in NEAR and delivered to the wallet.
- Buybacks are not burns. The two coverage views are kept separate on purpose.
- Gross issuance is derived, not read from the protocol, and daily values are lumpy because rewards
  are minted per epoch. Use windows, not single days.
- DefiLlama revenue and volume are third-party; the last days of its history are not final and are
  dropped. DefiLlama's volume definition (`dexs`) is assumed to be Intents volume.
- Prices exist only for part of the history (CoinGecko public API serves 365 days), so USD views
  have a later start than NEAR views.
- Correlation is not causation; out-of-sample lag tests, including null results, are reported as
  they come (CLAUDE.md rule 5).
