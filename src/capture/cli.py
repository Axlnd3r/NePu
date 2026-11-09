"""Command-line entry point: `capture <command>`."""

from __future__ import annotations

import shutil
import subprocess
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import httpx
import typer

from capture import build as build_mod
from capture import config
from capture import proof as proof_mod
from capture import snapshot as snapshot_mod
from capture.extract.run import run_extract
from capture.manifest import verify_manifest as verify_manifest_dir

app = typer.Typer(no_args_is_help=True, add_completion=False)


class Source(StrEnum):
    snapshot = "snapshot"
    live = "live"


def _gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB"


@app.command()
def extract(
    table: Annotated[
        list[str] | None,
        typer.Option("--table", "-t", help="Table to pull (repeatable). Default: all."),
    ] = None,
    start: Annotated[str | None, typer.Option(help="Override window start (YYYY-MM-DD).")] = None,
    end: Annotated[str | None, typer.Option(help="Override window end (YYYY-MM-DD).")] = None,
    dry_run: Annotated[
        bool, typer.Option(help="Only estimate BigQuery bytes; pull nothing.")
    ] = False,
) -> None:
    """Pull fresh data into data/live/ (needs .env credentials). Incremental by date."""
    tables = table or list(config.ALL_TABLES)
    unknown = sorted(set(tables) - set(config.ALL_TABLES))
    if unknown:
        typer.echo(
            f"unknown table(s): {', '.join(unknown)}; choose from {', '.join(config.ALL_TABLES)}",
            err=True,
        )
        raise typer.Exit(2)
    results = run_extract(
        tables,
        config.load_settings(),
        config.DATA_LIVE,
        start=date.fromisoformat(start) if start else None,
        end=date.fromisoformat(end) if end else None,
        dry_run_only=dry_run,
    )
    for r in results:
        span = f"{r.covered[0]}..{r.covered[1]}" if r.covered else "-"
        typer.echo(
            f"{r.name:28} {r.status:10} rows={r.rows_total:>9} (+{r.rows_added}) {span} "
            f"est={_gb(r.estimated_bytes)} billed={_gb(r.billed_bytes)} {r.note}"
        )
    typer.echo(f"BigQuery billed this run: {_gb(sum(r.billed_bytes for r in results))}")


@app.command()
def snapshot(
    freeze: Annotated[
        str, typer.Option(help="Last block_date to keep (YYYY-MM-DD), a complete day.")
    ],
) -> None:
    """Copy data/live into data/snapshot (rows up to --freeze) with a new manifest."""
    entries = snapshot_mod.freeze(date.fromisoformat(freeze))
    for e in entries:
        dr = f"{e.date_range[0]}..{e.date_range[1]}" if e.date_range else "-"
        typer.echo(f"{e.path:36} rows={e.rows:>9} {dr}")
    typer.echo(f"snapshot written: {len(entries)} files, manifest data/snapshot/manifest.json")


@app.command()
def build(
    source: Annotated[Source, typer.Option(help="Data directory to build from.")] = Source.snapshot,
) -> None:
    """Rebuild every metric from data/<source>/ into site/public/data/."""
    for out in build_mod.build(source.value):
        typer.echo(f"wrote {out.relative_to(build_mod.ROOT).as_posix()}")


@app.command("verify-manifest")
def verify_manifest(
    data_dir: Annotated[Path, typer.Argument(help="Directory holding manifest.json.")] = Path(
        "data/snapshot"
    ),
) -> None:
    """Recompute SHA-256 and row counts against manifest.json."""
    problems = verify_manifest_dir(data_dir)
    for p in problems:
        typer.echo(f"MISMATCH {p}", err=True)
    if problems:
        raise typer.Exit(1)
    typer.echo(f"{data_dir.as_posix()}/manifest.json: OK")


reference_app = typer.Typer(
    help="Reference data read from NEAR mainnet into data/reference/ (with its manifest).",
    no_args_is_help=True,
)
app.add_typer(reference_app, name="reference")


@reference_app.command("hsp029")
def reference_hsp029() -> None:
    """Read the HSP-029 vote from vote.dao (one keyless view call) into data/reference/."""
    import json

    from capture import manifest as mf
    from capture.extract import common, governance

    out = build_mod.REFERENCE / "hsp029_vote.json"
    record = governance.fetch_proposal()
    out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    entry = mf.make_entry(
        build_mod.REFERENCE,
        out,
        source=(
            f"near rpc {governance.RPC_URL} call_function {governance.CONTRACT} get_proposal "
            f"proposal_id={governance.HSP029_ID} (finality final, block {record['block_height']})"
        ),
        pulled_at_utc=common.utc_now_iso(),
    )
    mf.upsert_entries(build_mod.REFERENCE, [entry])
    summary = governance.summarize(record)
    typer.echo(f"wrote {out.relative_to(build_mod.ROOT).as_posix()}")
    typer.echo(
        f"status {summary['status']}, top option {summary['top_option_share']:.4%}, "
        f"turnout {summary['turnout']:.2%}, timelock ends {summary['timelock_end_utc']}"
    )


