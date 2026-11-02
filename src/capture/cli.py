"""Command-line entry point: `capture <command>`."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from capture import build as build_mod
from capture.manifest import verify_manifest as verify_manifest_dir

app = typer.Typer(no_args_is_help=True, add_completion=False)


class Source(StrEnum):
    snapshot = "snapshot"
    live = "live"


@app.command()
def extract() -> None:
    """Pull fresh data into data/live/ (needs .env credentials)."""
    typer.echo("extract: not implemented yet (phase F2).", err=True)
    raise typer.Exit(1)


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
