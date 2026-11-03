// The dashboard reads only site/public/data/*.json, written by `make build` (capture build).
import coverage from "../public/data/coverage.json";
import developer from "../public/data/developer.json";
import distribution from "../public/data/distribution.json";
import markers from "../public/data/markers.json";
import meta from "../public/data/meta.json";
import provenance from "../public/data/provenance.json";
import queries from "../public/data/queries.json";
import summary from "../public/data/summary.json";
import valuation from "../public/data/valuation.json";

export { coverage, developer, distribution, markers, meta, provenance, queries, summary, valuation };

export type SourceRow = (typeof provenance.sources)[number];
export type Query = (typeof queries.queries)[number];

export function source(table: string): SourceRow {
  const row = provenance.sources.find((s) => s.path === `${table}.parquet`);
  if (!row) throw new Error(`no provenance for ${table}`);
  return row;
}

export function query(table: string): Query {
  const q = queries.queries.find((x) => x.id === table);
  if (!q) throw new Error(`no query for ${table}`);
  return q;
}

/** Keep only the listed keys of each row, so client charts receive small payloads. */
export function pick<T extends Record<string, unknown>, K extends keyof T>(
  rows: T[],
  keys: K[],
): Pick<T, K>[] {
  return rows.map((r) => {
    const out = {} as Pick<T, K>;
    for (const k of keys) out[k] = r[k];
    return out;
  });
}

/** Trailing mean over `window` rows; null until the window is full or when a value is missing. */
export function rolling(values: (number | null)[], window: number): (number | null)[] {
  return values.map((_, i) => {
    if (i + 1 < window) return null;
    const slice = values.slice(i + 1 - window, i + 1);
    if (slice.some((v) => v === null)) return null;
    return (slice as number[]).reduce((a, b) => a + b, 0) / window;
  });
}

/** date is the event's day; at (if set) is where it is drawn on a weekly or monthly axis. */
export type Marker = {
  n: number;
  date: string;
  at?: string;
  label: string;
  kind: string;
  sources: string[];
};

/** Markers inside [first, last], numbered in date order for the chart labels and the list. */
export function markersBetween(first: string, last: string, ids?: string[]): Marker[] {
  return markers.markers
    .filter((m) => m.date >= first && m.date <= last && (!ids || ids.includes(m.id)))
    .map((m, i) => ({ n: i + 1, date: m.date, label: m.label, kind: m.kind, sources: m.sources }));
}