@reference_app.command("official")
def reference_official() -> None:
    """Save the revenue.near.org page (an 'illustrative' series) into data/reference/."""
    from capture import manifest as mf
    from capture.extract import common, official

    out = build_mod.REFERENCE / "revenue_near_org.html"
    out.write_bytes(official.fetch())
    rows = official.revenue_emissions(out.read_text(encoding="utf-8"))
    entry = mf.make_entry(
        build_mod.REFERENCE,
        out,
        source=f"{official.URL} (page as served; embedded series absoluteRevEmissions)",
        pulled_at_utc=common.utc_now_iso(),
        date_range=(rows[0]["date"], rows[-1]["date"]),
    )
    mf.upsert_entries(build_mod.REFERENCE, [entry])
    last = rows[-1]
    typer.echo(f"wrote {out.relative_to(build_mod.ROOT).as_posix()}: {len(rows)} days")
    typer.echo(f"{last['date']}: revenue / emissions since 1 January = {last['revenue_share']:.4f}")


@reference_app.command("buyback-flows")
def reference_buyback_flows() -> None:
    """Every balance change of the buyback wallet from NearBlocks (keyless, ~7 minutes)."""
    import json

    from capture import manifest as mf
    from capture.extract import common, nearblocks
    from capture.models import coverage

    out = build_mod.REFERENCE / "buyback_wallet_activities.json"
    rows = nearblocks.fetch_activities(
        coverage.BUYBACK_WALLET, on_page=lambda n, total: typer.echo(f"page {n}: {total} rows")
    )
    payload = {"account": coverage.BUYBACK_WALLET, "activities": rows}
    out.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8", newline="\n")
    days = [common.utc_day(int(r["block_timestamp"])) for r in rows]
    entry = mf.make_entry(
        build_mod.REFERENCE,
        out,
        source=f"{nearblocks.BASE}/{coverage.BUYBACK_WALLET}/activities (per_page "
        f"{nearblocks.PER_PAGE}, cursor paging; fields: {', '.join(nearblocks.KEEP)})",
        pulled_at_utc=common.utc_now_iso(),
        date_range=(min(days), max(days)),
    )
    mf.upsert_entries(build_mod.REFERENCE, [entry])
    typer.echo(f"wrote {out.relative_to(build_mod.ROOT).as_posix()}: {len(rows)} activities")


@reference_app.command("stable-legs")
def reference_stable_legs(
    start: Annotated[str, typer.Option(help="First day (YYYY-MM-DD).")] = "2026-10-24",
    end: Annotated[str, typer.Option(help="Last day (YYYY-MM-DD).")] = "2026-10-30",
) -> None:
    """Stablecoin legs of Intents swaps per day from BigQuery (dry-run first, under the cap)."""
    import pandas as pd
    from google.cloud import bigquery

    from capture import manifest as mf
    from capture.extract import common
    from capture.extract.bigquery import BigQueryRunner
    from capture.models import distribution

    s = config.load_settings()
    assets = pd.read_parquet(config.DATA_SNAPSHOT / "token_assets.parquet")
    stable = assets[
        assets["symbol"].isin(distribution.STABLECOIN_SYMBOLS)
        & assets["asset_id"].str.startswith(("nep141:", "nep245:"))
    ]
    extra = [
        bigquery.ArrayQueryParameter("stable_ids", "STRING", stable["asset_id"].tolist()),
        bigquery.ArrayQueryParameter(
            "stable_decimals", "INT64", stable["decimals"].astype(int).tolist()
        ),
    ]
    query_file = "sql/intents_stable_legs_daily.sql"
    sql = (config.ROOT / query_file).read_text(encoding="utf-8")
    runner = BigQueryRunner(
        s["GOOGLE_CLOUD_PROJECT"], int(s["BQ_MAX_BYTES"]), config.DATA_LIVE / "_bq_log.jsonl"
    )
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    frames, billed = [], 0
    for chunk in runner.plan(sql, first, last, extra):  # dry-run, split until under the cap
        typer.echo(f"{chunk.start}..{chunk.end}: dry-run {_gb(chunk.dry_run_bytes)}")
        df, b = runner.run_chunk("intents_stable_legs_daily", sql, chunk, extra)
        frames.append(df)
        billed += b
    out = build_mod.REFERENCE / "intents_stable_legs_daily.parquet"
    pd.concat(frames, ignore_index=True).sort_values("date").to_parquet(out, index=False)
    entry = mf.make_entry(
        build_mod.REFERENCE,
        out,
        source=f"bigquery:{config.DATASET}",
        pulled_at_utc=common.utc_now_iso(),
        query_file=query_file,
        date_range=(start, end),
        query_sha256=mf.sha256_file(config.ROOT / query_file),
    )
    mf.upsert_entries(build_mod.REFERENCE, [entry])
    typer.echo(f"wrote {out.relative_to(build_mod.ROOT).as_posix()}; billed {_gb(billed)}")


