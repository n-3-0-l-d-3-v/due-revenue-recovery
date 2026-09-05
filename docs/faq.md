# Hard questions, answered directly

The rest of `docs/` explains what was built. This file exists for the questions a
sharp reviewer asks *about* it — the ones a demo doesn't answer on its own. Every
answer here is the same one given anywhere else in this project: precise about
what's known, explicit about what isn't, no hedging into false confidence in
either direction.

---

### "Is there actually AI in this? The track title says 'agentic.'"

Built and cut, on evidence — not absent by oversight.

A Claude-based classifier was built for the one place a genuine prediction is
needed: the 5.7% of failures where the bank returns a generic decline code with
no reason attached (`card_declined`, `payment_failed`) — the reason was never
transmitted, so it has to be inferred from context rather than looked up.

Before trusting it, its ceiling was measured against two baselines:

| | inference accuracy |
|---|---|
| always guess the majority cause | 43.1% |
| the shipped heuristic (no LLM) | 46.6% |
| the theoretical best any predictor could reach | 48.7% |

About two points of headroom, on 5.7% of events. Not worth a per-event API call,
so the LLM path was removed rather than shipped for the sake of having one.
`ClaudeInferencer` (`due/core/diagnose.py`) is kept in the tree and documented,
not deleted, because the decision should be reproducible.

On "agentic": this is deliberately **not** a free-acting agent, and that's the
correct call for a domain where a wrong autonomous action means a real fine or a
real compliance breach. The system built here is the bounded core a safe agent —
human-run or AI-run — has to sit inside: the part that makes an illegal or
non-compliant action *structurally impossible* to take, regardless of what
anything upstream decides is optimal. Building the guardrail is the less
glamorous half of agentic systems in a regulated domain, and it's the half most
demos skip because it doesn't look as flashy as an agent doing things.

---

### "Are 11 rules enough? A real system needs way more."

Correct, and that's not a gap this project pretends to close.

11 rules is not the claim. The claim is the *pattern*: every rule is the same
shape — a citation, a parameter set, one predicate function, registered once
(`recoup.core.policy.engine`, the `@predicate` decorator). Adding rule #12 or
#100 is mechanical: one more entry in `rules.yaml`, one more function, no change
to the engine itself. `PolicyEngine.__init__` even refuses to start if a
declared rule has no matching predicate — a rule that exists on paper but isn't
enforced is a silently open gate, which is worse than no rule at all.

The 11 built here cover the highest-value, most-cited real constraints in
Indian digital payments — Visa/Mastercard attempt caps, RBI's e-mandate
framework, consent, contact fatigue. They are not a complete legal rulebook.
PCI-DSS specifics, state consumer-protection law, chargeback-specific rules,
and cross-border rules are all real and all absent. The architecture is built
so adding them doesn't require a redesign — that's the thing being
demonstrated, not "11 rules is sufficient for production."

---

### "Why hasn't Razorpay — or anyone — already built this?"

Partially, they have. Precision matters here, so the claim is narrower than it
might sound.

Razorpay's own **documented** subscription retry is fixed: retry daily for
three days, then mark the subscription `halted`. Separately, they announced an
**Intelligent Retry Engine** in beta, for one instrument — UPI Autopay —
claiming +8% over baseline. Both can be true at once: a stable documented
default, plus a newer beta feature for one corridor. What's *not* claimed here
is certainty about Razorpay's current internal production behaviour beyond
what's publicly documented — public docs can lag real internal state, and
saying otherwise would be guessing.

What multiple providers (Stripe, Adyen, Razorpay) already do, publicly: smart
*timing* for a single retry decision. What wasn't found publicly documented, as
one combined system, anywhere: all five leak points unified into one decision
layer, a hard compliance gate that runs *before* any value judgement rather
than only optimising success probability, a tamper-evident audit trail of every
decision, and customer fatigue and lifetime value priced into the same
optimisation as recovery probability. That's a gap in what's shipped and
documented publicly — not a claim that no engineer anywhere has an unpublished
internal version of some of these pieces.

