# Build Plan — Revenue Recovery Control Plane

Razorpay AI Buildathon, Track 03. Solo build. Ship **31 Aug 2026**, deadline **5 Sept 2026**.

Working name: **Due** (rename later if something better lands — do not spend an hour on this).

---

## The one-sentence pitch

> A merchant-side control plane that turns every at-risk rupee into a bounded, policy-gated recovery decision — and proves in a replayable audit trail that no action ever breached a card-network attempt cap or an RBI e-mandate rule.

## Non-negotiable design rule

**The policy gate evaluates before the learner. Always.**

```
RiskEvent
  → Diagnose            (reason code → root cause)
  → Enumerate actions   (retry / delay / nudge / instrument-switch / terminal / escalate)
  → POLICY GATE         (filters to the permitted set — hard constraints only)
  → Score EV            (net value over permitted actions only)
  → Allocate            (budget-constrained selection across the batch)
  → Execute             (RE-VALIDATE gate at execution time, then act idempotently)
  → Ledger              (hash-chained decision record)
```

The learner never chooses an action the gate did not already permit. Learning therefore **cannot** generate a fine or a compliance breach. This is the architectural claim the whole submission rests on — say it in the first 60 seconds of the video.

Second rule: **re-validate at execution time.** A decision made now that executes in 18 hours must re-check consent and attempt counters before acting. Consent is stateful and can change after the RBI pre-debit notification.

---

## Architecture

```
due/
├── sim/               event generator + ground truth
├── core/
│   ├── models.py      RiskEvent, Diagnosis, CandidateAction, DecisionRecord, Outcome
│   ├── diagnose.py    reason-code → root cause (evidence-linked table + LLM for ambiguous)
│   ├── policy/
│   │   ├── rules.yaml declarative gates
│   │   └── engine.py  evaluator, conflict detection, invariant checks
│   ├── counters.py    attempt counters (per instrument-token, per merchant, windowed)
│   ├── scorer.py      net-value EV
│   ├── allocator.py   budget-constrained selection (greedy → LP)
│   ├── executor.py    idempotent, dry-run default, circuit breaker
│   ├── ledger.py      hash-chained append-only audit
│   └── exceptions.py  exception queue with priority + closure
├── harness/           counterfactual runner + sensitivity analysis
├── rzp/               Razorpay test-mode client
├── api/               FastAPI
└── ui/                React dashboard
```

### DecisionRecord — the central schema

Every decision emits one. This is the audit trail, the debug tool, and the demo.

```python
DecisionRecord:
    id, batch_id, event_id, timestamp
    event:            RiskEvent snapshot
    diagnosis:        root_cause, confidence, evidence_ref
    candidates:       [CandidateAction]
    gate_results:     [{rule_id, verdict, rationale}]   # every rule, pass AND fail
    permitted:        [CandidateAction]
    ev_components:    {p_recovery, amount, attempt_cost, contact_cost,
                       support_cost, churn_risk, issuer_trust_penalty}
    chosen:           CandidateAction | None
    not_chosen_why:   str | None
    executed_at, idempotency_key, outcome
    prev_hash, hash
```

`gate_results` logs **every rule evaluated, including the ones that passed.** That is what makes the compliance claim provable rather than asserted.

### Policy gates (rules.yaml)

Hard constraints, versioned, each citing its source:

- `network.attempts_per_card_30d <= 15` — Visa/MC
- `network.attempts_per_card_24h <= 9` — Visa/MC
- `network.do_not_retry_codes` — MAC 03 and terminal reason codes, hard block
- `rbi.emandate_pre_debit_notice >= 24h` — schedule, notify, wait, then debit
- `rbi.afa_required_above_15000` — ₹1,00,000 for insurance / MF / credit-card bills
- `consent.revalidate_at_execution` — opt-out honoured
- `contact.max_per_customer_per_week <= 2` — fatigue cap
- `value.min_ev_threshold` — don't spend ₹60 chasing ₹40
- `obligation.still_valid` — never recover a cancelled or unfulfillable order

Engine must detect **contradictory rules** and prove the invariant *no execution path reaches >3 merchant-initiated retries*.

### Net-value scorer

```
EV = P(recovery | reason, instrument, timing, history) × amount
   − attempt_cost − contact_cost − expected_support_cost
   − churn_risk × customer_LTV
   − issuer_trust_penalty
```

`issuer_trust_penalty` rises with the merchant's recent decline rate against that issuer. This is the term that protects future approval rates and almost nobody models it.

### Data minimisation (do this from commit one)

Never store PANs. Instrument identity is a salted hash / token only. Contact details tokenised. Explicit retention policy in the README. Cheap, and it reads as adult engineering to a payments panel.

---

## The simulator

Ground truth is the whole point: we know the true root cause and the true counterfactual outcome, so precision/recall and recovered-value are *measurable*, not asserted.

Seeded **only from published external priors** — NPCI technical-vs-business decline split (18.26% / 81.7%), documented Razorpay reason-code semantics, real network caps, published dunning benchmarks. Generative parameters committed to the repo so anyone can inspect the assumed world.

Must include:
- **Correlated issuer-down days** — one issuer failing takes many payments with it
- **Contact fatigue** — success probability decays with contact volume
- **Per-customer payment-day history** — so salary-cycle priors have something to condition on
- Uncaptured authorizations and late-auth events, not just outright failures

## The counterfactual harness — this wins the pitch

Same batch, four strategies, side by side:

| Strategy | What it represents |
|---|---|
| Do nothing | Baseline floor |
| Fixed T+3 | Razorpay's standard subscription retry |
| Blind retry | What most competing submissions effectively are |
| **Gated agent** | Ours |

