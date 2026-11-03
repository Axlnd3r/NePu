import type { Metadata } from "next";
import Link from "next/link";
import { meta, provenance } from "@/lib/data";
import "./globals.css";

export const metadata: Metadata = {
  title: "NEAR Capture Ledger",
  description:
    "Can NEAR Intents value capture outgrow token issuance? Every number traced to its data.",
};

const NAV = [
  ["/", "Overview"],
  ["/token/", "Token economics"],
  ["/intents/", "Intents & channels"],
  ["/valuation/", "Valuation Lab"],
  ["/developer/", "Developer"],
  ["/methodology/", "Methodology & data"],
] as const;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="antialiased">
      <body className="min-h-screen">
        <a href="#main" className="sr-only focus:not-sr-only">
          Skip to content
        </a>
        <header className="border-b border-[var(--ring)] bg-surface">
          <nav
            aria-label="Main"
            className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 sm:px-6"
          >
            <Link href="/" className="mr-2 font-semibold">
              NEAR Capture Ledger
            </Link>
            {NAV.slice(1).map(([href, label]) => (
              <Link key={href} href={href} className="text-sm text-ink-2 hover:text-ink">
                {label}
              </Link>
            ))}
          </nav>
        </header>
        <main id="main" className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
          {children}
        </main>
        <footer className="border-t border-[var(--ring)] bg-surface">
          <div className="mx-auto max-w-6xl space-y-1 px-4 py-6 text-xs text-muted sm:px-6">
            <p>
              Built {meta.built_at_utc} from <span className="font-mono">{meta.source}</span> at
              commit <span className="font-mono">{meta.git_commit.slice(0, 12)}</span>. Snapshot
              manifest sha256{" "}
              <span className="font-mono break-all">{provenance.manifest_sha256}</span>.
            </p>
            <p>
              Evidence, not advice: no price is predicted and no price target is given. Buybacks
              are not burns. Correlation is not causation.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
