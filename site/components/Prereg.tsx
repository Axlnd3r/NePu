import { Badge } from "@/components/Bits";

type Test = {
  id: string;
  claim: string;
  quantity: string;
  window: [string, string];
  pass_if: [number, number] | string;
  scored_on: string;
};
type Result = { status: "pass" | "miss" | "pending"; value?: number | string; reason?: string };
export type PreregData = {
  registered: boolean;
  registered_at_utc?: string;
  manifest_sha256?: string;
  tests?: Test[];
  anchor?: { near: { network: string; contract: string; run_id: string; block_height: number; explorer_url: string } } | null;
  scores?: { scored_at_utc: string; results: Record<string, Result> } | null;
};

function rule(t: Test): string {
  if (typeof t.pass_if === "string") return t.pass_if;
  const [lo, hi] = t.pass_if;
  const f = (v: number) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : v.toPrecision(3));
  return `between ${f(lo)} and ${f(hi)}`;
}

/** The forward tests, registered before their data existed, with where each one stands. */
export function Prereg({ data }: { data: PreregData }) {
  if (!data.registered || !data.tests) return null;
  const anchor = data.anchor?.near;
  return (
    <section aria-labelledby="prereg" className="rounded-xl border border-[var(--ring)] bg-surface p-5 sm:p-8">
      <h2 id="prereg" className="text-lg font-medium tracking-tight">
        Pre-registered forward tests
      </h2>
      <p className="mt-1 text-sm text-ink-2">
        Written on {data.registered_at_utc?.slice(0, 10)}, before any window closed, and frozen (what
        each window already held is stated in <code>data/prereg/PREREG.md</code>). Each one is scored when its window closes; a miss is reported as a miss.{" "}
        {anchor ? (
          <>
            Their hash is on NEAR {anchor.network} at block {anchor.block_height.toLocaleString("en-US")}{" "}
            (<a className="underline hover:text-accent" href={anchor.explorer_url} rel="noreferrer" target="_blank">transaction</a>).
          </>
        ) : (
          <>The hash of the registration is not anchored on NEAR yet.</>
        )}
      </p>
      <ul className="mt-4 divide-y divide-[var(--ring)]">
        {data.tests.map((t) => {
          const r = data.scores?.results[t.id];
          const status = r?.status ?? "pending";
          return (
            <li key={t.id} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">
                  <span className="tabular mr-2 text-accent">{t.id}</span>
                  {t.claim}
                </p>
                <Badge tone={status === "pass" ? "good" : status === "miss" ? "critical" : "neutral"}>
                  {status === "pending" ? `pending, scored ${t.scored_on}` : status}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-ink-2">
                {t.quantity}; window {t.window[0].slice(0, 10)} to {t.window[1].slice(0, 10)}; passes if{" "}
                {rule(t)}.
              </p>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-muted">
        Files: <code>data/prereg/</code> (manifest sha256{" "}
        <span className="font-mono break-all">{data.manifest_sha256}</span>).
      </p>
    </section>
  );
}
