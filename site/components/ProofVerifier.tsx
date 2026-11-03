"use client";

import { useCallback, useEffect, useState } from "react";

type Props = {
  network: string;
  contract: string;
  runId: string;
  rpcUrl: string;
  /** Hash recorded in data/proof.json when the proof was made. */
  recordedHash: string;
};

type Result =
  | { state: "checking" }
  | { state: "done"; local: string; onChain: string | null }
  | { state: "error"; message: string };

const MANIFEST_URL = `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/data/snapshot-manifest.json`;

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Calls the contract's view method `get(run_id)` over JSON-RPC. null = nothing committed. */
async function readOnChain(rpcUrl: string, contract: string, runId: string): Promise<string | null> {
  const reply = await fetch(rpcUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "query",
      params: {
        request_type: "call_function",
        finality: "final",
        account_id: contract,
        method_name: "get",
        args_base64: btoa(JSON.stringify({ run_id: runId })),
      },
    }),
  });
  if (!reply.ok) throw new Error(`RPC answered HTTP ${reply.status}`);
  const body = await reply.json();
  if (body.error) throw new Error(`RPC error: ${body.error.cause?.name ?? body.error.name}`);
  if (body.result.error) throw new Error(body.result.error);
  const text = new TextDecoder().decode(Uint8Array.from(body.result.result as number[]));
  return JSON.parse(text) as string | null;
}

export function ProofVerifier({ network, contract, runId, rpcUrl, recordedHash }: Props) {
  const [result, setResult] = useState<Result>({ state: "checking" });

  const verify = useCallback(async () => {
    setResult({ state: "checking" });
    try {
      const file = await fetch(MANIFEST_URL, { cache: "no-store" });
      if (!file.ok) throw new Error(`manifest answered HTTP ${file.status}`);
      const local = await sha256Hex(await file.arrayBuffer());
      const onChain = await readOnChain(rpcUrl, contract, runId);
      setResult({ state: "done", local, onChain });
    } catch (e) {
      setResult({ state: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }, [rpcUrl, contract, runId]);

  useEffect(() => {
    void verify();
  }, [verify]);

  let verdict: { icon: string; text: string; tone: string } = {
    icon: "○",
    text: "Checking…",
    tone: "text-ink-2",
  };
  if (result.state === "error") {
    verdict = { icon: "○", text: `Could not check: ${result.message}`, tone: "text-ink-2" };
  } else if (result.state === "done") {
    if (result.onChain === null) {
      verdict = { icon: "✗", text: `Nothing is committed on ${network} for this run id.`, tone: "text-critical" };
    } else if (result.local === result.onChain) {
      verdict = {
        icon: "✓",
        text: `Match: the manifest served by this site has exactly the hash committed on NEAR ${network}.`,
        tone: "text-good-text",
      };
    } else {
      verdict = {
        icon: "✗",
        text: `Does not match: this site's manifest differs from the hash committed on NEAR ${network}.`,
        tone: "text-critical",
      };
    }
  }

  const local = result.state === "done" ? result.local : "…";
  const onChain = result.state === "done" ? (result.onChain ?? "(nothing committed)") : "…";

  return (
    <div data-testid="proof-verifier">
      <p role="status" aria-live="polite" className={`text-sm font-medium ${verdict.tone}`} data-testid="proof-verdict">
        <span aria-hidden>{verdict.icon} </span>
        {verdict.text}
      </p>
      <dl className="mt-3 space-y-2 text-xs">
        <div>
          <dt className="text-muted">SHA-256 of snapshot-manifest.json, computed in your browser</dt>
          <dd className="break-all font-mono" data-testid="proof-local">{local}</dd>
        </div>
        <div>
          <dt className="text-muted">
            Hash returned by <span className="font-mono">{contract}.get(&quot;{runId}&quot;)</span> on NEAR {network}
          </dt>
          <dd className="break-all font-mono" data-testid="proof-onchain">{onChain}</dd>
        </div>
        <div>
          <dt className="text-muted">Hash recorded when the proof was made (data/proof.json)</dt>
          <dd className="break-all font-mono">{recordedHash}</dd>
        </div>
      </dl>
      <button
        type="button"
        onClick={() => void verify()}
        className="mt-3 rounded-md border border-[var(--ring)] px-3 py-1 text-sm"
      >
        Verify again
      </button>
    </div>
  );
}
