"""Smoke test for the judge-facing demo.

The demo is the artifact most likely to be run and least likely to be covered by
unit tests. A refactor that breaks it fails silently everywhere except in front
of the person evaluating the submission.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_demo(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "demo.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_demo_runs_clean():
    result = run_demo("--events", "300", "--quick")
    assert result.returncode == 0, result.stderr[-2000:]


def test_demo_reports_every_section():
    result = run_demo("--events", "300")
    out = result.stdout
    for section in (
        "THE BATCH",
        "DIAGNOSIS",
        "THE DECISION PATH",
        "COUNTERFACTUAL",
        "WHAT THE CLAIMS ACTUALLY REST ON",
        "SENSITIVITY",
        "AUDIT TRAIL",
        "EXCEPTION QUEUE",
        "COMPLIANCE CERTIFICATE",
        "VERIFY IT YOURSELF",
    ):
        assert section in out, f"demo output is missing the {section} section"


def test_demo_actually_demonstrates_tamper_detection():
    """The tamper demo silently 'passed' once because it flipped a verdict that
    was already PASS. A demo that shows 'chain OK' after tampering is worse than
    no demo — it disproves the claim it is meant to prove."""
    out = run_demo("--events", "300", "--quick").stdout
    assert "BLOCK -> PASS" in out
    assert "chain BROKEN" in out
    assert "content hash mismatch" in out


def test_demo_publishes_the_unfavourable_boundary():
    """The sensitivity section must state where our own claim fails."""
    out = run_demo("--events", "300").stdout
    assert "winner: blind_retry" in out


def test_judge_mode_runs_and_leads_with_tier_a():
    """The 60-second version must still lead with the assumption-free claims and
    still publish the boundary. A short version that quietly drops the caveats
    would be the easiest possible place for the honesty to leak out."""
    out = run_demo("--events", "300", "--judge").stdout

    claims = out.index("CLAIMS THAT DEPEND ON NO ECONOMIC ASSUMPTION")
    fails = out.index("WHERE OUR OWN CLAIM FAILS")
    assert claims < fails, "judge mode leads with the conditional claim"
    assert "<- we lose" in out


def test_judge_mode_shows_a_material_refusal():
    """A Rs 173 block illustrates nothing. The example must be real money the
    system deliberately chose to leave alone, with the rule that refused it."""
    out = run_demo("--events", "300", "--judge").stdout
    section = out[out.index("ONE REFUSAL") : out.index("WHERE OUR OWN")]

    assert "BLOCK" in section
    assert "ok" in section, "passes must be shown too, not only the refusal"
    amount = int(
        section.split("at risk")[0].split("Rs")[-1].strip().replace(",", "").split(".")[0]
    )
    assert amount >= 1000, f"refusal example is only Rs {amount}; pick a material one"
