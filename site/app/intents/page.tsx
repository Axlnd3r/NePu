import type { Metadata } from "next";
import { BarRows, Callout, MarkerList, PageHeader } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { TimeChart } from "@/components/charts/TimeChart";
import {
  coverage,
  distribution,
  type Marker,
  markers as allMarkers,
  rolling,
  valuation,
} from "@/lib/data";
import { pct, usd } from "@/lib/format";

export const metadata: Metadata = { title: "Intents & channels · NEAR Capture Ledger" };

const REPORTED = allMarkers.markers.filter((m) => m.kind === "reported");
const EXPLORER = ["explorer_1click_daily", "explorer_channels_daily", "token_assets"];

/** Reported events dated to the period (week or month start) that contains them. */
function periodMarkers(periods: string[], days: number): Marker[] {
  return REPORTED.flatMap((m) => {
    const t = Date.parse(m.date);
    const p = periods.find((s) => t >= Date.parse(s) && t < Date.parse(s) + days * 864e5);
    return p ? [{ n: 0, date: p, label: m.label, kind: m.kind, sources: m.sources }] : [];
  }).map((m, i) => ({ ...m, n: i + 1 }));
}

export default function Intents() {
  const series = coverage.series.filter((r) => r.date >= valuation.growth.start);
  const vol7 = rolling(series.map((r) => r.volume_usd), 7);
  const volume = series.map((r, i) => ({ date: r.date, volume: vol7[i] }));
  const volMarkers = REPORTED.filter((m) => m.date >= series[0].date).map((m, i) => ({
    n: i + 1,
    date: m.date,
    label: m.label,
    kind: m.kind,
    sources: m.sources,
  }));
  const peak = volume.reduce((a, b) => ((b.volume ?? 0) > (a.volume ?? 0) ? b : a));
  const last30 = series.filter((r) => r.volume_usd !== null).slice(-30);
  const avg30 = last30.reduce((a, r) => a + (r.volume_usd as number), 0) / last30.length;

  const taus = coverage.series
    .filter((r) => r.tau_eff_30 !== null || r.tau_eff_buyback_30 !== null)
    .map((r) => ({ date: r.date, all: r.tau_eff_30, buyback: r.tau_eff_buyback_30 }));
  const lastTau = [...taus].reverse().find((r) => r.all !== null && r.buyback !== null)!;

  const months = distribution.periods.month.filter((p) => p.complete);
  const month = months[months.length - 1];
  const channelRows = distribution.channels.month
    .filter((c) => c.period === month.period && c.referral !== "(other)")
    .sort((a, b) => b.share - a.share);
  const top = channelRows.slice(0, 8);
  const other = 1 - top.reduce((a, c) => a + c.share, 0);

  const weeks = distribution.periods.week.filter((w) => w.complete);
  const weekly = weeks.map((w) => ({
    date: w.period,
    hhi_channel: w.hhi_channel,
    hhi_asset: w.hhi_asset,
    zec: w.zec_share,
    stable: w.stablecoin_share,
  }));
  const weekMarkers = periodMarkers(
    weeks.map((w) => w.period),
    7,
  );
  const lastWeek = weeks[weeks.length - 1];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Intents & channels"
        lede="Where the volume behind the buybacks comes from, how concentrated it is, and how much of it this data can see."
      />

      <Callout title="Scope of the channel data">
        Channel and asset views come from the NEAR Intents Explorer, which lists 1Click transactions
        only. It covered {pct(months[0].explorer_share_of_defillama_volume as number)} of DefiLlama
        Intents volume in {months[0].period} and {pct(month.explorer_share_of_defillama_volume as number)}{" "}
        in {month.period}. Every channel number below describes that fraction. near.com cannot be
        identified in this data.
      </Callout>

      <ChartCard
        id="volume"
        title="Intents volume, USD per day"
        sentence={
          <>
            Volume averaged {usd(avg30)} a day over the last 30 days of data; the 7-day average peaked
            at {usd(peak.volume as number)} on {peak.date}.
          </>
        }
        tables={["defillama_intents_daily"]}
        model="7-day mean of DefiLlama daily volume"
        table={{
          columns: ["Date", "Volume, 7-day mean"],
          rows: volume.slice(-30).map((r) => [r.date, r.volume === null ? null : usd(r.volume)]),
        }}
      >
        <TimeChart ariaLabel="Intents volume, 7-day mean" data={volume} format="usd" markers={volMarkers} series={[{ key: "volume", label: "Volume", color: "var(--neutral-series)" }]} />
        <MarkerList markers={volMarkers} />
      </ChartCard>

      <ChartCard
        id="tau"
        title="Take rate: revenue and buyback per dollar of volume"
        sentence={
          <>
            On {lastTau.date}, protocol revenue was {(lastTau.all! * 1e4).toFixed(2)} basis points of
            volume over 30 days, and the part that reached the buyback wallet{" "}
            {(lastTau.buyback! * 1e4).toFixed(2)} basis points.
          </>
        }
        tables={["defillama_intents_daily", "fee_wallet_inflows_daily", "price_daily"]}
        model="coverage.tau_eff, breakeven.tau_eff_buyback (30 days)"
      >
        <TimeChart
          ariaLabel="Take rate over 30 days, all revenue and buyback wallet"
          data={taus}
          format="bps"
          series={[
            { key: "all", label: "All protocol revenue", color: "var(--neutral-series)" },
            { key: "buyback", label: "Reached buyback wallet", color: "var(--accent)" },
          ]}
        />
      </ChartCard>

      <ChartCard
        id="channels"
        title={`Channel shares of 1Click volume, ${month.period}`}
        sentence={
          <>
            In {month.period} the largest channel, {top[0].referral}, carried {pct(top[0].share)} of
            1Click volume and the top five {pct(month.top5_channel_share as number)}; the channel HHI
            was {(month.hhi_channel as number).toFixed(3)}.
          </>
        }
        tables={EXPLORER}
        model="distribution.volume_shares, distribution.concentration"
        table={{
          columns: ["Channel", "Share", "Volume"],
          rows: channelRows.map((c) => [c.referral, pct(c.share), usd(c.volume_usd)]),
        }}
      >
        <BarRows
          max={top[0].share}
          rows={[
            ...top.map((c) => ({ label: c.referral, value: c.share, text: pct(c.share) })),
            { label: "All other channels", value: other, text: pct(other), muted: true },
          ]}
        />
        <p className="mt-2 text-xs text-muted">
          A channel is the transaction&apos;s referral value; &quot;(none)&quot; has no referral.
        </p>
      </ChartCard>

      <ChartCard
        id="concentration"
        title="Concentration by week (HHI)"
        sentence={
          <>
            In the week of {lastWeek.period}, the channel HHI was {lastWeek.hhi_channel.toFixed(3)} and
            the asset HHI {lastWeek.hhi_asset.toFixed(3)} (1 = one channel or asset holds everything).
          </>
        }
        tables={EXPLORER}
        model="distribution.concentration (complete weeks only)"
      >
        <TimeChart
          ariaLabel="Weekly HHI of channels and assets"
          data={weekly}
          format="ratio"
          markers={weekMarkers}
          series={[
            { key: "hhi_channel", label: "Channels", color: "var(--series-2)" },
            { key: "hhi_asset", label: "Origin assets", color: "var(--series-3)" },
          ]}
        />
        <MarkerList markers={weekMarkers} />
      </ChartCard>

      <ChartCard
        id="assets"
        title="Asset dependency: ZEC and stablecoins"
        sentence={
          <>
            In the week of {lastWeek.period}, ZEC was the origin asset of {pct(lastWeek.zec_share)} of
            1Click volume and stablecoins of {pct(lastWeek.stablecoin_share)}.
          </>
        }
        tables={EXPLORER}
        model="distribution.symbols, distribution.asset_categories (stablecoin list in distribution.json)"
      >
        <TimeChart
          ariaLabel="Weekly share of ZEC and stablecoins in 1Click volume"
          data={weekly}
          format="pct"
          markers={weekMarkers}
          series={[
            { key: "zec", label: "ZEC", color: "var(--series-2)" },
            { key: "stable", label: "Stablecoins", color: "var(--series-3)" },
          ]}
        />
        <MarkerList markers={weekMarkers} />
      </ChartCard>

      <ChartCard
        id="attribution"
        title="How much of on-chain revenue the channel data explains"
        sentence={
          <>
            Declared app fees to NEAR wallets explain {pct(month.attributable_share as number)} of
            on-chain revenue in {month.period}, against {pct(months[0].attributable_share as number)} in{" "}
            {months[0].period}; the rest has no per-transaction source in this data.
          </>
        }
        tables={[...EXPLORER, "fee_wallet_inflows_daily", "price_daily"]}
        model="distribution.near_attribution"
      >
        <BarRows
          max={1}
          rows={months.map((m) => ({
            label: m.period,
            value: m.attributable_share as number,
            text: pct(m.attributable_share as number),
          }))}
        />
      </ChartCard>
    </div>
  );
}
