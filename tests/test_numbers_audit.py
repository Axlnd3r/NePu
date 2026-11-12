"""Independent audit: every published number is recomputed from the parquet files (rule 1).

This module never imports capture.models. Each definition is re-implemented from
docs/METHODOLOGY.md with plain pandas/numpy and compared with what `capture build` publishes, so a
bug in a model function cannot pass by agreeing with itself. Hashes are checked against the
manifests. Only constants (seed, windows, policy parameters) are shared, and the policy
parameters are themselves checked against data/reference/parameters.csv.
"""

import csv
import hashlib
import itertools
import json
import os
import re

import numpy as np
import pandas as pd
import pytest

from capture import build, config

BUY = "buybacks.multisignature.near"
D = pd.Timestamp
REL = 1e-9


def close(a, b, rel=REL) -> bool:
    if a is None or b is None or (isinstance(b, float) and np.isnan(b)):
        return a is None and (b is None or np.isnan(b))
    return abs(a - b) <= rel * max(abs(b), 1e-12)


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- independent re-implementation
class Ledger:
    """Daily series rebuilt from the snapshot tables."""

    def __init__(self, data_dir):
        rd = lambda n: pd.read_parquet(data_dir / f"{n}.parquet")  # noqa: E731
        dated = lambda df: df.assign(date=pd.to_datetime(df["date"]))  # noqa: E731
        sup = dated(rd("supply_daily")).set_index("date").sort_index()
        self.idx = pd.date_range(sup.index.min(), sup.index.max(), freq="D")
        llama = dated(rd("defillama_intents_daily")).set_index("date")
        self.llama_raw = llama
        self.price = dated(rd("price_daily")).set_index("date")["near_usd"].reindex(self.idx)
        self.supply = sup["total_supply_near"].reindex(self.idx)
        self.burn = sup["burnt_near"].reindex(self.idx)
        self.issuance = (sup["total_supply_near"].diff() + sup["burnt_near"]).reindex(self.idx)
        self.vol, self.fees, self.rev = (
            llama[c].reindex(self.idx) for c in ("volume_usd", "fees_usd", "revenue_usd")
        )
        fw = dated(rd("fee_wallet_inflows_daily"))
        wallets = fw.pivot(index="date", columns="wallet", values="amount").reindex(self.idx)
        self.bb = (wallets[BUY].clip(lower=0) - self._transfers(wallets)).clip(lower=0)
        filled = wallets.copy()
        for c in filled:
            first, last = filled[c].first_valid_index(), filled[c].last_valid_index()
            inner = (filled.index > first) & (filled.index < last)
            filled.loc[inner & filled[c].isna(), c] = 0.0
        self.filled = filled
        rises = filled.clip(lower=0).sum(axis=1, min_count=1)
        self.onchain = (
            (rises - self._transfers(filled).fillna(0)).clip(lower=0).where(rises.notna())
        )

    @staticmethod
    def _transfers(w):
        others = w.drop(columns=[BUY])
        falls = (-others).where(others <= -1.0, 0.0).clip(lower=0).fillna(0).sum(axis=1)
        rise = w[BUY].clip(lower=0)
        return pd.concat([falls, rise], axis=1).min(axis=1).where(rise.notna())

    def transfers(self):
        return self._transfers(self.filled)

    @staticmethod
    def roll(s, w=30):
        return s.rolling(w, min_periods=w).sum()


@pytest.fixture(scope="module")
def ind(data_dir) -> Ledger:
    return Ledger(data_dir)


@pytest.fixture(scope="module")
def pub(data_dir) -> dict:
    """What `capture build` publishes, built from the same snapshot."""
    src = "snapshot"
    return {
        "coverage": build.coverage_payload(data_dir, src),
        "summary": build.summary_payload(data_dir, src),
        "valuation": build.valuation_payload(data_dir, src),
        "distribution": build.distribution_payload(data_dir, src),
        "developer": build.developer_payload(data_dir, src),
        "usage": build.usage_payload(data_dir, src),
        "markers": build.markers_payload(data_dir),
        "prereg": build.prereg_payload(),
        "provenance": build.provenance_payload(data_dir, src),
    }


# ---------------------------------------------------------------- hashes
def test_every_file_matches_its_manifest_and_every_payload_cites_that_hash(data_dir, pub) -> None:
    hashes = {}
    for d in (data_dir, build.REFERENCE):
        for e in json.loads((d / "manifest.json").read_text(encoding="utf-8"))["files"]:
            assert sha(d / e["path"]) == e["sha256"], e["path"]
            hashes[e["path"]] = e["sha256"]
    for name in ("coverage", "summary", "valuation", "distribution", "developer", "usage"):
        for inp in pub[name]["inputs"]:
            assert inp["sha256"] == hashes[inp["path"]], (name, inp["path"])
    for s in pub["provenance"]["sources"] + pub["provenance"]["reference"]:
        assert s["sha256_8"] == hashes[s["path"]][:8]


# ---------------------------------------------------------------- coverage.json, every day
SERIES = ["issuance_gross_near", "buyback_near", "burnt_near", "volume_usd", "fees_usd"]


def _mine(ind: Ledger) -> dict:
    r = ind.roll
    out = {
        "issuance_gross_near": ind.issuance,
        "buyback_near": ind.bb,
        "burnt_near": ind.burn,
        "volume_usd": ind.vol,
        "fees_usd": ind.fees,
        "revenue_usd": ind.rev,
    }
    for k in (7, 30, 90):
        out[f"cr_float_{k}"] = r(ind.bb + ind.burn, k) / r(ind.issuance, k)
        out[f"cr_supply_{k}"] = r(ind.burn, k) / r(ind.issuance, k)
        out[f"cr_float_usd_{k}"] = r((ind.bb + ind.burn) * ind.price, k) / r(
            ind.issuance * ind.price, k
        )
        revenue = r(ind.rev, k)
        out[f"tau_eff_{k}"] = revenue.where(revenue > 0) / r(ind.vol, k)
    out["tau_eff_buyback_30"] = (r(ind.bb * ind.price) / r(ind.vol)).where(
        (r(ind.vol) > 0) & (r(ind.bb * ind.price) > 0)
    )
    return out