prereg_app = typer.Typer(
    help="Pre-registered forward tests: freeze, anchor on NEAR, score.", no_args_is_help=True
)
app.add_typer(prereg_app, name="prereg")


def _activity_changes(rows: list[dict]):
    from capture.models import coverage, wallet_flows

    others = set(config.FEE_WALLETS) - {coverage.BUYBACK_WALLET}
    return wallet_flows.activity_changes(rows, others)


@prereg_app.command("write")
def prereg_write() -> None:
    """Freeze data/prereg/ from the snapshot and the reference files (refuses to overwrite)."""
    import json

    import pandas as pd

    from capture import prereg
    from capture.models import coverage

    payload = json.loads(build_mod.FLOWS_FILE.read_text(encoding="utf-8"))
    changes = _activity_changes(payload["activities"])
    end = pd.Timestamp(prereg.now_utc()[:10]) - pd.Timedelta(days=1)  # last complete UTC day
    start = end - pd.Timedelta(days=27)
    if changes["date"].max() < end:
        typer.echo(
            "the activity file does not reach yesterday: run `capture reference buyback-flows`",
            err=True,
        )
        raise typer.Exit(1)
    inside = changes[(changes["date"] >= start) & (changes["date"] <= end)]
    inflow = inside.loc[(inside["kind"] == "intents") & (inside["change_near"] > 0), "change_near"]
    summary = build_mod.summary_payload(config.DATA_SNAPSHOT, "snapshot")
    hsp = summary["governance"]["hsp029"]
    tests = prereg.build_tests(
        registered_at=prereg.now_utc(),
        inflow_per_day=float(inflow.sum()) / 28,
        inflow_base=(start.date().isoformat(), end.date().isoformat()),
        cr_float_30=summary["hero"]["cr_float_30"],
        cr_date=summary["hero"]["date"],
        routing=summary["ledger"]["kept"]["buyback_of_onchain"],
        routing_end=summary["ledger"]["end"],
        tolerance=coverage.RECONCILIATION_TOLERANCE,
        hsp029_status=hsp["status"],
        hsp029_block=hsp["read_at_block"],
    )
    try:
        written = prereg.write(tests)
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    for path in written:
        typer.echo(f"wrote {path.relative_to(build_mod.ROOT).as_posix()}")
    sha = prereg.manifest_sha256()
    typer.echo(f"manifest sha256 {sha}; anchor it with `capture prereg anchor`")


@prereg_app.command("anchor")
def prereg_anchor(
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
    tx: Annotated[str | None, typer.Option(help="Transaction id, if it cannot be read.")] = None,
) -> None:
    """Commit the SHA-256 of data/prereg/manifest.json to the proof contract (public, permanent)."""
    import json

    from capture import prereg

    s, network, contract, signer = _proof_setup()
    near_bin = shutil.which("near")
    if not near_bin:
        typer.echo("near-cli-rs not found on PATH (see README, 'Verify the proof').", err=True)
        raise typer.Exit(1)
    tests = json.loads(prereg.TESTS.read_text(encoding="utf-8"))
    sha = prereg.manifest_sha256()
    rid = prereg.run_id(sha, tests["registered_at_utc"][:10])
    rpc = proof_mod.NETWORKS[network]["rpc"]
    typer.echo(f"commit {rid}\n  hash     {sha}\n  network  {network}\n  contract {contract}")
    typer.echo("  This transaction is public and permanent.")
    with httpx.Client() as client:
        on_chain = proof_mod.get(client, rpc, contract, rid)
        if on_chain not in (None, sha):
            typer.echo(f"{rid} already holds another hash: {on_chain}", err=True)
            raise typer.Exit(1)
        if on_chain is None:
            if not yes and not typer.confirm("Send it?"):
                raise typer.Exit(1)
            argv = proof_mod.commit_argv(
                near_bin, contract, signer, network, rid, sha,
                s.get("PROOF_PUBLIC_KEY"), s.get("PROOF_PRIVATE_KEY"),
            )  # fmt: skip
            done = subprocess.run(argv, capture_output=True, text=True, check=False)
            if done.returncode != 0:
                typer.echo(f"near CLI failed (exit {done.returncode})", err=True)
                raise typer.Exit(1)
            tx = tx or proof_mod.parse_tx_id(done.stdout + done.stderr)
            if proof_mod.get(client, rpc, contract, rid) != sha:
                typer.echo("the chain does not show the hash after the call", err=True)
                raise typer.Exit(1)
        if not tx:
            typer.echo("the hash is on chain; pass the transaction id with --tx", err=True)
            raise typer.Exit(1)
        height = proof_mod.tx_block_height(client, rpc, tx, signer)
    record = {
        "manifest_sha256": sha,
        "near": proof_mod.near_record(network, contract, signer, rid, tx, height),
    }
    (prereg.PREREG / "anchor.json").write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    typer.echo(f"anchored at block {height}: {record['near']['explorer_url']}")


