"""THESIS.md is generated from the published JSON: no number is typed by hand (rule 1)."""

import json
import re

import pytest

from capture import build, thesis

SOURCE = "snapshot"
SECTIONS = [
    "## Summary",
    "## Claim",
    "## What it means for a holder",
    "## Supporting evidence",
    "## Contrary evidence",
    "## Why public estimates differ",
    "## What would change my mind",
    "## Unavailable metrics and why",
    "## Limitations",
]
# Names that contain digits but are not data.
NAMES = ("HSP-029", "NEP-297", "SHA-256")
ISO_DATE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@pytest.fixture(scope="module")
def payloads() -> dict:
    return build.build_payloads(SOURCE, build.ROOT / "data" / SOURCE)


@pytest.fixture(scope="module")
def rendered(payloads) -> tuple[str, list]:
    return thesis.render(payloads)


def test_the_sections_appear_in_the_required_order(rendered) -> None:
    text, _ = rendered
    positions = [text.index(s) for s in SECTIONS]
    assert positions == sorted(positions)


def test_every_number_comes_from_a_registered_fact(rendered) -> None:
    text, facts = rendered
    registered = {f.text for f in facts}
    body = text
    for name in NAMES:
        body = body.replace(name, "")
    for date in ISO_DATE.findall(body):
        assert date in registered, f"date {date} is not from the data"
    body = ISO_DATE.sub("", body)
    for token in NUMBER.findall(body):
        assert token.rstrip(".,") in registered, f"number {token!r} is not from the data"


def test_every_fact_resolves_in_the_published_json(rendered, payloads, tmp_path) -> None:
    _, facts = rendered
    build.build(SOURCE, tmp_path)
    published = {
        name: json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
        for name in payloads
        if (tmp_path / f"{name}.json").exists()
    }
    assert facts, "the thesis must use data"
    for fact in facts:
        assert thesis.resolve(published, fact.path) == fact.raw, fact.path


def test_the_committed_thesis_is_what_the_build_writes(tmp_path) -> None:
    build.build(SOURCE, tmp_path)
    assert (tmp_path / "THESIS.md").read_text(encoding="utf-8") == (
        build.ROOT / "THESIS.md"
    ).read_text(encoding="utf-8")


def test_the_claim_states_how_far_it_is_and_that_it_is_not_there_yet(rendered, payloads) -> None:
    text, _ = rendered
    claim = text[text.index("## Claim") : text.index("## Supporting evidence")]
    assert "Not yet" in claim
    cents = round(payloads["summary"]["hero"]["cr_float_usd_30"] * 100)
    assert f"{cents} cents" in claim


def test_the_three_numeric_triggers_are_listed_with_where_they_stand(rendered, payloads) -> None:
    text, _ = rendered
    section = text[text.index("## What would change my mind") : text.index("## Unavailable")]
    for condition in payloads["summary"]["conditions"]:
        assert condition["text"] in section
    assert section.count("- ") >= 3


def test_unavailable_metrics_name_what_is_missing_and_why(rendered, payloads) -> None:
    text, _ = rendered
    section = text[text.index("## Unavailable metrics and why") : text.index("## Limitations")]
    assert payloads["distribution"]["scope"]["near_com"]["reason"] in section
    for item in payloads["markers"]["not_drawn"]:
        assert item["label"] in section and item["reason"] in section
    assert "unavailable" in section.lower()


def test_the_proof_is_described_with_its_network_and_its_limit(rendered, payloads) -> None:
    text, _ = rendered
    proof = payloads["provenance"]["proof"]
    assert proof["network"] in text
    assert "does not show that the data is correct" in text


def test_the_text_makes_no_price_prediction(rendered) -> None:
    text, _ = rendered
    lowered = text.lower()
    for phrase in ("price target", "will reach", "will rise", "should buy", "to the moon"):
        assert phrase not in lowered
    assert "no price is predicted" in lowered


def test_contrary_evidence_includes_the_null_lead_lag_result(rendered, payloads) -> None:
    text, _ = rendered
    contrary = text[text.index("## Contrary evidence") : text.index("## What would change")]
    assert payloads["developer"]["lead_lag"]["verdict"]["text"] in contrary


