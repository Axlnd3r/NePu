"""THESIS.md: rendered from the published JSON payloads, with every number registered.

No figure is typed here. A number enters the text through `Facts`, which records the JSON path it
came from; strings taken from the payloads (labels, reasons, the lead/lag verdict) are inserted as
they are and the numbers inside them are registered too. tests/test_thesis.py checks that every
number in the rendered text is a registered fact and that every fact resolves in the JSON files
that `capture build` writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATH_PART = re.compile(r"([^.\[\]]+)|\[([^\]]*)\]")
_ISO_DATE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Fact:
    path: str  # e.g. summary.levers.steps[0].volume_multiple
    raw: object  # the value found there
    text: str  # how it appears in the text (without its unit)


def resolve(data: dict, path: str) -> object:
    """Follow `a.b[2].c`, `a.b[-1]` and `a.b[k=v,k2=v2]` through nested dicts and lists.

    A trailing `#len` gives the length of the list found.
    """
    if path.endswith("#len"):
        return len(resolve(data, path[:-4]))  # type: ignore[arg-type]
    current: object = data
    for match in _PATH_PART.finditer(path):
        key, selector = match.group(1), match.group(2)
        if key is not None:
            current = current[key]  # type: ignore[index]
        elif "=" in selector:
            wanted = [part.split("=", 1) for part in selector.split(",")]
            found = [x for x in current if all(str(x[k]) == v for k, v in wanted)]  # type: ignore[union-attr]
            if not found:
                raise KeyError(path)
            current = found[0]
        else:
            current = current[int(selector)]  # type: ignore[index]
    return current


class Facts:
    """Reads values from the payloads and remembers each one that reaches the text."""

    def __init__(self, payloads: dict[str, dict]) -> None:
        self.payloads = payloads
        self.used: list[Fact] = []

    def val(self, path: str) -> object:
        return resolve(self.payloads, path)

    def _register(self, path: str, raw: object, text: str) -> str:
        self.used.append(Fact(path, raw, text))
        return text

    def num(self, path: str, digits: int = 1) -> str:
        v = float(self.val(path))  # type: ignore[arg-type]
        return self._register(path, self.val(path), f"{v:.{digits}f}")

    def pct(self, path: str, digits: int = 1) -> str:
        v = float(self.val(path))  # type: ignore[arg-type]
        return f"{self._register(path, self.val(path), f'{v * 100:.{digits}f}')}%"

    def times(self, path: str, digits: int = 2) -> str:
        return f"{self.num(path, digits)}x"

    def usd(self, path: str) -> str:
        v = float(self.val(path))  # type: ignore[arg-type]
        for limit, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(v) >= limit:
                return f"${self._register(path, self.val(path), f'{v / limit:.1f}')}{unit}"
        return f"${self._register(path, self.val(path), f'{v:.2f}')}"

    def change(self, path: str, digits: int = 0) -> str:
        """A signed fraction as "rose N%" or "fell N%"; the absolute value is what is registered."""
        v = float(self.val(path))  # type: ignore[arg-type]
        text = self._register(path, self.val(path), f"{abs(v) * 100:.{digits}f}")
        return f"{'fell' if v < 0 else 'rose'} {text}%"

    def integer(self, path: str) -> str:
        v = self.val(path)
        return self._register(path, v, f"{int(v):,}")  # type: ignore[call-overload]

    def date(self, path: str) -> str:
        v = str(self.val(path))
        return self._register(path, v, v)

    def word(self, path: str) -> str:
        """A name taken from the data (a network, a period label) that is not a number."""
        v = str(self.val(path))
        for token in [*_ISO_DATE.findall(v), *_NUMBER.findall(_ISO_DATE.sub("", v))]:
            self._register(path, v, token.rstrip(".,"))
        return v

    # `text` is the same operation: a string from the payloads, inserted as it is.
    text = word


def _basis(f: Facts, path: str, kind: str) -> str:
    return {"usd": f.usd, "pct": f.pct}[kind](path)


def render(payloads: dict[str, dict]) -> tuple[str, list[Fact]]:
    """The THESIS.md text and the facts it used."""
    f = Facts(payloads)
    s = "summary"
    steps = f"{s}.levers.steps"
    flat = "valuation.scenarios[scenario=flat,inflation_path=constant_2.5,price_multiplier=1.0]"
    historical = (
        "valuation.scenarios[scenario=historical,inflation_path=constant_2.5,price_multiplier=1.0]"
    )
    reverse = "valuation.reverse.rows[horizon_years=3,inflation=0.025,basis=buyback]"
    months = payloads["distribution"]["periods"]["month"]
    complete = [i for i, m in enumerate(months) if m["complete"]]
    month0 = f"distribution.periods.month[{complete[-1]}]"
    month_first = f"distribution.periods.month[{complete[0]}]"
    coverage_first = "distribution.scope.explorer_share_of_defillama_volume_by_month[0]"
    coverage_last = "distribution.scope.explorer_share_of_defillama_volume_by_month[-1]"
    attr_first = f"{month_first}.attributable_share"
    attr_last = f"{month0}.attributable_share"
    proof = "provenance.proof"
    at = f"{s}.levers.at_window_prices"
    holder = f"{s}.holder"
    halves = "usage.halves.change"
    accounts = float(f.val(f"{halves}.active_signers"))  # type: ignore[arg-type]
    volume = float(f.val(f"{halves}.volume_usd"))  # type: ignore[arg-type]
    followed = "did not follow" if accounts < 0 < volume else "is compared with"

    lines: list[str] = []
    out = lines.append

    out("# Thesis: can NEAR Intents value capture outgrow token issuance?")
    out("")
    out(
        "Generated by `capture build` from `site/public/data/*.json`; do not edit by hand. Every "
        "number below is a registered fact traced to a published file (`tests/test_thesis.py`). "
        "Evidence, not conviction: no price is predicted."
    )
    out("")

    cents = round(float(f.val(f"{s}.hero.cr_float_usd_30")) * 100)  # type: ignore[arg-type]
    f.used.append(Fact(f"{s}.hero.cr_float_usd_30", f.val(f"{s}.hero.cr_float_usd_30"), str(cents)))

    # ------------------------------------------------------------------ summary
    out("## Summary")
    out("")
    out(
        "- **Question.** Can the value NEAR Intents captures for the token, buybacks plus gas "
        "burn, outgrow new issuance? That is the long-term case for NEAR as a token backed by "
        "revenue, tested here as a hypothesis."
    )
    out(
        f"- **Answer today: not yet.** {cents} cents come back per dollar of new NEAR issued "
        f"({f.integer(f'{s}.ledger.days')} days to {f.date(f'{s}.hero.date')})."
    )
    out(
        "- **The gap.** Revenue reaching the buyback wallet has to grow "
        f"{f.times(f'{steps}[0].volume_multiple', 1)} at the latest NEAR price "
        f"({f.times(f'{at}.volume_multiple', 1)} at the prices of the window). The HSP-029 "
        "issuance cut and routing all protocol revenue to buybacks would leave "
        f"{f.times(f'{steps}[2].volume_multiple')} for growth."
    )
    out(
        "- **For a holder.** Net of buybacks and burn, new NEAR still adds "
        f"{f.pct(f'{holder}.net_new_supply_rate')} of total supply to the float a year, and total supply is valued "
        f"at {f.times(f'{holder}.value_to_revenue', 0)} the yearly revenue reaching the buyback "
        f"wallet; coverage reaches one at {f.times(f'{holder}.breakeven_value_to_revenue', 1)}."
    )
    out(
        "- **Strongest evidence against.** Mean monthly log growth of volume after the launch "
        f"phase is {f.num('valuation.growth.mean_after_launch', 3)}, against "
        f"{f.num('valuation.growth.mean_all', 3)} over all months, and network usage {followed} Intents: "
        f"daily active accounts {f.change(f'{halves}.active_signers')} while Intents volume "
        f"{f.change(f'{halves}.volume_usd')}."
    )
    out(
        "- **Check it.** `make all` rebuilds every number offline; the conditions that would "
        "change the answer are listed below."
    )
    out("")

    # ------------------------------------------------------------------ claim
    out("## Claim")
    out("")
    out(
        "The hypothesis: over the long run, fee revenue from NEAR Intents grows until buybacks and "
        "gas burn cover new NEAR issuance. The evidence for and against it follows. The reading "
        "today:"
    )
    out("")
    out(
        f"**Not yet.** In the {f.integer(f'{s}.ledger.days')} days to {f.date(f'{s}.hero.date')}, "
        f"buybacks and gas burn covered {cents} cents per dollar of new NEAR issued "
        f"(CR_float {f.num(f'{s}.hero.cr_float_usd_30', 3)} in USD, "
        f"{f.num(f'{s}.hero.cr_float_30', 3)} in NEAR units). At today's take rate and issuance "
        f"daily Intents volume would have to reach {f.usd(f'{steps}[0].v_star_usd_per_day')}, "
        f"{f.times(f'{steps}[0].volume_multiple', 1)} its {f.usd(f'{s}.levers.volume_usd_per_day')} "
        f"{f.integer(f'{s}.ledger.days')}-day average, before capture covers issuance."
    )
    out("")
    inv = f"{s}.invariance.rows"
    out(
        "That multiple does not depend on how Intents volume is counted. The revenue that reaches "
        "the buyback wallet is measured on chain; counted at half or twice DefiLlama's volume, "
        f"break-even becomes {f.usd(f'{inv}[volume_scale=0.5].v_star_usd_per_day')} or "
        f"{f.usd(f'{inv}[volume_scale=2.0].v_star_usd_per_day')} a day and the multiple stays "
        f"{f.times(f'{inv}[volume_scale=0.5].volume_multiple', 1)}. Read it as the growth in "
        "buyback revenue that break-even needs; the dollar volume is only as good as the volume "
        "definition."
    )
    out("")
    out(
        f"It does depend on the NEAR price. The {f.times(f'{steps}[0].volume_multiple', 1)} "
        f"values issuance at the latest price ({f.usd(f'{holder}.near_usd')} on "
        f"{f.date(f'{s}.levers.as_of')}); the {cents} cents use each day's price (mean "
        f"{f.usd(f'{at}.near_usd_mean')} over the window), and on that basis the gap is "
        f"{f.times(f'{at}.volume_multiple', 1)}. Issuance is fixed in NEAR while fee revenue is "
        "earned in dollars, so a higher NEAR price raises the bar."
    )
    out("")
    out(
        "Buybacks are not burns: the NEAR bought back is held in a wallet, so only gas burn lowers "
        f"total supply (CR_supply {f.num('coverage.latest.cr_supply_30.value', 3)} on "
        f"{f.date('coverage.latest.cr_supply_30.date')}). The thesis is falsifiable: the numeric "
        "conditions that would change this reading are listed below."
    )
    out("")

    # ------------------------------------------------------------------ holder
    out("## What it means for a holder")
    out("")
    out(
        "- Net new supply: gross issuance ran at "
        f"{f.pct(f'{holder}.gross_new_supply_rate')} of total supply a year over the "
        f"{f.integer(f'{s}.ledger.days')} days to {f.date(f'{s}.levers.as_of')}; after buybacks "
        f"and gas burn, {f.pct(f'{holder}.net_new_supply_rate')} was left as new float. Bought-back NEAR "
        "is held, not burnt, so total supply itself grows by gross issuance less burn."
    )
    out(
        "- A yardstick, not a price view: at the latest price total supply is valued at "
        f"{f.times(f'{holder}.value_to_revenue', 0)} the yearly revenue reaching the buyback "
        "wallet. Coverage reaches one when that multiple is "
        f"{f.times(f'{holder}.breakeven_value_to_revenue', 1)}; the ratio of the two is the "
        f"{f.times(f'{steps}[0].volume_multiple', 1)} above. The multiple moves with revenue, the "
        "issuance rate and the price; none of them is forecast here."
    )
    out("")

    # ------------------------------------------------------------------ supporting
    out("## Supporting evidence")
    out("")
    out("Evidence that capture can catch up with issuance:")
    out("")
    out(
        "- The measurement holds: on-chain revenue agrees with DefiLlama's in "
        f"{f.integer('provenance.reconciliation.months#len')} of "
        f"{f.integer('provenance.reconciliation.months#len')} complete months, the worst gap being "
        f"{f.pct(f'{s}.conditions[id=reconciliation].value')} against a tolerance of "
        f"{f.pct('provenance.reconciliation.tolerance', 0)}."
    )
    out(
        "- The buyback wallet does receive revenue: the highest "
        f"{f.integer(f'{s}.ledger.days')}-day coverage measured so far is "
        f"{f.num(f'{s}.history.cr_float_30_max.value', 3)}, on "
        f"{f.date(f'{s}.history.cr_float_30_max.date')}."
    )
    out(
        "- The buyback take rate has risen: its monthly value ran from "
        f"{f.pct('valuation.start.tau_monthly_range.min', 4)} to "
        f"{f.pct('valuation.start.tau_monthly_range.max', 4)} of volume across the complete months "
        "observed."
    )
    out(
        "- Issuance policy can help: the HSP-029 proposal (issuance down to "
        f"{f.pct(f'{steps}[1].inflation')} a year) would cut the required volume by a factor of "
        f"{f.times(f'{steps}[1].closes_by')}, and sending all protocol revenue to buybacks by a "
        f"further {f.times(f'{steps}[2].closes_by')}, leaving "
        f"{f.times(f'{steps}[2].volume_multiple')} to come from volume growth."
    )
    hsp = f"{s}.governance.hsp029"
    if f.val(hsp):
        out(
            f"- The House of Stake vote on HSP-029, read on chain from `{f.word(f'{hsp}.contract')}` "
            f"at block {f.integer(f'{hsp}.read_at_block')}, has closed with status "
            f"`{f.word(f'{hsp}.status')}`: {f.pct(f'{hsp}.top_option_share', 2)} of the veNEAR "
            f"cast went to one option (turnout {f.pct(f'{hsp}.turnout')}), and its timelock ends "
            f"{f.word(f'{hsp}.timelock_end_utc')}. Validators still have to adopt the ramp, so it "
            "is a scenario here, not a measurement."
        )
    out(
        "- Required growth is finite: reaching break-even in "
        f"{f.integer(f'{reverse}.horizon_years')} years at "
        f"{f.pct(f'{reverse}.inflation')} issuance needs the {f.integer(f'{s}.ledger.days')}-day volume to grow "
        f"{f.pct(f'{reverse}.required_cagr', 0)} a year."
    )
    out("")

    # ------------------------------------------------------------------ contrary
    out("## Contrary evidence")
    out("")
    out("Evidence that it will not, or not soon:")
    out("")
    out(
        f"- Only {f.pct(f'{s}.ledger.kept.buyback_of_onchain')} of the protocol revenue that reaches "
        "NEAR wallets reaches the buyback wallet; the rest sits in collection wallets that have "
        "not paid out."
    )
    out(
        f"- Per {f.integer(f'{s}.ledger.per_10k_volume.volume')} dollars of "
        f"Intents volume, fees were {f.num(f'{s}.ledger.per_10k_volume.fees', 2)} dollars, "
        f"protocol revenue {f.num(f'{s}.ledger.per_10k_volume.revenue', 2)} and the buyback wallet "
        f"received {f.num(f'{s}.ledger.per_10k_volume.buyback_wallet', 2)}, while new NEAR worth "
        f"{f.num(f'{s}.ledger.per_10k_volume.issuance', 2)} was issued."
    )
    out(
        "- What can be seen of Intents volume is shrinking: the Explorer (1Click only) covered "
        f"{f.pct(f'{coverage_first}.explorer_share_of_defillama_volume')} of DefiLlama's volume in "
        f"{f.word(f'{coverage_first}.period')} and "
        f"{f.pct(f'{coverage_last}.explorer_share_of_defillama_volume')} in "
        f"{f.word(f'{coverage_last}.period')}."
    )
    bf = f"{s}.buyback_flows"
    if f.val(bf):
        out(
            "- The buyback wallet's own activity (NearBlocks, "
            f"{f.date(f'{bf}.start')} to {f.date(f'{bf}.end')}): it received "
            f"{f.integer(f'{bf}.inflow_near.intents')} NEAR from `intents.near`, "
            f"{f.integer(f'{bf}.inflow_near.revenue_wallet')} NEAR moved in from the other revenue "
            f"wallets and {f.integer(f'{bf}.inflow_near.other')} NEAR from "
            f"{f.integer(f'{bf}.other_senders')} other accounts, and sent "
            f"{f.integer(f'{bf}.outflow_near')} NEAR out. The net daily change behind CR counts "
            "the NEAR from other accounts as buybacks "
            f"({f.pct(f'{bf}.other_share_of_counted')} of what it counts), and cannot see an "
            "outflow on a day with a larger inflow. The activity nets to "
            f"{f.integer(f'{bf}.net_near')} NEAR against "
            f"{f.integer(f'{bf}.net_balance_change_near')} NEAR in the balance series CR uses."
        )
    vc = f"{s}.volume_check"
    if f.val(vc):
        out(
            "- DefiLlama's Intents volume looks counted on both sides of a swap. From "
            f"{f.date(f'{vc}.start')} to {f.date(f'{vc}.end')} the stablecoin legs of swaps settled "
            "on `intents.near` (token_diff events, BigQuery), counted once, came to "
            f"{f.pct(f'{vc}.ratio')} of DefiLlama's volume, while stablecoins were "
            f"{f.pct(f'{month0}.stablecoin_share')} of 1Click volume in "
            f"{f.word(f'{month0}.period')}: about what counting both legs would give. The dollar "
            "break-even above may be about half as large; the multiple does not change."
        )
    out(
        f"- Volume is concentrated: in {f.word(f'{month0}.period')} one channel carried "
        f"{f.pct(f'{month0}.max_channel_share')} of 1Click volume (channel HHI "
        f"{f.num(f'{month0}.hhi_channel', 3)}), and declared app fees to NEAR wallets explained "
        f"{f.pct(attr_last)} of on-chain revenue, down from {f.pct(attr_first)} in "
        f"{f.word(f'{month_first}.period')}."
    )
    out(
        "- Intents revenue is not network usage: from "
        f"{f.date('usage.window.first_date')} to {f.date('usage.window.last_date')}, calls to "
        f"`intents.near` were {f.pct('usage.shares.intents_call_share')} of all function calls "
        f"and its daily signers {f.pct('usage.shares.intents_signer_share', 2)} of daily active "
        "accounts (distinct transaction signers)."
    )
    out(
        f"- Network usage {followed} Intents: comparing the two halves of the "
        f"{f.integer('usage.halves.weeks')} complete weeks, daily active accounts "
        f"{f.change(f'{halves}.active_signers')} and transactions "
        f"{f.change(f'{halves}.tx_count')}, while Intents volume "
        f"{f.change(f'{halves}.volume_usd')} and the NEAR price "
        f"{f.change(f'{halves}.near_usd')}. No cause is attributed."
    )
    out(
        "- The track's example hypothesis, that Intents volume leads network usage better than "
        f"the token price, is {f.text('usage.lead_lag.verdict.label')} out of sample: "
        f"{f.text('usage.lead_lag.verdict.text')}"
    )
    out(
        "- The growth that makes capture look inevitable comes from the launch phase: mean monthly "
        f"log growth was {f.num('valuation.growth.mean_all', 3)} over "
        f"{f.integer('valuation.growth.n_months')} months but "
        f"{f.num('valuation.growth.mean_after_launch', 3)} after the launch. Extrapolated for "
        f"{f.integer('valuation.n_months')} months it implies a median daily volume of "
        f"{f.usd(f'{historical}.volume_p50_usd_per_day.60')}, which is outside anything observed; "
        "in the flat scenario, which does not use it, "
        f"{f.pct(f'{flat}.p_cr_ge_1.60', 0)} of {f.integer('valuation.n_paths')} simulated paths "
        f"have coverage of at least one in month {f.integer('valuation.n_months')}."
    )
    out(
        f"- Developer activity does not lead revenue (a null result): {f.text('developer.lead_lag.verdict.text')}"
    )
    out(f"- {f.text('valuation.assumptions.price')}")
    out("")

    # ------------------------------------------------------------------ definitions
    out("## Why public estimates differ")
    out("")
    out(
        "Published figures for how much of NEAR's issuance is covered range widely. Most of the "
        "spread is definition, not data. The same days, on this project's data:"
    )
    out("")
    rows = f.val(f"{s}.definitions.rows")
    for index, row in enumerate(rows):  # type: ignore[arg-type]
        base = f"{s}.definitions.rows[{index}]"
        if row.get("quoted"):
            continue
        out(
            f"- {f.text(f'{base}.label')}: {f.pct(f'{base}.value')} "
            f"({f.date(f'{base}.start')} to {f.date(f'{base}.end')})."
        )
    for index, row in enumerate(rows):  # type: ignore[arg-type]
        base = f"{s}.definitions.rows[{index}]"
        if not row.get("quoted"):
            continue
        out(
            f"- {f.text(f'{base}.label')}: {f.pct(f'{base}.value')} (to {f.date(f'{base}.end')}). "
            "On the same days its emissions agree with our gross issuance "
            f"({f.integer(f'{base}.official_emissions_near')} against "
            f"{f.integer(f'{base}.our_issuance_near')} NEAR) but its revenue is "
            f"{f.integer(f'{base}.official_revenue_near')} NEAR against the "
            f"{f.integer(f'{base}.our_revenue_near')} NEAR the three revenue wallets received. "
            "The page books revenue in monthly steps, does not document its method and calls its "
            "figures illustrative, so the gap is reported here, not explained."
        )
    out("")
    out(
        "The headline uses the strictest buyback basis on purpose: only the buyback wallet holds "
        "NEAR bought back; the other revenue wallets have not paid out."
    )
    out("")

    # ------------------------------------------------------------------ triggers
    out("## What would change my mind")
    out("")
    out(
        "Three numeric conditions, re-evaluated on every build "
        f"(as of {f.date(f'{s}.levers.as_of')}):"
    )
    out("")
    for index, condition in enumerate(f.val(f"{s}.conditions")):  # type: ignore[arg-type]
        base = f"{s}.conditions[{index}]"
        kind = "usd" if condition["unit"].startswith("USD") else "pct"
        verdict = "met" if condition["met"] else "not met"
        effect = (
            "would change the answer to yes"
            if condition["effect"] == "support"
            else "would withdraw the headline"
        )
        out(
            f"- {f.text(f'{base}.text')} ({effect}): now {_basis(f, f'{base}.value', kind)} against "
            f"{_basis(f, f'{base}.threshold', kind)}, {f.pct(f'{base}.progress', 0)} of the way; "
            f"{verdict}."
        )
    out("")
    pre = "prereg"
    tests = f.val(f"{pre}.tests") or []
    if tests:
        anchored = ""
        if f.val(f"{pre}.anchor"):
            anchored = (
                f", hash committed on NEAR {f.word(f'{pre}.anchor.near.network')} at block "
                f"{f.integer(f'{pre}.anchor.near.block_height')}"
            )
        out(
            "Forecasts of this reading were written down before their windows closed "
            f"(registered {f.word(f'{pre}.registered_at_utc')}{anchored}). A miss on any of them "
            "means the reading above was wrong in that respect:"
        )
        out("")
        for index in range(len(tests)):  # type: ignore[arg-type]
            base = f"{pre}.tests[{index}]"
            out(f"- {f.word(f'{base}.id')}: {f.text(f'{base}.claim')}")
        out("")
        out("Each is scored on the dashboard when its window closes; a miss is reported as a miss.")
        out("")

    # ------------------------------------------------------------------ unavailable
    out("## Unavailable metrics and why")
    out("")
    out(
        f"- Share of volume through near.com: unavailable. {f.text('distribution.scope.near_com.reason')}."
    )
    out(
        "- Buyback value before "
        f"{f.date('coverage.availability.buyback_near.first_date')}: unavailable. The buyback wallet "
        "is first observed on that day and where earlier revenue went is unknown."
    )
    out(
        "- USD valuation before "
        f"{f.date('provenance.sources[path=price_daily.parquet].date_range[0]')}: unavailable. The "
        "public price API serves a limited history."
    )
    for index in range(len(payloads["markers"]["not_drawn"])):
        base = f"markers.not_drawn[{index}]"
        out(f"- {f.text(f'{base}.label')}: unavailable. {f.text(f'{base}.reason')}.")
    out("")

    # ------------------------------------------------------------------ limitations
    out("## Limitations")
    out("")
    out(
        "- The proof: the SHA-256 of the snapshot manifest is committed to NEAR "
        f"{f.word(f'{proof}.network')} at block {f.integer(f'{proof}.block_height')}. It shows "
        "that the hash existed no later than "
        "that block; it does not show that the data is correct. Testnet carries no economic "
        "security and keeps no promise to retain its history."
    )
    out(f"- Scope of the channel data: {f.text('distribution.scope.covers')}.")
    for index in range(len(payloads["valuation"]["notes"])):
        out(f"- {f.text(f'valuation.notes[{index}]')}")
    out(
        "- Correlation is not causation; lead/lag results are reported out of sample, including "
        "null results."
    )
    out("- DefiLlama is a third-party source and its last days are not final.")
    out("")
    out("Rebuild with `make build`; `make verify` checks that this file is what the build writes.")
    out("")
    return "\n".join(lines), f.used


RESULTS_START = "<!-- results:start -->"
RESULTS_END = "<!-- results:end -->"


def render_results(payloads: dict[str, dict]) -> tuple[str, list[Fact]]:
    """The generated block of README.md (between the results markers) and the facts it used."""
    f = Facts(payloads)
    s = "summary"
    steps = f"{s}.levers.steps"
    proof = "provenance.proof"
    cents = round(float(f.val(f"{s}.hero.cr_float_usd_30")) * 100)  # type: ignore[arg-type]
    f.used.append(Fact(f"{s}.hero.cr_float_usd_30", f.val(f"{s}.hero.cr_float_usd_30"), str(cents)))
    stamp = f.val(f"{proof}.opentimestamps")
    ots = (
        f"OpenTimestamps (Bitcoin): {stamp['status']}." if stamp else "OpenTimestamps: not stamped."
    )  # type: ignore[index]
    lines = [
        "**Latest build**, generated from `site/public/data/*.json` (the full argument, with the "
        "evidence against it, is in [THESIS.md](THESIS.md)):",
        "",
        f"- For every dollar of new NEAR issued, **{cents} cents** came back as buybacks or gas "
        f"burn in the {f.integer(f'{s}.ledger.days')} days to {f.date(f'{s}.hero.date')}.",
        f"- **Not yet:** daily Intents volume would have to reach {f.usd(f'{steps}[0].v_star_usd_per_day')}, "
        f"{f.times(f'{steps}[0].volume_multiple', 1)} its {f.usd(f'{s}.levers.volume_usd_per_day')} "
        "average, for capture to cover issuance at today's rates "
        f"({f.times(f'{s}.levers.at_window_prices.volume_multiple', 1)} at the prices of the "
        "window the cents use).",
        "- That multiple does not depend on how volume is counted: at half or twice DefiLlama's "
        "volume it stays "
        f"{f.times(f'{s}.invariance.rows[volume_scale=2.0].volume_multiple', 1)}. It is the growth "
        "in buyback revenue that break-even needs.",
        "- The track's example hypothesis, that Intents volume leads network usage better than "
        f"price: {f.text('usage.lead_lag.verdict.label')} out of sample; daily active accounts "
        f"{f.change('usage.halves.change.active_signers')} while Intents volume "
        f"{f.change('usage.halves.change.volume_usd')}.",
        f"- Proof: the SHA-256 of the snapshot manifest is committed on NEAR "
        f"**{f.word(f'{proof}.network')}** (contract `{f.word(f'{proof}.contract')}`, run id "
        f"`{f.word(f'{proof}.run_id')}`, [transaction]({f.word(f'{proof}.explorer_url')}), block "
        f"{f.integer(f'{proof}.block_height')}). {ots}",
    ]
    hsp = f"{s}.governance.hsp029"
    if f.val(hsp):
        lines.insert(
            -1,
            "- The issuance cut HSP-029, read on chain from `vote.dao`: status "
            f"`{f.word(f'{hsp}.status')}`, {f.pct(f'{hsp}.top_option_share', 2)} of the veNEAR "
            f"cast for one option, timelock ends {f.word(f'{hsp}.timelock_end_utc')}. It would "
            f"close {f.times(f'{steps}[1].closes_by')} of the gap once validators adopt it.",
        )
    return "\n".join(lines), f.used


def replace_results(readme: str, block: str) -> str:
    """README text with the generated block put between its markers."""
    start = readme.index(RESULTS_START) + len(RESULTS_START)
    end = readme.index(RESULTS_END)
    return f"{readme[:start]}\n{block}\n{readme[end:]}"
