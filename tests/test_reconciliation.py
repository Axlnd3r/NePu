"""On-chain revenue vs DefiLlama revenue, month by month (offline, committed snapshot)."""

import re

import pandas as pd
import pytest

from capture.build import load_tables
from capture.config import DATA_SNAPSHOT, ROOT
from capture.models import coverage


@pytest.fixture(scope="module")
def months() -> pd.DataFrame:
    return coverage.monthly_reconciliation(coverage.build_inputs(load_tables(DATA_SNAPSHOT)))


def test_monthly_on_chain_revenue_matches_defillama_within_tolerance(months: pd.DataFrame) -> None:
    """Fails with the full monthly table; the tolerance is never loosened silently."""
    table = months.assign(deviation_pct=(months["deviation"] * 100).round(1))
    assert len(months) >= 6, "too few complete months to reconcile\n" + table.to_string()
    bad = months[~months["within_tolerance"]]
    assert bad.empty, (
        f"months outside +/-{coverage.RECONCILIATION_TOLERANCE:.0%}:\n{bad.index.tolist()}\n"
        f"full table:\n{table.to_string()}"
    )


def test_tolerance_matches_the_documented_value() -> None:
    """Changing the tolerance requires changing docs/METHODOLOGY.md in the same commit."""
    text = (ROOT / "docs" / "METHODOLOGY.md").read_text(encoding="utf-8")
    match = re.search(r"Reconciliation tolerance:\s*(\d+)%", text)
    assert match, "docs/METHODOLOGY.md must state 'Reconciliation tolerance: N%'"
    assert int(match.group(1)) / 100 == pytest.approx(coverage.RECONCILIATION_TOLERANCE)


def test_months_are_complete_calendar_months(months: pd.DataFrame) -> None:
    assert months.index.is_monotonic_increasing and months.index.is_unique
    assert (months["onchain_usd"] > 0).all() and (months["defillama_usd"] > 0).all()
