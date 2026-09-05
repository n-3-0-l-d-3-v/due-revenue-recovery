"""The FAQ must stay linked and stay honest.

Every other public claim in this repo is locked by a test so it can't quietly
drift or get trimmed away under deadline pressure. The FAQ is no different —
it's the one place the hardest questions get answered directly, and it's the
easiest one to gut "for time" without anyone noticing.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAQ = (ROOT / "docs" / "faq.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_links_the_faq():
    assert "docs/faq.md" in README


def test_faq_states_the_measured_ai_ceiling():
    """The single most important number if asked 'is there AI in this' —
    the Bayes ceiling that justified cutting the LLM path."""
    for figure in ("43.1%", "46.6%", "48.7%"):
        assert figure in FAQ


def test_faq_names_external_anchoring():
    """The precise answer to 'isn't tamper-evident a security hole' — naming
    the real fix, not just admitting the limitation exists."""
    assert "external anchoring" in FAQ.lower()


def test_faq_does_not_overclaim_certainty_about_razorpay_internals():
    assert "publicly documented" in FAQ


def test_faq_names_every_deferred_alternative():
    """'Are you sure there's no better strategy' must list what was actually
    considered and cut, not just assert confidence."""
    for alt in ("contextual bandit", "linear-programming", "trained classifier"):
        assert alt in FAQ.lower() or alt.replace("-", " ") in FAQ.lower()


def test_faq_names_every_out_of_scope_item():
    for gap in ("receivables", "multi-tenancy", "persistence"):
        assert gap in FAQ.lower()


def test_faq_frames_the_bounded_agent_argument():
    """Answers 'where's the agentic behaviour' without claiming agentic
    behaviour that doesn't exist."""
    assert "bounded" in FAQ.lower()
    assert "agent" in FAQ.lower()
