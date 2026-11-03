"use client";

import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatValue } from "./fmt";

type Run = {
  scenario: string;
  inflation_path: string;
  price_multiplier: number;
  p_cr_ge_1: Record<string, number>;
  median_first_month: number | string;
  fan: { p10: number[]; p50: number[]; p90: number[] };
  volume_p50_usd_per_day: Record<string, number>;
};

const SCENARIO_TEXT: Record<string, string> = {
  flat: "Flat: no drift, historical volatility",
  decay: "Decay: historical drift, halving every 12 months",
  historical: "Historical: growth as in the sample (launch-driven)",
};
const ORDER = ["flat", "decay", "historical"];
const PATHS: Record<string, string> = {
  "constant_2.5": "2.5% constant",
  "ramp_to_1.6": "HSP-029 ramp to 1.6%",
};

export function ValuationExplorer({ runs, volumeNow }: { runs: Run[]; volumeNow: number }) {
  const [path, setPath] = useState("constant_2.5");
  const [mult, setMult] = useState(1);
  const shown = ORDER.map(
    (s) => runs.find((r) => r.scenario === s && r.inflation_path === path && r.price_multiplier === mult)!,
  );

  return (
    <div>
      <div className="flex flex-wrap gap-4 text-sm">
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="sr-only">Inflation path</legend>
          {Object.entries(PATHS).map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={path === k}
              onClick={() => setPath(k)}
              className={`rounded-md border px-3 py-1 ${path === k ? "border-accent bg-accent text-white" : "border-[var(--ring)]"}`}
            >
              {label}
            </button>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="sr-only">Price held at</legend>
          {[0.5, 1, 2].map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mult === m}
              onClick={() => setMult(m)}
              className={`rounded-md border px-3 py-1 ${mult === m ? "border-accent bg-accent text-white" : "border-[var(--ring)]"}`}
            >
              price held at {m}x
            </button>
          ))}
        </fieldset>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {shown.map((run) => (
          <Panel key={run.scenario} run={run} volumeNow={volumeNow} />
        ))}
      </div>
    </div>
  );
}

function Panel({ run, volumeNow }: { run: Run; volumeNow: number }) {
  const data = run.fan.p50.map((p50, i) => ({
    month: i + 1,
    band: [run.fan.p10[i], run.fan.p90[i]] as [number, number],
    p50,
  }));
  const first = run.median_first_month;
  return (
    <figure className="rounded-lg border border-[var(--ring)] p-3">
      <figcaption className="text-sm font-medium">{SCENARIO_TEXT[run.scenario]}</figcaption>
      <div role="img" aria-label={`CR fan chart, ${run.scenario} scenario`}>
        <ResponsiveContainer width="100%" height={200} initialDimension={{ width: 320, height: 200 }}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 11, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--axis)" }}
              ticks={[12, 24, 36, 48, 60]}
            />
            <YAxis
              scale="log"
              domain={["auto", "auto"]}
              tick={{ fontSize: 11, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={false}
              width={44}
              tickFormatter={(v: number) => formatValue(v, "ratio", true)}
            />
            <Tooltip
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--ring)", fontSize: 12 }}
              labelFormatter={(m) => `Month ${m}`}
              formatter={(v) =>
                Array.isArray(v)
                  ? `${formatValue(v[0], "ratio")} to ${formatValue(v[1], "ratio")}`
                  : formatValue(Number(v), "ratio")
              }
            />
            <ReferenceLine y={1} stroke="var(--ink-2)" label={{ value: "CR = 1", position: "insideTopLeft", fontSize: 11, fill: "var(--ink-2)" }} />
            <Area dataKey="band" name="p10 to p90" stroke="none" fill="var(--accent)" fillOpacity={0.12} isAnimationActive={false} />
            <Line dataKey="p50" name="median" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <dl className="tabular mt-2 grid grid-cols-3 gap-1 text-xs">
        {["12", "36", "60"].map((m) => (
          <div key={m}>
            <dt className="text-muted">P(CR≥1), m{m}</dt>
            <dd className="font-medium">{(run.p_cr_ge_1[m] * 100).toFixed(0)}%</dd>
          </div>
        ))}
        {["12", "36", "60"].map((m) => (
          <div key={`v${m}`}>
            <dt className="text-muted">Volume implied, m{m}</dt>
            <dd className="font-medium">
              {formatValue(run.volume_p50_usd_per_day[m], "usd")}/d (
              {(run.volume_p50_usd_per_day[m] / volumeNow).toFixed(1)}x)
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-ink-2">
        Median first month with CR ≥ 1:{" "}
        <span className="font-medium text-ink">{typeof first === "number" ? `month ${first}` : first}</span>
      </p>
    </figure>
  );
}
