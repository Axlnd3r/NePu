"use client";

import { useId, useState } from "react";
import { formatValue } from "./charts/fmt";

type Props = {
  asOf: string;
  supply: number;
  price: number;
  burnPerDay: number;
  volume: number;
  tauBuyback: number;
  tauRevenue: number;
  inflationNow: number;
  inflationTarget: number;
  hsp029Status: string | null;
};

/** Revenue reaching the buyback wallet over net issuance, both in USD per day (1 = break-even).
 *  Same inputs and formula as ledger.lever_bridge: at the defaults it is V0 / V*, and the revenue
 *  growth still needed is its inverse. */
export function progressToBreakEven(p: {
  supply: number;
  price: number;
  burnPerDay: number;
  buybackUsdPerDay: number;
  inflation: number;
}): number {
  const netIssuanceUsd = Math.max((p.inflation * p.supply) / 365 - p.burnPerDay, 0) * p.price;
  return netIssuanceUsd === 0 ? Infinity : p.buybackUsdPerDay / netIssuanceUsd;
}

export function PathToYes(props: Props) {
  const ids = useId();
  const todayShare = props.tauBuyback / props.tauRevenue; // share of revenue reaching buybacks
  const [growth, setGrowth] = useState(1);
  const [share, setShare] = useState(todayShare);
  const [hsp, setHsp] = useState(false);
  const [priceMult, setPriceMult] = useState(1);

  const revenueUsd = props.tauRevenue * props.volume; // protocol revenue per day today
  const buybackUsd = revenueUsd * share * growth;
  const inflation = hsp ? props.inflationTarget : props.inflationNow;
  const progress = progressToBreakEven({
    supply: props.supply,
    price: props.price * priceMult,
    burnPerDay: props.burnPerDay,
    buybackUsdPerDay: buybackUsd,
    inflation,
  });
  const reached = progress >= 1;
  const stillNeeded = 1 / progress;

  const reset = () => {
    setGrowth(1);
    setShare(todayShare);
    setHsp(false);
    setPriceMult(1);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
      <div className="space-y-5">
        <label className="block text-sm text-ink-2" htmlFor={`${ids}-growth`}>
          Growth in protocol revenue: <span className="tabular text-ink">{growth.toFixed(1)}x</span>
          <input
            id={`${ids}-growth`}
            data-testid="ptys-growth"
            type="range"
            min={1}
            max={10}
            step={0.1}
            value={growth}
            onChange={(e) => setGrowth(Number(e.target.value))}
            className="mt-1 w-full accent-[var(--accent)]"
          />
          <span className="text-xs text-muted">
            More volume or a higher take rate: the same lever, since the multiple does not depend on
            how volume is counted.
          </span>
        </label>
        <label className="block text-sm text-ink-2" htmlFor={`${ids}-share`}>
          Share of protocol revenue sent to the buyback wallet:{" "}
          <span className="tabular text-ink">{(share * 100).toFixed(0)}%</span>
          <input
            id={`${ids}-share`}
            data-testid="ptys-share"
            type="range"
            min={Math.floor(todayShare * 100) / 100}
            max={1}
            step={0.01}
            value={share}
            onChange={(e) => setShare(Number(e.target.value))}
            className="mt-1 w-full accent-[var(--accent)]"
          />
          <span className="text-xs text-muted">
            Today {(todayShare * 100).toFixed(1)}% (buyback wallet over all protocol revenue); the
            rest waits in collection wallets.
          </span>
        </label>
        <fieldset>
          <legend className="text-sm text-ink-2">Annual issuance</legend>
          <div className="mt-1 flex flex-wrap gap-2">
            {[false, true].map((v) => (
              <button
                key={String(v)}
                type="button"
                data-testid={v ? "ptys-hsp" : "ptys-now"}
                aria-pressed={hsp === v}
                onClick={() => setHsp(v)}
                className={`rounded-md border px-3 py-1 text-sm ${
                  hsp === v ? "border-accent bg-accent text-on-accent" : "border-[var(--ring)]"
                }`}
              >
                {v
                  ? `${(props.inflationTarget * 100).toFixed(1)}% (HSP-029)`
                  : `${(props.inflationNow * 100).toFixed(1)}% (today)`}
              </button>
            ))}
          </div>
          {props.hsp029Status && (
            <p className="mt-1 text-xs text-muted">
              HSP-029 on chain: status <span className="font-mono">{props.hsp029Status}</span>; the
              ramp still needs validators, so this is a scenario.
            </p>
          )}
        </fieldset>
        <label className="block text-sm text-ink-2" htmlFor={`${ids}-price`}>
          NEAR price multiple (a sensitivity, not a forecast):{" "}
          <span className="tabular text-ink">{priceMult.toFixed(1)}x</span>
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
        <button
          type="button"
          onClick={reset}
          className="rounded-md border border-[var(--ring)] px-3 py-1 text-sm text-ink-2 hover:text-accent"
        >
          Reset to the measured state
        </button>
      </div>

      <div
        className={`rounded-lg border p-5 transition-colors sm:p-6 ${
          reached ? "border-accent bg-accent-soft" : "border-[var(--ring)] bg-raised"
        }`}
        aria-live="polite"
      >
        <p className="text-sm text-ink-2">Buybacks against new NEAR, net of burn</p>
        <p
          className="display mt-2 text-5xl font-medium text-accent"
          data-testid="ptys-progress"
          data-value={progress}
        >
          {Number.isFinite(progress) ? `${(progress * 100).toFixed(progress < 0.1 ? 1 : 0)}%` : "∞"}
          <span className="ml-2 text-base font-normal text-ink-2">of break-even</span>
        </p>
        <div
          className="mt-4 h-3 w-full rounded-full bg-accent-soft"
          role="meter"
          aria-label="Progress to break-even"
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={Number(Math.min(progress, 1).toFixed(3))}
        >
          <div
            className="h-3 rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${Math.min(progress, 1) * 100}%` }}
          />
        </div>
        <p className="mt-4 text-sm" data-testid="ptys-needed" data-value={stillNeeded}>
          {reached ? (
            <span className="font-medium text-accent">
              Break-even reached at these settings: buybacks would cover net issuance.
            </span>
          ) : (
            <>
              Revenue would still have to grow{" "}
              <span className="tabular font-medium text-ink">{stillNeeded.toFixed(2)}x</span> more.
            </>
          )}
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-xs text-ink-2">
          <div>
            <dt>To the buyback wallet</dt>
            <dd className="tabular text-ink">{formatValue(buybackUsd, "usd")}/day</dd>
          </div>
          <div>
            <dt>New NEAR net of burn</dt>
            <dd className="tabular text-ink">
              {formatValue(buybackUsd / progress, "usd")}/day
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-muted">
          Inputs as of {props.asOf} from the data: 30-day revenue, supply, burn and price. The
          dashboard moves levers; it does not predict where they go.
        </p>
      </div>
    </div>
  );
}