@prereg_app.command("score")
def prereg_score(
    source: Annotated[Source, typer.Option(help="Data directory for T2-T4.")] = Source.live,
    online: Annotated[
        bool, typer.Option(help="Read NearBlocks and vote.dao for T1 and T5.")
    ] = True,
) -> None:
    """Score every test whose window has closed; write data/prereg/scores.json."""
    import json

    import pandas as pd

    from capture import prereg
    from capture.extract import governance, nearblocks
    from capture.models import coverage, ledger

    tests = json.loads(prereg.TESTS.read_text(encoding="utf-8"))
    by_id = {t["id"]: t for t in tests["tests"]}
    changes = proposal = read_at = None
    if online:
        changes = _activity_changes(
            nearblocks.fetch_activities(
                coverage.BUYBACK_WALLET, on_page=lambda n, k: typer.echo(f"page {n}: {k} rows")
            )
        )
        proposal, read_at = governance.fetch_proposal()["proposal"], prereg.now_utc()

    data_dir = build_mod.ROOT / "data" / source.value
    state = None
    try:
        state = build_mod.start_state(data_dir)
    except (FileNotFoundError, IndexError):
        state = None

    def cr_on(day: str) -> float | None:
        if state is None or pd.Timestamp(day) not in state.table.index:
            return None
        v = state.table.loc[pd.Timestamp(day), "cr_float_30"]
        return None if pd.isna(v) else float(v)

    def routing_on(day: str) -> float | None:
        if state is None:
            return None
        try:
            daily = build_mod.ledger_daily(state)
            return ledger.waterfall(daily, pd.Timestamp(day), 30)["kept"]["buyback_of_onchain"]
        except (KeyError, ValueError):
            return None

    def deviation_on(day: str) -> float | None:
        if state is None:
            return None
        months = coverage.monthly_reconciliation(state.frame)
        month = day[:7]
        hit = months[months.index.astype(str) == month]
        return None if hit.empty else float(abs(hit["deviation"].iloc[0]))

    scores = {
        "scored_at_utc": prereg.now_utc(),
        "source": f"data/{source.value}",
        "results": {
            "T1": prereg.score_t1(by_id["T1"], changes),
            "T2": prereg.score_series(by_id["T2"], cr_on),
            "T3": prereg.score_series(by_id["T3"], routing_on),
            "T4": prereg.score_series(by_id["T4"], deviation_on),
            "T5": prereg.score_t5(by_id["T5"], proposal, read_at),
        },
    }
    prereg.SCORES.write_text(json.dumps(scores, indent=1) + "\n", encoding="utf-8", newline="\n")
    for key, result in scores["results"].items():
        typer.echo(f"{key} {result['status']:8} {result.get('value', result.get('reason', ''))}")


proof_app = typer.Typer(
    help="Proof of analysis: commit the snapshot manifest hash to a NEAR network.",
    no_args_is_help=True,
)
app.add_typer(proof_app, name="proof")


def _proof_setup() -> tuple[dict[str, str], str, str, str]:
    """(settings, network, contract, signer) from .env / the environment; testnet by default."""
    s = config.load_settings()
    network = s.get("PROOF_NETWORK", "testnet")
    signer = s.get("PROOF_ACCOUNT_ID")
    if not signer:
        typer.echo("PROOF_ACCOUNT_ID is not set (see .env.example and README).", err=True)
        raise typer.Exit(1)
    return s, network, s.get("PROOF_CONTRACT_ID", signer), signer


