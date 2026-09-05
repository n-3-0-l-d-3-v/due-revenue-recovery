# Submission form — long-answer questions

Drafted to paste directly into the buildathon form. Kept short on purpose, so
a reviewer skimming a hundred entries actually reads the whole thing, without
dropping the numbers that back each claim.

---

## Project Objectives — What does it solve?

A failed payment isn't one problem. It's five. Most "recovery" tooling only
sees one of them: the retry. Due covers the full portfolio: failed payments,
abandoned checkouts, halted mandates, plus two categories almost nobody
names. **Authorised-but-uncaptured** payments, where the bank already said
yes and the merchant just forgot to collect. And **late authorisations**,
where the bank said yes after the customer had already given up. Together
these make up 12.7% of the money at risk in the sample batch. A retry bot
scores that money as ₹0, because there's nothing to retry. You just have to
go get it.

For everything else, Due answers three questions in strict order. First,
what actually happened: the root cause, not just an error code. 94% of the
time that's a direct citation against Razorpay's own documentation; the rest
is genuine inference, because the bank gave no reason. Second, is acting even
allowed: a compliance gate checks network attempt caps, RBI's e-mandate
window, active consent, and contact fatigue before any value judgement runs
at all, so profit can never outvote a rule. Only then, third, is it worth it:
expected recovery weighed against every real cost, including the risk of
losing the customer for good.

Measured on the same batch, with the same scoring code for every option: a
strategy that ignores cause and compliance recovers ₹59,755 more, and gets
there by breaking a network or RBI rule 2,493 times. Due recovers 86% of that
same money with zero violations, and comes out ₹565,138 ahead on net value.
The exact point where that ranking flips is published and checked by an
automated test, not just claimed.

---

## Build Challenges & Technical Obstacles — What issues did you face, and how did you solve them?

**Compliance had to be impossible to outvote, not just usually respected.**
My first instinct was to fold it into the same scoring pass as expected
value. That's a bad idea: give a scorer enough tuning pressure and it will
eventually decide a small violation is worth a large recovery. I fixed this
architecturally instead. The gate runs first, and the object it evaluates
simply has no access to expected value. Profit isn't allowed to see the
scoreboard until compliance has already decided, so it can't win.

**A green test suite doesn't prove the tests would catch a real bug.** So I
wrote `tools/mutation_check.py`, which deliberately breaks each of 8 core
safety rules and checks that the suite catches every one. Building it turned
up two of my own tests that were passing without actually testing anything:
one checked the retry cap against the same config value it was supposed to
be validating, and the other generated test data too sparse to ever hit the
case it claimed to cover. Both are fixed, and both are visible in the commit
history.

**The headline "worth more" claim rested on one assumption I hadn't stated
out loud:** that repeatedly contacting a customer costs the merchant
something, even a little. So I swept that cost down to exactly zero and
checked what happens. The naive strategy wins there, by about 9%. That
boundary is now a permanent test that asserts the other strategy wins in
that specific regime. A claim with a published failure point is more
credible than one without, not less.

**Razorpay's `receipt` field doesn't deduplicate orders,** which I'd
originally assumed it did. I checked this live against their test sandbox:
two calls with the same receipt value came back as two separate order IDs.
Fixed with a client-side idempotency map, keyed by event and action, before
it ever became a real duplicate-charge bug.

**A 15,000-event stress batch took over two minutes instead of about sixteen
seconds.** The cause was a lookup getting rebuilt inside the execution loop
instead of once before it. The stress test I'd built for an unrelated reason
caught it; I fixed it by hoisting the lookup out of the loop and confirmed
the fix with a before-and-after timing check.

**Figuring out what I should actually be judged on.** The track calls for
something "agentic." In a domain where one wrong autonomous move is a real
compliance fine, the honest engineering call was to build the bounded,
auditable core a safe agent has to sit inside, not a free-acting agent
itself, and to say so plainly rather than let it look like an oversight. The
same thinking applied to AI: I built a Claude classifier for the 5.7% of
declines where the bank gives no reason at all, then measured its ceiling
before trusting it. It reached 46.6% against a theoretical best of 48.7%,
about two points of headroom, which isn't worth a per-event API call. So I
cut it. Knowing when not to reach for a model felt like the more useful
thing to demonstrate for this role.
