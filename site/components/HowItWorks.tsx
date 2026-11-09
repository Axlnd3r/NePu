"use client";

import { useState, type ReactNode } from "react";

export type Step = {
  key: string;
  title: string;
  short: string;
  body: ReactNode;
  command?: string;
  href?: string;
  link?: string;
};

/** The four steps from public data to an on-chain proof, one open at a time. */
export function HowItWorks({ steps }: { steps: Step[] }) {
  const [open, setOpen] = useState(0);
  const [copied, setCopied] = useState<string | null>(null);
  const step = steps[open];

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(text);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      setCopied(null);
    }
  };

  return (
    <div>
      <ol className="grid gap-2 sm:grid-cols-4" role="tablist" aria-label="How NePu works">
        {steps.map((s, i) => (
          <li key={s.key} className="flex">
            <button
              type="button"
              role="tab"
              id={`hiw-tab-${s.key}`}
              aria-selected={open === i}
              aria-controls={`hiw-panel-${s.key}`}
              onClick={() => setOpen(i)}
              className={`group w-full rounded-lg border p-4 text-left transition-colors ${
                open === i
                  ? "border-accent bg-accent-soft"
                  : "border-[var(--ring)] hover:border-accent"
              }`}
            >
              <span
                className={`tabular text-xs ${open === i ? "text-accent" : "text-muted"}`}
                aria-hidden
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="mt-1 block text-sm font-medium">{s.title}</span>
              <span className="mt-1 block text-xs text-ink-2">{s.short}</span>
            </button>
          </li>
        ))}
      </ol>
      <div
        role="tabpanel"
        id={`hiw-panel-${step.key}`}
        aria-labelledby={`hiw-tab-${step.key}`}
        className="mt-3 rounded-lg border border-[var(--ring)] bg-raised p-5 text-sm text-ink-2 sm:p-6"
      >
        <div className="max-w-3xl space-y-3">{step.body}</div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {step.command && (
            <button
              type="button"
              onClick={() => copy(step.command as string)}
              className="inline-flex items-center gap-2 rounded-md border border-[var(--ring)] px-3 py-1.5 font-mono text-xs text-ink hover:border-accent"
              aria-label={`Copy the command ${step.command}`}
            >
              <span aria-hidden className="text-accent">
                $
              </span>
              {step.command}
              <span className="text-muted">{copied === step.command ? "copied" : "copy"}</span>
            </button>
          )}
          {step.href && (
            <a href={step.href} className="text-sm text-ink hover:text-accent">
              {step.link} <span aria-hidden>→</span>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
