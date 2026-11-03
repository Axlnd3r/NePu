import type { ReactNode } from "react";
import { source } from "@/lib/data";

type Props = {
  id: string;
  /** The number as shown. */
  children: ReactNode;
  /** How it is computed, in words. */
  formula: string;
  tables: string[];
  asOf?: string;
  className?: string;
};

/** A number that opens its own evidence: formula, input files, ranges and hashes.
 *
 * It sits inside headings and paragraphs, so the popover uses phrasing content only (spans):
 * a div or p there is invalid HTML, which the browser re-parents and React then fails to hydrate.
 */
export function Evidence({ id, children, formula, tables, asOf, className = "" }: Props) {
  const pop = `evidence-${id}`;
  return (
    <>
      <button
        type="button"
        popoverTarget={pop}
        className={`cursor-help underline decoration-dotted decoration-1 underline-offset-4 ${className}`}
        aria-label="Show where this number comes from"
      >
        {children}
      </button>
      <span id={pop} popover="auto" className="text-left text-sm font-normal tracking-normal">
        <span className="block font-semibold">Where this number comes from</span>
        <span className="mt-2 block">{formula}</span>
        {asOf && <span className="mt-1 block text-ink-2">As of {asOf}.</span>}
        <span className="mt-3 block space-y-1 text-xs text-ink-2">
          {tables.map((t) => {
            const s = source(t);
            return (
              <span key={t} className="block break-words">
                <span className="font-mono">{s.path}</span>
                {s.date_range ? ` · ${s.date_range[0]} to ${s.date_range[1]}` : ""} · sha256{" "}
                <span className="font-mono">{s.sha256_8}</span>
              </span>
            );
          })}
        </span>
        <span className="mt-3 block text-xs text-muted">
          Rebuild offline with <code>make build</code>; hashes are checked by{" "}
          <code>make verify</code>.
        </span>
      </span>
    </>
  );
}
