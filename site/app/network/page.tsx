import type { Metadata } from "next";
import { Badge, PageHeader } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { TimeChart } from "@/components/charts/TimeChart";
import { rolling, usage } from "@/lib/data";
import { compact, pct } from "@/lib/format";

export const metadata: Metadata = { title: "Network usage · NEAR Capture Ledger" };

const TABLES = ["network_daily", "intents_onchain_daily", "defillama_intents_daily", "price_daily"];
const MODEL = "src/capture/models/usage.py";

/** "rose 72%" or "fell 33%", from a signed fraction. */
function change(v: number): string {
  return `${v < 0 ? "fell" : "rose"} ${pct(Math.abs(v), 0)}`;
}

const fixed = (v: number | null, digits = 2) => (v === null ? null : v.toFixed(digits));

type Side = { lag: number; test_r: number; test_n: number; p_value: number | null } | null;

/** One predictor's out-of-sample result, or why there is none. */
function side(s: Side): string {
  if (s === null) return "too few weekly pairs";
  const weeks = s.lag === 1 ? "week" : "weeks";
  return `lag ${s.lag} ${weeks}, test r ${s.test_r.toFixed(2)} on ${s.test_n} weeks (p ${fixed(s.p_value) ?? "n/a"})`;
}

const RESULT_TEXT: Record<string, string> = {
  not_supported: "Not supported",
  supported: "Supported",
  insufficient_data: "Insufficient data",
};

