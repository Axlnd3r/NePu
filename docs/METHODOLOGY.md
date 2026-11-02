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

## Limitations

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
