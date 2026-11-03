import type { Metadata } from "next";
import { Badge, PageHeader } from "@/components/Bits";
import { ProofVerifier } from "@/components/ProofVerifier";
import { markers, meta, provenance, queries } from "@/lib/data";
import { pct } from "@/lib/format";

export const metadata: Metadata = { title: "Methodology & data · NEAR Capture Ledger" };

type ProofShape = {
  status: string;
  note?: string;
  network?: string;
  contract?: string;
  run_id?: string;
  manifest_sha256?: string;
  tx?: string | null;
  block_height?: number;
  explorer_url?: string;
  rpc_url?: string;
  current?: boolean | null;
  opentimestamps?: {
    status: string;
    bitcoin_blocks: number[];
    pending_calendars: string[];
    checked_at_utc: string;
    file: string;
  } | null;
};

function sourceName(text: string): string {
  if (text.startsWith("bigquery:")) return `BigQuery ${text.slice("bigquery:".length)}`;
  if (text.startsWith("manual:")) return "Curated reference (sources per row)";
  return text.split(";")[0].trim();
}

export default function Methodology() {
  const { sources, reference, reconciliation } = provenance;
  // The shape depends on whether data/proof.json exists, so every field is optional here.
  const proof = provenance.proof as ProofShape;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Methodology & data"
        lede={
          <>
            Every number on this site is computed by <code>make build</code> from the files below,
            offline and without credentials. Their hashes are checked by <code>make verify</code>.
          </>
        }
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
          The SHA-256 of the snapshot manifest (which lists the hash of every data file) is committed
          to a NEAR contract, so anyone can check that these numbers came from these files, and that
          the hash existed no later than the block of the transaction. It does not show that the data
          is correct.
        </p>
        {proof.status === "committed" && proof.network ? (
          <>
            <p className="mt-3 text-sm">
              <Badge tone="neutral">NEAR {proof.network}</Badge>{" "}
              {proof.current === false && <Badge tone="critical">made for an older snapshot</Badge>}
            </p>
            {proof.network === "testnet" && (
              <p className="mt-2 text-xs text-muted">
                This is a testnet commit, not mainnet: testnet carries no economic security and is not
                guaranteed to keep its history. It was chosen because it costs nothing.
              </p>
            )}
            <dl className="mt-3 space-y-1 text-xs">
              <div>
                <dt className="inline text-muted">Contract: </dt>
                <dd className="inline font-mono">{proof.contract}</dd>
              </div>
              <div>
                <dt className="inline text-muted">Run id: </dt>
                <dd className="inline font-mono break-all">{proof.run_id}</dd>
              </div>
              <div>
                <dt className="inline text-muted">Transaction: </dt>
                <dd className="inline">
                  <a className="font-mono underline break-all" href={proof.explorer_url} rel="noreferrer" target="_blank">
                    {proof.tx}
                  </a>{" "}
                  (block {proof.block_height})
                </dd>
              </div>
            </dl>
            <div className="mt-4 rounded-lg bg-plane p-4">
              <p className="text-sm font-medium">Verify it yourself</p>
              <ProofVerifier
                network={proof.network}
                contract={proof.contract as string}
                runId={proof.run_id as string}
                rpcUrl={proof.rpc_url as string}
                recordedHash={proof.manifest_sha256 as string}
              />
              <p className="mt-3 text-xs text-muted">
                Without this page: hash <code>data/snapshot/manifest.json</code> (for example with{" "}
                <code>sha256sum</code>) and compare it with the value of <code>get</code> for the run id above
                (<code>near contract call-function as-read-only</code>, or <code>capture proof status</code>).
              </p>
            </div>
          </>
        ) : (
          <p className="mt-2 text-sm">
            Status: <Badge tone="neutral">{proof.status}</Badge>
            <span className="ml-2 text-xs text-muted">{proof.note}</span>
          </p>
        )}
        <div className="mt-4 text-sm">
          <p>
            OpenTimestamps (Bitcoin):{" "}
            <Badge tone={proof.opentimestamps?.status === "confirmed" ? "good" : "neutral"}>
              {proof.opentimestamps?.status ?? "not stamped yet"}
            </Badge>
          </p>
          {proof.opentimestamps ? (
            <p className="mt-2 text-xs text-muted">
              {proof.opentimestamps.status === "confirmed"
                ? `Attested in Bitcoin block ${proof.opentimestamps.bitcoin_blocks.join(", ")} according to the proof file; check it with ots verify and a Bitcoin node.`
                : `Submitted to ${proof.opentimestamps.pending_calendars.length} calendar servers; a Bitcoin block attests it a few hours later and the proof workflow then completes the file.`}{" "}
              Checked {proof.opentimestamps.checked_at_utc}.{" "}
              <a
                className="underline"
                href={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/${proof.opentimestamps.file}`}
              >
                manifest.json.ots
              </a>{" "}
              (to verify, save it next to <code>data/snapshot/manifest.json</code> and run{" "}
              <code>ots verify manifest.json.ots</code>; the client needs a Bitcoin Core node).
            </p>
          ) : (
            <p className="mt-2 text-xs text-muted">
              The stamp is made by the proof workflow in CI, because the <code>ots</code> client does
              not run on Windows.
            </p>
          )}
        </div>
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
