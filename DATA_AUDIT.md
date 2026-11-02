# DATA_AUDIT

Every external fact the pipeline relies on (endpoint, table, field, account id), how it was
verified, and the fallback if an assumption fails. Newest entry on top.

## Open questions (from CLAUDE.md, to resolve in F1)
| # | Question | Status | How verified | Fallback |
|---|---|---|---|---|
| Q1 | Freshness of bigquery-public-data.crypto_near_mainnet_us after NEAR Lake deprecation (2026-03-24) | open | | |
| Q2 | Full account IDs of revenue wallets fefundsadmin / 1csfundsadmin (per revenue.near.org) | open | | |
| Q3 | How Intents fees move: NEP-245 balances inside the intents verifier contract? | open | | |
| Q4 | Intents Explorer API (https://explorer.near-intents.org/api/v0): JWT, 1 req / 5 s, 1Click only | open | | |
| Q5 | DefiLlama endpoints: /protocol/near-intents and fees/revenue summary | open | | |

## Verified facts
| Date | Fact | How verified | Used by |
|---|---|---|---|

## Log
### 2026-11-02 — F0
- No external data sources used. Toolchain only: uv 0.13.6, GNU make 4.4.1, Node 24.19, Next.js 16.4.3.
