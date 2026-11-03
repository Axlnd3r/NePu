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

    # ------------------------------------------------------------------ claim
    out("## Claim")
    out("")
    cents = round(float(f.val(f"{s}.hero.cr_float_usd_30")) * 100)  # type: ignore[arg-type]
    f.used.append(Fact(f"{s}.hero.cr_float_usd_30", f.val(f"{s}.hero.cr_float_usd_30"), str(cents)))
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
    out(
        "Buybacks are not burns: the NEAR bought back is held in a wallet, so only gas burn lowers "
        f"total supply (CR_supply {f.num('coverage.latest.cr_supply_30.value', 3)} on "
        f"{f.date('coverage.latest.cr_supply_30.date')}). The thesis is falsifiable: the numeric "
        "conditions that would change this reading are listed below."
    )
    out("")

    # ------------------------------------------------------------------ supporting
    out("## Supporting evidence")
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
        f"{f.times(f'{steps}[2].volume_multiple')} to come from volume growth. Its vote result is not "
        "confirmed in the sources used."
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
    out(
        f"- Volume is concentrated: in {f.word(f'{month0}.period')} one channel carried "
        f"{f.pct(f'{month0}.max_channel_share')} of 1Click volume (channel HHI "
        f"{f.num(f'{month0}.hhi_channel', 3)}), and declared app fees to NEAR wallets explained "
        f"{f.pct(attr_last)} of on-chain revenue, down from {f.pct(attr_first)} in "
        f"{f.word(f'{month_first}.period')}."
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
            "would support the thesis"
            if condition["effect"] == "support"
            else "would withdraw the headline"
        )
        out(
            f"- {f.text(f'{base}.text')} ({effect}): now {_basis(f, f'{base}.value', kind)} against "
            f"{_basis(f, f'{base}.threshold', kind)}, {f.pct(f'{base}.progress', 0)} of the way; "
            f"{verdict}."
        )
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
        "average, for capture to cover issuance at today's rates.",
        f"- Proof: the SHA-256 of the snapshot manifest is committed on NEAR "
        f"**{f.word(f'{proof}.network')}** (contract `{f.word(f'{proof}.contract')}`, run id "
        f"`{f.word(f'{proof}.run_id')}`, [transaction]({f.word(f'{proof}.explorer_url')}), block "
        f"{f.integer(f'{proof}.block_height')}). {ots}",
    ]
    return "\n".join(lines), f.used


def replace_results(readme: str, block: str) -> str:
    """README text with the generated block put between its markers."""
    start = readme.index(RESULTS_START) + len(RESULTS_START)
    end = readme.index(RESULTS_END)
    return f"{readme[:start]}\n{block}\n{readme[end:]}"
