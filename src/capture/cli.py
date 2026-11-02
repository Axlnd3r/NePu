"""Command-line entry point: `capture <command>`."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from capture import build as build_mod
from capture import config
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
    out = build_mod.build(source.value)
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


@app.command()
def proof() -> None:
    """Hash the manifest and commit it to NEAR mainnet (needs PROOF_ACCOUNT_ID)."""
    typer.echo("proof: not implemented yet (phase F7).", err=True)
    raise typer.Exit(1)
