-- fee_wallet_inflows_daily (raw balances): end-of-day liquid NEAR balance of the revenue wallets.
-- Params: @start_date, @end_date (inclusive), @wallets (ARRAY<STRING>).
-- ft_balances_daily has no block_date column; its partition column is epoch_date, so the date
-- filter is on epoch_date (documented exception to CLAUDE.md rule 2). liquid is in NEAR units.
-- Daily changes are derived in Python (capture.extract.fee_wallets).
SELECT
  epoch_date AS `date`,
  account_id AS wallet,
  'NEAR' AS token,
  liquid AS balance_end
FROM `bigquery-public-data.crypto_near_mainnet_us.ft_balances_daily`
WHERE epoch_date BETWEEN @start_date AND @end_date
  AND account_id IN UNNEST(@wallets)
ORDER BY 1, 2
