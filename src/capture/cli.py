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
