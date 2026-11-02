-- contracts_daily: one row per (block_date, receiving account) with at least one FUNCTION_CALL.
-- Params: @start_date, @end_date (inclusive). unique_callers = distinct predecessor accounts.
SELECT
  block_date AS `date`,
  receipt_receiver_account_id AS contract_account,
  COUNTIF(action_kind = 'DEPLOY_CONTRACT') AS deploys,
  COUNTIF(action_kind = 'FUNCTION_CALL') AS function_calls_received,
  COUNT(DISTINCT IF(action_kind = 'FUNCTION_CALL', receipt_predecessor_account_id, NULL))
    AS unique_callers
FROM `bigquery-public-data.crypto_near_mainnet_us.receipt_actions`
WHERE block_date BETWEEN @start_date AND @end_date
  AND action_kind IN ('DEPLOY_CONTRACT', 'FUNCTION_CALL')
GROUP BY block_date, receipt_receiver_account_id
HAVING function_calls_received >= 1
ORDER BY 1, 2
