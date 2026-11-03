import { BarRows, Badge, MarkerList, Meter } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { BreakEvenMeter } from "@/components/charts/BreakEvenMeter";
import { TimeChart } from "@/components/charts/TimeChart";
import { Evidence } from "@/components/Evidence";
import { coverage, distribution, markersBetween, summary, valuation } from "@/lib/data";
import { pct, ratio, times, usd } from "@/lib/format";

const CORE = ["supply_daily", "fee_wallet_inflows_daily", "price_daily", "defillama_intents_daily"];

export default function Overview() {
  const { hero, ledger, levers, conditions } = summary;
  const start = valuation.start;
  const steps = levers.steps;
  const explorerShares = distribution.scope.explorer_share_of_defillama_volume_by_month;
  const lastExplorer = explorerShares[explorerShares.length - 1];

  const series = coverage.series.filter((r) => r.cr_float_7 !== null);
  const cr = series.map((r) => ({
    date: r.date,
    cr_float_7: r.cr_float_7,
    cr_float_30: r.cr_float_30,
    cr_float_90: r.cr_float_90,
  }));
  const cr30 = series.filter((r) => r.cr_float_30 !== null).map((r) => r.cr_float_30 as number);
  const maxCr30 = Math.max(...cr30);
  const markers = markersBetween(series[0].date, series[series.length - 1].date);

  const per10k = ledger.per_10k_volume;
  const money = (v: number) => `$${v.toFixed(2)}`;

  return (
    <div className="space-y-10">
      <section aria-labelledby="hero" className="rounded-2xl bg-surface p-6 sm:p-10">
        <p className="text-sm font-medium text-accent">Can NEAR Intents value capture outgrow token issuance?</p>
        <h1 id="hero" className="mt-3 text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
          For every $1 of new NEAR issued,{" "}
          <Evidence
            id="hero"
            formula="CR_float in USD over 30 days: (NEAR received by the buyback wallet + NEAR burnt as gas), each day valued at that day's price, divided by gross issuance valued the same way."
            tables={["supply_daily", "fee_wallet_inflows_daily", "price_daily"]}
            asOf={hero.date}
            className="text-accent"
          >
            {Math.round(hero.cr_float_usd_30 * 100)} cents
          </Evidence>{" "}
          come back as buybacks or gas burn.
        </h1>
        <p className="mt-4 max-w-3xl text-ink-2">
          30 days to {hero.date}. In NEAR units the same ratio is {ratio(hero.cr_float_30)}.{" "}
          {summary.this_week.sentence}. Break-even means 100 cents.
        </p>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-[var(--ring)] p-4">
            <p className="text-sm text-ink-2">Volume needed to break even</p>
            <p className="tabular mt-1 text-2xl font-semibold">
              <Evidence
                id="multiple"
                formula="V* / V0: break-even daily Intents volume (buyback take rate, 2.5% issuance, current price and burn) over the 30-day average volume."
                tables={CORE}
                asOf={levers.as_of}
              >
                {times(steps[0].volume_multiple, 1)}
              </Evidence>
            </p>
            <p className="mt-1 text-xs text-muted">
              {usd(steps[0].v_star_usd_per_day)} per day against {usd(levers.volume_usd_per_day)} today
            </p>
          </div>
          <div className="rounded-xl border border-[var(--ring)] p-4">
            <p className="text-sm text-ink-2">Protocol revenue that reaches the buyback wallet</p>
            <p className="tabular mt-1 text-2xl font-semibold">
              <Evidence
                id="routing"
                formula="Buyback wallet inflow / revenue reaching all NEAR revenue wallets (internal transfers netted), both valued at daily prices, 30 days."
                tables={["fee_wallet_inflows_daily", "price_daily"]}
                asOf={ledger.end}
              >
                {pct(ledger.kept.buyback_of_onchain)}
              </Evidence>
            </p>
            <p className="mt-1 text-xs text-muted">The rest is held in collection wallets that have not paid out</p>
          </div>
          <div className="rounded-xl border border-[var(--ring)] p-4">
            <p className="text-sm text-ink-2">Intents volume our channel data covers</p>
            <p className="tabular mt-1 text-2xl font-semibold">
              <Evidence
                id="coverage"
                formula="Volume in the Intents Explorer (1Click transactions only) / DefiLlama Intents volume, same days."
                tables={["explorer_1click_daily", "defillama_intents_daily"]}
                asOf={lastExplorer.period}
              >
                {pct(lastExplorer.explorer_share_of_defillama_volume)}
              </Evidence>
            </p>
            <p className="mt-1 text-xs text-muted">
              In {lastExplorer.period}, down from {pct(explorerShares[0].explorer_share_of_defillama_volume)} in{" "}
              {explorerShares[0].period}: channel claims carry this scope
            </p>
          </div>
        </div>
      </section>

      <ChartCard
        id="ledger"
        title="Where $10,000 of Intents volume goes"
        sentence={
          <>
            In the 30 days to {ledger.end}, every $10,000 of Intents volume produced{" "}
            {money(per10k.fees)} of fees, {money(per10k.revenue)} of protocol revenue and{" "}
            {money(per10k.buyback_wallet)} that reached the buyback wallet, while new NEAR worth{" "}
            {money(per10k.issuance)} was issued.
          </>
        }
        tables={CORE}
        model="ledger.waterfall (src/capture/models/ledger.py)"
        table={{
          columns: ["Step", "USD, 30 days", "Per $10,000 of volume"],
          rows: Object.entries(ledger.usd).map(([k, v]) => [
            k,
            usd(v, 2),
            money(per10k[k as keyof typeof per10k]),
          ]),
        }}
      >
        <BarRows
          max={per10k.issuance}
          rows={[
            { label: "Fees", value: per10k.fees, text: money(per10k.fees) },
            { label: "Protocol revenue", value: per10k.revenue, text: money(per10k.revenue) },
            { label: "Reached NEAR wallets", value: per10k.onchain_revenue, text: money(per10k.onchain_revenue) },
            { label: "Reached buyback wallet", value: per10k.buyback_wallet, text: money(per10k.buyback_wallet), accent: true },
            { label: "Gas burn (chain-wide)", value: per10k.burn, text: money(per10k.burn), accent: true },
            { label: "New NEAR issued", value: per10k.issuance, text: money(per10k.issuance), muted: true },
          ]}
        />
        <p className="mt-3 text-xs text-muted">
          Kept at each step: fees {pct(ledger.kept.fees_of_volume, 2)} of volume, revenue{" "}
          {pct(ledger.kept.revenue_of_fees)} of fees, on-chain {pct(ledger.kept.onchain_of_revenue)} of
          DefiLlama revenue, buyback wallet {pct(ledger.kept.buyback_of_onchain)} of on-chain revenue.
          Accent bars are what counts in CR; the grey bar is what they are measured against.
        </p>
      </ChartCard>

      <ChartCard
        id="levers"
        title="What closes the gap to break-even"
        sentence={
          <>
            Volume must grow {times(steps[0].volume_multiple)} to cover issuance today. The HSP-029
            issuance cut would close {times(steps[1].closes_by as number)} of that and sending all
            revenue to buybacks another {times(steps[2].closes_by as number)}, which still leaves{" "}
            {times(steps[2].volume_multiple)} for volume growth.
          </>
        }
        tables={CORE}
        model="ledger.lever_bridge (src/capture/models/ledger.py)"
      >
        <BarRows
          max={steps[0].volume_multiple}
          rows={[
            { label: "Today (2.5%, buyback wallet)", value: steps[0].volume_multiple, text: times(steps[0].volume_multiple), accent: true },
            { label: "+ issuance cut to 1.6%", value: steps[1].volume_multiple, text: times(steps[1].volume_multiple), accent: true },
            { label: "+ all revenue to buybacks", value: steps[2].volume_multiple, text: times(steps[2].volume_multiple), accent: true },
          ]}
        />
        <p className="mt-3 text-xs text-muted">{levers.note} HSP-029 is a proposal; its vote result is not confirmed in our sources.</p>
      </ChartCard>

      <ChartCard
        id="cr-trend"
        title="Coverage ratio over 7, 30 and 90 days"
        sentence={
          <>
            CR_float over 30 days was {ratio(hero.cr_float_30)} on {hero.date}; its highest value since
            the buyback wallet appeared is {ratio(maxCr30)}, so buybacks and burn have not yet covered
            issuance in any 30-day window measured.
          </>
        }
        tables={["supply_daily", "fee_wallet_inflows_daily"]}
        model="coverage.cr_float (src/capture/models/coverage.py)"
        table={{
          columns: ["Date", "CR 7d", "CR 30d", "CR 90d"],
          rows: cr.slice(-30).map((r) => [
            r.date,
            r.cr_float_7?.toFixed(3) ?? null,
            r.cr_float_30?.toFixed(3) ?? null,
            r.cr_float_90?.toFixed(3) ?? null,
          ]),
        }}
      >
        <TimeChart
          ariaLabel="Coverage ratio over 7, 30 and 90 days"
          data={cr}
          format="ratio"
          markers={markers}
          series={[
            { key: "cr_float_7", label: "7 days", color: "var(--accent-light)", width: 1.5 },
            { key: "cr_float_30", label: "30 days", color: "var(--accent)" },
            { key: "cr_float_90", label: "90 days", color: "var(--accent-deep)" },
          ]}
        />
        <MarkerList markers={markers} />
      </ChartCard>

      <ChartCard
        id="meter"
        title="Break-even meter"
        sentence={
          <>
            At today&apos;s inputs, break-even volume is {usd(steps[0].v_star_usd_per_day)} a day on the
            buyback basis. Change issuance, take rate and the price assumption to see how V* moves.
          </>
        }
        tables={CORE}
        model="valuation.breakeven_volume (same formula, run in the browser)"
      >
        <BreakEvenMeter
          asOf={start.as_of}
          supply={start.total_supply_near}
          price={start.near_usd}
          burnPerDay={start.burnt_near_per_day}
          tauBuyback={start.tau_buyback_30}
          tauRevenue={start.tau_revenue_30}
          volume={start.volume_usd_per_day}
        />
      </ChartCard>

      <section aria-labelledby="mind" className="rounded-xl border border-[var(--ring)] bg-surface p-4 sm:p-6">
        <h2 id="mind" className="text-base font-semibold">What would change our mind</h2>
        <p className="mt-1 text-sm text-ink-2">
          Three numeric conditions, re-evaluated on every build. The first two would support the
          thesis that capture can outgrow issuance; they move independently. The third would withdraw
          the headline until explained.
        </p>
        <ul className="mt-4 space-y-5">
          {conditions.map((c) => (
            <li key={c.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">{c.text}</p>
                {c.effect === "support" ? (
                  <Badge tone={c.met ? "good" : "neutral"}>{c.met ? "met" : "not met"}</Badge>
                ) : (
                  <Badge tone={c.met ? "critical" : "good"}>
                    {c.met ? "triggered: headline withdrawn" : "not triggered"}
                  </Badge>
                )}
              </div>
              <p className="tabular mt-1 text-xs text-ink-2">
                Now {formatCondition(c.value, c.id)} against {formatCondition(c.threshold, c.id)} (
                {pct(c.progress, 0)} of the way)
              </p>
              <div className="mt-2">
                <Meter value={c.progress} label={c.text} />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function formatCondition(v: number, id: string): string {
  if (id === "volume") return `${usd(v)}/day`;
  return pct(v);
}
