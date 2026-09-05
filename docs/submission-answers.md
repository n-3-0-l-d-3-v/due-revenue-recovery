# Submission form — long-answer questions

These are drafted to paste directly into the buildathon form. Same voice as
the pitch — direct, numbers-first — but written to be read on a screen at
whatever pace a reviewer chooses, not performed, so they lean on the exact
figures a bit harder than the spoken script does.

---

## Project Objectives — What does it solve?

A failed payment isn't one problem, it's five, and most "recovery" tooling
only sees one of them: the retry. Due handles the full portfolio — failed
payments, abandoned checkouts, halted mandates, and the two categories almost
nobody names: **authorised-but-uncaptured payments** (the bank already said
yes, the merchant just didn't collect) and **late authorisations** (the bank
said yes after the customer already gave up). In the sample batch this
project measures against, those two account for 12.7% of the money at risk —
money a retry-based system scores at exactly ₹0, because there's nothing to
retry. You just have to go get it.

For the payments that did fail, Due answers three questions in order, and
refuses to answer the third before the first two: **what actually happened**
(root cause, not just an error code — 94% of the time a direct citation
against Razorpay's own documentation, the rest genuine inference where the
bank's response never carried a reason), **is acting even allowed** (a
hard-coded compliance gate — card-network attempt caps, RBI's e-mandate
notice window, active consent, contact fatigue — checked *before* any value
judgement, so no amount of "but it's profitable" can override a rule), and
only then **is acting worth it** (expected recovery value against every real
cost: the attempt itself, contacting the customer, the risk of losing them
for good).

The result, measured against the same batch with identical scoring code: a
strategy that ignores cause and compliance recovers ₹59,755 more, by breaking
a card-network or RBI rule 2,493 times to do it. Due recovers 86% of that
money with **zero** rule violations and net value ₹565,138 higher, because
compliance breaches and unnecessary customer contact are real costs, not
externalities. That comparison, and the exact boundary condition under which
it stops holding, is published and locked by an automated test rather than
asserted — the honest version of "it works" is "here's exactly where it stops
working," and this project states both.

---

## Build Challenges & Technical Obstacles — What issues did you face, and how did you solve them?

**The gate had to be structurally incapable of being outvoted, not just
usually right.** Early on, it would have been simpler to fold compliance into
the same scoring pass as expected value — one function, one set of weights.
That design has a fatal property: given enough tuning pressure, a scorer will
eventually learn that a small compliance violation is worth a large
recovery. The fix wasn't a stronger scorer, it was an architectural one — the
gate runs first, and `GateContext` (the object the gate evaluates) is
constructed without access to expected value at all. It's not a rule that says
"don't let compliance lose to profit." It's a type signature that makes
profit invisible at decision time, so it cannot possibly win.

**A green test suite doesn't prove the tests would catch a real break.** To
check that, I wrote `tools/mutation_check.py`, which deliberately sabotages
each of the eight core safety invariants and confirms the suite fails loudly
for every one. Building it surfaced two of my own tests that were passing
**vacuously** — one validated the retry cap against the same config value it
was supposed to be checking against (raise the cap, the assertion rises with
it, always green), the other generated test payment IDs from a range so wide
that no single payment ever accumulated the second retry the test claimed to
be testing. Both are fixed, and both are visible in the commit history rather
than quietly folded into a later commit — a bug you found by actively trying
to break your own system is evidence the system got safer, not something to
hide.

**A claimed advantage that only held under one unstated assumption.** The
headline "Due is worth more" result depends on exactly one qualitative
assumption: that repeatedly contacting or retrying a customer costs something
beyond direct fees, even a small amount of goodwill. I didn't want to
discover that dependency after publishing the claim, so I swept the cost
model to its extreme — retention cost set to exactly zero — and found the
naive strategy wins there, by about 9%. That boundary is now a permanent,
named test (`test_ranking_flips_when_all_retention_cost_is_removed`) that
asserts the *other* strategy wins in that regime. A claim with a published
failure boundary is more credible than one without, not less.

**An unverified assumption about the real payment gateway.** I'd assumed
Razorpay's `receipt` field deduplicated retried orders — it doesn't; verified
live against their test-mode sandbox, two calls with the same receipt value
produced two distinct order IDs. Left unfixed, that's a duplicate-charge risk
the moment a retry gets sent twice by accident. Fixed with a client-side
idempotency map keyed by (event, action) that short-circuits a repeat call
before it reaches the network.

**A silent performance cliff that only showed up at scale.** The 1,000-event
demo batch ran in about two seconds; a 15,000-event stress batch, built to
check the compliance guarantee still held outside the toy example, took over
two minutes — a per-action lookup was being rebuilt inside the execution loop
instead of once before it. Found by running the stress test I'd built for an
unrelated reason (proving zero violations survives scale), fixed by hoisting
the lookup out of the loop, confirmed with a before/after timing comparison.

**Deciding what an AI engineering candidate should actually be judged on.**
The track title says "agentic," and the honest technical call for a domain
where one wrong autonomous action is a real compliance fine was to *not*
build a free-acting agent — to build the bounded, auditable core a safe agent
sits inside instead, and to be explicit that this was a deliberate scope
decision rather than something missing. I also built and then measured a
Claude-based classifier for the one place real inference was needed — the
5.7% of declines where the bank gives no reason at all — and cut it after
measuring its ceiling against a theoretical best (46.6% achieved vs. 48.7%
theoretically possible: about two points of headroom, not worth a per-event
API call). Knowing when *not* to reach for a model, and being able to say
exactly by how much, felt like the more relevant signal to send for this role
than shipping an LLM call for its own sake.