---

### "Isn't 'tamper-evident, not tamper-proof' a security hole for a fintech company?"

It's the opposite: overclaiming "tamper-proof" would have been the actual hole.

Any single append-only log — hash-chained or not — has this exact limitation if
one party controls the storage. It's true of a bank's own internal ledger. It's
true of Git: someone with full history-rewrite access can force-push a
fabricated history, a known, real limitation of Git itself. It's even true of
one blockchain node in isolation — a blockchain's real security doesn't come
from hashing, it comes from thousands of independent parties having to agree,
which hash-chaining alone does not provide.

The real fix has a name — **external anchoring**: periodically publish just the
chain's head fingerprint somewhere outside your own control (a third-party
notary, WORM storage such as AWS S3 Object Lock, which real banks use for
records retention). `Ledger.head` and `compliance_certificate()` exist
specifically so that step can be bolted on later without changing anything
upstream. Naming the exact missing step, precisely, is the sign of security
awareness. Pretending the chain can't be forged at all would have been the
tell that it wasn't understood.

---

### "This is a simulator. They wanted something real that runs."

Two different things are being asked about here, and only one of them is
synthetic.

**Synthetic:** the batch of example transactions used to demonstrate and
measure the decision logic.

**Real, running, no mocks in the path:** the decision engine is real, callable
code. The Razorpay integration makes real HTTP calls to Razorpay's actual
test-mode servers — real order IDs come back, a real payment link exists that a
real person can open and pay with a test card (`live_demo.py --live`). That's
not a shortcut; it's the standard way every Razorpay integration is built and
tested by every real merchant, before it ever touches live money.

The batch is synthetic because no company — Razorpay included — hands a student
applicant real, commercially sensitive merchant transaction data, and because
testing a brand-new financial decision system against real customers *before*
validating it in simulation isn't something a responsible engineer does, ever.
Simulating first is the responsible sequence, not a workaround for one.

---

### "Are you sure there's no better strategy than this one?"

No — and pretending certainty here would be the actual red flag, not admitting
its absence.

This was built solo in about nine days. More sophisticated approaches clearly
exist, and several were explicitly considered and *deferred* — meaning named
and set aside on purpose, not missed:

- A learned timing model (a contextual bandit) instead of the current
  rule-based salary-cycle prior
- A linear-programming allocator spending the retry/contact budget across a
  whole batch at once, instead of scoring each event independently
- A trained classifier for ambiguous declines instead of the hand-weighted
  heuristic
- Formal verification of the policy rules instead of property-based testing

Each was cut for the same reason the LLM classifier was cut: a fully tested,
honestly measured, boring-but-correct system beats a more sophisticated-sounding
one that couldn't be verified in the time available. That prioritisation call
is itself the thing being demonstrated, not a limit on what's possible.

---

### "What's actually out of scope, that nobody's asked about yet?"

- **No receivables or invoice handling.** The track's example list includes a
  "B2B receivables chaser." This covers the payment-failure family of leak
  points, not invoices — a scope choice, not an oversight.
- **No persistence layer.** Everything lives in memory during a run; the JSONL
  ledger export is the only durability story. A real deployment needs an
  actual database.
- **Single market.** Every compliance rule is India/RBI-specific. Extending to
  another country's payment law means writing new rules — mechanical, per the
  pattern above, but not done here.
- **No multi-tenancy.** No concept of different merchants with different risk
  appetites beyond one hardcoded category field used in a couple of places.
- **Two causes are unidentifiable even in principle.** `risk_blocked` and
  `issuer_down` sit at 0% recovery even at the Bayes-optimal ceiling for a
  generic decline code — not a flaw in the code, an honest measurement that the
  bank's silence removes the information needed, for anyone, ever.
