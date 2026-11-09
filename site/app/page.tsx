import { BarRows, Badge, MarkerList, Meter } from "@/components/Bits";
import { ChartCard } from "@/components/ChartCard";
import { BreakEvenMeter } from "@/components/charts/BreakEvenMeter";
import { HowItWorks } from "@/components/HowItWorks";
import { NearMark } from "@/components/NearMark";
import { PathToYes } from "@/components/PathToYes";
import { Prereg, type PreregData } from "@/components/Prereg";
import { TimeChart } from "@/components/charts/TimeChart";
import { Evidence } from "@/components/Evidence";
import { coverage, distribution, markersBetween, prereg, provenance, summary, valuation } from "@/lib/data";
import { pct, ratio, times, usd } from "@/lib/format";

const CORE = ["supply_daily", "fee_wallet_inflows_daily", "price_daily", "defillama_intents_daily"];
const REPO = "https://github.com/Axlnd3r/NePu";

export default function Overview() {
  const { hero, ledger, levers, conditions, governance, definitions, invariance } = summary;
  const hsp = governance.hsp029;
  const proof = provenance.proof;
  const months = provenance.reconciliation.months.length;
  const own = definitions.rows.filter((r) => !("quoted" in r));
  const quoted = definitions.rows.find((r) => "quoted" in r);
  const start = valuation.start;
  const steps = levers.steps;
  const explorerShares = distribution.scope.explorer_share_of_defillama_volume_by_month;
  const lastExplorer = explorerShares[explorerShares.length - 1];

  const series = coverage.series.filter((r) => r.cr_float_7 !== null);
  const cr = series.map((r) => ({
    date: r.date,
    cr_float_7: r.cr_float_7,
    cr_float_30: r.cr_float_30,
    cr_float_90: r.cr_float_90,
  }));
  const cr30 = series.filter((r) => r.cr_float_30 !== null).map((r) => r.cr_float_30 as number);
  const maxCr30 = Math.max(...cr30);
  const markers = markersBetween(series[0].date, series[series.length - 1].date);

  const per10k = ledger.per_10k_volume;
  const money = (v: number) => `$${v.toFixed(2)}`;

  return (
    <div className="space-y-10">
      <section aria-labelledby="hero" className="pb-6 text-center sm:pb-10">
        <NearMark id="hero-mark" className="mx-auto h-[min(36vh,18rem)] w-auto" />
        <p className="eyebrow mt-10 sm:mt-14">Can NEAR Intents value capture outgrow token issuance?</p>
        <h1
          id="hero"
          className="display mx-auto mt-4 max-w-3xl text-[2rem] font-medium sm:text-5xl lg:text-[3.5rem]"
        >
          For every $1 of new NEAR issued,{" "}
          <Evidence
            id="hero"
            formula="CR_float in USD over 30 days: (NEAR received by the buyback wallet + NEAR burnt as gas), each day valued at that day's price, divided by gross issuance valued the same way."
            tables={["supply_daily", "fee_wallet_inflows_daily", "price_daily"]}
            asOf={hero.date}
            className="text-accent"
          >
            {Math.round(hero.cr_float_usd_30 * 100)} cents
          </Evidence>{" "}
          come back as buybacks or gas burn.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-ink-2">
          30 days to {hero.date}. In NEAR units the same ratio is {ratio(hero.cr_float_30)}.{" "}
          {summary.this_week.sentence}. Break-even means 100 cents.
        </p>
        <a
          href="https://github.com/Axlnd3r/NePu/blob/main/THESIS.md"
          className="mt-6 inline-block text-sm text-ink hover:text-accent"
        >
          Read the thesis <span aria-hidden>→</span>
        </a>

        <div className="mt-14 grid gap-4 text-left sm:grid-cols-3">
          <div className="rounded-xl border border-[var(--ring)] p-5 sm:p-6">
            <p className="text-sm text-ink-2">Volume needed to break even</p>
            <p className="display mt-3 text-3xl font-medium text-accent">
              <Evidence
                id="multiple"
                formula="V* / V0: break-even daily Intents volume (buyback take rate, 2.5% issuance, current price and burn) over the 30-day average volume."
                tables={CORE}
                asOf={levers.as_of}
              >
                {times(steps[0].volume_multiple, 1)}
              </Evidence>
            </p>
            <p className="mt-1 text-xs text-muted">
              {usd(steps[0].v_star_usd_per_day)} per day against {usd(levers.volume_usd_per_day)} today
            </p>
          </div>
          <div className="rounded-xl border border-[var(--ring)] p-5 sm:p-6">
            <p className="text-sm text-ink-2">Protocol revenue that reaches the buyback wallet</p>
            <p className="display mt-3 text-3xl font-medium text-accent">
              <Evidence
                id="routing"
                formula="Buyback wallet inflow / revenue reaching all NEAR revenue wallets (internal transfers netted), both valued at daily prices, 30 days."
                tables={["fee_wallet_inflows_daily", "price_daily"]}
                asOf={ledger.end}
              >
                {pct(ledger.kept.buyback_of_onchain)}
              </Evidence>
            </p>
            <p className="mt-1 text-xs text-muted">The rest is held in collection wallets that have not paid out</p>
          </div>
          <div className="rounded-xl border border-[var(--ring)] p-5 sm:p-6">
            <p className="text-sm text-ink-2">Intents volume our channel data covers</p>
            <p className="display mt-3 text-3xl font-medium text-accent">
              <Evidence
                id="coverage"
                formula="Volume in the Intents Explorer (1Click transactions only) / DefiLlama Intents volume, same days."
                tables={["explorer_1click_daily", "defillama_intents_daily"]}
                asOf={lastExplorer.period}
              >
                {pct(lastExplorer.explorer_share_of_defillama_volume)}
              </Evidence>
            </p>
            <p className="mt-1 text-xs text-muted">
              In {lastExplorer.period}, down from {pct(explorerShares[0].explorer_share_of_defillama_volume)} in{" "}
              {explorerShares[0].period}: channel claims carry this scope
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="what" className="rounded-xl border border-[var(--ring)] bg-surface p-5 sm:p-8">
        <p className="eyebrow">What NePu is</p>
        <h2 id="what" className="display mt-2 max-w-3xl text-2xl font-medium sm:text-3xl">
          A ledger that checks one claim about NEAR against the chain, and lets you check it back.
        </h2>
        <p className="mt-3 max-w-3xl text-ink-2">
          NEAR Intents routes cross-chain swaps and part of its fees buys NEAR, while new NEAR is
          issued every epoch. NePu measures whether that capture can outgrow issuance: it pulls the
          numbers from NEAR&apos;s own chain and three public APIs, reconciles them, publishes the
          evidence for and against, and commits a hash of its inputs to NEAR so anyone can tell the
          published numbers came from these files. It predicts no price.
        </p>
        <div className="mt-6">
          <HowItWorks
            steps={[
              {
                key: "pull",
                title: "Pull",
                short: "NEAR BigQuery, Intents Explorer, DefiLlama, CoinGecko",
                body: (
                  <>
                    <p>
                      Every BigQuery query filters on <code>block_date</code>, is dry-run first and
                      runs under a byte cap. Revenue wallets are read as NEAR transfers from{" "}
                      <code>intents.near</code>; 1Click transactions come from the Intents Explorer
                      with a partner key.
                    </p>
                    <p>Each query or request is shown under its chart (open “Query and model”).</p>
                  </>
                ),
                href: `${REPO}/blob/main/DATA_AUDIT.md`,
                link: "How each source was checked",
              },
              {
                key: "freeze",
                title: "Freeze and hash",
                short: "Committed snapshot, SHA-256 per file",
                body: (
                  <p>
                    The inputs are frozen in <code>data/snapshot/</code> with a manifest holding each
                    file&apos;s hash, query text, date range and pull time. The whole dashboard and
                    the thesis rebuild from it offline, without credentials.
                  </p>
                ),
                command: "make all",
                href: `${REPO}#quickstart-offline`,
                link: "Rebuild it yourself",
              },
              {
                key: "measure",
                title: "Measure and reconcile",
                short: "Coverage ratio, break-even, independent audit",
                body: (
                  <p>
                    Coverage, break-even and every published number are recomputed by a second,
                    independent implementation in the tests. On-chain revenue is reconciled with
                    DefiLlama month by month: {months} of {months} complete months within tolerance.
                  </p>
                ),
                command: "make verify",
                href: `${REPO}/blob/main/THESIS.md`,
                link: "Read the thesis, evidence against included",
              },
              {
                key: "prove",
                title: "Prove on NEAR",
                short: `Manifest hash on NEAR ${proof.network}`,
                body: (
                  <p>
                    The SHA-256 of the manifest is written to the contract{" "}
                    <code>{proof.contract}</code> on NEAR {proof.network} (block{" "}
                    {proof.block_height?.toLocaleString("en-US")}) and stamped with OpenTimestamps.
                    It shows the hash existed no later than that block; it does not show the data is
                    correct.
                  </p>
                ),
                href: "methodology/#proof",
                link: "Verify it in your browser",
              },
            ]}
          />
        </div>
        <div className="mt-8 grid items-center gap-6 border-t border-[var(--ring)] pt-8 md:grid-cols-[minmax(0,22rem)_1fr]">
          <video
            controls
            preload="none"
            poster="media/nepu-demo-cover.png"
            className="w-full rounded-lg border border-[var(--ring)] bg-raised"
          >
            <source src="media/nepu-demo.mp4" type="video/mp4" />
          </video>
          <div className="text-sm text-ink-2">
            <p className="eyebrow">Demo</p>
            <p className="mt-2 text-base text-ink">
              The whole argument in under a minute: the gap, what closes it, and the proof.
            </p>
            <p className="mt-2">
              Every figure on screen is read from the same JSON files as this dashboard. The video is
              rendered from code in <code>video/</code>, so it rebuilds with the data.
            </p>
          </div>
        </div>
      </section>

      <ChartCard
        id="ledger"
        title="Where $10,000 of Intents volume goes"
        sentence={
          <>
            In the 30 days to {ledger.end}, every $10,000 of Intents volume produced{" "}
            {money(per10k.fees)} of fees, {money(per10k.revenue)} of protocol revenue and{" "}
            {money(per10k.buyback_wallet)} that reached the buyback wallet, while new NEAR worth{" "}
            {money(per10k.issuance)} was issued.
          </>
        }
        tables={CORE}
        model="ledger.waterfall (src/capture/models/ledger.py)"
        table={{
          columns: ["Step", "USD, 30 days", "Per $10,000 of volume"],
          rows: Object.entries(ledger.usd).map(([k, v]) => [
            k,
            usd(v, 2),
            money(per10k[k as keyof typeof per10k]),
          ]),
        }}
      >
        <BarRows
          max={per10k.issuance}
          rows={[
            { label: "Fees", value: per10k.fees, text: money(per10k.fees) },
            { label: "Protocol revenue", value: per10k.revenue, text: money(per10k.revenue) },
            { label: "Reached NEAR wallets", value: per10k.onchain_revenue, text: money(per10k.onchain_revenue) },
            { label: "Reached buyback wallet", value: per10k.buyback_wallet, text: money(per10k.buyback_wallet), accent: true },
            { label: "Gas burn (chain-wide)", value: per10k.burn, text: money(per10k.burn), accent: true },
            { label: "New NEAR issued", value: per10k.issuance, text: money(per10k.issuance), muted: true },
          ]}
        />
        <p className="mt-3 text-xs text-muted">
          Kept at each step: fees {pct(ledger.kept.fees_of_volume, 2)} of volume, revenue{" "}
          {pct(ledger.kept.revenue_of_fees)} of fees, on-chain {pct(ledger.kept.onchain_of_revenue)} of
          DefiLlama revenue, buyback wallet {pct(ledger.kept.buyback_of_onchain)} of on-chain revenue.
          Gold bars are what counts in CR; the outlined bar is what they are measured against.
        </p>
      </ChartCard>

      <ChartCard
        id="levers"
        title="What closes the gap to break-even"
        sentence={
          <>
            Volume must grow {times(steps[0].volume_multiple)} to cover issuance today. The HSP-029
            issuance cut would close {times(steps[1].closes_by as number)} of that and sending all
            revenue to buybacks another {times(steps[2].closes_by as number)}, which still leaves{" "}
            {times(steps[2].volume_multiple)} for volume growth.
          </>
        }
        tables={CORE}
        model="ledger.lever_bridge (src/capture/models/ledger.py)"
      >
        <BarRows
          max={steps[0].volume_multiple}
          rows={[
            { label: "Today (2.5%, buyback wallet)", value: steps[0].volume_multiple, text: times(steps[0].volume_multiple), accent: true },
            { label: "+ issuance cut to 1.6%", value: steps[1].volume_multiple, text: times(steps[1].volume_multiple), accent: true },
            { label: "+ all revenue to buybacks", value: steps[2].volume_multiple, text: times(steps[2].volume_multiple), accent: true },
          ]}
        />
        <p className="mt-3 text-xs text-muted">{levers.note}</p>
        {hsp && (
          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-[var(--ring)] bg-raised p-4 text-sm">
            <Badge tone="neutral">HSP-029 on chain: {hsp.status}</Badge>
            <span className="text-ink-2">
              Read from <code>{hsp.contract}</code> at block {hsp.read_at_block.toLocaleString("en-US")}:{" "}
              {pct(hsp.top_option_share, 2)} of the veNEAR cast went to one option (turnout{" "}
              {pct(hsp.turnout)}); the timelock ends {hsp.timelock_end_utc.replace("T", " ").replace("Z", " UTC")}.
              Validators still have to adopt the ramp, so the cut stays a scenario.
            </span>
          </div>
        )}
      </ChartCard>

      <ChartCard
        id="path"
        title="Path to yes: move the levers yourself"
        sentence={
          <>
            Today the buyback wallet receives {pct(1 / steps[0].volume_multiple)} of what break-even
            needs. Push revenue, routing and issuance and see when buybacks would cover new NEAR. The
            multiple does not depend on how Intents volume is counted: at half or twice
            DefiLlama&apos;s volume it stays {times(invariance.rows[0].volume_multiple, 1)}.
          </>
        }
        tables={CORE}
        model="ledger.lever_bridge and ledger.volume_scale_invariance (same formula, in the browser)"
        references={hsp ? ["hsp029_vote.json"] : []}
      >
        <PathToYes
          asOf={valuation.start.as_of}
          supply={start.total_supply_near}
          price={start.near_usd}
          burnPerDay={start.burnt_near_per_day}
          volume={start.volume_usd_per_day}
          tauBuyback={start.tau_buyback_30}
          tauRevenue={start.tau_revenue_30}
          inflationNow={steps[0].inflation}
          inflationTarget={steps[1].inflation}
          hsp029Status={hsp?.status ?? null}
        />
      </ChartCard>

      <ChartCard
        id="definitions"
        title="Why public estimates differ"
        sentence={
          <>
            Depending on the definition, coverage of issuance runs from{" "}
            {pct(Math.min(...own.map((r) => r.value)))} (burn only) to{" "}
            {pct(Math.max(...definitions.rows.map((r) => r.value)))}. Most of the spread is
            definition, not data: counting all three revenue wallets instead of the buyback wallet
            alone moves the 30-day figure from {pct(own[0].value)} to{" "}
            {pct(own.find((r) => r.id === "all_wallets")!.value)}.
          </>
        }
        tables={CORE}
        model="ledger.definition_table (src/capture/models/ledger.py)"
        references={quoted ? ["revenue_near_org.html"] : []}
        table={{
          columns: ["Definition", "Days", "Unit", "Coverage"],
          rows: definitions.rows.map((r) => [
            r.label,
            `${r.start} to ${r.end}`,
            r.unit === "usd" ? "USD at daily prices" : "NEAR",
            pct(r.value),
          ]),
        }}
      >
        <BarRows
          max={Math.max(...definitions.rows.map((r) => r.value))}
          rows={definitions.rows.map((r) => ({
            label: r.label,
            value: r.value,
            text: pct(r.value),
            accent: r.id === "headline",
            muted: "quoted" in r,
          }))}
        />
        <p className="mt-3 text-xs text-muted">
          {definitions.note} The gold bar is the headline&apos;s basis; the outlined bar is quoted, not
          measured.
          {quoted?.official_revenue_near && quoted.our_revenue_near && quoted.official_emissions_near && quoted.our_issuance_near && (
            <>
              {" "}
              On the same days the official emissions match our gross issuance within{" "}
              {pct(Math.abs(quoted.official_emissions_near / quoted.our_issuance_near - 1), 1)}, while
              its revenue is {pct(quoted.official_revenue_near / quoted.our_revenue_near - 1, 0)}{" "}
              above what the three revenue wallets received; its method is not documented, so the
              gap is shown, not explained.
            </>
          )}
        </p>
      </ChartCard>

      <ChartCard
        id="cr-trend"
        title="Coverage ratio over 7, 30 and 90 days"
        sentence={
          <>
            CR_float over 30 days was {ratio(hero.cr_float_30)} on {hero.date}; its highest value since
            the buyback wallet appeared is {ratio(maxCr30)}, so buybacks and burn have not yet covered
            issuance in any 30-day window measured.
          </>
        }
        tables={["supply_daily", "fee_wallet_inflows_daily"]}
        model="coverage.cr_float (src/capture/models/coverage.py)"
        table={{
          columns: ["Date", "CR 7d", "CR 30d", "CR 90d"],
          rows: cr.slice(-30).map((r) => [
            r.date,
            r.cr_float_7?.toFixed(3) ?? null,
            r.cr_float_30?.toFixed(3) ?? null,
            r.cr_float_90?.toFixed(3) ?? null,
          ]),
        }}
      >
        <TimeChart
          ariaLabel="Coverage ratio over 7, 30 and 90 days"
          data={cr}
          format="ratio"
          markers={markers}
          series={[
            { key: "cr_float_7", label: "7 days", color: "var(--cat-2)", width: 1.5 },
            { key: "cr_float_30", label: "30 days", color: "var(--cat-1)" },
            { key: "cr_float_90", label: "90 days", color: "var(--cat-3)" },
          ]}
        />
        <MarkerList markers={markers} />
      </ChartCard>

      <ChartCard
        id="meter"
        title="Break-even meter"
        sentence={
          <>
            At today&apos;s inputs, break-even volume is {usd(steps[0].v_star_usd_per_day)} a day on the
            buyback basis. Change issuance, take rate and the price assumption to see how V* moves.
          </>
        }
        tables={CORE}
        model="valuation.breakeven_volume (same formula, run in the browser)"
      >
        <BreakEvenMeter
          asOf={start.as_of}
          supply={start.total_supply_near}
          price={start.near_usd}
          burnPerDay={start.burnt_near_per_day}
          tauBuyback={start.tau_buyback_30}
          tauRevenue={start.tau_revenue_30}
          volume={start.volume_usd_per_day}
        />
      </ChartCard>

      <section aria-labelledby="mind" className="rounded-xl border border-[var(--ring)] bg-surface p-5 sm:p-8">
        <h2 id="mind" className="text-lg font-medium tracking-tight">What would change our mind</h2>
        <p className="mt-1 text-sm text-ink-2">
          Three numeric conditions, re-evaluated on every build. The first two would support the
          thesis that capture can outgrow issuance; they move independently. The third would withdraw
          the headline until explained.
        </p>
        <ul className="mt-4 space-y-5">
          {conditions.map((c) => (
            <li key={c.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">{c.text}</p>
                {c.effect === "support" ? (
                  <Badge tone={c.met ? "good" : "neutral"}>{c.met ? "met" : "not met"}</Badge>
                ) : (
                  <Badge tone={c.met ? "critical" : "good"}>
                    {c.met ? "triggered: headline withdrawn" : "not triggered"}
                  </Badge>
                )}
              </div>
              <p className="tabular mt-1 text-xs text-ink-2">
                Now {formatCondition(c.value, c.id)} against {formatCondition(c.threshold, c.id)} (
                {pct(c.progress, 0)} of the way)
              </p>
              <div className="mt-2">
                <Meter value={c.progress} label={c.text} />
              </div>
            </li>
          ))}
        </ul>
      </section>

      <Prereg data={prereg as unknown as PreregData} />
    </div>
  );
}

function formatCondition(v: number, id: string): string {
  if (id === "volume") return `${usd(v)}/day`;
  return pct(v);
}
