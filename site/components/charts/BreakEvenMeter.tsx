"use client";

import { useId, useState } from "react";
import { formatValue } from "./fmt";

type Props = {
  asOf: string;
  supply: number;
  price: number;
  burnPerDay: number;
  tauBuyback: number;
  tauRevenue: number;
  volume: number;
};

/** V* = max((i x S / 365 - burn) x P, 0) / tau  (docs/METHODOLOGY.md, sensitivity grid). */
export function breakEven(i: number, s: number, p: number, burn: number, tau: number): number {
  return Math.max((i * s) / 365 - burn, 0) * p / tau;
}

export function BreakEvenMeter(props: Props) {
  const [inflation, setInflation] = useState(0.025);
  const [basis, setBasis] = useState<"buyback" | "revenue">("buyback");
  const [priceMult, setPriceMult] = useState(1);
  const [tauMult, setTauMult] = useState(1);
  const ids = useId();

  const tau = (basis === "buyback" ? props.tauBuyback : props.tauRevenue) * tauMult;
  const vStar = breakEven(inflation, props.supply, props.price * priceMult, props.burnPerDay, tau);
  const share = props.volume / vStar;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <fieldset>
          <legend className="text-sm text-ink-2">Annual issuance</legend>
          <div className="mt-1 flex gap-2">
            {[0.025, 0.016].map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={inflation === v}
                onClick={() => setInflation(v)}
                className={`rounded-md border px-3 py-1 text-sm ${
                  inflation === v ? "border-accent bg-accent text-white" : "border-[var(--ring)]"
                }`}
              >
                {v === 0.025 ? "2.5% (today)" : "1.6% (HSP-029)"}
              </button>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="text-sm text-ink-2">Take rate basis</legend>
          <div className="mt-1 flex gap-2">
            {(["buyback", "revenue"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={basis === v}
                onClick={() => setBasis(v)}
                className={`rounded-md border px-3 py-1 text-sm ${
                  basis === v ? "border-accent bg-accent text-white" : "border-[var(--ring)]"
                }`}
              >
                {v === "buyback" ? "Buyback wallet" : "All revenue"}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="text-sm text-ink-2" htmlFor={`${ids}-price`}>
          NEAR price multiple: <span className="tabular text-ink">{priceMult.toFixed(1)}x</span>
          <input
            id={`${ids}-price`}
            type="range"
            min={0.5}
            max={2}
            step={0.1}
            value={priceMult}
            onChange={(e) => setPriceMult(Number(e.target.value))}
            className="mt-1 w-full accent-[var(--accent)]"
          />
        </label>
        <label className="text-sm text-ink-2" htmlFor={`${ids}-tau`}>
          Take rate multiple: <span className="tabular text-ink">{tauMult.toFixed(1)}x</span>
          <input
            id={`${ids}-tau`}
            type="range"
            min={0.5}
            max={2}
            step={0.1}
            value={tauMult}
            onChange={(e) => setTauMult(Number(e.target.value))}
            className="mt-1 w-full accent-[var(--accent)]"
          />
        </label>
      </div>

      <div className="rounded-lg bg-plane p-4">
        <p className="text-sm text-ink-2">Break-even Intents volume V*</p>
        <p className="tabular text-3xl font-semibold" data-testid="vstar" data-value={vStar}>
          {formatValue(vStar, "usd")}
          <span className="text-base font-normal text-ink-2"> per day</span>
        </p>
        <p className="mt-1 text-sm text-ink-2">
          Actual 30-day average: <span className="tabular">{formatValue(props.volume, "usd")}</span>{" "}
          per day, {share >= 1 ? "above" : `${(1 / share).toFixed(1)}x short of`} break-even (
          {(share * 100).toFixed(0)}% of V*).
        </p>
        <div
          className="mt-3 h-3 w-full rounded-full bg-accent-soft"
          role="meter"
          aria-label="Actual volume as a share of V*"
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={Number(Math.min(share, 1).toFixed(3))}
        >
          <div
            className="h-3 rounded-full bg-accent"
            style={{ width: `${Math.min(share, 1) * 100}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-muted">
          Inputs as of {props.asOf}: supply, price, 30-day burn and take rates from the data.
          Moving a slider is a sensitivity, not a forecast; no price is predicted.
        </p>
      </div>
    </div>
  );
}
