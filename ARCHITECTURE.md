# Architecture

Written for an engineer who wants to find the weak points. The known ones are in
§6, stated rather than left to be discovered.

---

## 1. Control flow

```
RiskEvent
   │
   ├─► diagnose ─────────► Diagnosis {root_cause, confidence, evidence_ref}
   │                        94% citation-backed table lookup
   │                         6% inference over generic declines
   │
   ├─► enumerate ────────► [CandidateAction]  (cause-specific, timing included)
   │
   ├─► POLICY GATE ──────► permitted / deferred / blocked
   │                        every rule recorded — passes AND blocks
   │
   ├─► score ────────────► EVComponents  (over PERMITTED actions only)
   │
   ├─► execute ──────────► re-validate the gate against fresh state, then act
   │                        idempotent, dry-run by default
   │
   └─► ledger ───────────► sealed, hash-chained DecisionRecord
```

Two orderings carry the safety argument:

**Gate before score.** The scorer never sees a blocked action, so no amount of value
tuning can buy past a compliance rule. `GateContext` deliberately cannot read expected
value — a gate that could see money would eventually be tuned to trade compliance for
it, which is the failure this design exists to prevent.

**Re-validate before execute.** A decision made now that fires in 18 hours re-runs the
full gate first. Consent can be withdrawn and counters can move in between.

---

## 2. Module map

```
recoup/
├── core/
│   ├── models.py       RiskEvent · Diagnosis · CandidateAction · GateResult
│   │                   EVComponents · DecisionRecord · RevalidationEntry
│   ├── diagnose.py     reason code → root cause; BatchContext signals
│   ├── actions.py      cause → candidate actions, including retry timing
│   ├── policy/
│   │   ├── rules.yaml  11 gates: params, verdicts, citations
│   │   └── engine.py   predicates, evaluation, re-validation, invariant checks
│   ├── counters.py     attempt + contact windows
│   ├── scorer.py       net-value EV over permitted actions
│   ├── exceptions.py   human-in-the-loop queue with idempotent closure
│   ├── ledger.py       append-only hash chain + compliance certificate
│   └── pipeline.py     orchestration; the only writer to the ledger
├── sim/                generator · priors · oracle · Bayes ceiling   [EVAL ONLY]
├── harness/            strategies · counterfactual · sensitivity     [EVAL ONLY]
└── rzp/client.py       Razorpay test-mode client
```

### The import boundary that makes the numbers mean anything

`recoup.core` **must never import from `recoup.sim`.**

The simulator holds the latent truth — the real cause behind each decline, the day a
customer's balance actually recovers, whether an issuer was genuinely down. If any
production module could read it, every measured figure would be circular.

Three places this discipline shows up:

| Production side | Simulator side | Independent because |
|---|---|---|
| `diagnose.DIAGNOSIS_TABLE` | `priors.REASON_TO_ROOT_CAUSE` | Both derive from Razorpay's public error docs, neither from the other |
| `scorer.BELIEF_*` | `priors.BASE_RECOVERY_PROB` | The system's beliefs are anchored to published benchmarks and **disagree** with the simulator's truth — which is the point |
| `HeuristicInferencer.PRIOR` | `priors.AMBIGUOUS_HIDDEN_CAUSE` | Same domain facts, independently chosen magnitudes |

The counterfactual therefore measures how a system performs with *imperfect* beliefs,
which is the only situation any real system is ever in.

---

## 3. Key structures

### DecisionRecord

Field order mirrors the control flow, so a reader follows the decision top to bottom.

```
decision_id · batch_id · event_id · decided_at
event          RiskEvent snapshot
diagnosis      root_cause, confidence, evidence_ref  (evidence_ref is mandatory)
candidates     everything considered
gate_results   EVERY rule evaluated — {rule_id, verdict, rationale, source}
permitted      what survived
ev_components  p_recovery, amount, and every cost term, kept separable
chosen         the action, or None
not_chosen_why explicit reason for inaction
prev_hash · hash
```

`gate_results` records passes as well as blocks. A gate that logs only refusals can
prove it *noticed* some violations; it cannot prove compliance.

### The hash chain

```
GENESIS ← entry[0].prev_hash
          entry[0].hash ← entry[1].prev_hash ← …
```

Each entry's hash covers its full content, so editing a field breaks that entry.
Each commits to its predecessor, so deleting or reordering breaks the link. Both
failures are localised to a sequence number.

`from_jsonl` deliberately bypasses `append()` — re-sealing on load would launder a
forged file into a valid chain.