def test_every_daily_series_matches_on_every_day(ind, pub) -> None:
    series = pd.DataFrame(pub["coverage"]["series"]).assign(date=lambda d: pd.to_datetime(d.date))
    series = series.set_index("date")
    for col, mine in _mine(ind).items():
        theirs = series[col].astype(float)
        mine = mine.reindex(theirs.index)
        assert (theirs.isna() == mine.isna()).all(), f"{col}: empty days differ"
        both = theirs.notna()
        err = ((theirs[both] - mine[both]).abs() / mine[both].abs().clip(lower=1e-12)).max()
        assert err < 1e-9, f"{col}: relative error {err}"


def test_reconciliation_months(ind, pub) -> None:
    m = pd.DataFrame({"on": ind.onchain * ind.price, "dl": ind.rev}).dropna()
    g = m.groupby(m.index.to_period("M"))
    months = g.sum().assign(n=g.size())
    months = months[months["n"] == months.index.days_in_month]
    dev = months["on"] / months["dl"] - 1
    theirs = {r["month"]: r["deviation"] for r in pub["coverage"]["reconciliation"]["months"]}
    assert set(theirs) == {str(p) for p in dev.index}
    for p, v in dev.items():
        assert close(theirs[str(p)], v), p


# ---------------------------------------------------------------- summary.json and valuation start
def _start(ind: Ledger, as_of: str) -> dict:
    a, r = D(as_of), ind.roll
    return {
        "v0": ind.vol.rolling(30, min_periods=30).mean()[a],
        "S": ind.supply[a],
        "P": ind.price[a],
        "B": ind.burn.rolling(30, min_periods=30).mean()[a],
        "tau_bb": r(ind.bb * ind.price)[a] / r(ind.vol)[a],
        "tau_rev": r(ind.rev)[a] / r(ind.vol)[a],
    }


def _vstar(st: dict, inflation: float, tau: float, price: float | None = None) -> float:
    p = st["P"] if price is None else price
    return max((inflation * st["S"] / 365 - st["B"]) * p, 0.0) / tau


def test_summary_numbers(ind, pub) -> None:
    s, r = pub["summary"], ind.roll
    cr_usd = r((ind.bb + ind.burn) * ind.price) / r(ind.issuance * ind.price)
    cr = r(ind.bb + ind.burn) / r(ind.issuance)
    assert close(s["hero"]["cr_float_usd_30"], cr_usd[D(s["hero"]["date"])])
    assert f"{round(cr_usd[D(s['hero']['date'])] * 100)} cents" in s["hero"]["sentence"]
    assert close(s["this_week"]["value"], cr[D(s["this_week"]["date"])])
    best = s["history"]["cr_float_30_max"]
    assert close(best["value"], cr.max()) and best["date"] == cr.idxmax().date().isoformat()
    assert close(s["this_week"]["prev"], cr[D(s["this_week"]["prev_date"])])

    end = D(s["ledger"]["end"])
    w = slice(end - pd.Timedelta(days=29), end)
    p = ind.price[w]
    usd = {
        "volume": ind.vol[w].sum(),
        "fees": ind.fees[w].sum(),
        "revenue": ind.rev[w].sum(),
        "onchain_revenue": (ind.onchain[w] * p).sum(),
        "buyback_wallet": (ind.bb[w] * p).sum(),
        "burn": (ind.burn[w] * p).sum(),
        "issuance": (ind.issuance[w] * p).sum(),
    }
    for k, v in usd.items():
        assert close(s["ledger"]["usd"][k], v), k
    kept = s["ledger"]["kept"]["buyback_of_onchain"]
    assert close(kept, usd["buyback_wallet"] / usd["onchain_revenue"])

    st = _start(ind, s["levers"]["as_of"])
    stages = [(config.INFLATION_CURRENT, st["tau_bb"]), (config.INFLATION_PROPOSAL, st["tau_bb"]),
              (config.INFLATION_PROPOSAL, st["tau_rev"])]  # fmt: skip
    for step, (i, tau) in zip(s["levers"]["steps"], stages, strict=True):
        assert close(step["volume_multiple"], _vstar(st, i, tau) / st["v0"]), step["step"]
    cond = {c["id"]: c for c in s["conditions"]}
    assert close(cond["volume"]["progress"], st["v0"] / _vstar(st, 0.025, st["tau_bb"]))
    assert close(cond["routing"]["value"], kept)


def test_valuation_start_and_reverse_table(ind, pub) -> None:
    v = pub["valuation"]
    st = _start(ind, v["start"]["as_of"])
    mine = {"volume_usd_per_day": st["v0"], "total_supply_near": st["S"], "near_usd": st["P"],
            "burnt_near_per_day": st["B"], "tau_buyback_30": st["tau_bb"],
            "tau_revenue_30": st["tau_rev"]}  # fmt: skip
    for k, x in mine.items():
        assert close(v["start"][k], x), k
    for row in v["reverse"]["rows"]:
        tau = st["tau_bb"] if row["basis"] == "buyback" else st["tau_rev"]
        expected = (_vstar(st, row["inflation"], tau) / st["v0"]) ** (1 / row["horizon_years"]) - 1
        assert close(row["required_cagr"], expected), row


# ---------------------------------------------------------------- Monte Carlo, all 18 runs
def _growth(ind: Ledger) -> np.ndarray:
    daily = ind.llama_raw["volume_usd"].dropna()
    monthly = daily[daily.index >= pd.Timestamp(config.GROWTH_START)].resample("MS").mean()
    return np.log(monthly.dropna()).diff().dropna().to_numpy()


