import type { Metadata } from "next";
import { Callout, PageHeader } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { ValuationExplorer } from "@/components/charts/ValuationExplorer";
import { valuation } from "@/lib/data";
import { pct, ratio, usd } from "@/lib/format";

export const metadata: Metadata = { title: "Valuation Lab · NEAR Capture Ledger" };

const CORE = ["supply_daily", "fee_wallet_inflows_daily", "price_daily", "defillama_intents_daily"];

export default function ValuationLab() {
  const { start, growth, reverse, assumptions, scenarios } = valuation;
  const rows = reverse.rows;
  const horizons = [1, 3, 5];
  const cell = (h: number, i: number, basis: string) =>
    rows.find((r) => r.horizon_years === h && r.inflation === i && r.basis === basis)!;
  const flat = scenarios.find(
    (r) => r.scenario === "flat" && r.inflation_path === "constant_2.5" && r.price_multiplier === 1,
  )!;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Valuation Lab"
        lede="How much Intents volume would have to grow for buybacks and burn to cover issuance, and how likely that is if volume keeps behaving as it has. Conditional on stated assumptions; not a forecast."
      />

      <Callout title="The NEAR price is held constant in every run">
        {assumptions.price} Starting price {usd(start.near_usd)} on {start.as_of}.
      </Callout>

      <ChartCard
        id="reverse"
        title="Required annual growth of Intents volume"
        sentence={
          <>
            To reach CR = 1 in three years at 2.5% issuance, 30-day volume would have to grow{" "}
            {pct(cell(3, 0.025, "buyback").required_cagr)} a year on the buyback basis; under the
            HSP-029 rate of 1.6% it would be {pct(cell(3, 0.016, "buyback").required_cagr)}.
          </>
        }
        tables={CORE}
        model="valuation.reverse_table (src/capture/models/valuation.py)"
      >
        <div className="overflow-x-auto">
          <table className="tabular w-full min-w-[34rem] text-left text-sm">
            <thead>
              <tr className="text-ink-2">
                <th className="py-2 pr-4 font-medium">Issuance</th>
                <th className="py-2 pr-4 font-medium">Take rate basis</th>
                <th className="py-2 pr-4 font-medium">V* per day</th>
                {horizons.map((h) => (
                  <th key={h} className="py-2 pr-4 font-medium">
                    {h} year{h > 1 ? "s" : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[0.025, 0.016].flatMap((i) =>
                ["buyback", "revenue"].map((basis) => (
                  <tr key={`${i}-${basis}`} className="border-t border-grid">
                    <td className="py-2 pr-4">{i === 0.025 ? "2.5%" : "1.6% (HSP-029)"}</td>
                    <td className="py-2 pr-4">{basis === "buyback" ? "Buyback wallet" : "All revenue"}</td>
                    <td className="py-2 pr-4">{usd(cell(1, i, basis).breakeven_volume_usd_per_day)}</td>
                    {horizons.map((h) => (
                      <td key={h} className={`py-2 pr-4 ${basis === "buyback" && i === 0.025 ? "font-semibold" : ""}`}>
                        +{pct(cell(h, i, basis).required_cagr, 0)}
                      </td>
                    ))}
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          From a 30-day average of {usd(start.volume_usd_per_day)} per day; take rates{" "}
          {(start.tau_buyback_30 * 1e4).toFixed(2)} bp (buyback wallet) and{" "}
          {(start.tau_revenue_30 * 1e4).toFixed(2)} bp (all revenue) held at their current values.
        </p>
      </ChartCard>

      <ChartCard
        id="montecarlo"
        title="Monte Carlo of the coverage ratio, 60 months"
        sentence={
          <>
            If volume keeps its historical volatility but stops trending (flat), {pct(flat.p_cr_ge_1["60"], 0)}{" "}
            of {valuation.n_paths.toLocaleString("en-US")} paths have CR ≥ 1 in month 60 at 2.5% issuance. The other two scenarios carry the
            launch-phase growth and imply far larger volumes, shown under each panel.
          </>
        }
        tables={CORE}
        model="valuation.run_scenarios (block bootstrap, seed in config)"
      >
        <ValuationExplorer runs={scenarios} volumeNow={start.volume_usd_per_day} />
        <div className="mt-4 grid gap-3 text-xs text-ink-2 sm:grid-cols-2">
          <p>
            Growth sample: {growth.n_months} monthly changes from {growth.first_month}, drawn in{" "}
            {valuation.block_months}-month blocks ({growth.n_blocks_available} blocks). Mean monthly log
            growth {growth.mean_all.toFixed(3)}; from {growth.launch_phase_ends} on it is{" "}
            {growth.mean_after_launch.toFixed(3)} ({growth.n_months_after_launch} months). The
            historical scenario is driven by the launch phase.
          </p>
          <p>
            Month-0 check: at the latest price the model starts at CR {ratio(start.cr_model_month0)}; at
            the mean price of the same 30 days ({usd(start.near_usd_window_mean)}) it gives{" "}
            {ratio(start.cr_model_month0_at_window_price)}, against a measured{" "}
            {ratio(start.cr_float_30_observed)}. The gap is the price move inside the window.
          </p>
        </div>
      </ChartCard>

      <section className="rounded-xl border border-[var(--ring)] bg-surface p-4 text-sm sm:p-6" aria-labelledby="assumptions">
        <h2 id="assumptions" className="text-base font-semibold">Assumptions and their sources</h2>
        <dl className="mt-3 space-y-3">
          {(["price", "volume", "tau", "inflation", "supply", "burn"] as const).map((k) => (
            <div key={k}>
              <dt className="font-medium capitalize">{k === "tau" ? "Take rate" : k}</dt>
              <dd className="text-ink-2">{assumptions[k]}</dd>
            </div>
          ))}
          <div>
            <dt className="font-medium">Scenarios</dt>
            <dd className="text-ink-2">
              {Object.entries(assumptions.scenarios).map(([k, v]) => (
                <span key={k} className="block">
                  {k}: {v}
                </span>
              ))}
            </dd>
          </div>
        </dl>
        <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-muted">
          {valuation.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
