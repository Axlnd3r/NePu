import type { Metadata } from "next";
import { MarkerList, PageHeader } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { TimeChart } from "@/components/charts/TimeChart";
import { coverage, markersBetween, rolling } from "@/lib/data";
import { near, ratio } from "@/lib/format";

export const metadata: Metadata = { title: "Token economics · NEAR Capture Ledger" };

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

export default function TokenEconomics() {
  const rows = coverage.series;
  const issuance7 = rolling(rows.map((r) => r.issuance_gross_near), 7);
  const buyback7 = rolling(rows.map((r) => r.buyback_near), 7);
  const burn7 = rolling(rows.map((r) => r.burnt_near), 7);
  const flows = rows.map((r, i) => ({
    date: r.date,
    issuance: issuance7[i],
    buyback: buyback7[i],
    burn: burn7[i],
  }));
  const markers = markersBetween(rows[0].date, rows[rows.length - 1].date);
  const step = markers.find((m) => m.label.startsWith("Daily gross issuance"));

  // Last 30 complete days on which all three flows exist.
  const complete = rows.filter(
    (r) => r.issuance_gross_near !== null && r.buyback_near !== null && r.burnt_near !== null,
  );
  const last30 = complete.slice(-30);
  const avgIssuance = mean(last30.map((r) => r.issuance_gross_near as number));
  const avgBuyback = mean(last30.map((r) => r.buyback_near as number));
  const avgBurn = mean(last30.map((r) => r.burnt_near as number));
  const lastDay = last30[last30.length - 1].date;

  const views = rows
    .filter((r) => r.cr_float_30 !== null || r.cr_supply_30 !== null)
    .map((r) => ({ date: r.date, cr_float_30: r.cr_float_30, cr_supply_30: r.cr_supply_30 }));
  const lastView = [...views].reverse().find((r) => r.cr_float_30 !== null && r.cr_supply_30 !== null)!;
  const viewMarkers = markersBetween(views[0].date, views[views.length - 1].date);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Token economics"
        lede="New NEAR is minted every epoch. Gas burn destroys NEAR; buybacks move NEAR into a wallet that holds it. The two are kept apart: only burn lowers total supply."
      />

      <ChartCard
        id="flows"
        title="Issuance, buybacks and burn, NEAR per day"
        sentence={
          <>
            In the 30 days to {lastDay}, about {near(avgIssuance)} were issued per day, against{" "}
            {near(avgBuyback)} received by the buyback wallet and {near(avgBurn)} burnt as gas.
            {step ? ` Issuance roughly halved at marker ${step.n} (${step.date}).` : ""}
          </>
        }
        tables={["supply_daily", "fee_wallet_inflows_daily"]}
        model="coverage.issuance_gross_near, coverage.buyback_near (7-day means)"
        table={{
          columns: ["Date", "Issuance", "Buyback", "Burn"],
          rows: flows.slice(-30).map((r) => [
            r.date,
            r.issuance?.toFixed(0) ?? null,
            r.buyback?.toFixed(0) ?? null,
            r.burn?.toFixed(0) ?? null,
          ]),
        }}
      >
        <TimeChart
          ariaLabel="Issuance, buybacks and burn in NEAR per day, 7-day means"
          data={flows}
          format="near"
          markers={markers}
          series={[
            { key: "issuance", label: "Gross issuance", color: "var(--neutral-series)" },
            { key: "buyback", label: "Buyback wallet inflow", color: "var(--cat-1)" },
            { key: "burn", label: "Gas burn", color: "var(--cat-2)" },
          ]}
        />
        <MarkerList markers={markers} />
        <p className="mt-2 text-xs text-muted">
          7-day means. The buyback wallet is first observed on{" "}
          {coverage.availability.buyback_near.first_date}; where buybacks went before that is unknown,
          so the line starts there. Issuance is derived from total supply plus burn.
        </p>
      </ChartCard>

      <ChartCard
        id="views"
        title="Two views of coverage: float and total supply"
        sentence={
          <>
            On {lastView.date}, buybacks and burn covered {ratio(lastView.cr_float_30 as number)} of
            30-day issuance in the float view, but only {ratio(lastView.cr_supply_30 as number)} in the
            total-supply view, because NEAR bought back is held, not burnt.
          </>
        }
        tables={["supply_daily", "fee_wallet_inflows_daily"]}
        model="coverage.cr_float, coverage.cr_supply (src/capture/models/coverage.py)"
        table={{
          columns: ["Date", "CR_float 30d", "CR_supply 30d"],
          rows: views.slice(-30).map((r) => [
            r.date,
            r.cr_float_30?.toFixed(3) ?? null,
            r.cr_supply_30?.toFixed(3) ?? null,
          ]),
        }}
      >
        <TimeChart
          ariaLabel="CR_float and CR_supply over 30 days"
          data={views}
          format="ratio"
          markers={viewMarkers}
          series={[
            { key: "cr_float_30", label: "CR_float (buyback + burn)", color: "var(--cat-1)" },
            { key: "cr_supply_30", label: "CR_supply (burn only)", color: "var(--neutral-series)" },
          ]}
        />
        <MarkerList markers={viewMarkers} />
      </ChartCard>
    </div>
  );
}
