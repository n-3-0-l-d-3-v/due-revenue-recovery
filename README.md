# Recoup — a policy-gated revenue recovery control plane

**Razorpay AI Buildathon · Track 03 — AI Revenue Recovery**

Recovering failed payments is not the hard part. Knowing **which failures are worth
recovering, when, and when you are legally required to stop** is the hard part.

Recoup turns every at-risk rupee into a bounded, policy-gated decision and proves in a
replayable audit trail that no action ever breached a card-network attempt cap or an
RBI e-mandate rule.

```bash
pip install -r requirements.txt
python demo.py          # ~2s, every claim below, computed live
```

---

## What it does, in one measured table

Same 1,000-event batch, ₹1,113,772 at risk, four strategies, identical scoring machinery:

| strategy | recovered | rate | attempts | contacts | violations | **net value** |
|---|---:|---:|---:|---:|---:|---:|
| do nothing | ₹0 | 0.0% | 0 | 0 | 0 | ₹0 |
| fixed T+3 *(Razorpay's documented retry)* | ₹294,538 | 26.4% | 2,151 | 0 | 715 | ₹236,167 |
| blind retry *(what most "AI retry agents" are)* | ₹439,822 | **39.5%** | 4,652 | 1,768 | 2,493 | **−₹239,741** |
| **Recoup** | ₹380,067 | 34.1% | **441** | **313** | **0** | **₹325,397** |

Blind retry recovers ₹59,755 **more** and is worth ₹565,138 **less**.

---

## What these claims rest on

Not every claim here has the same footing. Collapsing them into one headline would be
the dishonest move, so they are stated separately.

### Tier A — independent of every economic assumption

- **0 policy violations** vs blind retry's **2,493**
- **441 attempts** vs 4,652 · **313 contacts** vs 1,768
- while recovering **86%** of what blind retry recovers

These are counts of actions and rule evaluations. **No cost parameter can move them** —
verified under four different cost models including one with every cost set to zero.

### Tier B — depends on one qualitative assumption

- **highest net value** (₹325,397)

This holds provided that repeated retries and repeated contact carry *any*
customer-retention cost. Not a specific magnitude — just non-zero.

**Where it fails:** set all retention cost to exactly zero and blind retry wins by
about 9%. That boundary is published in [docs/sensitivity.md](docs/sensitivity.md),
printed by `demo.py`, and locked by a test that asserts *the competitor wins* there.

---

## How it works

```
RiskEvent → diagnose → enumerate actions → POLICY GATE
          → score net value (permitted actions only)
          → execute (re-validate the gate first) → hash-chained ledger
```

**The gate runs before any scoring or learning.** Nothing may choose an action the gate
did not already permit, so optimisation cannot produce a fine or a compliance breach —
by construction, not by training.

**DEFER is not BLOCK.** An RBI pre-debit window makes a mandate debit illegitimate
*now*, not illegitimate. Deferred actions are held, then re-validated against fresh
state before firing — because consent can be withdrawn between deciding and acting.

**Sealed records cannot be edited.** A re-validation outcome or a payment result
arrives as its own chained entry, never as a mutation of the decision it refers to. An
append-only log whose entries can be rewritten is a log, not an audit trail.

### The five leak points

Failed payments · **uncaptured authorisations** · late authorisations · abandoned
checkouts · failed mandates · halted subscriptions — in one prioritised portfolio.

12.7% of the batch's value is **authorised-but-uncaptured**: the bank approved it, the
customer consented, and it appears in no failure dashboard. A retry-based system scores
exactly ₹0 against it because there is nothing to retry — you simply have to capture.

---

## Where this sits next to Razorpay

Razorpay ships an **Intelligent Retry Engine** (beta, GFF 2026) that already does
context-aware retry timing for UPI Autopay, reporting +8% over baseline. This is not a
claim to have invented smart retries.

That engine optimises **the debit attempt, at the gateway layer**. Recoup optimises the
**merchant's recovery portfolio** — the parts a PSP is structurally unable to see:

- allocating a finite attempt-and-contact budget across a whole batch
- merchant-side economics: contact fatigue, customer LTV, issuer standing
- **net value**, not success rate
- one portfolio across all leak points, not just mandate debits
- a merchant-facing, replayable compliance artifact
- a **post-`halted` playbook** — native tooling stops where the customer is actually lost

---

## Honesty notes

Things a reviewer would otherwise have to find:

- **Diagnosis is 94% lookup, not prediction.** Razorpay documents what
  `insufficient_funds` means, so mapping it is a table lookup and reporting "accuracy"
  on it would be dishonest. Only the ~6% of generic declines require real inference.
- **We cut the LLM.** We measured the Bayes-optimal ceiling on that inference subset and
  found ~2 points of residual headroom after a five-rule heuristic. A per-event API call
  could not justify itself, so the classification claim was removed rather than shipped.
- **Network penalties carry 1.8% of the result.** "Blind retry is expensive because of
  fines" is roughly false. The compliance case stands on regulatory exposure and issuer
  standing, not economics.
- **Simulated under stated priors.** Every rupee figure is simulated; every generative
  parameter is committed and tagged `[CITED]` / `[DERIVED]` / `[ASSUMED]`. Compliance,
  audit integrity, and replay determinism are *proven* and hold on any input.
- **Tamper-evident, not tamper-proof.** Someone with write access could recompute the
  chain forward. Preventing that needs an external anchor.
- **16% of decisions go to a human.** A system claiming 100% automation is lying or
  unsafe.

**What would falsify this:** replay against real merchant traffic with observed
retention outcomes. If the retention effect is zero, Tier B dies and Tier A survives
untouched.

---

## Verify it yourself

```bash
python demo.py                   # every number above, computed live
python tools/mutation_check.py   # break each safety rule, confirm the tests catch it
pytest -q                        # 142 tests, 15 property-based
python live_demo.py --live       # real Razorpay test-mode payment link
```

`mutation_check.py` exists because a green suite proves the tests pass, not that they
would fail if the system broke. It found the headline invariant test passing
**vacuously** — twice.

## Docs

- [docs/domain-primer.md](docs/domain-primer.md) — the payments reasoning behind every rule
- [docs/sensitivity.md](docs/sensitivity.md) — where the claims hold and where they fail
- [docs/build-plan.md](docs/build-plan.md) — scope and schedule

## Safety

Razorpay **test mode only** — the client refuses to construct with a live key.
Dry run is the default. Customer notifications are hard-off at the call site. No PAN
ever enters the system; instruments are salted tokens.
