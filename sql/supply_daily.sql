-- supply_daily: end-of-day total supply and gas burn, in NEAR (yocto / 1e24).
-- Params: @start_date, @end_date (inclusive).
-- burnt_near = tokens_burnt of execution outcomes + receipt_conversion_tokens_burnt of transactions
-- (DATA_AUDIT.md check 2). Values are FLOAT64 in the source: ~15 significant digits.
WITH blk AS (
  SELECT
    block_date,
    MAX(block_height) AS block_height,
    MAX_BY(total_supply, block_height) AS total_supply
  FROM `bigquery-public-data.crypto_near_mainnet_us.blocks`
  WHERE block_date BETWEEN @start_date AND @end_date
  GROUP BY block_date
),
eo AS (
  SELECT block_date, SUM(tokens_burnt) AS burnt_receipts
  FROM `bigquery-public-data.crypto_near_mainnet_us.execution_outcomes`
  WHERE block_date BETWEEN @start_date AND @end_date
  GROUP BY block_date
),
tx AS (
  SELECT block_date, SUM(receipt_conversion_tokens_burnt) AS burnt_conversion
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @start_date AND @end_date
  GROUP BY block_date
),
circ AS (
  SELECT
    block_date,
    MAX_BY(circulating_tokens_supply, computed_at_block_height) AS circulating_supply
  FROM `bigquery-public-data.crypto_near_mainnet_us.circulating_supply`
  WHERE block_date BETWEEN @start_date AND @end_date
  GROUP BY block_date
)
SELECT
  block_date AS `date`,
  block_height,
  total_supply / 1e24 AS total_supply_near,
  (burnt_receipts + burnt_conversion) / 1e24 AS burnt_near,
  burnt_receipts / 1e24 AS burnt_receipts_near,
  burnt_conversion / 1e24 AS burnt_conversion_near,
  circulating_supply / 1e24 AS circulating_supply_near
FROM blk
LEFT JOIN eo USING (block_date)
LEFT JOIN tx USING (block_date)
LEFT JOIN circ USING (block_date)
ORDER BY 1
