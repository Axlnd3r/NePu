import type { Metadata } from "next";
import { Badge, PageHeader } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { developer } from "@/lib/data";
import { pct } from "@/lib/format";

export const metadata: Metadata = { title: "Developer · NEAR Capture Ledger" };

const TABLES = ["contracts_daily", "defillama_intents_daily"];

/** Sequential single-hue fill: the accent mixed into the surface by share (0 to about 60 %). */
function fill(share: number): { background: string; color: string } {
  const strength = Math.min(share / 0.6, 1) * 85 + 8;
  return {
    background: `color-mix(in oklab, var(--accent) ${strength.toFixed(0)}%, var(--surface))`,
    color: strength > 55 ? "#ffffff" : "var(--ink)",
  };
}

export default function Developer() {
  const cohorts = developer.cohorts.filter((c) => c.complete);
  const { verdict, rows } = developer.lead_lag;
  const lagged = cohorts.filter((c) => c.share_1 !== null);
  const latest = lagged[lagged.length - 1];
  const train0 = rows.find((r) => r.transform === "levels" && r.sample === "train" && r.lag === 0);
  const test0 = rows.find((r) => r.transform === "levels" && r.sample === "test" && r.lag === 0);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Developer"
        lede="Do new contracts stay in use, and does that move with Intents revenue? A contract counts as retained in a month if it receives at least one function call."
      />

      <ChartCard
        id="cohorts"
        title="Retention of new contracts by monthly cohort"
        sentence={
          <>
            Of the {latest.cohort_size} contracts first deployed in {latest.cohort},{" "}
            {pct(latest.share_1 as number)} were still called the next month.
          </>
        }
        tables={["contracts_daily"]}
        model="developer.new_contracts, developer.cohort_table (src/capture/models/developer.py)"
      >
        <div className="overflow-x-auto">
          <table className="tabular w-full min-w-[34rem] text-left text-sm">
            <thead>
              <tr className="text-ink-2">
                <th className="py-2 pr-3 font-medium">Cohort</th>
                <th className="py-2 pr-3 font-medium">New contracts</th>
                <th className="py-2 pr-3 font-medium">Largest parent</th>
                <th className="py-2 pr-3 font-medium">Month +1</th>
                <th className="py-2 pr-3 font-medium">Month +2</th>
                <th className="py-2 pr-3 font-medium">Month +3</th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((c) => (
                <tr key={c.cohort} className="border-t border-grid">
                  <td className="py-1.5 pr-3">{c.cohort}</td>
                  <td className="py-1.5 pr-3">{c.cohort_size}</td>
                  <td className="py-1.5 pr-3 text-xs text-ink-2">
                    {c.top_parent} ({pct(c.top_parent_share, 0)})
                  </td>
                  {[c.share_1, c.share_2, c.share_3].map((s, i) => (
                    <td key={i} className="py-1 pr-1">
                      {s === null ? (
                        <span className="block px-2 py-1 text-xs text-muted">not yet</span>
                      ) : (
                        <span className="block rounded px-2 py-1 text-center text-xs font-medium" style={fill(s)}>
                          {pct(s, 0)}
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          Darker means a larger share still in use. A cohort can jump when one parent account deploys
          many sub-accounts; the largest parent and its share are shown for that reason.
        </p>
      </ChartCard>

      <ChartCard
        id="leadlag"
        title="Does developer activity lead Intents revenue?"
        sentence={<>Result: {verdict.result === "null" ? "no detectable relationship (a null result)" : verdict.result}. {verdict.text}</>}
        tables={TABLES}
        model="developer.lead_lag, developer.verdict (train/test split, permutation test)"
        table={{
          columns: ["Transform", "Sample", "Lag (months)", "Pairs", "Pearson r", "Spearman", "p", "Note"],
          rows: rows.map((r) => [
            r.transform,
            r.sample,
            r.lag,
            r.n,
            r.pearson === null ? null : r.pearson.toFixed(2),
            r.spearman === null ? null : r.spearman.toFixed(2),
            r.p_value === null ? null : r.p_value.toFixed(2),
            r.note,
          ]),
        }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone="neutral">{verdict.result === "null" ? "Null result" : verdict.result}</Badge>
          <span className="text-sm text-ink-2">
            Lag chosen in training: {verdict.lag_chosen_in_train} months · significance level{" "}
            {verdict.alpha}
          </span>
        </div>
        <p className="mt-3 text-sm text-ink-2">
          Reported as it came out (CLAUDE.md rule 5). At lag 0 the test has {train0?.n ?? 0}{" "}
          training and {test0?.n ?? 0} test pairs of months, so it has little power; the null result
          says only that nothing can be told apart from chance yet. Correlation would not show cause
          in either direction.
        </p>
      </ChartCard>
    </div>
  );
}
