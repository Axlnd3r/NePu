-- intents_onchain_daily: FUNCTION_CALL receipts to the Intents verifier contract (intents.near).
-- Params: @start_date, @end_date (inclusive). unique_signers = distinct transaction signers.
SELECT
  block_date AS `date`,
  COUNT(*) AS calls_to_intents,
  COUNT(DISTINCT signer_account_id) AS unique_signers
FROM `bigquery-public-data.crypto_near_mainnet_us.receipt_actions`
WHERE block_date BETWEEN @start_date AND @end_date
  AND receipt_receiver_account_id = 'intents.near'
  AND action_kind = 'FUNCTION_CALL'
GROUP BY block_date
ORDER BY 1
