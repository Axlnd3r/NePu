"""Rebuild every metric from data/<source>/ into site/public/data/*.json.

F0: placeholder that only writes meta.json (build time, git commit, source).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE_DATA = ROOT / "site" / "public" / "data"


def git_commit(root: Path = ROOT) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(source: str, out_dir: Path = SITE_DATA) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(),
        "source": f"data/{source}",
    }
    out = out_dir / "meta.json"
    out.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return out