export default function NetworkUsage() {
  const series = usage.series;
  const signers7 = rolling(series.map((r) => r.active_signers), 7);
  const tx7 = rolling(series.map((r) => r.tx_count), 7);
  const calls7 = rolling(series.map((r) => r.calls_to_intents), 7);
  const daily = series.map((r, i) => ({
    date: r.date,
    active_signers: signers7[i],
    tx_count: tx7[i],
    calls_to_intents: calls7[i],
  }));
  const latest = [...daily].reverse().find((r) => r.active_signers !== null && r.tx_count !== null)!;

  const weeks = usage.weekly;
  const base = weeks[0];
  const indexed = weeks.map((w) => ({
    date: w.week,
    active_signers: w.active_signers / base.active_signers,
    tx_count: w.tx_count / base.tx_count,
    volume_usd: w.volume_usd / base.volume_usd,
    near_usd: w.near_usd / base.near_usd,
  }));
  const { halves, shares, window } = usage;
  const { verdict, rows, split_week } = usage.lead_lag;
  const trainWeeks = weeks.filter((w) => w.week < split_week).length;
  const testWeeks = weeks.length - trainWeeks;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Network usage"
        lede="Does NEAR's own activity move with Intents? Daily active accounts are distinct transaction signers; a relayed call is signed by its relayer."
      />

      <ChartCard
        id="activity"
        title="Daily active accounts and transactions"
        sentence={
          <>
            In the 7 days to {latest.date}, about {compact(latest.active_signers as number)} accounts
            signed a transaction each day, and the network carried about{" "}
            {compact(latest.tx_count as number)} transactions a day.
          </>
        }
        tables={["network_daily"]}
        model={`usage.daily_table (${MODEL}), 7-day means`}
        table={{
          columns: ["Date", "Active accounts", "Transactions"],
          rows: daily.slice(-30).map((r) => [r.date, fixed(r.active_signers, 0), fixed(r.tx_count, 0)]),
        }}
      >
        <TimeChart
          ariaLabel="Daily active accounts, 7-day mean"
          data={daily}
          format="count"
          series={[{ key: "active_signers", label: "Daily active accounts", color: "var(--cat-1)" }]}
        />
        <TimeChart
          ariaLabel="Transactions per day, 7-day mean"
          data={daily}
          format="count"
          series={[{ key: "tx_count", label: "Transactions per day", color: "var(--cat-2)" }]}
        />
      </ChartCard>

      <ChartCard
        id="divergence"
        title="Network usage against Intents volume and price"
        sentence={
          <>
            Comparing the first {halves.first.weeks} complete weeks ({halves.first.start} to{" "}
            {halves.first.end}) with the next {halves.second.weeks}, daily active accounts{" "}
            {change(halves.change.active_signers)} while Intents volume{" "}
            {change(halves.change.volume_usd)} and the NEAR price {change(halves.change.near_usd)}.
          </>
        }
        tables={TABLES}
        model={`usage.weekly_table, usage.halves (${MODEL})`}
        table={{
          columns: ["Week", "Active accounts", "Transactions", "Intents volume", "NEAR price"],
          rows: indexed.map((r) => [
            r.date,
            r.active_signers.toFixed(2),
            r.tx_count.toFixed(2),
            r.volume_usd.toFixed(2),
            r.near_usd.toFixed(2),
          ]),
        }}
      >
        <TimeChart
          ariaLabel="Weekly network usage, Intents volume and NEAR price, each divided by its first week"
          data={indexed}
          format="ratio"
          refY={{ y: 1, label: "first week" }}
          series={[
            { key: "active_signers", label: "Daily active accounts", color: "var(--cat-1)" },
            { key: "tx_count", label: "Transactions", color: "var(--cat-2)" },
            { key: "volume_usd", label: "Intents volume", color: "var(--cat-3)" },
            { key: "near_usd", label: "NEAR price", color: "var(--neutral-series)" },
          ]}
        />
        <p className="mt-2 text-xs text-muted">
          Each weekly value divided by the week of {base.week}. Accounts and price are weekly means;
          transactions and volume are weekly sums. No cause is attributed.
        </p>
      </ChartCard>

      <ChartCard
        id="footprint"
        title="How much of NEAR's activity is Intents"
        sentence={
          <>
            From {window.first_date} to {window.last_date}, calls to <code>intents.near</code> were{" "}
            {pct(shares.intents_call_share)} of all function calls, and its daily signers{" "}
            {pct(shares.intents_signer_share, 2)} of daily active accounts.
          </>
        }
        tables={["intents_onchain_daily", "network_daily"]}
        model={`usage.shares (${MODEL}), 7-day means`}
        table={{
          columns: ["Date", "Calls to intents.near"],
          rows: daily.slice(-30).map((r) => [r.date, fixed(r.calls_to_intents, 0)]),
        }}
      >
        <TimeChart
          ariaLabel="Function calls to intents.near per day, 7-day mean"
          data={daily}
          format="count"
          series={[{ key: "calls_to_intents", label: "Calls to intents.near", color: "var(--cat-3)" }]}
        />
        <p className="mt-2 text-xs text-muted">
          Intents revenue can grow while the rest of the network does not: the two are different
          measures and are kept apart here.
        </p>
      </ChartCard>

      <ChartCard
        id="usage-leadlag"
        title="Does Intents volume lead network usage better than price?"
        sentence={<>Result: {verdict.label}. {verdict.text}</>}
        tables={TABLES}
        model={`usage.lead_lag_table, usage.verdict (${MODEL}; train/test split, permutation test)`}
        table={{
          columns: ["Usage", "Predictor", "Sample", "Lag (weeks)", "Pairs", "Pearson r", "Spearman", "p", "Note"],
          rows: rows.map((r) => [
            r.usage,
            r.predictor,
            r.sample,
            r.lag,
            r.n,
            fixed(r.pearson),
            fixed(r.spearman),
            fixed(r.p_value),
            r.note,
          ]),
        }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone="neutral">{RESULT_TEXT[verdict.result] ?? verdict.label}</Badge>
          <span className="text-sm text-ink-2">
            Split at the week of {split_week} · significance level {verdict.alpha}
          </span>
        </div>
        <ul className="mt-3 space-y-1 text-sm text-ink-2">
          {verdict.by_usage.map((u) => (
            <li key={u.usage}>
              {u.label}: Intents volume {side(u.volume)}; NEAR price {side(u.price)}.
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm text-ink-2">
          Reported as it came out (CLAUDE.md rule 5). The {weeks.length} complete weeks give{" "}
          {trainWeeks} weeks for training and {testWeeks} for testing, so the test has little power.
          It was designed after an exploratory look at the same data, so it is not blind. Correlation
          would not show cause in either direction.
        </p>
      </ChartCard>
    </div>
  );
}
