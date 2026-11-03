import type { ReactNode } from "react";
import type { Marker } from "@/lib/data";

export function MarkerList({ markers }: { markers: Marker[] }) {
  if (!markers.length) return null;
  return (
    <ol className="mt-3 space-y-1 text-xs text-ink-2">
      {markers.map((m) => (
        <li key={m.n} className="flex gap-2">
          <span className="tabular font-semibold text-ink">{m.n}</span>
          <span>
            {m.date}: {m.label}{" "}
            <span className="text-muted">
              ({m.kind === "data" ? "from the data" : "reported"}
              {m.sources.map((s, i) => (
                <span key={s}>
                  {", "}
                  <a className="underline" href={s} rel="noreferrer" target="_blank">
                    source {i + 1}
                  </a>
                </span>
              ))}
              )
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Horizontal bars in plain HTML: one series, so one colour; the highlighted bar carries the accent. */
export function BarRows({
  rows,
  max,
}: {
  rows: { label: string; value: number; text: string; accent?: boolean; muted?: boolean }[];
  max: number;
}) {
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        // The bar is sized against its own track, so lengths stay proportional at every width;
        // on phones the label sits above the bar instead of squeezing it.
        <div
          key={r.label}
          className="grid grid-cols-[1fr_4.5rem] items-center gap-x-3 gap-y-0.5 sm:grid-cols-[minmax(7rem,12rem)_1fr_4.5rem]"
        >
          <span className="col-span-2 text-sm text-ink-2 sm:col-span-1">{r.label}</span>
          <div className="h-5">
            {/* The muted bar is the yardstick the others are measured against: an outline, not a fill. */}
            <div
              className="h-5 rounded-r-[4px]"
              style={{
                width: `${Math.max((r.value / max) * 100, 0.5)}%`,
                background: r.accent ? "var(--accent)" : r.muted ? "transparent" : "var(--neutral-series)",
                border: r.muted ? "1px solid var(--muted)" : undefined,
              }}
            />
          </div>
          <span className="tabular text-sm font-medium">{r.text}</span>
        </div>
      ))}
    </div>
  );
}

/** Progress toward a threshold; the track is a lighter step of the fill. */
export function Meter({ value, label }: { value: number; label: string }) {
  const width = Math.min(Math.max(value, 0), 1) * 100;
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={Number(value.toFixed(3))}
      aria-label={label}
      className="h-2.5 w-full rounded-full bg-accent-soft"
    >
      <div className="h-2.5 rounded-full bg-accent" style={{ width: `${width}%` }} />
    </div>
  );
}

const TONES = {
  good: ["border-good text-good-text", "✓"],
  critical: ["border-critical text-critical", "✗"],
  neutral: ["border-[var(--ring)] text-ink-2", "○"],
} as const;

/** Status badge: the colour never carries the meaning alone (icon + label). */
export function Badge({ tone, children }: { tone: keyof typeof TONES; children: ReactNode }) {
  const [classes, icon] = TONES[tone];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${classes}`}>
      <span aria-hidden>{icon}</span>
      {children}
    </span>
  );
}

export function PageHeader({ title, lede }: { title: string; lede: ReactNode }) {
  return (
    <header className="mb-12 border-b border-[var(--ring)] pb-10">
      <h1 className="display text-3xl font-medium sm:text-[2.75rem]">{title}</h1>
      <p className="mt-4 max-w-3xl text-ink-2">{lede}</p>
    </header>
  );
}

export function Callout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <aside className="rounded-xl border border-accent bg-surface p-5 text-sm sm:p-6">
      <p className="font-medium text-accent">{title}</p>
      <div className="mt-1 text-ink-2">{children}</div>
    </aside>
  );
}
