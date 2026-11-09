import type { ReactNode } from "react";
import { query, reference, source } from "@/lib/data";

export type DataTable = { columns: string[]; rows: (string | number | null)[][] };

type Props = {
  id: string;
  title: string;
  /** One plain-English sentence: what the chart shows, with its number. */
  sentence: ReactNode;
  /** Input tables (names in data/snapshot/manifest.json) the chart is computed from. */
  tables: string[];
  /** Python function(s) that turn the tables into the plotted series. */
  model: string;
  table?: DataTable;
  /** Files in data/reference/ (with their own manifest) the chart also reads. */
  references?: string[];
  children: ReactNode;
};

/** Every chart: the chart, one sentence, the query text, and provenance (CLAUDE.md conventions). */
export function ChartCard({ id, title, sentence, tables, model, table, references = [], children }: Props) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="rounded-xl border border-[var(--ring)] bg-surface p-5 sm:p-8"
    >
      <h3 id={`${id}-title`} className="text-lg font-medium tracking-tight">
        {title}
      </h3>
      <p className="mt-1 text-sm text-ink-2">{sentence}</p>
      <div className="mt-4">{children}</div>

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-ink-2 hover:text-accent">Query and model</summary>
        <p className="mt-2 text-muted">
          Computed by <code>{model}</code> from the tables below.
        </p>
        {tables.map((t) => {
          const q = query(t);
          return (
            <div key={t} className="mt-3">
              <p className="font-mono text-xs text-ink-2">
                {t} ({q.kind === "bigquery_sql" ? q.file : "HTTP API"})
              </p>
              <pre className="mt-1 max-h-72 overflow-auto rounded-md border border-[var(--ring)] bg-raised p-3 text-xs leading-relaxed text-ink-2">
                {q.text}
              </pre>
            </div>
          );
        })}
      </details>

      {table && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-ink-2 hover:text-accent">Data table</summary>
          <div className="mt-2 max-h-80 overflow-auto">
            <table className="tabular w-full text-left text-xs">
              <thead>
                <tr>
                  {table.columns.map((c) => (
                    <th key={c} className="sticky top-0 bg-surface py-1 pr-3 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i} className="border-t border-grid">
                    {r.map((v, j) => (
                      <td key={j} className="py-1 pr-3">
                        {v ?? "–"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <ul className="mt-3 space-y-0.5 text-xs text-muted">
        {tables.map((t) => {
          const s = source(t);
          const range = s.date_range ? `${s.date_range[0]} to ${s.date_range[1]}` : "no date column";
          return (
            <li key={t} className="break-words">
              <span className="font-mono">{s.path}</span> · {shortSource(s.source)} · {range} ·
              pulled {s.pulled_at_utc} · sha256 <span className="font-mono">{s.sha256_8}</span>
            </li>
          );
        })}
        {references.map((path) => {
          const r = reference(path);
          const range = r.date_range ? `${r.date_range[0]} to ${r.date_range[1]}` : "no date range";
          return (
            <li key={path} className="break-words">
              <span className="font-mono">data/reference/{r.path}</span> · {shortSource(r.source)} ·{" "}
              {range} · pulled {r.pulled_at_utc} · sha256{" "}
              <span className="font-mono">{r.sha256_8}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function shortSource(text: string): string {
  if (text.startsWith("bigquery:")) return "BigQuery public dataset";
  if (text.includes("llama.fi")) return "DefiLlama API";
  if (text.includes("near-intents.org")) return "NEAR Intents Explorer API";
  if (text.includes("coingecko")) return "CoinGecko API";
  if (text.includes("chaindefuser")) return "1Click token list";
  if (text.includes("vote.dao")) return "NEAR mainnet RPC, vote.dao get_proposal";
  if (text.includes("revenue.near.org")) return "revenue.near.org (as published)";
  if (text.includes("nearblocks")) return "NearBlocks API";
  return text.split(";")[0];
}
