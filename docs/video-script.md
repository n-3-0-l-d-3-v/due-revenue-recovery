# 5-Minute Pitch Video — Script

Read this aloud. Do not improvise. Improvised takes run long, bury the numbers, and
lose the one line that matters.

**Total spoken words: ~720.** At a calm 150 wpm that is 4:48, leaving margin.

**Rule for the whole video:** lead with what cannot be argued with. Tier A first
(counts and rule evaluations), Tier B second (net value, with its condition stated).
Opening on the ₹565k gap invites *"where does that number come from?"* as the first
question instead of the last.

---

## Before you record

Have four terminals ready, pre-`cd`'d into the repo, font size ~18pt, dark theme:

| Terminal | Pre-typed command (do not press Enter yet) |
|---|---|
| A | `python demo.py` |
| B | `python tools/mutation_check.py` |
| C | `python live_demo.py --live` |
| D | `pytest -q` |

Also open: the counterfactual table section of `README.md`, and the Razorpay dashboard
showing the two orders with the identical receipt.

Record at 1080p minimum. Terminal only — no webcam needed, but keep audio clean.

---

## 0:00 – 0:25 · The result, immediately

> **SCREEN:** the counterfactual table, already on screen. No title card.

"Same batch of a thousand failed payments. Eleven lakh rupees at risk.

Look at the second row and the fourth. Blind retry — which is what most AI payment
recovery agents actually are — recovers **more money** than my system. Fifty-nine
thousand, seven hundred and fifty-five rupees more.

It also commits **two thousand four hundred and ninety-three** card network and RBI
violations. Mine commits zero. And it burns ten times the retry attempts to get there.

That gap is the whole project."

---

## 0:25 – 1:05 · The real problem

> **SCREEN:** `docs/domain-primer.md`, scroll the failure taxonomy table slowly.

"Recovering failed payments is not the hard part. The hard part is knowing which
failures are worth recovering, when to try, and when you are legally required to stop.

On UPI, **eighty-two percent** of failures are business declines — the bank
deliberately said no. Retrying those unchanged gets the same answer. And some codes are
terminal: retry an expired card or a fraud-flagged payment and Mastercard charges you
per attempt under its Excessive Attempts programme.

There's also money nobody looks at. **Twelve point seven percent** of the value in this
batch is authorised-but-uncaptured — the bank approved it, the customer consented, and
the merchant never claimed it. It appears in no failure dashboard, because nothing
failed. A retry-based system scores exactly zero against it. You just have to capture."

---

## 1:05 – 1:50 · The architecture, and a live block

> **SCREEN:** Terminal A. Press Enter. Let section 3 render, then scroll to the gate blocks.

"So every event runs through the same path: diagnose the root cause, enumerate the
actions that make sense for that cause, and then — before anything is scored — the
policy gate.

The gate runs **before** the scorer. Nothing downstream can choose an action the gate
did not already permit. That means no amount of optimisation can buy its way past a
compliance rule — by construction, not by training.

Here it is refusing. A hundred and nineteen actions blocked by the contact fatigue cap,
forty-seven by withdrawn consent. And every rule that *passed* is recorded too — because
a gate that logs only its refusals can prove it noticed some violations. It cannot prove
compliance."

---

## 1:50 – 2:40 · The counterfactual

> **SCREEN:** Terminal A, section 4 — the table. Then section 5, the Tier split.

"Four strategies, same events, same scoring code. Nobody scores themselves.

Fixed T+3 is Razorpay's own documented subscription retry — not a strawman. Blind retry
is the reason-agnostic version. Mine is the gated one.

Blind retry wins on recovery rate. It loses on everything else: four thousand six hundred
attempts against my four hundred and forty-one, two thousand four hundred violations
against zero.

And notice how the claims are split. The counts — zero violations, ten times fewer
attempts, eighty-six percent of the recovery — depend on **no economic assumption at
all**. I verified that under four cost models, including one where every cost is zero.
Those numbers cannot be argued with.

