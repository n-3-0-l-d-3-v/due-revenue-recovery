# What to say — word for word (final)

This is the finished script. Read it aloud a few times before recording — not to
sound like you're reading, but to find the handful of words that don't sit right
in your mouth and swap them for ones that do. **The numbers do not move.** Every
figure below is exact on purpose — a rounded number sounds like a guess, an
exact one sounds like a measurement, and you measured everything here.

Companion doc: `docs/demo-guide.md` has the shot-by-shot visual plan — what's on
screen at every second, including on-screen text that carries some of the detail
so you don't have to say every number out loud.

**~573 spoken words — down from an earlier ~910-word draft, cut specifically
so a real recorded take stays under 5:00.** Here's the actual math, not a
guess: at a natural, unhurried pace (~150–160 wpm) this reads in about
3:35–3:50. But this script is number-heavy — "two thousand four hundred and
ninety-three" has to be said more slowly and deliberately than filler words,
the same way "pause before a number" already tells you to — so treat 150 wpm
as closer to true than 175. On top of that, real recording adds time a silent
read never shows: breath, a flubbed line restarted, the two-second pauses this
script asks for while a terminal renders. Budgeted at roughly 5–10 seconds per
block across 9 blocks, that's up to ~75 seconds of overhead. Put together:
**expect 4:50–5:05 on a real take**, not 3:45.

That's still tight against a 5:00 cap — do one full recorded take (not a
silent read) before you touch the video edit at all, and compare it against
this estimate. If it comes in over, cut further using the list near the
bottom of this file, in order, rather than speeding up your delivery — a
rushed number is worse than a shorter script.

---

## 0:00–0:20 — Cold open

> Same batch, a thousand failed payments, eleven lakh rupees on the line.
>
> A blind retry bot — what most "AI revenue recovery" actually is — recovers
> fifty-nine thousand, seven hundred and fifty-five rupees more than mine.
> To get there, it breaks a card-network or RBI rule two thousand four
> hundred and ninety-three times. Mine: zero.
>
> That trade is the whole point.

---

## 0:20–0:50 — The problem nobody names correctly

> A failed payment isn't one problem. It's five.
>
> A card declines, a checkout's abandoned, a subscription bounces. And two
> nobody names — an approved payment never collected, and one that arrives
> after the customer gave up. Together, thirteen percent of the money at
> risk. Nothing to retry. You just go get it.
>
> On UPI, eighty-two percent of declines are the bank saying no on purpose.
> Legally, some of those you can't even retry.

---

## 0:50–1:35 — How it actually decides

> Every at-risk rupee goes through four steps.
>
> Diagnose the real cause, not the error code — ninety-four percent lookup
> against Razorpay's docs, the rest genuine inference where the bank didn't
> say why.
>
> Then, a rulebook, before anything else. Eleven hard rules: attempt caps,
> RBI's notice window, consent, contact fatigue. Eleven isn't the claim —
> the pattern is. Rule twelve is one file, not a rewrite.
>
> Only then does it ask if acting is worth it, against every real cost,
> including losing the customer for good.
>
> Every decision gets sealed into a hash-chained record, forever.
> Tamper-evident, not tamper-proof — the real fix, an external anchor, is
> already built in.

---

## 1:35–2:10 — One real refusal

> Five thousand two hundred and eighty-three rupees. Insufficient funds. Six
> rules pass. Then: this customer opted out.
>
> Blocked. Full stop. Real money on the table doesn't matter — consent
> overrides the profit calculation.

---

## 2:10–2:45 — The comparison, and the split that matters

> Four strategies, one batch, the same code grading all of them.
>
> Say it plainly: blind retry wins on raw recovery, loses everywhere else.
> Four thousand six hundred and fifty-two attempts against my four hundred
> and forty-one, six times the contacts, two thousand four hundred and
> ninety-three violations against zero.
>
> Those counts don't rest on any cost assumption. Checked four ways,
> including zero cost. Nobody argues with a count.

---

## 2:45–3:15 — Breaking it on purpose

> A green suite proves tests pass, not that they'd catch a real break. So I
> built something whose only job is to sabotage my own rules.
>
> *(mutation check runs)* Eight for eight, caught. It found worse first: my
> main safety test was passing without testing anything, twice. Both fixed,
> both in the commit history.

---

## 3:15–3:45 — Where I'm wrong

> The "worth more" claim rests on one assumption: annoying a customer costs
> something, even a little.
>
> Watch what happens at zero. *(drag the slider to zero)*
>
> Blind retry wins, by about nine percent — printed by the tool itself, with
> a test whose only job is making sure the other guy wins right here.

---

## 3:45–4:10 — Not luck, and not just rules

> A hundred and sixty tests. Fifty random batches, fifty thousand payments,
> zero violations in every one, plus a batch built purely hostile.
>
> I also built a Claude classifier for the toughest declines, measured its
> ceiling — forty-six point six against a theoretical best of forty-eight
> point seven — and cut it. Not worth the API call.
>
> This is deliberately not a free-acting agent — the bounded core a safe
> agent sits inside, where one wrong move is a real fine.

---

## 4:10–4:30 — Close

> Razorpay already has smart retry timing at the gateway. This sits one
> layer up, on the parts a gateway can't see.
>
> Every number here runs from one command, right now — nothing pre-baked.
> Thanks for watching.

---

## If you're still over, cut in this order

1. The UPI-decline line in the problem section.
2. The Bayes-ceiling line in "Not luck, and not just rules" — keep the
   headline decision (measured, then cut) and drop the two percentages.
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
  and small pauses for the visual beats all add real seconds a silent read
  skips. If your first full take lands past 4:30, that's the signal to trim
  further using the list above, not to speed-talk through it.
