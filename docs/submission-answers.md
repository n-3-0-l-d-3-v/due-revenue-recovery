# Submission form — long-answer questions

Drafted to paste directly into the buildathon form. Kept short on purpose —
concise enough that a reviewer skimming a hundred entries actually reads the
whole thing — without dropping the numbers that back each claim.

---

## Project Objectives — What does it solve?

A failed payment isn't one problem, it's five. Most "recovery" tooling only
sees one: the retry. Due covers the full portfolio — failed payments,
abandoned checkouts, halted mandates, plus two categories almost nobody
names: **authorised-but-uncaptured** payments (bank already said yes,
merchant forgot to collect) and **late authorisations** (bank said yes after
the customer gave up). Together these are 12.7% of the money at risk in the
sample batch — money a retry bot scores as ₹0, because there's nothing to
retry.

For everything else, Due answers three questions in strict order: **what
happened** (root cause, 94% direct citation against Razorpay's docs, 6%
genuine inference where the bank gave no reason), **is acting allowed** (a
compliance gate — network attempt caps, RBI's e-mandate window, consent,
contact fatigue — checked *before* any value judgement, so profit can never
outvote a rule), and only then **is it worth it** (expected recovery against
every real cost, including the risk of losing the customer for good).

Measured on the same batch, same scoring code: a strategy that ignores cause
and compliance recovers ₹59,755 more — by breaking a network or RBI rule
2,493 times. Due recovers 86% of that money with **zero** violations and net
value ₹565,138 higher. The exact condition under which that ranking flips is
published and locked by an automated test, not just asserted.

---

## Build Challenges & Technical Obstacles — What issues did you face, and how did you solve them?

- **Compliance had to be un-outvotable, not just usually respected.** Folding
  it into the same scoring pass as expected value means a tuned-enough scorer
  eventually learns a small violation is worth a large recovery. Fixed
  architecturally: the gate runs first, and the object it evaluates has no
  access to expected value at all — profit is structurally invisible at
  decision time, so it can't win.

- **A green suite doesn't prove the tests would catch a real break.**
  `tools/mutation_check.py` deliberately sabotages each of 8 safety
  invariants and confirms the suite fails loudly for every one. Building it
  found two of my own tests passing **vacuously** — one checked the retry cap
  against the same config it was validating; the other generated test data
  too sparse to ever hit the case it claimed to cover. Both fixed, both in
  the commit history.

- **The headline "worth more" claim rested on one unstated assumption** —
  that repeated contact costs the merchant something, even a little. I swept
  that cost to exactly zero and found the naive strategy wins there, by about
  9%. That boundary is now a permanent test asserting the *other* strategy
  wins in that regime — a claim with a published failure point is more
  credible, not less.

- **Razorpay's `receipt` field doesn't deduplicate**, contrary to my initial
  assumption — verified live against their test sandbox, two calls with the
  same receipt produced two order IDs. Fixed with a client-side idempotency
  map keyed by (event, action) before it was ever a duplicate-charge bug.

- **A 15,000-event stress batch took 2 minutes instead of ~16 seconds** —
  a lookup was being rebuilt inside the execution loop instead of once before
  it. Found by the stress test itself, fixed by hoisting it out, confirmed
  with a before/after timing check.

- **Deciding what to actually be judged on.** The track says "agentic"; the
  honest call in a domain where one wrong autonomous move is a real
  compliance fine was to build the bounded, auditable core a safe agent sits
  inside, not a free-acting one — and say so. Same logic on AI: I built a
  Claude classifier for the 5.7% of declines with no stated reason, measured
  its ceiling (46.6% achieved vs. 48.7% theoretical best), and cut it — about
  two points of headroom isn't worth a per-event API call. Knowing when not
  to reach for a model felt like the more relevant signal for this role.
