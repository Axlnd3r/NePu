import type { Metadata } from "next";
import { Badge, PageHeader } from "@/components/Bits";
import { markers, meta, provenance, queries } from "@/lib/data";
import { pct } from "@/lib/format";

export const metadata: Metadata = { title: "Methodology & data · NEAR Capture Ledger" };

function sourceName(text: string): string {
  if (text.startsWith("bigquery:")) return `BigQuery ${text.slice("bigquery:".length)}`;
  if (text.startsWith("manual:")) return "Curated reference (sources per row)";
  return text.split(";")[0].trim();
}

export default function Methodology() {
  const { sources, reference, reconciliation, proof } = provenance;
  const proofTx = (proof as { tx?: string | null }).tx;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Methodology & data"
        lede="Every number on this site is computed by `make build` from the files below, offline and without credentials. Their hashes are checked by `make verify`."
      />

      <section className="rounded-xl border border-[var(--ring)] bg-surface p-4 sm:p-6" aria-labelledby="sources">
        <h2 id="sources" className="text-base font-semibold">Sources and freshness</h2>
        <p className="mt-1 text-sm text-ink-2">
          One row per input file in <code>data/snapshot/manifest.json</code>. The last date is the
          freshest day in that file.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="tabular w-full min-w-[46rem] text-left text-xs">
            <thead>
              <tr className="text-ink-2">
                <th className="py-2 pr-3 font-medium">File</th>
                <th className="py-2 pr-3 font-medium">Source</th>
                <th className="py-2 pr-3 font-medium">Rows</th>
                <th className="py-2 pr-3 font-medium">First date</th>
                <th className="py-2 pr-3 font-medium">Last date</th>
                <th className="py-2 pr-3 font-medium">Pulled (UTC)</th>
                <th className="py-2 pr-3 font-medium">sha256</th>
              </tr>
            </thead>
            <tbody>
              {[...sources, ...reference].map((s) => (
                <tr key={s.path} className="border-t border-grid align-top">
                  <td className="py-1.5 pr-3 font-mono">{s.path}</td>
                  <td className="max-w-[18rem] break-words py-1.5 pr-3">{sourceName(s.source)}</td>
                  <td className="py-1.5 pr-3">{s.rows?.toLocaleString("en-US") ?? "–"}</td>
                  <td className="py-1.5 pr-3">{s.date_range?.[0] ?? "–"}</td>
                  <td className="py-1.5 pr-3 font-medium">{s.date_range?.[1] ?? "–"}</td>
                  <td className="py-1.5 pr-3">{s.pulled_at_utc}</td>
                  <td className="py-1.5 pr-3 font-mono">{s.sha256_8}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 break-all text-xs text-muted">
          Snapshot manifest sha256: <span className="font-mono">{provenance.manifest_sha256}</span>
        </p>
      </section>

      <section className="rounded-xl border border-[var(--ring)] bg-surface p-4 sm:p-6" aria-labelledby="recon">
        <h2 id="recon" className="text-base font-semibold">Reconciliation: on-chain revenue against DefiLlama</h2>
        <p className="mt-1 text-sm text-ink-2">
          Every complete month, revenue measured from the NEAR revenue wallets (internal transfers
          netted, daily prices) is compared with DefiLlama&apos;s. Tolerance{" "}
          {pct(reconciliation.tolerance, 0)}; a month outside it withdraws the headline.
        </p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {reconciliation.months.map((m) => (
            <li key={m.month}>
              <Badge tone={m.within_tolerance ? "good" : "critical"}>
                {m.month}: {m.deviation >= 0 ? "+" : ""}
                {pct(m.deviation)}
              </Badge>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-[var(--ring)] bg-surface p-4 sm:p-6" aria-labelledby="proof">
        <h2 id="proof" className="text-base font-semibold">Proof of analysis</h2>
        <p className="mt-1 text-sm text-ink-2">
          The snapshot manifest hash is committed to NEAR mainnet so anyone can check that these
          numbers came from these files at that time.
        </p>
        <p className="mt-2 text-sm">
          Status: <Badge tone={proofTx ? "good" : "neutral"}>{proof.status}</Badge>
          {proofTx ? (
            <>
              {" "}
              <a className="underline" href={`https://nearblocks.io/txns/${proofTx}`} rel="noreferrer" target="_blank">
                transaction {proofTx.slice(0, 10)}…
              </a>
            </>
          ) : (
            <span className="ml-2 text-xs text-muted">{proof.note}</span>
          )}
        </p>
      </section>

      <section className="rounded-xl border border-[var(--ring)] bg-surface p-4 sm:p-6" aria-labelledby="events">
        <h2 id="events" className="text-base font-semibold">Events on the charts</h2>
        <ul className="mt-3 space-y-2 text-sm">
          {markers.markers.map((m) => (
            <li key={m.id}>
              <span className="tabular font-medium">{m.date}</span> · {m.label}{" "}
              <span className="text-xs text-muted">
                ({m.kind === "data" ? `from the data: ${m.evidence}` : `reported: ${m.evidence}`})
              </span>
            </li>
          ))}
        </ul>
        <h3 className="mt-5 text-sm font-semibold">Not drawn, and why</h3>
        <ul className="mt-2 space-y-2 text-sm">
          {markers.not_drawn.map((n) => (
            <li key={n.label}>
              {n.label}: <span className="text-ink-2">{n.reason}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-[var(--ring)] bg-surface p-4 text-sm sm:p-6" aria-labelledby="repro">
        <h2 id="repro" className="text-base font-semibold">Reproduce</h2>
        <pre className="mt-3 overflow-x-auto rounded-md bg-plane p-3 text-xs">{`make setup    # Python (uv) and Node dependencies
make build    # every metric from data/snapshot -> site/public/data/*.json
make verify   # tests, reconciliation, invariants, manifest hashes
make site     # this dashboard, static, into site/out/`}</pre>
        <p className="mt-3 text-ink-2">
          Definitions, formulas and limitations: <code>docs/METHODOLOGY.md</code>. How every source
          was checked: <code>DATA_AUDIT.md</code>. {queries.queries.length} input tables; the SQL or
          API request of each is shown under every chart. This build:{" "}
          <span className="font-mono">{meta.git_commit.slice(0, 12)}</span>, {meta.built_at_utc}.
        </p>
      </section>
    </div>
  );
}
