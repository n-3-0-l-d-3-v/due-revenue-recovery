"""The same numbers, in the same words, everywhere.

Five artifacts state the submission's claims: README, ARCHITECTURE, the video
script, `demo.py`, and `demo.py --judge`. A judge may see any subset of them, in
any order. If the video says one number and the README says another, the whole
result becomes suspect regardless of which one is right.

This caught the video script rounding Rs 59,755 to "fifty-nine thousand" — in the
same document whose own guidance says "do not round", because a rounded figure
lands as an estimate and a precise one lands as a measurement.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

README = (ROOT / "README.md").read_text(encoding="utf-8")
ARCHITECTURE = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
SCRIPT = (ROOT / "docs" / "video-script.md").read_text(encoding="utf-8")


def _run(*args: str) -> str:
    return subprocess.run(
        [sys.executable, "demo.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    ).stdout


@pytest.fixture(scope="module")
def artifacts():
    return {
        "README": README,
        "ARCHITECTURE": ARCHITECTURE,
        "video script": SCRIPT,
        "demo": _run(),
        "judge mode": _run("--judge"),
    }


def _normalise(text: str) -> str:
    for old, new in ((",", ""), ("−", "-"), ("–", "-"), ("₹", ""), ("Rs ", "")):
        text = text.replace(old, new)
    return text


def _flat(text: str) -> str:
    """Lowercase with whitespace collapsed.

    Markdown hard-wraps prose, so a spoken number can straddle a line break and
    a naive substring check misses it. The demo also prints its headers in caps.
    Both are presentation, not substance."""
    return re.sub(r"\s+", " ", text).lower()


# Figure -> how it may legitimately appear when spoken aloud in the script.
SPOKEN = {
    "2493": "two thousand four hundred and ninety-three",
    "441": "four hundred and forty-one",
    "4652": "four thousand six hundred",
    "59755": "fifty-nine thousand, seven hundred and fifty-five",
}


def _states(text: str, figure: str) -> bool:
    if figure in _normalise(text):
        return True
    spoken = SPOKEN.get(figure)
    return bool(spoken and spoken in _flat(text))


# Every artifact that mentions a figure at all must agree on it. Artifacts are not
# required to mention every figure — the architecture doc has no reason to quote
# rupee totals — but a mention must be correct.
CORE_FIGURES = ["2493", "441", "4652"]


@pytest.mark.parametrize("figure", CORE_FIGURES)
def test_headline_counts_agree_across_artifacts(artifacts, figure):
    """The Tier A counts lead every telling of this, so all five must carry them."""
    missing = [name for name, text in artifacts.items() if not _states(text, figure)]
    # ARCHITECTURE quotes the counts once, in its Tier note.
    assert not missing, f"{figure} is missing from: {', '.join(missing)}"


def test_video_script_does_not_round_the_headline_delta():
    """The script's own guidance says a rounded number lands as an estimate.
    It rounded this one anyway until this test existed."""
    flat = _flat(SCRIPT)
    assert "fifty-nine thousand, seven hundred and fifty-five" in flat
    assert "fifty-nine thousand rupees more" not in flat


def test_tier_vocabulary_is_defined_wherever_it_is_used(artifacts):
    """Referring to 'Tier B' in a document that never defines Tier A leaves the
    reader with no referent."""
    for name, text in artifacts.items():
        flat = _flat(text)
        if "tier b" in flat:
            assert "tier a" in flat, f"{name} references Tier B without defining Tier A"


def test_tier_a_precedes_tier_b_everywhere(artifacts):
    """Order is part of the claim. Leading with the conditional number invites
    'where does that come from?' as the first question rather than the last."""
    for name, text in artifacts.items():
        flat = _flat(text)
        if "tier a" in flat and "tier b" in flat:
            assert flat.index("tier a") < flat.index("tier b"), (
                f"{name} presents Tier B before Tier A"
            )


def test_the_unfavourable_boundary_survives_in_every_public_artifact(artifacts):
    """The place our own claim fails must not be quietly dropped from the short
    versions. That is the easiest place for the honesty to leak out."""
    markers = {
        "README": "blind retry wins",
        "video script": "blind retry wins",
        "demo": "winner: blind_retry",
        "judge mode": "<- we lose",
    }
    for name, marker in markers.items():
        assert marker in artifacts[name], f"{name} no longer publishes the boundary"


def test_no_artifact_calls_it_an_ai_agent(artifacts):
    """The judges have heard 'AI agent' all day; it signals nothing and it
    describes nothing about what this actually does."""
    for name, text in artifacts.items():
        if name == "video script":
            continue  # the script names the phrase only to warn against it
        assert "AI agent" not in text, f"{name} says 'AI agent'"


def test_zero_violations_is_stated_as_zero_not_as_few(artifacts):
    """'Almost no violations' is a different and much weaker claim."""
    for phrase in ("few violations", "almost no violations", "minimal violations"):
        for name, text in artifacts.items():
            assert phrase not in text.lower(), f"{name} hedges the zero-violation claim"