def test_every_monte_carlo_run_is_reproduced(ind, pub) -> None:
    v = pub["valuation"]
    st, g = _start(ind, v["start"]["as_of"]), _growth(ind)
    assert v["growth"]["n_months"] == len(g)
    assert close(v["growth"]["mean_all"], g.mean()) and close(v["growth"]["std_all"], g.std(ddof=1))
    n, months, block = v["n_paths"], v["n_months"], v["block_months"]
    rng = np.random.default_rng(v["seed"])
    starts = rng.integers(0, len(g) - block + 1, size=(n, -(-months // block)))
    boot = g[starts[:, :, None] + np.arange(block)].reshape(n, -1)[:, :months]
    taus = rng.uniform(
        v["start"]["tau_monthly_range"]["min"], v["start"]["tau_monthly_range"]["max"], n
    )
    mu, t = g.mean(), np.arange(1, months + 1)
    growth = {
        "historical": boot,
        "flat": boot - mu,
        "decay": boot - mu + mu * 0.5 ** ((t - 1) / config.DECAY_HALF_LIFE_MONTHS),
    }
    ramp = np.clip((t - config.INFLATION_GRACE_MONTHS) / config.INFLATION_RAMP_MONTHS, 0, 1)
    paths = {
        "constant_2.5": np.full(months, config.INFLATION_CURRENT),
        "ramp_to_1.6": config.INFLATION_CURRENT
        + (config.INFLATION_PROPOSAL - config.INFLATION_CURRENT) * ramp,
    }
    for run in v["scenarios"]:
        price = st["P"] * run["price_multiplier"]
        volume = st["v0"] * np.exp(np.cumsum(growth[run["scenario"]], axis=1))
        issuance = paths[run["inflation_path"]] * st["S"] / 365 * price
        cr = (taus[:, None] * volume + st["B"] * price) / issuance
        key = (run["scenario"], run["inflation_path"], run["price_multiplier"])
        for m, p in run["p_cr_ge_1"].items():
            assert p == float((cr[:, int(m) - 1] >= 1).mean()), (key, m)
        hit = cr >= 1
        first = float(np.median(np.where(hit.any(1), hit.argmax(1) + 1.0, np.inf)))
        assert run["median_first_month"] == (first if np.isfinite(first) else "not reached"), key
        for label, q in (("p10", 10), ("p50", 50), ("p90", 90)):
            assert np.allclose(run["fan"][label], np.percentile(cr, q, axis=0), rtol=1e-12), key
        for m, x in run["volume_p50_usd_per_day"].items():
            assert close(x, float(np.median(volume[:, int(m) - 1]))), key


# ---------------------------------------------------------------- markers
def test_markers(ind, pub) -> None:
    mk = {m["id"]: m for m in pub["markers"]["markers"]}
    iss = ind.issuance.dropna()
    pos = iss.index.get_loc(D(mk["issuance_step"]["date"]))
    before, after = iss.iloc[pos - 15 : pos - 1].mean(), iss.iloc[pos : pos + 14].mean()
    assert iss.iloc[pos - 1] < iss.iloc[pos - 15 : pos - 1].min()  # transition day
    assert f"{before:,.0f} to {after:,.0f}" in mk["issuance_step"]["label"]
    tr = ind.transfers()
    assert mk["internal_transfer"]["date"] == tr.idxmax().date().isoformat()
    assert f"{tr.max():,.0f} NEAR" in mk["internal_transfer"]["label"]
    assert (
        mk["buyback_wallet_first_inflow"]["date"] == ind.bb.first_valid_index().date().isoformat()
    )


# ---------------------------------------------------------------- distribution.json, every period
def _period(dates: pd.Series, freq: str) -> pd.Series:
    if freq == "month":
        return dates.dt.to_period("M").astype(str)
    return (dates - pd.to_timedelta(dates.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")


def test_every_distribution_period(data_dir, ind, pub) -> None:
    dist = pub["distribution"]
    rd = lambda n: pd.read_parquet(data_dir / f"{n}.parquet").assign(  # noqa: E731
        date=lambda d: pd.to_datetime(d["date"])
    )
    ex, ch, rc = (
        rd("explorer_1click_daily"),
        rd("explorer_channels_daily"),
        rd("explorer_recipients_daily"),
    )
    tokens = pd.read_parquet(data_dir / "token_assets.parquet").drop_duplicates("asset_id")
    ex["symbol"] = ex["asset_in"].map(tokens.set_index("asset_id")["symbol"]).fillna("(unmapped)")
    near = set(dist["near_revenue_wallets"])
    stables = set(dist["stablecoin_symbols"])
    ex["near_only"] = ex["affiliate"].map(
        lambda a: bool([r for r in a.split(",") if r]) and all(r in near for r in a.split(",") if r)
    )
    onchain_usd = (ind.onchain * ind.price).reindex(pd.Index(rc["date"].unique())).dropna()
    dl = ind.llama_raw["volume_usd"]

    def hhi(s):
        sh = s / s.sum()
        return (
            float((sh**2).sum()),
            float(sh.sort_values(ascending=False).iloc[:5].sum()),
            float(sh.max()),
        )

    for freq in ("month", "week"):
        ex["p"], ch["p"], rc["p"] = (
            _period(ex["date"], freq),
            _period(ch["date"], freq),
            _period(rc["date"], freq),
        )
        on_by = onchain_usd.groupby(
            _period(pd.Series(onchain_usd.index, index=onchain_usd.index), freq)
        ).sum()
        exd = ex.groupby("date")["volume_usd"].sum()
        both = pd.concat([exd, dl], axis=1, keys=["e", "d"], sort=True).dropna()
        cov = both.groupby(_period(pd.Series(both.index, index=both.index), freq)).sum()
        for row in dist["periods"][freq]:
            p = row["period"]
            c = ch[ch["p"] == p].groupby("referral")["volume_usd"].sum()
            a = ex[ex["p"] == p].groupby("symbol")["volume_usd"].sum()
            e = ex[ex["p"] == p]
            total = e["volume_usd"].sum()
            (hc, tc, mc), (ha, ta, ma) = hhi(c), hhi(a)
            mine = {
                "volume_usd": c.sum(),
                "hhi_channel": hc, "top5_channel_share": tc, "max_channel_share": mc,
                "hhi_asset": ha, "top5_asset_share": ta, "max_asset_share": ma,
                "zec_share": a.get("ZEC", 0.0) / a.sum(),
                "stablecoin_share": a[a.index.isin(stables)].sum() / a.sum(),
                "near_wallet_only_share": e.loc[e["near_only"], "volume_usd"].sum() / total,
                "no_app_fee_share": e.loc[e["affiliate"] == "", "volume_usd"].sum() / total,
            }  # fmt: skip
            r = rc[rc["p"] == p]
            near_fee = r.loc[r["recipient"].isin(near), "fee_usd"].sum()
            mine["declared_fee_share_to_near"] = near_fee / r["fee_usd"].sum()
            if p in on_by.index and on_by[p] > 0:
                mine["attributable_share"] = near_fee / on_by[p]
            if p in cov.index:
                mine["explorer_share_of_defillama_volume"] = cov.loc[p, "e"] / cov.loc[p, "d"]
            for k, x in mine.items():
                assert close(row[k], float(x)), (freq, p, k)

    take = dist["take_rates"]["monthly"]
    f = ind.llama_raw[["volume_usd", "fees_usd", "revenue_usd"]].dropna()
    f = f[f["volume_usd"] > 0]
    sums = f.groupby(f.index.to_period("M")).sum()
    for row in take:
        s = sums.loc[pd.Period(row["period"])]
        assert close(row["fees_take_rate"], s["fees_usd"] / s["volume_usd"]), row["period"]
        assert close(row["revenue_take_rate"], s["revenue_usd"] / s["volume_usd"]), row["period"]


# ---------------------------------------------------------------- developer.json
def test_every_cohort_and_the_lead_lag_table(data_dir, ind, pub) -> None:
    dev = pub["developer"]
    cd = pd.read_parquet(data_dir / "contracts_daily.parquet").assign(
        date=lambda d: pd.to_datetime(d["date"])
    )
    start, last = cd["date"].min(), cd["date"].max()
    first_row = cd.groupby("contract_account")["date"].min()
    first_dep = cd[cd["deploys"] > 0].groupby("contract_account")["date"].min()
    first_row = first_row.reindex(first_dep.index)
    new = first_dep[(first_dep >= start + pd.Timedelta(days=30)) & (first_row >= first_dep)]
    cohort = new.dt.to_period("M")
    calls = (
        cd.assign(m=cd["date"].dt.to_period("M"))
        .groupby(["contract_account", "m"])["function_calls_received"]
        .sum()
    )
    last_complete = (
        last.to_period("M")
        if last == last.to_period("M").end_time.normalize()
        else last.to_period("M") - 1
    )
    for table, min_calls in (("cohorts", 1), ("cohorts_strict", 10)):
        rows = dev[table] if table == "cohorts" else dev[table]["rows"]
        active = calls[calls >= min_calls]
        for row in rows:
            members = set(cohort[cohort == pd.Period(row["cohort"])].index)
            assert row["cohort_size"] == len(members), row["cohort"]
            for k in (1, 2, 3):
                target = pd.Period(row["cohort"]) + k
                if target > last_complete:
                    assert row[f"share_{k}"] is None
                    continue
                kept = (
                    members & set(active.xs(target, level=1).index)
                    if target in active.index.get_level_values(1)
                    else set()
                )
                assert close(row[f"share_{k}"], len(kept) / len(members)), (table, row["cohort"], k)

    # Lead/lag: x(t) = cohort t-1 still called in t (complete cohorts), y = monthly revenue.
    valid = [c for c in dev["cohorts"] if c["complete"] and c["retained_1"] is not None]
    x = pd.Series(
        [float(c["retained_1"]) for c in valid],
        index=pd.PeriodIndex([pd.Period(c["cohort"]) + 1 for c in valid]),
    )
    rev = ind.llama_raw["revenue_usd"].dropna()
    g = rev.groupby(rev.index.to_period("M"))
    y = g.sum()[g.size() == g.sum().index.days_in_month]
    months = pd.period_range(
        min(x.index.min(), y.index.min()), max(x.index.max(), y.index.max()), freq="M"
    )
    x, y = x.reindex(months), y.reindex(months)
    split = pd.Period("2026-05", "M")

    def r_of(a, b):
        return None if np.std(a) == 0 or np.std(b) == 0 else float(np.corrcoef(a, b)[0, 1])

    for row in dev["lead_lag"]["rows"]:
        xs_, ys_ = (x.diff(), y.diff()) if row["transform"] == "diff" else (x, y)
        pairs = []
        for t, xv in xs_.dropna().items():
            yv = ys_.get(t + row["lag"])
            in_sample = t + row["lag"] < split if row["sample"] == "train" else t >= split
            if yv is not None and not pd.isna(yv) and in_sample:
                pairs.append((xv, yv))
        assert row["n"] == len(pairs), row
        if len(pairs) < 4:
            assert row["pearson"] is None
            continue
        a, b = np.array(pairs).T
        obs = r_of(a, b)
        assert close(row["pearson"], obs), row
        assert close(
            row["spearman"], r_of(pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy())
        ), row
        za, zb = (a - a.mean()) / a.std(), (b - b.mean()) / b.std()
        if len(a) <= 8:
            shuffled = zb[np.array(list(itertools.permutations(range(len(a)))))]
        else:
            rng = np.random.default_rng(config.RANDOM_SEED + row["lag"])
            shuffled = rng.permuted(np.tile(zb, (10_000, 1)), axis=1)
        p = float(np.mean(np.abs((shuffled * za).mean(axis=1)) >= abs(obs) - 1e-12))
        assert close(row["p_value"], p), row


# ---------------------------------------------------------------- usage.json
USAGE_MEAN = ("active_signers", "intents_signers", "near_usd")
USAGE_SPLIT = D("2026-08-10")  # the split week of the plan, fixed before the result was seen


def _usage_weekly(data_dir) -> tuple[pd.DataFrame, pd.DataFrame]:
    def rd(name, cols):
        df = pd.read_parquet(data_dir / f"{name}.parquet")
        return df.assign(date=pd.to_datetime(df["date"])).set_index("date")[cols]

    daily = (
        pd.concat(
            [
                rd(
                    "network_daily",
                    ["active_signers", "tx_count", "new_accounts", "function_calls"],
                ),
                rd("intents_onchain_daily", ["calls_to_intents", "unique_signers"]).rename(
                    columns={"unique_signers": "intents_signers"}
                ),
                rd("defillama_intents_daily", ["volume_usd"]),
                rd("price_daily", ["near_usd"]),
            ],
            axis=1,
            join="inner",
        )
        .dropna()
        .sort_index()
    )
    monday = daily.index - pd.to_timedelta(daily.index.day_of_week, unit="D")
    grouped = daily.groupby(monday)
    weekly = grouped.agg({c: "mean" if c in USAGE_MEAN else "sum" for c in daily.columns})
    return daily, weekly[grouped.size() == 7]


def _usage_rows(weekly: pd.DataFrame) -> dict:
    """(usage, predictor, sample, lag) -> (n, pearson, spearman, p) on weekly log changes."""
    full = pd.date_range(weekly.index.min(), weekly.index.max(), freq="7D")

    def r_of(a, b):
        return None if np.std(a) == 0 or np.std(b) == 0 else float(np.corrcoef(a, b)[0, 1])

    out = {}
    for u in ("active_signers", "tx_count"):
        for p in ("volume_usd", "near_usd"):
            x = np.log(weekly[p]).reindex(full).diff()
            y = np.log(weekly[u]).reindex(full).diff()
            for sample in ("train", "test"):
                for lag in range(4):
                    pairs = []
                    for t, xv in x.dropna().items():
                        later = t + pd.Timedelta(weeks=lag)
                        yv = y.get(later)
                        ok = later < USAGE_SPLIT if sample == "train" else t >= USAGE_SPLIT
                        if yv is not None and not pd.isna(yv) and ok:
                            pairs.append((xv, yv))
                    key = (u, p, sample, lag)
                    obs = None
                    if len(pairs) >= 4:
                        a, b = np.array(pairs).T
                        obs = r_of(a, b)
                    if obs is None:
                        out[key] = (len(pairs), None, None, None)
                        continue
                    rank = r_of(pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy())
                    za, zb = (a - a.mean()) / a.std(), (b - b.mean()) / b.std()
                    if len(a) <= 8:
                        shuffled = zb[np.array(list(itertools.permutations(range(len(a)))))]
                    else:
                        rng = np.random.default_rng(config.RANDOM_SEED + lag)
                        shuffled = rng.permuted(np.tile(zb, (10_000, 1)), axis=1)
                    pv = float(np.mean(np.abs((shuffled * za).mean(axis=1)) >= abs(obs) - 1e-12))
                    out[key] = (len(pairs), obs, rank, pv)
    return out


def test_usage_is_recomputed_independently(data_dir, pub) -> None:
    u = pub["usage"]
    daily, weekly = _usage_weekly(data_dir)
    assert u["window"] == {
        "first_date": daily.index.min().date().isoformat(),
        "last_date": daily.index.max().date().isoformat(),
        "days": len(daily),
    }
    assert [w["week"] for w in u["weekly"]] == [d.date().isoformat() for d in weekly.index]
    for row, (_, mine) in zip(u["weekly"], weekly.iterrows(), strict=True):
        for column, value in mine.items():
            assert close(row[column], float(value)), (row["week"], column)

    calls = daily["calls_to_intents"].sum() / daily["function_calls"].sum()
    signers = (daily["intents_signers"] / daily["active_signers"]).mean()
    assert close(u["shares"]["intents_call_share"], float(calls))
    assert close(u["shares"]["intents_signer_share"], float(signers))

    n = len(weekly)
    first, second = weekly.iloc[: n // 2].mean(), weekly.iloc[n // 2 :].mean()
    h = u["halves"]
    assert h["weeks"] == n and h["first"]["weeks"] == n // 2
    assert h["first"]["start"] == weekly.index[0].date().isoformat()
    assert h["second"]["end"] == (weekly.index[-1] + pd.Timedelta(days=6)).date().isoformat()
    for column, change in h["change"].items():
        assert close(change, float(second[column] / first[column] - 1)), column

    mine = _usage_rows(weekly)
    assert u["lead_lag"]["split_week"] == USAGE_SPLIT.date().isoformat()
    for row in u["lead_lag"]["rows"]:
        n_, r, rank, p = mine[(row["usage"], row["predictor"], row["sample"], row["lag"])]
        assert row["n"] == n_, row
        assert close(row["pearson"], r) and close(row["spearman"], rank), row
        assert close(row["p_value"], p), row

    # The verdict, re-derived from the recomputed rows by the rule in METHODOLOGY.md.
    v = u["lead_lag"]["verdict"]
    text = v["text"]
    results = {}
    for usage in ("active_signers", "tx_count"):
        sides = {}
        for predictor in ("volume_usd", "near_usd"):
            train = [
                (lag, mine[(usage, predictor, "train", lag)][1])
                for lag in (1, 2, 3)
                if mine[(usage, predictor, "train", lag)][1] is not None
            ]
            if not train:
                sides[predictor] = None
                continue
            lag, train_r = min(train, key=lambda item: (-abs(item[1]), item[0]))
            n_, test_r, _, p = mine[(usage, predictor, "test", lag)]
            if test_r is None:
                sides[predictor] = None
                continue
            leads = p < 0.1 and np.sign(train_r) == np.sign(test_r)
            sides[predictor] = (leads, test_r)
            assert f"r={train_r:.2f} in training and r={test_r:.2f} on {n_} test weeks" in text
            assert f"(p={p:.2f})" in text
        vol, price = sides["volume_usd"], sides["near_usd"]
        if vol is None or price is None:
            results[usage] = "insufficient_data"
        elif vol[0] and (not price[0] or abs(vol[1]) > abs(price[1])):
            results[usage] = "volume_leads"
        elif price[0]:
            results[usage] = "price_leads"
        else:
            results[usage] = "null"
    assert {b["usage"]: b["result"] for b in v["by_usage"]} == results
    if "insufficient_data" in results.values():
        overall = "insufficient_data"
    elif set(results.values()) == {"volume_leads"}:
        overall = "supported"
    else:
        overall = "not_supported"
    assert v["result"] == overall
    assert v["label"] == overall.replace("_", " ")


# ---------------------------------------------------------------- reference parameters
def test_policy_parameters_come_from_the_reference_file(ind) -> None:
    with (build.REFERENCE / "parameters.csv").open(encoding="utf-8", newline="") as f:
        params = {r["name"]: float(r["value"]) for r in csv.DictReader(f)}
    assert params["inflation_current"] == config.INFLATION_CURRENT
    assert params["hsp029_target"] == config.INFLATION_PROPOSAL
    assert params["hsp029_ramp_months"] == config.INFLATION_RAMP_MONTHS
    assert params["hsp029_grace_months"] == config.INFLATION_GRACE_MONTHS
    # 2.5 % is the observed rate: 30-day annualised net supply growth at the last day of data.
    s = ind.supply.dropna()
    growth = (s.iloc[-1] / s.iloc[-31]) ** (365 / 30) - 1
    assert abs(growth - params["inflation_current"]) < 0.001


def test_methodology_claims(ind, pub) -> None:
    g = _growth(ind)
    assert len(g) == 16 and len(g) - config.MC_BLOCK_MONTHS + 1 == 14
    st = _start(ind, pub["valuation"]["start"]["as_of"])
    a = D(pub["valuation"]["start"]["as_of"])
    window = ind.issuance[a - pd.Timedelta(days=29) : a].sum()
    assert abs(config.INFLATION_CURRENT * st["S"] / 365 * 30 / window - 1) < 0.001


# ---------------------------------------------------------------- what THESIS and the README cite
# Every JSON path that THESIS.md or the README results block uses (with list positions and selectors
# written as [*]) must be named here, and each one is recomputed by a test below. test_thesis.py
# fails when the thesis starts citing a path that is not listed.
def test_the_multiple_does_not_move_with_the_volume_definition(ind, pub) -> None:
    s = pub["summary"]
    st = _start(ind, s["levers"]["as_of"])
    revenue = st["tau_bb"] * st["v0"]
    for row in s["invariance"]["rows"]:
        volume = st["v0"] * row["volume_scale"]
        v_star = _vstar(st, config.INFLATION_CURRENT, revenue / volume)
        assert close(row["v_star_usd_per_day"], v_star), row["volume_scale"]
        assert close(row["volume_multiple"], v_star / volume), row["volume_scale"]
        assert close(row["volume_multiple"], s["levers"]["steps"][0]["volume_multiple"])


def test_every_definition_row(ind, pub) -> None:
    rows = {r["id"]: r for r in pub["summary"]["definitions"]["rows"]}
    proxy = ind.llama_raw["holders_revenue_usd"].reindex(ind.idx) / ind.price
    numerators = {
        "headline": (ind.bb.fillna(0) + ind.burn, 30, True),
        "window_90": (ind.bb.fillna(0) + ind.burn, 90, True),
        "all_wallets": (ind.onchain.fillna(0) + ind.burn, 30, True),
        "defillama_proxy": (proxy.fillna(0) + ind.burn, 30, True),
        "all_wallets_ytd": (ind.onchain.fillna(0), None, False),
        "burn_only": (ind.burn, 30, False),
    }
    for key, (top, days, usd) in numerators.items():
        row = rows[key]
        end = D(row["end"])
        start = D(f"{end.year}-01-01") if days is None else end - pd.Timedelta(days=days - 1)
        assert row["start"] == start.date().isoformat(), key
        w = slice(start, end)
        t, b = top[w], ind.issuance[w]
        if usd:
            t, b = t * ind.price[w], b * ind.price[w]
        assert close(row["value"], t.sum() / b.sum()), key
    # the headline row is the published CR_float in USD on the same day
    cr_usd = ind.roll((ind.bb + ind.burn) * ind.price) / ind.roll(ind.issuance * ind.price)
    assert close(rows["headline"]["value"], cr_usd[D(rows["headline"]["end"])])


def test_the_official_row_is_quoted_from_the_stored_page(ind, pub) -> None:
    row = next(r for r in pub["summary"]["definitions"]["rows"] if r.get("quoted"))
    page = (build.REFERENCE / "revenue_near_org.html").read_text(encoding="utf-8")
    page = page.replace('\\"', '"')
    m = re.search(r'\{"date":"' + row["end"] + r'","emissionsNear":[^{}]*\}', page)
    found = json.loads(m.group(0))
    assert close(row["official_emissions_near"], found["emissionsNear"])
    assert close(row["official_revenue_near"], found["revenueNear"])
    assert close(row["value"], found["revenueNear"] / found["emissionsNear"])
    w = slice(D(row["start"]), D(row["end"]))
    assert close(row["our_issuance_near"], ind.issuance[w].sum())
    assert close(row["our_revenue_near"], ind.onchain[w].sum())


def test_the_buyback_wallet_flows_are_rebuilt_from_its_activity(ind, pub) -> None:
    flows = pub["summary"]["buyback_flows"]
    path = build.REFERENCE / "buyback_wallet_activities.json"
    if flows is None:
        assert not path.exists()
        return
    acts = sorted(json.loads(path.read_text(encoding="utf-8"))["activities"],
                  key=lambda a: int(a["event_index"]))  # fmt: skip
    prev, sums, out, senders = 0, {"intents": 0.0, "revenue_wallet": 0.0, "other": 0.0}, 0.0, set()
    start, end = D(flows["start"]), D(flows["end"])
    others = {"fefundsadmin.sputnik-dao.near", "1csfundsadmin.sputnik-dao.near"}
    for a in acts:
        bal = int(a["absolute_nonstaked_amount"])
        change, prev = (bal - prev) / 10**24, bal
        day = pd.Timestamp(int(a["block_timestamp"]), unit="ns").normalize()
        if not start <= day <= end:
            continue
        who = a["involved_account_id"]
        if change > 0:
            kind = (
                "intents"
                if who == "intents.near"
                else "revenue_wallet"
                if who in others
                else "other"
            )
            sums[kind] += change
            if kind == "other":
                senders.add(who)
        else:
            out -= change
    for k, v in sums.items():
        assert close(flows["inflow_near"][k], v, 1e-6), k
    assert close(flows["outflow_near"], out, 1e-6) and flows["other_senders"] == len(senders)
    assert close(flows["net_near"], sum(sums.values()) - out, 1e-6)
    assert close(flows["net_balance_change_near"], ind.filled[BUY][start:end].sum(), 1e-9)
    counted = ind.bb[start:end].sum()
    assert close(flows["counted_as_buyback_near"], counted)
    assert close(flows["other_share_of_counted"], sums["other"] / counted, 1e-6)


def test_the_volume_check_is_recomputed_from_the_stored_legs(ind, pub) -> None:
    v = pub["summary"]["volume_check"]
    legs = pd.read_parquet(build.REFERENCE / "intents_stable_legs_daily.parquet")
    days = pd.to_datetime(legs["date"])
    llama = ind.vol.reindex(days)
    assert v["start"] == days.min().date().isoformat() and v["end"] == days.max().date().isoformat()
    assert close(v["ratio"], legs["stable_leg_volume_usd"].sum() / llama.sum())


def test_the_hsp029_vote_is_read_from_the_stored_reply(pub) -> None:
    g = pub["summary"]["governance"]["hsp029"]
    raw = json.loads((build.REFERENCE / "hsp029_vote.json").read_text(encoding="utf-8"))
    p = raw["proposal"]
    cast = int(p["total_votes"]["total_venear"])
    assert g["status"] == p["status"] and g["read_at_block"] == raw["block_height"]
    assert g["contract"] == raw["request"]["account_id"] == "vote.dao"
    assert close(g["top_option_share"], max(int(v["total_venear"]) for v in p["votes"]) / cast)
    assert close(g["turnout"], cast / int(p["snapshot_and_state"]["total_venear"]))
    end_s = (int(p["voting_start_time_ns"]) + int(p["voting_duration_ns"])
             + int(p["timelock_duration_ns"])) // 10**9  # fmt: skip
    stamp = pd.Timestamp(end_s, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    assert g["timelock_end_utc"] == stamp


AUDITED = {
    "coverage.availability.buyback_near.first_date",
    "coverage.latest.cr_supply_30.date",
    "coverage.latest.cr_supply_30.value",
    "developer.lead_lag.verdict.text",
    "distribution.periods.month[*].attributable_share",
    "distribution.periods.month[*].hhi_channel",
    "distribution.periods.month[*].max_channel_share",
    "distribution.periods.month[*].period",
    "distribution.periods.month[*].stablecoin_share",
    "distribution.scope.explorer_share_of_defillama_volume_by_month[*].explorer_share_of_defillama_volume",
    "distribution.scope.explorer_share_of_defillama_volume_by_month[*].period",
    "markers.not_drawn[*].label",
    "markers.not_drawn[*].reason",
    "provenance.proof.block_height",
    "provenance.proof.explorer_url",
    "provenance.proof.run_id",
    "provenance.reconciliation.months#len",
    "provenance.reconciliation.tolerance",
    "provenance.sources[*].date_range[*]",
    "summary.conditions[*].progress",
    "summary.conditions[*].text",
    "summary.conditions[*].threshold",
    "summary.conditions[*].value",
    "summary.definitions.rows[*].end",
    "summary.definitions.rows[*].label",
    "summary.definitions.rows[*].official_emissions_near",
    "summary.definitions.rows[*].official_revenue_near",
    "summary.definitions.rows[*].our_issuance_near",
    "summary.definitions.rows[*].our_revenue_near",
    "summary.definitions.rows[*].start",
    "summary.definitions.rows[*].value",
    "summary.buyback_flows.end",
    "summary.buyback_flows.inflow_near.intents",
    "summary.buyback_flows.inflow_near.other",
    "summary.buyback_flows.inflow_near.revenue_wallet",
    "summary.buyback_flows.net_balance_change_near",
    "summary.buyback_flows.net_near",
    "summary.buyback_flows.other_senders",
    "summary.buyback_flows.other_share_of_counted",
    "summary.buyback_flows.outflow_near",
    "summary.buyback_flows.start",
    "summary.governance.hsp029.read_at_block",
    "summary.governance.hsp029.timelock_end_utc",
    "summary.governance.hsp029.top_option_share",
    "summary.governance.hsp029.turnout",
    "summary.hero.cr_float_30",
    "summary.hero.cr_float_usd_30",
    "summary.hero.date",
    "summary.history.cr_float_30_max.date",
    "summary.history.cr_float_30_max.value",
    "summary.invariance.rows[*].v_star_usd_per_day",
    "summary.invariance.rows[*].volume_multiple",
    "summary.ledger.days",
    "summary.ledger.kept.buyback_of_onchain",
    "summary.ledger.per_10k_volume.buyback_wallet",
    "summary.ledger.per_10k_volume.fees",
    "summary.ledger.per_10k_volume.issuance",
    "summary.ledger.per_10k_volume.revenue",
    "summary.ledger.per_10k_volume.volume",
    "summary.levers.as_of",
    "summary.levers.steps[*].closes_by",
    "summary.levers.steps[*].inflation",
    "summary.levers.steps[*].v_star_usd_per_day",
    "summary.levers.steps[*].volume_multiple",
    "summary.levers.volume_usd_per_day",
    "summary.volume_check.end",
    "summary.volume_check.ratio",
    "summary.volume_check.start",
    "valuation.growth.mean_after_launch",
    "valuation.growth.mean_all",
    "valuation.growth.n_months",
    "valuation.n_months",
    "valuation.n_paths",
    "valuation.reverse.rows[*].horizon_years",
    "valuation.reverse.rows[*].inflation",
    "valuation.reverse.rows[*].required_cagr",
    "valuation.scenarios[*].p_cr_ge_1.60",
    "valuation.scenarios[*].volume_p50_usd_per_day.60",
    "valuation.start.tau_monthly_range.max",
    "valuation.start.tau_monthly_range.min",
}
# Text written in the code (definitions and assumptions), reviewed in docs/METHODOLOGY.md rather
# than recomputed: a number inside them is a method constant, not a measurement.
DESCRIPTIVE = {
    "distribution.scope.covers",
    "valuation.assumptions.price",
    "valuation.notes[*]",
}


def test_the_monthly_buyback_take_rate_range(ind, pub) -> None:
    usd = ind.bb * ind.price
    both = usd.notna() & ind.vol.notna()
    frame = pd.DataFrame({"b": usd[both], "v": ind.vol[both]})
    grouped = frame.groupby(frame.index.to_period("M"))
    sums, days = grouped.sum(), grouped.size()
    keep = (days / sums.index.days_in_month >= 0.9) & (sums["v"] > 0)
    tau = (sums["b"] / sums["v"])[keep]
    rng = pub["valuation"]["start"]["tau_monthly_range"]
    assert close(rng["min"], float(tau.min())) and close(rng["max"], float(tau.max()))
    shown = {m["month"]: m["tau_buyback"] for m in rng["months"]}
    assert set(shown) == {f"{p}-01" for p in tau.index.astype(str)}
    for p, v in tau.items():
        assert close(shown[f"{p}-01"], float(v)), p


def test_the_three_conditions_and_the_lever_steps(ind, pub) -> None:
    s = pub["summary"]
    as_of = s["levers"]["as_of"]
    st = _start(ind, as_of)
    assert as_of == pub["valuation"]["start"]["as_of"]
    assert close(s["levers"]["volume_usd_per_day"], st["v0"])

    end = D(as_of)
    window = slice(end - pd.Timedelta(days=29), end)
    assert s["ledger"]["days"] == 30 == len(ind.vol[window])
    price = ind.price[window]
    kept = (ind.bb[window] * price).sum() / (ind.onchain[window] * price).sum()

    m = pd.DataFrame({"on": ind.onchain * ind.price, "dl": ind.rev}).dropna()
    g = m.groupby(m.index.to_period("M"))
    months = g.sum().assign(n=g.size())
    months = months[months["n"] == months.index.days_in_month]
    worst = float((months["on"] / months["dl"] - 1).abs().max())

    vstar = _vstar(st, config.INFLATION_CURRENT, st["tau_bb"])
    c = {x["id"]: x for x in s["conditions"]}
    assert close(c["volume"]["value"], st["v0"]) and close(c["volume"]["threshold"], vstar)
    assert close(c["volume"]["progress"], st["v0"] / vstar)
    assert close(c["routing"]["value"], kept) and c["routing"]["threshold"] == 1.0
    assert close(c["routing"]["progress"], kept)
    assert close(c["reconciliation"]["value"], worst)
    assert c["reconciliation"]["threshold"] == 0.15  # the tolerance documented in METHODOLOGY.md
    assert close(c["reconciliation"]["progress"], worst / 0.15)
    met = [bool(c[k]["met"]) for k in ("volume", "routing", "reconciliation")]
    assert met == [st["v0"] >= vstar, kept >= 1.0, worst > 0.15]

    stages = [
        (config.INFLATION_CURRENT, st["tau_bb"]),
        (config.INFLATION_PROPOSAL, st["tau_bb"]),
        (config.INFLATION_PROPOSAL, st["tau_rev"]),
    ]
    previous = None
    for step, (i, tau) in zip(s["levers"]["steps"], stages, strict=True):
        v_star = _vstar(st, i, tau)
        multiple = v_star / st["v0"]
        assert step["inflation"] == i and close(step["v_star_usd_per_day"], v_star)
        assert close(step["volume_multiple"], multiple)
        if previous is None:
            assert step["closes_by"] is None
        else:
            assert close(step["closes_by"], previous / multiple)
        previous = multiple


def test_growth_after_the_launch_phase(ind, pub) -> None:
    daily = ind.llama_raw["volume_usd"].dropna()
    monthly = daily[daily.index >= pd.Timestamp(config.GROWTH_START)].resample("MS").mean().dropna()
    growth = np.log(monthly).diff().dropna()
    after = growth[growth.index >= pd.Timestamp(f"{build.LAUNCH_END}-01")]
    g = pub["valuation"]["growth"]
    assert close(g["mean_after_launch"], float(after.mean()))
    assert g["n_months_after_launch"] == len(after)
    assert pub["valuation"]["n_paths"] == config.MC_PATHS
    assert pub["valuation"]["n_months"] == config.MC_MONTHS


def test_explorer_coverage_by_month_in_the_scope(data_dir, ind, pub) -> None:
    ex = pd.read_parquet(data_dir / "explorer_1click_daily.parquet")
    ex["date"] = pd.to_datetime(ex["date"])
    explorer = ex.groupby("date")["volume_usd"].sum()
    for row in pub["distribution"]["scope"]["explorer_share_of_defillama_volume_by_month"]:
        month = pd.Period(row["period"])
        days = [d for d in explorer.index if d.to_period("M") == month and pd.notna(ind.vol.get(d))]
        share = explorer[days].sum() / ind.vol[days].sum()
        assert close(row["explorer_share_of_defillama_volume"], float(share)), row["period"]


def test_the_not_drawn_events_are_the_reference_rows(pub) -> None:
    with (build.REFERENCE / "events.csv").open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["kind"] == "not_drawn"]
    shown = [(n["label"], n["reason"]) for n in pub["markers"]["not_drawn"]]
    assert shown == [(r["label"], r["verified"]) for r in rows]


def test_every_source_range_is_the_range_of_its_file(data_dir, pub) -> None:
    for source in pub["provenance"]["sources"]:
        if not source["date_range"]:
            continue
        dates = pd.to_datetime(pd.read_parquet(data_dir / source["path"], columns=["date"])["date"])
        shown = [dates.min().date().isoformat(), dates.max().date().isoformat()]
        assert shown == list(source["date_range"]), source["path"]


def test_the_latest_supply_coverage_and_the_documented_tolerance(ind, pub) -> None:
    cr = ind.roll(ind.burn) / ind.roll(ind.issuance)
    last = cr.dropna().index[-1]
    latest = pub["coverage"]["latest"]["cr_supply_30"]
    assert latest["date"] == last.date().isoformat() and close(latest["value"], float(cr[last]))
    assert pub["provenance"]["reconciliation"]["tolerance"] == 0.15
    assert "15%" in (build.ROOT / "docs" / "METHODOLOGY.md").read_text(encoding="utf-8")
    first_buyback = ind.bb.first_valid_index().date().isoformat()
    assert pub["coverage"]["availability"]["buyback_near"]["first_date"] == first_buyback


def test_the_lead_lag_verdict_quotes_the_audited_rows(pub) -> None:
    """The verdict sentence is built from the table; its numbers must be the table's."""
    dev = pub["developer"]["lead_lag"]
    rows = [r for r in dev["rows"] if r["transform"] == "levels" and r["pearson"] is not None]
    train = [r for r in rows if r["sample"] == "train"]
    chosen = max(train, key=lambda r: abs(r["pearson"]))
    test = next(r for r in rows if r["sample"] == "test" and r["lag"] == chosen["lag"])
    text = dev["verdict"]["text"]
    assert f"r={chosen['pearson']:.2f}" in text
    assert f"r={test['pearson']:.2f} on {test['n']} pairs" in text
    assert f"p={test['p_value']:.2f}" in text
    assert dev["verdict"]["lag_chosen_in_train"] == chosen["lag"]


@pytest.mark.skipif(os.environ.get("CAPTURE_ONLINE") != "1", reason="reads the NEAR chain")
def test_the_recorded_transaction_is_on_chain_at_that_block(data_dir) -> None:
    """Online (CAPTURE_ONLINE=1): proof.json's block height is the block of its transaction, and
    the manifest in this repository still has the recorded hash."""
    import httpx

    record = json.loads((build.ROOT / "data" / "proof.json").read_text(encoding="utf-8"))
    near = record["near"]
    assert near["network"] == "testnet", "only testnet is wired for this check"
    rpc = "https://rpc.testnet.fastnear.com"

    def call(method: str, params: dict) -> dict:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        return httpx.post(rpc, json=body, timeout=30).json()["result"]

    tx = call(
        "tx",
        {"tx_hash": near["tx_hash"], "sender_account_id": near["signer"], "wait_until": "FINAL"},
    )
    block = call("block", {"block_id": tx["transaction_outcome"]["block_hash"]})
    assert block["header"]["height"] == near["block_height"]
    digest = hashlib.sha256((data_dir / "manifest.json").read_bytes()).hexdigest()
    assert digest == record["manifest_sha256"]
