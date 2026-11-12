# Network Usage Module and Thesis Framing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two gaps found in the 2026-11-12 review: the network-usage data the track asks for is in the snapshot but unused, and `THESIS.md` reads as a measurement verdict instead of a long-term investment thesis.

**Architecture:** A new pure model `models/usage.py` turns four tables already in `data/snapshot/` into `usage.json` (weekly usage, Intents footprint, an out-of-sample lead/lag test of the track's example hypothesis) with a new dashboard page. `summary.json` gains a price-basis row and a holder view. `thesis.py` is re-framed around an explicit hypothesis with a summary, a holder section and downside signals taken from the pre-registered tests. Every new number goes through the existing chain: model, payload, independent audit, registered fact.

**Tech Stack:** Python 3.12, uv, pandas, numpy, pytest, ruff; Next.js static export, Recharts, TypeScript; Playwright QA. No new dependency.

**Spec:** There is no separate spec. The decisions are in "Design decisions" below; the review they come from is summarised in "Why".

## Why

- The track's example prompt (`tracks/02-thesis.md`) asks for SQL on daily active accounts, transaction counts and contract usage, and proposes the hypothesis "cross-chain volume through NEAR Intents is a better leading indicator of real network usage than token price". `network_daily` and `intents_onchain_daily` are in the hashed snapshot and their SQL is published in `queries.json`, but no model, chart or sentence uses them.
- The official track text is "Build a long-term investment thesis for NEAR and back it with data". `THESIS.md` claims "Not yet" while its "Supporting evidence" supports the opposite direction, has no reading for a holder, and its conditions only point one way.
- The headline pairs 12 cents (each day's price) with 7.6x (latest price). On the window's prices the same gap is about 9.2x. This is disclosed in Limitations only.

## Global Constraints

- **Never change `data/snapshot/`, `data/proof.json`, `data/proof/` or `video/`.** The testnet proof and the OpenTimestamps stamp are for the current snapshot manifest. `git status` must show no change under those paths after every task.
- `data/prereg/` and `data/reference/` change only in Task 8.
- Never invent numbers (CLAUDE.md rule 1): no figure is typed in `thesis.py`, `README.md` (outside code spans), tests or site copy. Numbers reach text through `Facts`; site copy reads them from JSON.
- Models are pure functions: DataFrames in, DataFrames or dicts out. No I/O in `models/`.
- A missing input is never replaced by zero or by a shorter window.
- No price prediction or price target. `THESIS.md` must keep the sentence "no price is predicted".
- Report results as they come out, null results included. **Do not change the split week, the lags, the metrics or the significance level after seeing a result.**
- Repository text is English. Line endings are LF (`tests/test_build.py` fails on CRLF).
- No new Python or npm dependency.
- Commit messages: `F8: <what>`, with the session's attribution trailer.
- Work on branch `f8-usage-thesis`. Do not push, merge or tag without the user's go-ahead.
- After each task: `make build` then `uv run pytest -q` are green, and the regenerated `THESIS.md` and `README.md` are committed with the code that changed them.

## Review Focus

1. **A week with a missing day in any input.** Expected: the week is dropped, never summed over fewer days. Test in Task 2.
2. **A non-positive weekly value (log of zero).** Expected: `usage.lead_lag_table` raises `ValueError` naming the column, instead of writing `-inf` that breaks `json.dumps(allow_nan=False)`. Test in Task 2.
3. **A negative change in the thesis text.** `Facts.pct` would render `-34.0%` and the number test sees `34.0`, which is not registered. Expected: `Facts.change` renders "fell" or "rose" with the absolute value. Test in Task 5.
4. **`data/prereg/scores.json` appears on 2026-11-14.** Expected: `THESIS.md` does not change, because it never cites `prereg.scores` (a new cited path on the deadline day would fail the audited-paths test). Test in Task 5.
5. **A lead/lag row without a correlation (fewer than four pairs, or zero variance).** Expected: the page shows an empty cell and the verdict says `insufficient_data`; nothing calls `.toFixed` on `null`. Covered by the null handling in Task 6 and the verdict test in Task 2.

## Design decisions

**Usage model**

- Tables: `network_daily`, `intents_onchain_daily`, `defillama_intents_daily`, `price_daily`. Days are kept only where all four have a row.
- Weeks run Monday to Sunday (pandas `W-SUN`), complete weeks only, labelled by the Monday's ISO date as in `distribution.py`.
- Weekly aggregation: mean of daily values for `active_signers`, `intents_signers` and `near_usd`; sum for `tx_count`, `function_calls`, `calls_to_intents` and `volume_usd`.
- "Daily active accounts" means distinct transaction signers per day (`active_signers`). The text always says so once.
- Lead/lag test: weekly log changes; predictors `volume_usd` and `near_usd`; usage series `active_signers` and `tx_count`; lags 0 to 3 weeks, of which only 1 to 3 count as a lead; split week `2026-08-10` (train pairs lie wholly before it, test pairs start on or after it); permutation p-values from `developer.permutation_p`; alpha `developer.ALPHA` (0.1).
- The test is not blind. An exploratory look at the same data on 2026-11-12 (whole-sample weekly correlations at lags 0 to 3 and a 60/40 error comparison) came before this design. METHODOLOGY.md and DATA_AUDIT.md must say so.

**Holder view** (`summary.holder`), all at `levers.as_of`:

- `market_value_usd` = total supply x latest price.
- `buyback_revenue_usd_per_year` = buyback revenue per day (`tau_buyback x v0`) x 365.
- `value_to_revenue` = the first divided by the second.
- `breakeven_value_to_revenue` = `1 / (inflation - 365 x burnt_near_per_day / supply)`. Identity to test: `value_to_revenue / breakeven_value_to_revenue` equals `levers.steps[0].volume_multiple`.
- `gross_new_supply_rate` = window gross issuance in NEAR / days x 365 / supply; `net_new_supply_rate` = the same with buyback and burn subtracted.

**Price basis** (`summary.levers.at_window_prices`): over the ledger window, `near_usd_mean` is the mean daily price and `volume_multiple` is `(sum(issuance x price) - sum(burn x price)) / sum(buyback x price)`.

**Downside signals** come from `prereg.json` (ids, claims, registration time, anchor). `ledger.conditions` is not changed.

**Sanity expectations** (exploratory, 2026-11-12, hand computed; for checking only, never typed into code, tests or copy): 26 complete weeks; `at_window_prices.volume_multiple` about 9.2; `near_usd_mean` about 4.92; `value_to_revenue` about 308; `breakeven_value_to_revenue` about 40.6; gross rate about 2.5 %; net rate about 2.2 %; active accounts lower in the second half, Intents volume and price higher; Intents signers below 1 % of active accounts. If a result is far from these, investigate before continuing; do not adjust the method to match them.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `src/capture/models/developer.py` | modify | `lead_lag` accepts a period frequency |
| `src/capture/models/usage.py` | create | weekly usage, shares, halves, lead/lag table, verdict |
| `src/capture/models/ledger.py` | modify | `price_basis`, `holder_view` |
| `src/capture/build.py` | modify | `usage_payload`; new keys in `summary_payload`; `build_payloads` |
| `src/capture/thesis.py` | modify | `Facts.change`; new sections and copy; README results |
| `tests/test_usage_golden.py` | create | hand-made fixtures for `usage.py` |
| `tests/test_usage.py` | create | `usage.json` on the snapshot |
| `tests/test_developer_golden.py`, `test_ledger_golden.py`, `test_site_data.py`, `test_build.py`, `test_thesis.py`, `test_numbers_audit.py` | modify | new cases |
| `site/app/network/page.tsx` | create | "Network usage" page, four cards |
| `site/lib/data.ts`, `site/app/layout.tsx`, `site/app/page.tsx`, `qa/check.mjs` | modify | import, nav, overview copy and holder card, QA page list |
| `docs/METHODOLOGY.md`, `README.md`, `DATA_AUDIT.md`, `PROGRESS.md` | modify | definitions, checklist, facts, session log |

---

### Task 0: Branch and baseline

- [ ] **Step 1:** `git checkout -b f8-usage-thesis` from an up-to-date `main`, then commit this plan file as `F8: plan for the usage module and the thesis framing`.
- [ ] **Step 2:** Run `make build` then `git status --short`. Expected: only `?? gcloud-login.sh` (a local helper, never committed). A diff here means the committed outputs are stale; stop and report.
- [ ] **Step 3:** Run `make verify`. Expected: ruff clean, three manifests `OK`, all tests pass. Record the pass count.

### Task 1: `developer.lead_lag` accepts a frequency

**Files:**
- Modify: `src/capture/models/developer.py` (`lead_lag`)
- Test: `tests/test_developer_golden.py`

**Interfaces:**
- Produces: `lead_lag(x, y, split, lags=LAGS, seed=0, freq="M") -> pd.DataFrame`. `x` and `y` carry a `PeriodIndex` of frequency `freq`; `split` is parsed with `pd.Period(split, freq)`. Default behaviour is unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_lead_lag_works_on_weekly_periods() -> None:
    weeks = pd.period_range("2026-06-01", periods=16, freq="W-SUN")
    x = pd.Series(np.arange(16, dtype=float) ** 2, index=weeks)
    y = x.shift(1)  # y(t + 1) = x(t)
    table = developer.lead_lag(x, y, "2026-07-27", lags=(0, 1), freq="W-SUN")
    row = table[(table["transform"] == "levels") & (table["sample"] == "test") & (table["lag"] == 1)]
    assert row["n"].iloc[0] >= developer.MIN_PAIRS
    assert row["pearson"].iloc[0] == pytest.approx(1.0)
```

- [ ] **Step 2:** `uv run pytest tests/test_developer_golden.py -q`. Expected: FAIL, unexpected keyword `freq`.
- [ ] **Step 3:** Add the `freq` parameter; use it for the split period and for `pd.period_range`.
- [ ] **Step 4:** `uv run pytest tests/test_developer_golden.py tests/test_developer.py tests/test_numbers_audit.py -q`. Expected: PASS (the monthly results are unchanged).
- [ ] **Step 5:** Commit `F8: lead_lag accepts a period frequency`.

### Task 2: `models/usage.py`

**Files:**
- Create: `src/capture/models/usage.py`
- Test: `tests/test_usage_golden.py`

**Interfaces:**
- Consumes: `developer.lead_lag(..., freq=)`, `developer.ALPHA`, `developer.MIN_PAIRS`.
- Produces:

```python
WEEK = "W-SUN"
USAGE_METRICS = ("active_signers", "tx_count")
USAGE_LABELS = {"active_signers": "Daily active accounts", "tx_count": "Transactions"}
PREDICTORS = ("volume_usd", "near_usd")
LAGS = (0, 1, 2, 3)
LEAD_LAGS = (1, 2, 3)
HALF_COLUMNS = ("active_signers", "tx_count", "calls_to_intents", "volume_usd", "near_usd")

def daily_table(network, intents_onchain, defillama, price) -> pd.DataFrame
def weekly_table(daily: pd.DataFrame) -> pd.DataFrame
def shares(daily: pd.DataFrame) -> dict[str, float]
def halves(weekly: pd.DataFrame) -> dict
def lead_lag_table(weekly: pd.DataFrame, split: str, seed: int = 0) -> pd.DataFrame
def verdict(table: pd.DataFrame) -> dict
```

- `daily_table`: inner join on `date`; `DatetimeIndex`; columns `active_signers, tx_count, new_accounts, function_calls, calls_to_intents, intents_signers` (renamed from `unique_signers`), `volume_usd, near_usd`. Rows with any empty value are dropped.
- `weekly_table`: `PeriodIndex` (`W-SUN`); only weeks with seven daily rows; aggregation as in Design decisions.
- `shares`: `intents_call_share` = sum of `calls_to_intents` / sum of `function_calls`; `intents_signer_share` = mean of the daily ratio `intents_signers / active_signers`.
- `halves`: with `n` weeks, first = the first `n // 2`, second = the rest. Returns `{"weeks": n, "first": {...}, "second": {...}, "change": {...}}`; each half has `start` (Monday), `end` (Sunday), `weeks` and the mean of each `HALF_COLUMNS` weekly value; `change[c] = second[c] / first[c] - 1`.
- `lead_lag_table`: for each usage metric and predictor, `developer.lead_lag(np.log(weekly[predictor]), np.log(weekly[usage]), split, lags=LAGS, seed=seed, freq=WEEK)`, keeping only `transform == "diff"`. Columns: `usage, predictor, sample, lag, n, pearson, spearman, p_value, note`. Raises `ValueError` naming the column if a weekly value is not positive.
- `verdict` returns:

```python
{
  "result": "supported" | "not_supported" | "insufficient_data",
  "label": "supported" | "not supported" | "insufficient data",
  "alpha": developer.ALPHA,
  "by_usage": [
    {"usage": ..., "label": USAGE_LABELS[...],
     "result": "volume_leads" | "price_leads" | "null" | "insufficient_data",
     "volume": {"lag", "train_r", "test_r", "test_n", "p_value", "leads"},
     "price":  {same keys}},
  ],
  "text": str,
}
```

Verdict rule, per usage metric and predictor: among train rows with `lag` in `LEAD_LAGS` and a correlation, take the lag with the largest absolute `pearson` (the smallest lag on a tie); read the test row at that lag; `leads` is true when its `p_value` is below alpha and its sign equals the train sign. Per usage: `volume_leads` if volume leads and (price does not, or `abs(volume test_r) > abs(price test_r)`); otherwise `price_leads` if price leads; otherwise `null`; `insufficient_data` if a needed row has no correlation. Overall: `insufficient_data` if any usage is; `supported` if every usage is `volume_leads`; else `not_supported`.

Verdict text: one sentence per usage metric, then one closing sentence.

```
{label}: Intents volume, lag {k} weeks, r={train_r:.2f} in training and r={test_r:.2f} on {test_n} test weeks (p={p:.2f}); NEAR price, lag {k} weeks, r={train_r:.2f} in training and r={test_r:.2f} on {test_n} test weeks (p={p:.2f}).
```

Closing sentence by result: `supported`: "Volume passes out of sample for every usage series and more strongly than price; this describes co-movement, not a cause." `not_supported`: "Volume does not lead usage out of sample more reliably than price; with this few weeks that is a null result, not proof of absence." `insufficient_data`: "Too few weekly pairs to choose a lag."

- [ ] **Step 1: Write the failing tests** in `tests/test_usage_golden.py`. Build the four input frames by hand with a helper `frames(days, **columns)`.

```python
def test_only_complete_weeks_are_kept_and_aggregated() -> None:
    # 2026-06-01 is a Monday. 23 days: three full weeks and two days of a fourth.
    daily = usage.daily_table(*inputs(start="2026-06-01", days=23, active=[100] * 7 + [200] * 7 + [400] * 9))
    weekly = usage.weekly_table(daily)
    assert [str(p.start_time.date()) for p in weekly.index] == ["2026-06-01", "2026-06-08", "2026-06-15"]
    assert weekly["active_signers"].tolist() == [100.0, 200.0, 400.0]   # mean
    assert weekly["tx_count"].tolist() == [70, 70, 70]                  # sum of 10 a day

def test_a_week_with_a_missing_day_in_any_input_is_dropped() -> None:
    # remove 2026-06-10 from the price frame only
    assert [str(p.start_time.date()) for p in weekly.index] == ["2026-06-01", "2026-06-15"]

def test_shares() -> None:
    # calls_to_intents 5 and function_calls 100 every day; intents signers 2 a day
    assert s["intents_call_share"] == pytest.approx(0.05)
    assert s["intents_signer_share"] == pytest.approx((0.02 * 7 + 0.01 * 7 + 0.005 * 7) / 21)

def test_halves_compare_the_first_weeks_with_the_rest() -> None:
    h = usage.halves(weekly)   # three weeks: one, then two
    assert h["weeks"] == 3 and h["first"]["weeks"] == 1 and h["second"]["weeks"] == 2
    assert h["first"]["start"] == "2026-06-01" and h["second"]["end"] == "2026-06-21"
    assert h["change"]["active_signers"] == pytest.approx(300 / 100 - 1)

def test_volume_leads_when_usage_repeats_last_weeks_volume_change() -> None:
    # 16 weeks; log changes of usage equal the previous week's log changes of volume;
    # price changes are a fixed pattern unrelated to both. Split "2026-07-27".
    v = usage.verdict(usage.lead_lag_table(weekly, "2026-07-27"))
    by = {u["usage"]: u for u in v["by_usage"]}
    assert by["active_signers"]["result"] == "volume_leads"
    assert by["active_signers"]["volume"]["lag"] == 1

def test_price_leads_when_the_roles_are_swapped() -> None:
    assert by["active_signers"]["result"] == "price_leads"

def test_constant_growth_gives_insufficient_data() -> None:
    # usage grows by the same factor every week: zero variance in its log changes
    assert v["result"] == "insufficient_data" and v["label"] == "insufficient data"

def test_a_non_positive_weekly_value_is_refused() -> None:
    with pytest.raises(ValueError, match="volume_usd"):
        usage.lead_lag_table(weekly_with_a_zero_volume_week, "2026-07-27")

def test_the_verdict_text_states_every_number_it_rests_on() -> None:
    assert "Daily active accounts" in v["text"] and "Transactions" in v["text"]
    for u in v["by_usage"]:
        assert f"r={u['volume']['test_r']:.2f}" in v["text"]
```

- [ ] **Step 2:** `uv run pytest tests/test_usage_golden.py -q`. Expected: FAIL, module `capture.models.usage` not found.
- [ ] **Step 3:** Implement `usage.py` with the module docstring stating: what "active accounts" means, that the test describes co-movement of short weekly series and says nothing about cause.
- [ ] **Step 4:** `uv run pytest tests/test_usage_golden.py -q` and `uv run ruff check src tests`. Expected: PASS, clean.
- [ ] **Step 5:** Commit `F8: usage model (weekly network usage, Intents footprint, lead/lag against volume and price)`.

### Task 3: `usage.json` and its independent audit

**Files:**
- Modify: `src/capture/build.py`, `tests/test_build.py`, `tests/test_numbers_audit.py`
- Create: `tests/test_usage.py`

**Interfaces:**
- Consumes: Task 2 functions.
- Produces: `build.USAGE_TABLES`, `build.USAGE_SPLIT_WEEK = "2026-08-10"`, `build.usage_payload(data_dir, source) -> dict`, and `"usage"` in `build_payloads` (after `"developer"`).

Payload shape:

```python
{
  "schema_version": 1,
  "source": f"data/{source}",
  "inputs": manifest_inputs(data_dir, USAGE_TABLES),
  "window": {"first_date", "last_date", "days"},          # of the joined daily table
  "definitions": {...}, "notes": USAGE_NOTES,
  "series": records(daily, "date"),                       # every column of daily_table
  "weekly": [...],                                        # "week" = Monday ISO date + weekly columns
  "shares": usage.shares(daily),
  "halves": usage.halves(weekly),
  "lead_lag": {
    "transform": "weekly log changes",
    "split_week": USAGE_SPLIT_WEEK,
    "lags_in_weeks": list(usage.LAGS), "lead_lags_in_weeks": list(usage.LEAD_LAGS),
    "rows": _frame_records(table),
    "verdict": usage.verdict(table),
  },
}
```

`USAGE_NOTES` must state: active accounts are distinct transaction signers, and relayed calls are signed by the relayer; Intents signers are signers of calls to `intents.near`, mostly solvers and relayers, not end users; the fall or rise of a usage series is not attributed to a cause; the test was designed after an exploratory look at the same data.

- [ ] **Step 1: Write the failing tests.** In `tests/test_usage.py` (module fixture `payload = build.usage_payload(data_dir, "snapshot")`):

```python
def test_payload_is_json_safe_and_names_its_inputs(payload) -> None:
    json.dumps(payload, allow_nan=False)
    assert {i["path"] for i in payload["inputs"]} == {
        "network_daily.parquet", "intents_onchain_daily.parquet",
        "defillama_intents_daily.parquet", "price_daily.parquet"}

def test_every_week_is_complete_and_inside_the_window(payload) -> None:
    weeks = [pd.Timestamp(w["week"]) for w in payload["weekly"]]
    assert all(w.day_of_week == 0 for w in weeks) and weeks == sorted(weeks)
    assert payload["halves"]["weeks"] == len(weeks)
    assert weeks[0] >= pd.Timestamp(payload["window"]["first_date"])
    assert weeks[-1] + pd.Timedelta(days=6) <= pd.Timestamp(payload["window"]["last_date"])

def test_shares_are_fractions(payload) -> None:
    assert 0 < payload["shares"]["intents_call_share"] < 1
    assert 0 < payload["shares"]["intents_signer_share"] < 1

def test_lead_lag_covers_every_metric_predictor_sample_and_lag(payload) -> None:
    rows = payload["lead_lag"]["rows"]
    assert len(rows) == 2 * 2 * 2 * 4
    assert payload["lead_lag"]["verdict"]["result"] in {"supported", "not_supported", "insufficient_data"}
```

In `tests/test_build.py` add `"usage.json"` to the expected names (sorted position: after `summary.json`). In `tests/test_numbers_audit.py` add `"usage": build.usage_payload(data_dir, src)` and `"prereg": build.prereg_payload()` to `pub`, add `"usage"` to the names whose `inputs` hashes are checked, and add `test_usage_is_recomputed_independently(data_dir, pub)`. It must not import `capture.models` and must recompute from the parquet files and assert, with `close`:
  - `window`, the weekly rows (every column, every week), `shares`, `halves.weeks` and every `halves.change` value;
  - every `lead_lag.rows` entry: `n`, `pearson`, `spearman`, `p_value` (pairs built as in `test_every_cohort_and_the_lead_lag_table`, with `W-SUN` periods, log changes, split `2026-08-10`, seed `config.RANDOM_SEED + lag`);
  - per usage metric and predictor, the lag chosen in training, and each `by_usage` result and the overall `verdict.result` re-derived from the rows by the rule in Task 2.

- [ ] **Step 2:** `uv run pytest tests/test_usage.py tests/test_build.py tests/test_numbers_audit.py -q`. Expected: FAIL, `usage_payload` missing.
- [ ] **Step 3:** Implement `usage_payload` and register it in `build_payloads`.
- [ ] **Step 4:** Run the same command. Expected: PASS. Then mutate one value by hand (for example the aggregation of `active_signers` from mean to sum), confirm the audit test fails, and restore it.
- [ ] **Step 5:** `make build`; `git status --short` shows only the files of this task plus regenerated outputs that did not change in content. Commit `F8: usage.json with its independent audit`.

### Task 4: price basis and holder view in `summary.json`

**Files:**
- Modify: `src/capture/models/ledger.py`, `src/capture/build.py` (`summary_payload`), `tests/test_ledger_golden.py`, `tests/test_site_data.py`, `tests/test_numbers_audit.py`

**Interfaces:**
- Produces:

```python
def price_basis(daily: pd.DataFrame, end: pd.Timestamp, days: int = 30) -> dict
    # {"near_usd_mean": float, "volume_multiple": float}; raises ValueError on a gap, like waterfall

def holder_view(daily: pd.DataFrame, end: pd.Timestamp, days: int = 30, *, supply: float,
                price: float, buyback_usd_per_day: float, inflation: float,
                burnt_near_per_day: float) -> dict
    # keys: as_of, near_usd, market_value_usd, buyback_revenue_usd_per_year, value_to_revenue,
    #       breakeven_value_to_revenue, gross_new_supply_rate, net_new_supply_rate
```

- `summary["levers"]["at_window_prices"] = ledger.price_basis(daily, start.as_of, TAU_WINDOW)`.
- `summary["holder"] = {**ledger.holder_view(...), "note": HOLDER_NOTE}` with `supply=inputs.total_supply_near`, `price=inputs.near_usd`, `buyback_usd_per_day=taus["buyback"] * v0`, `inflation=config.INFLATION_CURRENT`, `burnt_near_per_day=inputs.burnt_near_per_day`. `HOLDER_NOTE` says the multiple is a yardstick at the latest price, not a forecast, and that it uses total supply so that it lines up with the coverage ratio.

- [ ] **Step 1: Write the failing tests.**

`tests/test_ledger_golden.py` (three-day hand-made `daily`, price 2, 4, 6; issuance 10 NEAR a day; buyback 1; burn 0.5):

```python
def test_price_basis_values_the_gap_at_each_days_price() -> None:
    out = ledger.price_basis(daily, end, days=3)
    assert out["near_usd_mean"] == pytest.approx(4.0)
    assert out["volume_multiple"] == pytest.approx((10 - 0.5) * 12 / (1 * 12))

def test_holder_view_identity_and_rates() -> None:
    out = ledger.holder_view(daily, end, days=3, supply=1000.0, price=2.0,
                             buyback_usd_per_day=1.0, inflation=0.0365, burnt_near_per_day=0.01)
    assert out["market_value_usd"] == pytest.approx(2000.0)
    assert out["value_to_revenue"] == pytest.approx(2000.0 / 365.0)
    assert out["breakeven_value_to_revenue"] == pytest.approx(1 / (0.0365 - 365 * 0.01 / 1000))
    assert out["gross_new_supply_rate"] == pytest.approx(10 * 365 / 1000)
    assert out["net_new_supply_rate"] == pytest.approx((10 - 1 - 0.5) * 365 / 1000)
```

`tests/test_site_data.py`:

```python
def test_the_holder_multiple_over_its_break_even_is_the_volume_multiple(summary: dict) -> None:
    h, steps = summary["holder"], summary["levers"]["steps"]
    assert h["value_to_revenue"] / h["breakeven_value_to_revenue"] == pytest.approx(steps[0]["volume_multiple"])
    assert 0 < h["net_new_supply_rate"] < h["gross_new_supply_rate"]
    assert h["gross_new_supply_rate"] == pytest.approx(config.INFLATION_CURRENT, abs=0.002)

def test_the_multiple_at_window_prices_follows_the_ledger(summary: dict) -> None:
    usd = summary["ledger"]["usd"]
    at = summary["levers"]["at_window_prices"]
    assert at["volume_multiple"] == pytest.approx((usd["issuance"] - usd["burn"]) / usd["buyback_wallet"])
```

`tests/test_numbers_audit.py`: add `test_the_price_basis_and_the_holder_view(ind, pub)` recomputing every key of `summary.levers.at_window_prices` and `summary.holder` from `ind` (`ind.issuance`, `ind.bb`, `ind.burn`, `ind.price`, `ind.supply`, and `_start(ind, as_of)` for `v0`, `tau_bb`, `S`, `P`, burn per day).

- [ ] **Step 2:** `uv run pytest tests/test_ledger_golden.py tests/test_site_data.py tests/test_numbers_audit.py -q`. Expected: FAIL, `price_basis` missing.
- [ ] **Step 3:** Implement both functions and the two payload keys.
- [ ] **Step 4:** Run the same command. Expected: PASS. Compare the snapshot values with the sanity expectations.
- [ ] **Step 5:** `make build`, then commit `F8: price basis of the headline multiple and a holder view in summary.json`.

### Task 5: thesis framing

**Files:**
- Modify: `src/capture/thesis.py`, `tests/test_thesis.py`, `tests/test_numbers_audit.py` (`AUDITED`, `DESCRIPTIVE`, one prereg test), regenerated `THESIS.md` and `README.md`

**Interfaces:**
- Consumes: `usage.*`, `summary.holder.*`, `summary.levers.at_window_prices.*`, `prereg.*` payload paths.
- Produces: `Facts.change(path, digits=0) -> str`: for a signed fraction returns `"rose N%"` or `"fell N%"`, registering the absolute value's text against the path with the signed raw value.

Section order of `THESIS.md` after this task: `## Summary`, `## Claim`, `## What it means for a holder`, `## Supporting evidence`, `## Contrary evidence`, `## Why public estimates differ`, `## What would change my mind`, `## Unavailable metrics and why`, `## Limitations`.

Copy. `{...}` marks a registered fact; nothing else may contain a digit.

**Summary** (after the generated-by note):

```
- **Question.** Can the value NEAR Intents captures for the token, buybacks plus gas burn, outgrow new issuance? That is the long-term case for NEAR as a token backed by revenue, tested here as a hypothesis.
- **Answer today: not yet.** {cents} cents come back per dollar of new NEAR issued ({ledger.days} days to {hero.date}).
- **The gap.** Revenue reaching the buyback wallet has to grow {steps[0].volume_multiple, 1 digit}x at the latest NEAR price ({at_window_prices.volume_multiple, 1 digit}x at the prices of the window). The HSP-029 issuance cut and routing all protocol revenue to buybacks would leave {steps[2].volume_multiple}x for growth.
- **For a holder.** Net of buybacks and burn, new NEAR still adds {holder.net_new_supply_rate, pct 1} to supply a year, and total supply is valued at {holder.value_to_revenue, 0 digits}x the yearly revenue reaching the buyback wallet; coverage reaches one at {holder.breakeven_value_to_revenue, 1 digit}x.
- **Strongest evidence against.** Mean monthly log growth of volume after the launch phase is {valuation.growth.mean_after_launch, 3 digits}, and network usage did not follow Intents: daily active accounts {change active_signers} while Intents volume {change volume_usd}.
- **Check it.** `make all` rebuilds every number offline; the conditions that would change the answer are listed below.
```

**Claim.** Before the existing "**Not yet.**" paragraph:

```
The hypothesis: over the long run, fee revenue from NEAR Intents grows until buybacks and gas burn cover new NEAR issuance. The evidence for and against it follows. The reading today:
```

After the volume-invariance paragraph:

```
It does depend on the NEAR price. The {steps[0].volume_multiple, 1 digit}x values issuance at the latest price ({holder.near_usd, usd} on {levers.as_of}); the {cents} cents use each day's price (mean {at_window_prices.near_usd_mean, usd} over the window), and on that basis the gap is {at_window_prices.volume_multiple, 1 digit}x. Issuance is fixed in NEAR while fee revenue is earned in dollars, so a higher NEAR price raises the bar.
```

**What it means for a holder:**

```
- Net new supply: gross issuance ran at {holder.gross_new_supply_rate, pct 1} of total supply a year over the {ledger.days} days to {levers.as_of}; after buybacks and gas burn, {holder.net_new_supply_rate, pct 1} was left.
- A yardstick, not a price view: at the latest price total supply is valued at {holder.value_to_revenue, 0 digits}x the yearly revenue reaching the buyback wallet. Coverage reaches one when that multiple is {holder.breakeven_value_to_revenue, 1 digit}x; the ratio of the two is the {steps[0].volume_multiple, 1 digit}x above. The multiple moves with revenue, the issuance rate and the price; none of them is forecast here.
```

**Supporting evidence**: first line "Evidence that capture can catch up with issuance:" then a blank line and the existing bullets.

**Contrary evidence**: first line "Evidence that it will not, or not soon:" then a blank line, the existing bullets, and three new ones placed after the "Volume is concentrated" bullet:

```
- Intents revenue is not network usage: from {usage.window.first_date} to {usage.window.last_date}, calls to `intents.near` were {shares.intents_call_share, pct 1} of all function calls and its daily signers {shares.intents_signer_share, pct 2} of daily active accounts (distinct transaction signers).
- Network usage did not follow Intents: comparing the two halves of the {usage.halves.weeks} complete weeks, daily active accounts {change active_signers} and transactions {change tx_count}, while Intents volume {change volume_usd} and the NEAR price {change near_usd}. No cause is attributed.
- The track's example hypothesis, that Intents volume leads network usage better than the token price, is {usage.lead_lag.verdict.label} out of sample: {usage.lead_lag.verdict.text}
```

**What would change my mind**: the effect label for `support` becomes "would change the answer to yes". After the three conditions:

```
Signs that would move the answer toward no were written down before their windows closed (registered {prereg.registered_at_utc}, hash committed on NEAR {prereg.anchor.near.network} at block {prereg.anchor.near.block_height}). A miss on any of them counts against the hypothesis:

- {tests[i].id}: {tests[i].claim}        (one line per test)

Each is scored on the dashboard when its window closes; a miss is reported as a miss.
```

If `prereg.anchor` is empty, drop the clause in parentheses after the registration time. If the payload has no tests, omit the whole block.

**README results block** (`render_results`): extend the "Not yet" bullet with "({at_window_prices.volume_multiple, 1 digit}x at the prices of the window the cents use)" and add, before the Proof bullet:

```
- The track's example hypothesis, that Intents volume leads network usage better than price: {usage.lead_lag.verdict.label} out of sample; daily active accounts {change active_signers} while Intents volume {change volume_usd}.
```

- [ ] **Step 1: Write the failing tests** in `tests/test_thesis.py`. Add `"## Summary"` (first) and `"## What it means for a holder"` (after `"## Claim"`) to `SECTIONS`, then:

```python
def test_change_words_a_signed_fraction_and_registers_its_absolute_value() -> None:
    f = thesis.Facts({"a": {"down": -0.341, "up": 0.76}})
    assert f.change("a.down") == "fell 34%" and f.change("a.up") == "rose 76%"
    assert [(x.raw, x.text) for x in f.used] == [(-0.341, "34"), (0.76, "76")]

def test_the_hypothesis_is_stated_before_the_reading(rendered) -> None:
    text, _ = rendered
    claim = text[text.index("## Claim") : text.index("## What it means for a holder")]
    assert claim.index("The hypothesis:") < claim.index("Not yet")
    assert "It does depend on the NEAR price" in claim

def test_the_usage_result_is_reported_as_it_came_out(rendered, payloads) -> None:
    text, _ = rendered
    contrary = text[text.index("## Contrary evidence") : text.index("## Why public estimates differ")]
    assert payloads["usage"]["lead_lag"]["verdict"]["text"] in contrary
    assert payloads["usage"]["lead_lag"]["verdict"]["label"] in contrary

def test_downside_signals_list_every_pre_registered_test(rendered, payloads) -> None:
    text, _ = rendered
    section = text[text.index("## What would change my mind") : text.index("## Unavailable")]
    for t in payloads["prereg"]["tests"]:
        assert f"- {t['id']}: {t['claim']}" in section

def test_scores_do_not_change_the_thesis(payloads) -> None:
    scored = {**payloads, "prereg": {**payloads["prereg"],
              "scores": {"scored_at_utc": "x", "results": {"T1": {"status": "pass"}}}}}
    assert thesis.render(scored)[0] == thesis.render(payloads)[0]

def test_a_missing_anchor_drops_only_its_clause(payloads) -> None:
    bare = {**payloads, "prereg": {**payloads["prereg"], "anchor": None}}
    text, _ = thesis.render(bare)
    assert "hash committed on NEAR" not in text and "- T1:" in text
```

- [ ] **Step 2:** `uv run pytest tests/test_thesis.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `Facts.change`, the sections and copy above, and the README bullets.
- [ ] **Step 4:** Run `uv run pytest tests/test_thesis.py -q`. `test_every_path_the_thesis_and_the_readme_cite_is_independently_audited` prints the cited-but-not-audited and the stale paths. Make `AUDITED` and `DESCRIPTIVE` in `tests/test_numbers_audit.py` match: every new `usage.*`, `summary.holder.*` and `summary.levers.at_window_prices.*` path goes in `AUDITED` (recomputed in Tasks 3 and 4; `usage.lead_lag.verdict.text` and `.label` are covered there by re-deriving the result, and the text test below); `prereg.tests[*].id`, `prereg.tests[*].claim`, `prereg.registered_at_utc`, `prereg.anchor.near.network` and `prereg.anchor.near.block_height` go in `AUDITED` with a new test:

```python
def test_the_pre_registration_is_read_from_its_frozen_files(pub) -> None:
    d = build.PREREG_DIR
    tests = json.loads((d / "tests.json").read_text(encoding="utf-8"))
    anchor = json.loads((d / "anchor.json").read_text(encoding="utf-8"))
    p = pub["prereg"]
    assert p["registered_at_utc"] == tests["registered_at_utc"]
    assert [(t["id"], t["claim"]) for t in p["tests"]] == [(t["id"], t["claim"]) for t in tests["tests"]]
    assert p["anchor"]["near"]["network"] == anchor["near"]["network"]
    assert p["anchor"]["near"]["block_height"] == anchor["near"]["block_height"]
    for e in json.loads((d / "manifest.json").read_text(encoding="utf-8"))["files"]:
        assert sha(d / e["path"]) == e["sha256"], e["path"]
```

Also add to `test_usage_is_recomputed_independently` an assertion that `verdict.text` contains, for every usage metric and predictor, the independently computed `r=` values formatted to two digits.

- [ ] **Step 5:** `make build`, then `uv run pytest -q`. Expected: PASS. Read the regenerated `THESIS.md` top to bottom once as a reader: every sentence must be true of the numbers beside it (for example "fell" and "rose" must match the direction the reader expects from the charts). If a sentence reads wrong because a result came out differently from the sanity expectations, change the wording to fit the result, never the result.
- [ ] **Step 6:** Commit `F8: thesis framed as a hypothesis, with a summary, a holder view, the usage result and downside signals`.

### Task 6: dashboard

**Files:**
- Create: `site/app/network/page.tsx`
- Modify: `site/lib/data.ts`, `site/app/layout.tsx`, `site/app/page.tsx`, `qa/check.mjs`

**Interfaces:**
- Consumes: `usage.json` (Task 3), `summary.holder`, `summary.levers.at_window_prices` (Task 4).

- [ ] **Step 1:** `site/lib/data.ts`: import and export `usage` from `../public/data/usage.json`.
- [ ] **Step 2:** `site/app/layout.tsx`: add `["/network/", "Network usage"]` to `NAV` after "Intents & channels". `qa/check.mjs`: add `["network", "/network/"]` to `PAGES` in the same position.
- [ ] **Step 3:** Create `site/app/network/page.tsx` following `site/app/token/page.tsx` and `site/app/developer/page.tsx` (server component, `PageHeader`, `ChartCard`, `TimeChart`, `rolling`, formatters from `@/lib/format`). Page title "Network usage"; lede: "Does NEAR's own activity move with Intents? Daily active accounts are distinct transaction signers; a relayed call is signed by its relayer." Four cards:

| `id` | Title | Chart | `tables` | Sentence built from |
|---|---|---|---|---|
| `activity` | Daily active accounts and transactions | two `TimeChart`s (`format="count"`), 7-day means of `active_signers` and `tx_count` | `network_daily` | the latest 7-day means and their date |
| `divergence` | Network usage against Intents volume and price | one `TimeChart` (`format="ratio"`) of weekly values divided by the first week's value: active accounts, transactions, Intents volume, NEAR price; `refY={{ y: 1, label: "first week" }}` | all four usage tables | `halves.change` for active accounts, volume and price, worded "fell"/"rose" from the sign |
| `footprint` | How much of NEAR's activity is Intents | `TimeChart` (`format="count"`), 7-day mean of `calls_to_intents` | `intents_onchain_daily`, `network_daily` | `shares.intents_call_share` and `shares.intents_signer_share` |
| `usage-leadlag` | Does Intents volume lead network usage better than price? | `Badge` with the verdict label, the per-usage summary, and the rows as the card's `table` | all four usage tables | `verdict.label` and `verdict.text` |

Each card has a `model` string naming the `usage.py` functions, and a data table. Series colours: `var(--cat-1)`, `var(--cat-2)`, `var(--cat-3)`, `var(--neutral-series)` as already defined in `globals.css` (price takes the neutral colour). Every nullable number is rendered with the `value === null ? null : value.toFixed(2)` pattern used on the Developer page. The lead/lag card ends with the same kind of caution paragraph as the Developer page: number of train and test weeks, reported as it came out, designed after an exploratory look at the same data, correlation is not cause.

- [ ] **Step 4:** `site/app/page.tsx`:
  - Under the "Volume needed to break even" card, change the small line to: `{usd(v*)} per day against {usd(v0)} today, at the latest NEAR price; {times(at_window_prices.volume_multiple, 1)} at the prices of the 30 days behind the cents`.
  - After the `levers` card add `<ChartCard id="holder" title="What the gap means for a holder" tables={CORE} model="ledger.holder_view (src/capture/models/ledger.py)">` with two horizontal bars whose lengths are proportional to `holder.value_to_revenue` and `holder.breakeven_value_to_revenue` (the `BarRows` component from `@/components/Bits`, as the `ledger` card uses it), labelled "Today" and "At break-even", and the sentence: "At the latest price, total supply is valued at {N}x the yearly revenue reaching the buyback wallet; coverage reaches one at {M}x. Net of buybacks and burn, new NEAR adds {pct} to supply a year. A yardstick, not a forecast: no price is predicted."
  - In the "What would change our mind" section replace "would support the thesis" wording with "would change the answer to yes", and add one sentence pointing to the pre-registered tests below as the signs that would move the answer toward no.
- [ ] **Step 5:** `make site`. Expected: the export lists `/network`. Then `make qa`. Expected: every page clean on desktop and phone, including `network`. Open `qa/screenshots/` for the network page and the overview and check by eye: no overlapping labels, the indexed chart starts at 1, bars are proportional.
- [ ] **Step 6:** Commit `F8: Network usage page, holder card and price basis on the overview`.

### Task 7: documents

**Files:** `docs/METHODOLOGY.md`, `README.md`, `DATA_AUDIT.md`, `PROGRESS.md`

- [ ] **Step 1: `docs/METHODOLOGY.md`.** Add a section "Network usage (`usage.json`)" between "Developer indicator" and "Capture ledger": inputs table, the definitions and the lead/lag rule from Design decisions, the verdict rule from Task 2, and limitations (signers are not people; relayed traffic; about two dozen weekly changes; both predictors share market conditions; the test was designed after an exploratory look at the same data on 2026-11-12; no cause is claimed). Under "Capture ledger, levers and conditions" add "Price basis" and "Holder view" paragraphs with their formulas and the identity. In "Generated documents" add the section list and `Facts.change`. In "Independent audit" add usage, the price basis, the holder view and the pre-registration. Change "Six static pages" to "Seven static pages". This document states definitions and never quotes results.
- [ ] **Step 2: `README.md`** (no digit outside the generated block, code spans and links):
  - Track checklist, first row: ask "SQL against the NEAR BigQuery public dataset for daily active accounts, transaction counts and contract usage, always filtered on `block_date`"; where: `sql/network_daily.sql`, `sql/intents_onchain_daily.sql`, `sql/contracts_daily.sql`, shown on the Network usage and Developer pages.
  - Add a row: ask "The example hypothesis: Intents volume leads network usage better than token price, with the evidence against"; where: the Network usage page and `THESIS.md`, tested out of sample and reported as it came out.
  - "six pages" becomes "seven pages"; add `usage` to the list of JSON outputs under "For tools and agents"; add `usage` to the models in Layout.
- [ ] **Step 3: `DATA_AUDIT.md`.** New section "F8 network usage and thesis framing (2026-11-12)": tables used and their ranges; no new source and no BigQuery query; the numbers found, each with its JSON path; the result of the lead/lag test as it came out; the statement that an exploratory look preceded the design, and what it looked at; the price basis finding (the two multiples and the two prices).
- [ ] **Step 4:** `make build` then `make verify`. Expected: all green. `git status --short` shows no change under `data/snapshot/`, `data/proof*`, `data/prereg/`, `data/reference/`, `video/`.
- [ ] **Step 5: `PROGRESS.md`.** New session entry on top (done, numbers found with source files, decisions, blockers, next), and update the F8 row of the phase table.
- [ ] **Step 6:** Commit `F8: methodology, README checklist, DATA_AUDIT and PROGRESS for the usage module and the thesis framing`. Ask the user before merging to `main` and pushing; after the push, run `QA_URL=https://axlnd3r.github.io/NePu make qa` once the Pages workflow is green.

### Task 8: deadline-day steps (user-gated)

Run on **2026-11-14 after 00:00 UTC and well before 23:59 UTC**. Each step that sends something outside the machine needs the user's go-ahead.

- [ ] **Step 1:** `uv run capture reference hsp029` (keyless view call). Expected: `data/reference/hsp029_vote.json` and its manifest entry refreshed. If the status is no longer `Timelock`, stop and report before building.
- [ ] **Step 2:** `uv run capture prereg score`. Expected: `data/prereg/scores.json` with a result for T1; a miss is kept as a miss.
- [ ] **Step 3:** `make build` then `make verify`. Expected: green; `THESIS.md` changes only where the HSP-029 block height or status changed.
- [ ] **Step 4:** Commit `F8: HSP-029 re-read and T1 scored`. With the user's go-ahead: merge to `main`, push, wait for the ci, pages and proof workflows, run `QA_URL=https://axlnd3r.github.io/NePu make qa`.
- [ ] **Step 5:** With the user's go-ahead: `git tag hackathon-submission` on that commit and `git push origin hackathon-submission`. Update `PROGRESS.md` (Gate 3, final state).

## Out of scope

- Refreshing `data/snapshot/` (it would change the headline against the demo video and need a new proof).
- A mainnet proof (needs the user's funds and signature; decide separately).
- A peer comparison with other chains (needs new sources with their own manifest).
- Changing `ledger.conditions`, the Valuation Lab or the Distribution Map.
