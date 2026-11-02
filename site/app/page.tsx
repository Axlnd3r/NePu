// meta.json is written by `capture build` (make build) before `next build`.
import meta from "../public/data/meta.json";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">NEAR Capture Ledger</h1>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">
        Can NEAR Intents value capture outgrow token issuance?
      </p>
      <section className="mt-10">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">Build</h2>
        <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 font-mono text-sm">
          <dt>built_at_utc</dt>
          <dd>{meta.built_at_utc}</dd>
          <dt>git_commit</dt>
          <dd className="break-all">{meta.git_commit}</dd>
          <dt>source</dt>
          <dd>{meta.source}</dd>
        </dl>
      </section>
    </main>
  );
}