@proof_app.command("status")
def proof_status(
    data_dir: Annotated[Path, typer.Argument()] = config.DATA_SNAPSHOT,
) -> None:
    """Compare the snapshot manifest hash with the hash the contract holds. Changes nothing."""
    _, network, contract, _ = _proof_setup()
    sha = proof_mod.manifest_sha256(data_dir)
    run_id = proof_mod.make_run_id(sha, proof_mod.snapshot_end(data_dir))
    rpc = proof_mod.NETWORKS[network]["rpc"]
    try:
        with httpx.Client() as client:
            on_chain = proof_mod.get(client, rpc, contract, run_id)
    except proof_mod.ProofError as exc:
        typer.echo(f"proof: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"network   {network}")
    typer.echo(f"contract  {contract}")
    typer.echo(f"run_id    {run_id}")
    typer.echo(f"manifest  {sha}")
    typer.echo(f"on chain  {on_chain}")
    if on_chain == sha:
        typer.echo("MATCH: this snapshot's manifest hash is committed on chain.")
    elif on_chain is None:
        typer.echo("NOT COMMITTED: run `make proof`.")
    else:
        typer.echo("DIFFERENT hash on chain for this run_id.", err=True)
        raise typer.Exit(1)


@proof_app.command("preflight")
def proof_preflight(
    wasm: Annotated[Path, typer.Option(help="The contract .wasm that will be deployed.")],
) -> None:
    """Check that the proof account exists and can hold the contract code. Changes nothing."""
    _, network, _, signer = _proof_setup()
    size = wasm.stat().st_size
    with httpx.Client() as client:
        checks = proof_mod.preflight(client, proof_mod.NETWORKS[network]["rpc"], signer, size)
    for c in checks:
        typer.echo(f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.detail}")
    if not all(c.ok for c in checks):
        raise typer.Exit(1)


@proof_app.command("ots-record")
def proof_ots_record() -> None:
    """Record the status of the OpenTimestamps stamp (`ots info`) in data/proof.json."""
    ots_bin = shutil.which("ots")
    if not ots_bin:
        typer.echo("ots not found on PATH (it runs in CI: .github/workflows/proof.yml).", err=True)
        raise typer.Exit(1)

    def run(argv: list[str]) -> tuple[int, str]:
        done = subprocess.run([ots_bin, *argv[1:]], capture_output=True, text=True, check=False)
        return done.returncode, done.stdout + done.stderr

    try:
        record = proof_mod.ots_record(config.ROOT / "data" / "proof.json", run)
    except proof_mod.ProofError as exc:
        typer.echo(f"proof: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"opentimestamps: {record['opentimestamps']['status']}")


@proof_app.command("commit")
def proof_commit(
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
    tx: Annotated[str | None, typer.Option(help="Transaction id, if it cannot be read.")] = None,
    data_dir: Annotated[Path, typer.Argument()] = config.DATA_SNAPSHOT,
) -> None:
    """Commit the manifest hash to the contract (a public, permanent transaction)."""
    s, network, contract, signer = _proof_setup()
    near_bin = shutil.which("near")
    if not near_bin:
        typer.echo("near-cli-rs not found on PATH (see README, 'Verify the proof').", err=True)
        raise typer.Exit(1)
    sha = proof_mod.manifest_sha256(data_dir)
    run_id = proof_mod.make_run_id(sha, proof_mod.snapshot_end(data_dir))
    typer.echo(f"commit {run_id}")
    typer.echo(f"  hash     {sha}")
    typer.echo(f"  network  {network}")
    typer.echo(f"  contract {contract}")
    typer.echo(f"  signer   {signer}")
    typer.echo("  This transaction is public and permanent.")
    if not yes and not typer.confirm("Send it?"):
        raise typer.Exit(1)

    def run(argv: list[str]) -> tuple[int, str]:
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        return done.returncode, done.stdout + done.stderr

    try:
        with httpx.Client() as client:
            record = proof_mod.commit(
                data_dir, config.ROOT / "data" / "proof.json",
                network=network, contract=contract, signer=signer, client=client, run=run,
                near_bin=near_bin, public_key=s.get("PROOF_PUBLIC_KEY"),
                private_key=s.get("PROOF_PRIVATE_KEY"), tx_hash=tx,
            )  # fmt: skip
    except proof_mod.ProofError as exc:
        typer.echo(f"proof: {exc}", err=True)
        raise typer.Exit(1) from exc
    near = record["near"]
    typer.echo(f"committed at block {near['block_height']}: {near['explorer_url']}")