---

## 4. Policy gates

`rules.yaml` holds parameters, verdicts, and a citation per rule. `engine.py` holds the
predicate logic keyed by rule id. No expression interpreter, nothing `eval`'d, so every
rule is directly unit-testable.

`PolicyEngine.__init__` raises if a rule is declared with no predicate — a
declared-but-unimplemented rule is a *silently open gate*, the worst failure mode
because the audit trail would show it being "evaluated".

`check_invariants()` runs static contradiction checks: our own retry cap must be tighter
than the network caps, the 24h cap must not exceed the 30d cap, exempt AFA thresholds
must not be stricter than the base. A self-contradicting rule set fails silently at
runtime by permitting or blocking everything.

Two deliberate carve-outs, documented in the YAML so they read as decisions rather than
omissions:

- **`capture_authorized` is exempt from `consent.active`.** Capture is not a new debit —
  the customer already authenticated that exact amount. Consent withdrawal governs
  future debits and contact. Blocking it would strand money the customer intended to
  pay, then auto-refund it days later.
- **`ESCALATE_HUMAN` and `STOP_UNCOLLECTIBLE` are ungated.** They move no money and
  contact nobody.

---

## 5. Testing

142 tests. The interesting ones are not the unit tests.

**Property-based (15).** Hypothesis generates ~250 event shapes per property, including
degenerate ones. Universally quantified: nothing permitted was also blocked · terminal
declines are never retried · withdrawn consent permits no debit or contact · dead
obligations are never pursued · evaluation is pure and replayable.

**Mutation check** (`tools/mutation_check.py`). Breaks each safety rule in turn and
confirms the suite catches it. All 8 mutations caught.

This found the headline invariant test passing **vacuously, twice**: it read the cap
from the same config it was validating (raise 3→99 and the assertion rises with it),
and it drew `payment_id` from a million-wide range so no payment ever accumulated a
second retry. Both fixed; `test_the_retry_cap_actually_binds` now guards the guard.

**Boundary tests.** `test_ranking_flips_when_all_retention_cost_is_removed` asserts the
*competitor* wins in the region where our claim fails. Publishing a boundary you have
tested is honest; publishing a claim whose boundary you never looked for is not.

**Demo tests.** The demo is the artifact most likely to be run and least likely to be
covered. `test_demo_actually_demonstrates_tamper_detection` exists because the tamper
section once printed "chain OK" after tampering — it flipped a verdict that was already
`PASS`.

---

## 6. Known limitations

Stated, not hidden. Every one of these is a real gap.

A note on which claims they touch. The README splits the submission's claims in two:

- **Tier A** — zero policy violations against blind retry's 2,493, 441 attempts
  against its 4,652, 313
  contacts against 1,768, while recovering 86% of what blind retry recovers. These are
  counts of actions and rule evaluations, so no economic assumption can move them.
- **Tier B** — highest net value. This one is conditional, and the condition is named
  below.

Nothing in this section touches Tier A.

**Counters are in-process.** Strong consistency by virtue of being one process. At scale
two workers can each read 14 attempts and each authorise a 15th, producing 16. The fix
is not eventual consistency with reconciliation — by the time you reconcile, the fine
exists. It needs a compare-and-set reservation (increment first, act second, release on
failure), which degrades safely: a crashed worker leaks one attempt, costing a lost
recovery rather than a fine.

**Idempotency is in-process.** Verified against the live sandbox: Razorpay does **not**
deduplicate on `receipt` — the same receipt mints a second order. The client keeps its
own map, but a restart loses it and a second worker never had it. Production needs it in
the same durable store as the ledger, keyed by (event_id, action), written *before* the
outbound call.

**Tamper-evident, not tamper-proof.** Write access allows recomputing the chain forward.
Needs an external anchor — publishing the head hash somewhere the same actor does not
control. `Ledger.head` and `compliance_certificate()` exist for exactly that.

**Every economic parameter is assumed.** None is measured from real merchant data.
`docs/sensitivity.md` reports how hard each is working; one of them carries the entire
Tier B claim.

**Two causes are unidentifiable.** `risk_blocked` and `issuer_down` sit at 0% recovery
even at the Bayes-optimal ceiling for generic declines. Reported per-cause rather than
hidden in an aggregate.

**The simulator is ours.** Priors are seeded only from published external data and every
generative parameter is committed, but we wrote the generator. Compliance, audit
integrity, replay determinism, and action counts are unaffected by this. Recovery
figures are not, and are labelled accordingly.