Report for each: **₹ recovered, attempts spent, contacts sent, policy violations, estimated penalty exposure, net value.** Blind retry will "win" on raw recovery and lose badly on net value and violations. That table is the moment.

Then **sensitivity analysis**: sweep the priors, show the region where the gated agent still wins and name the region where it stops. Converts "you rigged it" into "here are the conditions under which this holds."

## Claim discipline

Two vocabularies, never blurred:

- **"Proven"** — compliance gates, audit integrity, replay determinism, throughput. These hold on any input.
- **"Simulated under stated priors"** — every recovery-rate and rupee figure.

And name the falsifier out loud: *"Replay against real traffic. If the timing priors don't hold, the learner degrades to the fixed schedule — and the policy and audit layers still work."*

---

## The quality bar

Quality first, time second. The target is not "more features" — it is **more checkable claims**.
At the top of the pile everyone has a working demo. What separates the top five from the top fifty:

1. **Does it survive interrogation?** Tests, proven invariants, honestly stated limits.
2. **Is the demo memorable?** One moment a judge retells to a colleague.
3. **Can a judge verify the claim in two minutes?** A live URL and a one-command run.
   If they must clone, install, and debug, they will skim the README and score on vibes.

Definition of done — all thirteen, or it isn't finished:

1. Runs end-to-end on live Razorpay **test-mode** API and on the simulator
2. Policy gate with **property-based tests proving** the attempt-cap invariant
3. Hash-chained ledger with tamper-evidence demo and deterministic replay
4. Unified portfolio across all five leak points
5. Net-value objective with every term separable and logged
6. Constrained bandit + offline policy evaluation with confidence intervals
7. Counterfactual across four strategies + sensitivity analysis
8. Exception queue with a human-in-the-loop interface
9. Compliance certificate generation
10. Deployed live demo
11. Test suite covering the core decision path
12. README + ARCHITECTURE a payments engineer respects
13. Polished 5-minute video, multiple takes

## Schedule — 9 days, ship Sept 3, submit Sept 4

| Day | Date | Deliverable |
|---|---|---|
| 0 | Aug 25 | ✅ Models, DecisionRecord, scaffold, README. **Remaining: Razorpay test keys, simulator v0** |
| 1 | Aug 26 | Simulator v1 — all five event types, correlated issuer-down days, contact fatigue, per-customer payment history. Policy DSL + engine + conflict detection |
| 2 | Aug 27 | Attempt counters + full gate path end-to-end + hash-chained ledger + tamper test. Diagnosis (evidence-linked table, LLM for ambiguous codes) |
| 3 | Aug 28 | Net-value scorer + unified portfolio queue + executor (idempotency, dry-run, circuit breaker) + exception queue with priority and closure |
| 4 | Aug 29 | **Live Razorpay integration** — real test payments, payment links, webhooks. Instrument-switch + post-`halted` flows |
| 5 | Aug 30 | Allocator (greedy → LP) + counterfactual harness (4 strategies) + sensitivity analysis |
| 6 | Aug 31 | Constrained bandit + offline policy evaluation (IPS / doubly-robust) + within-window quasi-experiment |
| 7 | Sept 1 | **FEATURE FREEZE.** Property-based tests, invariant proofs, replay/tamper/idempotency tests, adversarial self-review of every claim |
| 8 | Sept 2 | Dashboard polish + compliance certificate + deploy live demo + README/ARCHITECTURE + one-command run |
| 9 | Sept 3 | Video — script, rehearse, record 2–3 takes, edit |
| — | Sept 4 | Submit |
| — | Sept 5 | Deadline. Untouched buffer |

**Feature freeze on Sept 1 is non-negotiable.** Nine days becomes nine days of half-finished
features without a wall. Everything after the freeze is tests, docs, deploy, and video.

### Pre-committed cut order

Decided now, so no judgment calls get made while tired:

1. Offline policy evaluation — keep the bandit, claim less
2. LP allocator — greedy is fine
3. Deployed demo — fall back to one-command local run

**Never cut:** policy gate · audit ledger · test suite · video.

The video is a third of the submission and the thing everyone under-invests in. Most competitors
record one take the night before. This plan gives it a dedicated day and three takes.

## Video structure (5:00)

- **0:00–0:30** The number. ₹ recovered, attempts spent, zero violations.
- **0:30–1:15** The real problem: not "retry failures" but which are worth recovering, when, and when you are legally required to stop.
- **1:15–2:45** Live batch run. Decisions streaming. Show a blocked action and the exact rule that blocked it.
- **2:45–3:30** The counterfactual table.
- **3:30–4:15** Deliberate failure: inject API outage → circuit breaker → exception quarantine → ledger → clean resume.
- **4:15–5:00** Architecture in three boxes, ledger replay, honest limits, what's next.

## Tonight (Day 0)

1. Razorpay account + **test-mode API keys** (test mode needs no business verification)
2. `git init`, repo structure, dependencies
3. `core/models.py` — RiskEvent, DecisionRecord, CandidateAction
4. `sim/` — 200 events with ground truth, seeded from published priors
5. One real Razorpay test call: create an order, create a payment link
6. README stub with the positioning line and the Razorpay-overlap paragraph

Positioning paragraph goes in the README on night one, so it is never forgotten:

> Razorpay's Intelligent Retry Engine optimises the debit attempt at the gateway layer. This optimises the merchant's recovery portfolio — allocating a constrained, compliance-bounded budget across every at-risk rupee, and proving every decision stayed inside network and RBI limits.
