# What to say — word for word (final)

This is the finished script. Read it aloud a few times before recording — not to
sound like you're reading, but to find the handful of words that don't sit right
in your mouth and swap them for ones that do. **The numbers do not move.** Every
figure below is exact on purpose — a rounded number sounds like a guess, an
exact one sounds like a measurement, and you measured everything here.

Companion doc: `docs/demo-guide.md` has the shot-by-shot visual plan — what's on
screen at every second, including on-screen text that carries some of the detail
so you don't have to say every number out loud.

**~700 spoken words, written as full sentences on purpose** — an earlier pass
of this script cut so hard it turned into clipped fragments, which read as
robotic rather than pitched. That's fixed now; this version should sound like
a person talking, not a list of facts.

Here's the honest timing math. At a natural pace (~160 wpm) that's about
4:20 of speaking. This script is also number-heavy — a figure like "two
thousand four hundred and ninety-three" has to be said more slowly and
deliberately than ordinary words, exactly like the delivery notes below ask
for — and real recording always adds time a silent read doesn't show: breath,
a restarted line, the couple of seconds this script asks you to hold while a
terminal renders. Put together, expect a real take to land around
**4:45–5:05** — close to the 5:00 cap, not comfortably under it.

So: do one full recorded take, not a silent read-through, before you touch
the video edit. If it comes in over 5:00, cut using the list near the bottom
of this file — don't speed-talk or clip sentences back into fragments to
compensate. A slightly longer script delivered like a person beats a shorter
one that sounds read off a card.

---

## 0:00–0:20 — Cold open

> Same batch, a thousand failed payments, eleven lakh rupees on the line.
>
> A blind retry bot — stripped of the buzzwords, what most "AI revenue
> recovery" actually is — recovers fifty-nine thousand, seven hundred and
> fifty-five rupees more than mine does, and breaks a card-network or RBI
> rule two thousand four hundred and ninety-three times to get there. Mine
> breaks zero.
>
> That trade is the whole point.

---

## 0:20–0:55 — The problem nobody names correctly

> A failed payment isn't one problem. It's five.
>
> A card declines. A checkout gets abandoned. A subscription bounces. And
> two you've probably never heard named: a payment the bank already
> approved that the merchant forgot to collect, and one that arrives after
> the customer's already given up. Together, those two are almost thirteen
> percent of the money at risk, and there's nothing to retry — you just go
> get it.
>
> For the ones that actually failed: on UPI, eighty-two percent of declines
> are the bank saying no on purpose, and legally, some you can't even retry.

---

## 0:55–1:40 — How it actually decides

> Every at-risk rupee goes through the same four steps.
>
> First, diagnose the real cause, not just the error code — ninety-four
> percent lookup against Razorpay's own docs, the rest genuine inference,
> because the bank didn't say why.
>
> Then, a rulebook, before anything else: eleven hard rules today, covering
> attempt caps, RBI's notice window, consent, and contact fatigue. Eleven
> isn't the claim, though — the pattern is, since adding a twelfth is one
> file, not a rewrite.
>
> Only after that does it ask if acting is worth it, weighing success
> against every real cost, including losing the customer for good.
>
> And every decision gets sealed into a hash-chained record, forever —
> tamper-evident, not tamper-proof, with the real fix, an external anchor,
> already built in.

---

## 1:40–2:15 — One real refusal

> Five thousand two hundred and eighty-three rupees. Insufficient funds.
> Seven rules checked, and six of them pass. Then: this customer opted out.
>
> Blocked, full stop. It doesn't matter that the money's just sitting there.
> Consent overrides the profit calculation.

---

## 2:15–2:50 — The comparison, and the split that matters

> Four strategies, one batch, the exact same code grading all of them.
>
> Let's say it plainly: blind retry wins on raw recovery, and loses
> everywhere else — four thousand six hundred and fifty-two attempts against
> my four hundred and forty-one, six times the contacts, two thousand four
> hundred and ninety-three violations against zero.
>
> Here's the part worth sitting with: those counts don't depend on any cost
> assumption I made. I checked that four ways, including zero cost, and
> they don't move — nobody can argue with a count.

---

## 2:50–3:25 — Breaking it on purpose

> A green test suite proves the tests pass, not that they'd catch a real
> break. So I built something whose only job is to sabotage my own rules.
>
> *(mutation check runs)* Eight for eight, caught. But building that tool
> found something worse first: my main safety test was passing without
> testing anything, twice — both fixed now, both sitting in the commit
> history, not smoothed over.

---

## 3:25–3:55 — Where I'm wrong

> The "worth more" claim rests on exactly one assumption: that annoying a
> customer costs something, even a little.
>
> Watch what happens if it costs nothing. *(drag the slider to zero)*
>
> Blind retry wins, by about nine percent — printed by the tool itself,
> right on the page, with a test whose entire job is making sure the other
> guy wins in exactly this spot.

---

## 3:55–4:20 — Not luck, and not just rules

> A hundred and sixty tests back this up. Fifty random batches, fifty
> thousand payments, zero violations every time, plus a batch built to be
> hostile on purpose — and it held there too.
>
> I also built a Claude classifier for the toughest declines, then measured
> its ceiling before trusting it: forty-six point six against a theoretical
> best of forty-eight point seven. Barely two points of headroom, so I cut
> it.
>
> And this is deliberately not a free-acting agent — in a domain where one
> wrong move means a real fine, the responsible build is the bounded core a
> safe agent sits inside, not something that acts first and explains later.

---

## 4:20–4:45 — Close

> Razorpay already has smart retry timing at the gateway — I'm not claiming
> to have beaten that. This sits one layer up, on what a gateway can't see.
>
> Every number here runs from one command, right now. Thanks for watching.

---

## If you're still over time, cut in this order

1. The UPI-decline line in the problem section, and the last sentence of the
   cold open.
2. In "Not luck, and not just rules," drop the two Claude-ceiling
   percentages — keep just "I measured its ceiling, and it wasn't worth it."
3. **Never cut:** the refusal walkthrough, the mutation-check moment, or the
   sensitivity slider. Those three are the whole demo.

## Delivery notes

- **Don't say "AI agent."** Say what it does instead — everyone judging today
  has heard the phrase and it tells them nothing.
- **Pause before a number, not after.** Half a second of silence before
  "fifty-nine thousand, seven hundred and fifty-five" makes it land as a
  fact, not filler.
- **Let the terminal finish rendering before you talk over it.** Two seconds
  of quiet while text appears is fine. Talking over unreadable text isn't.
- **If you flub a line, stop, breathe, restart the sentence.** A clean
  restart cuts easily; a mid-sentence patch reads as nervous even when it
  wasn't.
- **Time yourself on an actual recorded take, not a silent read-through.**
  A silent read always runs faster than a recorded one — breath, emphasis,
  and the small pauses this script asks for all add real seconds a silent
  read skips. If your first full take lands past 4:50, trim further using
  the list above rather than speeding up your delivery.