The net value number can. I'll come back to that."

---

## 2:40 – 3:20 · The tests catch a broken gate

> **SCREEN:** Terminal D — `pytest -q`, show 131 passed. Then Terminal B — mutation check.

"A hundred and thirty-one tests, fifteen of them property-based.

But a green suite proves the tests pass. It does not prove they would fail if the system
broke. So this deliberately breaks each safety rule and checks the suite notices.

All eight caught. And this found something: my headline invariant test — the one proving
retries never exceed the cap — was passing **vacuously**. Twice. It read the cap from the
same config it was validating, and it generated payment IDs so unique that no payment
ever reached a second retry. There was nothing to cap.

I'd have shipped a proof of nothing."

---

## 3:20 – 3:55 · The bug the live API found

> **SCREEN:** Terminal C, then the Razorpay dashboard showing two orders, same receipt.

"This runs against Razorpay's real test-mode API.

I used the `receipt` field as my idempotency key — that's the intuitive reading. So I
sent the same receipt twice.

Two orders. Two different IDs. Razorpay does not deduplicate on receipt.

In production that's a double charge: network timeout, automatic retry, customer billed
twice. I had written that exact failure mode into my own domain notes and then wrote it
into my client anyway. Reading the docs didn't catch it. Calling the API did.

It's fixed client-side now, and the remaining limitation — that the map is in-process —
is documented rather than hidden."

---

## 3:55 – 4:30 · Where my own claim fails

> **SCREEN:** Terminal A, section 6 — sensitivity.

"Back to net value. That claim depends on one assumption: that repeatedly retrying and
contacting a customer costs you something in retention.

So I measured what happens if it costs nothing. Here — with all retention cost removed,
**blind retry wins.** By about nine percent.

That's in my README, it's printed by the demo, and there's a test that asserts the
competitor wins in that region. If someone quietly deletes it, the suite fails.

The counts from earlier are untouched by this. Zero violations is still zero."

---

## 4:30 – 5:00 · Close

> **SCREEN:** Terminal A, section 8 — exception queue. Then the repo tree.

"Sixteen percent of decisions go to a human, with a suggested action and a closure path
that survives the next batch. A system claiming a hundred percent automation is either
lying or unsafe.

Razorpay already ships an Intelligent Retry Engine that does context-aware retry timing
at the gateway layer. This isn't a claim to have invented smart retries. It sits one
layer up — the merchant's recovery portfolio, where contact fatigue, customer lifetime
value and issuer standing live, and where a PSP structurally cannot see.

Everything I've shown runs in one command. Thank you."

---

## What to cut if you run long

In this order — the last item is load-bearing and never gets cut:

1. The uncaptured-authorisations paragraph (0:25–1:05) — trim to one sentence
2. The domain-primer scroll — cut to a static frame
3. The exception queue (4:30) — trim to one sentence
4. **Never cut:** the Tier A counts, the mutation check, the sensitivity boundary

## Common mistakes to avoid on the take

- **Do not say "AI agent."** Say what it does. The judges have heard "AI agent" four
  hundred times today and it signals nothing.
- **Do not round.** "Two thousand four hundred and ninety-three" lands as measurement.
  "About two and a half thousand" lands as estimate.
- **Do not apologise for the simulator.** State it once, in the sensitivity section,
  and move on. Hedging repeatedly reads as insecurity about the whole result.
- **Do not skip the boundary section to save time.** It is the single most credible
  thirty-five seconds in the video. Anyone can show a demo that works; almost nobody
  shows where their own claim breaks.
- **Let the terminal finish rendering** before you talk over it. Dead air for two
  seconds is fine; talking over output nobody can read is not.

## After the first take

Watch it once with the sound off. If you cannot tell what is happening from the screen
alone, the screen is wrong, not the script. Then watch with sound only — if the numbers
don't land as spoken words, slow down.

Expect take one to run 6:30. That's normal. The cuts above get you to 5:00.
