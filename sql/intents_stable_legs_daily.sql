-- intents_stable_legs_daily: swap volume carried by stablecoin legs of NEAR Intents settlements,
-- counted once per swap, from the token_diff events intents.near logs (a cross-check of the volume
-- definition; a lower bound, since swaps with no stablecoin leg are not counted).
-- Params: @start_date, @end_date (inclusive); @stable_ids ARRAY<STRING> and @stable_decimals
-- ARRAY<INT64>, same order (the stablecoins of the 1Click token list, distribution.STABLECOIN_SYMBOLS).
-- A swap writes one token_diff entry per side (user and solver). An entry's stablecoin notional is the
-- larger of the stablecoins it received and gave; the day's once-counted volume is half their sum.
WITH stables AS (
  SELECT id, d AS decimals
  FROM UNNEST(@stable_ids) AS id WITH OFFSET i
  JOIN UNNEST(@stable_decimals) AS d WITH OFFSET j ON i = j
),
events AS (
  SELECT eo.block_date, eo.receipt_id, li, SAFE.PARSE_JSON(SUBSTR(l.element, 12)) AS ev
  FROM `bigquery-public-data.crypto_near_mainnet_us.execution_outcomes` AS eo,
    UNNEST(eo.logs.list) AS l WITH OFFSET li
  WHERE eo.block_date BETWEEN @start_date AND @end_date
    AND eo.executor_account_id = 'intents.near'
    AND l.element LIKE 'EVENT_JSON:%token_diff%'
),
entries AS (
  SELECT
    block_date,
    CONCAT(receipt_id, '/', CAST(li AS STRING), '/', CAST(di AS STRING)) AS entry_id,
    TO_JSON_STRING(JSON_QUERY(e, '$.diff')) AS diff
  FROM events, UNNEST(JSON_QUERY_ARRAY(ev, '$.data')) AS e WITH OFFSET di
  WHERE JSON_VALUE(ev, '$.event') = 'token_diff'
),
per_entry AS (
  SELECT
    entry_id,
    GREATEST(SUM(IF(v > 0, v, 0)), SUM(IF(v < 0, -v, 0))) AS notional
  FROM (
    SELECT
      entry_id,
      SAFE_CAST(REGEXP_EXTRACT(p, r':"(-?[0-9]+)"$') AS FLOAT64) / POW(10, s.decimals) AS v
    FROM entries, UNNEST(REGEXP_EXTRACT_ALL(diff, r'"[^"]+":"-?[0-9]+"')) AS p
    JOIN stables AS s ON s.id = REGEXP_EXTRACT(p, r'^"([^"]+)"')
  )
  GROUP BY entry_id
)
SELECT
  e.block_date AS `date`,
  COUNT(*) AS token_diff_entries,
  COUNTIF(p.notional IS NOT NULL) AS entries_with_stablecoin,
  COALESCE(SUM(p.notional), 0) / 2 AS stable_leg_volume_usd
FROM entries AS e
LEFT JOIN per_entry AS p USING (entry_id)
GROUP BY `date`
ORDER BY `date`
