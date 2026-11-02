-- network_daily: one row per block_date. Params: @start_date, @end_date (inclusive).
-- new_accounts counts CREATE_ACCOUNT actions only; implicit accounts are created by TRANSFER and
-- are not counted (DATA_AUDIT.md, F2 notes).
WITH tx AS (
  SELECT
    block_date,
    COUNT(*) AS tx_count,
    COUNT(DISTINCT signer_account_id) AS active_signers
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @start_date AND @end_date
  GROUP BY block_date
),
ra AS (
  SELECT
    block_date,
    COUNTIF(action_kind = 'CREATE_ACCOUNT') AS new_accounts,
    COUNTIF(action_kind = 'FUNCTION_CALL') AS function_calls
  FROM `bigquery-public-data.crypto_near_mainnet_us.receipt_actions`
  WHERE block_date BETWEEN @start_date AND @end_date
  GROUP BY block_date
)
SELECT block_date AS `date`, active_signers, tx_count, new_accounts, function_calls
FROM tx
JOIN ra USING (block_date)
ORDER BY 1