def test_resolve_follows_keys_indices_and_selectors() -> None:
    data = {"a": {"b": [{"k": "x", "v": 1}, {"k": "y", "v": 2}]}}
    assert thesis.resolve(data, "a.b[1].v") == 2
    assert thesis.resolve(data, "a.b[k=x].v") == 1
    with pytest.raises(KeyError):
        thesis.resolve(data, "a.b[k=z].v")


def _normalised(facts) -> set[str]:
    return {re.sub(r"\[[^\]]*\]", "[*]", f.path) for f in facts}


def test_every_path_the_thesis_and_the_readme_cite_is_independently_audited(payloads) -> None:
    """Citing a new JSON path without a recomputation in test_numbers_audit.py fails here."""
    import test_numbers_audit as audit

    _, thesis_facts = thesis.render(payloads)
    _, readme_facts = thesis.render_results(payloads)
    cited = _normalised(thesis_facts) | _normalised(readme_facts)
    missing = cited - audit.AUDITED - audit.DESCRIPTIVE
    assert not missing, f"cited but not audited: {sorted(missing)}"
    stale = (audit.AUDITED | audit.DESCRIPTIVE) - cited
    assert not stale, f"listed as audited but not cited: {sorted(stale)}"


def test_change_words_a_signed_fraction_and_registers_its_absolute_value() -> None:
    f = thesis.Facts({"a": {"down": -0.341, "up": 0.76}})
    assert f.change("a.down") == "fell 34%" and f.change("a.up") == "rose 76%"
    assert [(x.raw, x.text) for x in f.used] == [(-0.341, "34"), (0.76, "76")]


def test_the_summary_comes_first_and_answers_not_yet(rendered) -> None:
    text, _ = rendered
    summary = text[text.index("## Summary") : text.index("## Claim")]
    assert "**Answer today: not yet.**" in summary and "**For a holder.**" in summary


def test_the_hypothesis_is_stated_before_the_reading(rendered) -> None:
    text, _ = rendered
    claim = text[text.index("## Claim") : text.index("## What it means for a holder")]
    assert claim.index("The hypothesis:") < claim.index("Not yet")
    assert "It does depend on the NEAR price" in claim


def test_the_usage_result_is_reported_as_it_came_out(rendered, payloads) -> None:
    text, _ = rendered
    contrary = text[
        text.index("## Contrary evidence") : text.index("## Why public estimates differ")
    ]
    assert payloads["usage"]["lead_lag"]["verdict"]["text"] in contrary
    assert payloads["usage"]["lead_lag"]["verdict"]["label"] in contrary


def test_downside_signals_list_every_pre_registered_test(rendered, payloads) -> None:
    text, _ = rendered
    section = text[text.index("## What would change my mind") : text.index("## Unavailable")]
    assert "would change the answer to yes" in section and "would support the thesis" not in section
    for t in payloads["prereg"]["tests"]:
        assert f"- {t['id']}: {t['claim']}" in section


def test_scores_do_not_change_the_thesis(payloads) -> None:
    scored = {
        **payloads,
        "prereg": {
            **payloads["prereg"],
            "scores": {"scored_at_utc": "x", "results": {"T1": {"status": "pass"}}},
        },
    }
    assert thesis.render(scored)[0] == thesis.render(payloads)[0]


def test_a_missing_anchor_drops_only_its_clause(payloads) -> None:
    bare = {**payloads, "prereg": {**payloads["prereg"], "anchor": None}}
    text, _ = thesis.render(bare)
    assert "hash committed on NEAR" not in text and "- T1:" in text


def test_no_tests_no_downside_block(payloads) -> None:
    bare = {**payloads, "prereg": {**payloads["prereg"], "tests": []}}
    text, _ = thesis.render(bare)
    assert "Forecasts of this reading were written down" not in text


def test_the_readme_results_carry_both_price_bases_and_the_usage_result(payloads) -> None:
    block, _ = thesis.render_results(payloads)
    assert "at the prices of the window the cents use" in block
    assert payloads["usage"]["lead_lag"]["verdict"]["label"] in block
