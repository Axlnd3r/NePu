"""README.md: the results block is generated from the data; nothing else in it states a number."""

import json
import re
import tomllib

import pytest

from capture import build, thesis

README = build.ROOT / "README.md"
START, END = "<!-- results:start -->", "<!-- results:end -->"
# Names that contain digits but are not data, and the numbers of markdown list items.
NAMES = ("SHA-256", "HACKATHON 2026", "1Click", "HSP-029")
LIST_ITEM = re.compile(r"(?m)^\s*\d+\.\s")


@pytest.fixture(scope="module")
def text() -> str:
    return README.read_text(encoding="utf-8")


def test_the_results_block_is_what_the_build_writes(tmp_path) -> None:
    build.build("snapshot", tmp_path)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == README.read_text(
        encoding="utf-8"
    )


def test_the_results_block_uses_registered_facts_only(text: str) -> None:
    payloads = build.build_payloads("snapshot", build.ROOT / "data" / "snapshot")
    block, facts = thesis.render_results(payloads)
    inside = text[text.index(START) + len(START) : text.index(END)]
    assert inside.strip() == block.strip()
    registered = {f.text for f in facts}
    body = re.sub(r"https?://\S+|`[^`]*`", "", block)
    for name in NAMES:
        body = body.replace(name, "")
    body = re.sub(r"\d{4}-\d{2}(?:-\d{2})?", "", body)
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", body):
        assert token.rstrip(".,") in registered, token


def test_no_number_is_stated_outside_the_block_code_and_links(text: str) -> None:
    outside = text[: text.index(START)] + text[text.index(END) :]
    outside = re.sub(r"```.*?```", "", outside, flags=re.S)  # fenced commands (and the diagram)
    outside = re.sub(r"<[^>]+>", "", outside)  # HTML markup (widths, links) states no data
    outside = re.sub(r"`[^`]*`", "", outside)  # code spans (versions, ids, ports)
    outside = re.sub(r"\]\([^)]*\)|https?://\S+", "", outside)  # link targets
    outside = LIST_ITEM.sub("", outside)
    for name in NAMES:
        outside = outside.replace(name, "")
    assert re.findall(r"\d+", outside) == []


@pytest.mark.parametrize(
    "heading",
    [
        "## What it is",
        "## The problem",
        "## Results",
        "## Quickstart (offline)",
        "## Live mode",
        "## Verify the proof",
        "## Dashboard and demo video",
        "## Track checklist",
        "## AI & libraries disclosure",
        "## Hackathon diff",
    ],
)
def test_has_the_required_section(text: str, heading: str) -> None:
    assert heading in text


def test_quickstart_serves_the_site_because_the_export_uses_absolute_paths(text: str) -> None:
    quick = text[text.index("## Quickstart (offline)") : text.index("## Live mode")]
    assert "make all" in quick and "http.server" in quick and "site/out" in quick


def test_every_dependency_is_disclosed_and_the_use_of_claude_code_is_stated(text: str) -> None:
    pyproject = tomllib.loads((build.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((build.ROOT / "site" / "package.json").read_text(encoding="utf-8"))
    names = [re.split(r"[<>=\[]", d)[0] for d in pyproject["project"]["dependencies"]]
    names += list(package["dependencies"])
    for name in names:
        assert name.lower() in text.lower(), name
    assert "Claude Code" in text and "near-sdk" in text and "OpenTimestamps" in text


def test_the_network_is_named_wherever_mainnet_is_mentioned(text: str) -> None:
    if "mainnet" in text.lower():
        assert "testnet" in text.lower()


def test_links_the_dashboard_the_thesis_and_both_diffs(text: str) -> None:
    for needle in (
        "https://axlnd3r.github.io/NePu/",
        "THESIS.md",
        "compare/pre-hackathon...hackathon-submission",
        "compare/pre-hackathon...main",
    ):
        assert needle in text


def test_the_checklist_maps_the_official_sources_and_marks_our_own_items(text: str) -> None:
    checklist = text[text.index("## Track checklist") : text.index("## AI & libraries")]
    assert "https://nearhackathon.com/HACKATHON.md" in checklist
    assert "near-hackathon-prompt-examples/blob/main/tracks/02-thesis.md" in checklist
    assert "Our own" in checklist
