# What to say — word for word

Read this out loud a few times before you record. Not to memorize it like a
script — to find where *your* voice would say it differently, and change those
words to yours. The numbers stay exact. Everything else is allowed to sound
like you.

**~700 words. At normal talking speed that's about 4:40, which leaves you room.**

The one rule that matters more than any line below: **say the real number, not
the round one.** "Two thousand four hundred and ninety-three" sounds like
someone who measured it. "About two and a half thousand" sounds like someone
who's guessing. You're not guessing, so don't talk like you are.

---

## 0:00–0:25 — Open cold, on the number

*Screen: the dashboard, summary strip, already loaded and sitting still.*

> Same batch. A thousand failed payments, eleven lakh rupees on the line.
>
> Look at these two numbers. A blind retry bot — which, stripped of the buzzwords,
> is what most "AI payment recovery" actually is — recovers more money than my
> system does. Fifty-nine thousand, seven hundred and fifty-five rupees more.
>
> And in doing that, it breaks a card network rule or an RBI rule two thousand
> four hundred and ninety-three times. Mine breaks it zero times.
>
> That gap — recovering slightly less, but never once crossing a line — is the
> whole project. Let me show you why that trade is the right one.

---

## 0:25–1:00 — Why this is actually hard

*Screen: still the dashboard, scroll slowly to the comparison table.*

> Here's the thing nobody tells you about a failed payment: retrying it isn't
> automatically the right move. On UPI, about eighty percent of failures are the
> bank saying no on purpose — wrong PIN, no balance, card blocked. Retry those
> and you get the same "no" again. Some of them you're not even allowed to
> retry — Mastercard fines you for hammering a dead card.
>
> There's also money that isn't even failed. Almost thirteen percent of what's
> at risk in this batch is money the bank already approved — the merchant just
> never collected it. Retrying does nothing there. You have to go grab it.

---

## 1:00–1:50 — One real refusal, start to finish

*Screen: scroll to the refusal card. Let the ₹5,283 sit for a beat before talking.*

> So here's how it actually decides. One event: five thousand two hundred and
> eighty-three rupees, insufficient funds. It checks seven rules before it does
> anything — network caps, is this card even allowed to retry, is there an RBI
> notice window open. All fine. Then it hits one thing: this customer opted out.
>
> Blocked. Full stop. Doesn't matter that it's real money. That's not a
> judgment call the system is allowed to make — consent overrides everything,
> every time.
>
> And notice it logged the six checks that *passed*, not just the one that
> failed. If you only write down your refusals, you can't actually prove you
> checked anything else.

---

## 1:50–2:30 — The four-way comparison

*Screen: the full comparison table.*

> Four approaches, same thousand events, same code measuring all of them —
> nobody grades their own homework here.
>
> Fixed T+3 is what Razorpay's own retry logic actually does today, not a
> strawman I invented. Blind retry is the reason-agnostic version — try
> everything, five times. Mine diagnoses first, checks the rulebook, then
> decides.
>
> blind retry wins on raw recovery. It loses everywhere else — four thousand six
> hundred and fifty-two attempts against my four hundred and forty-one, two
> thousand four hundred violations against zero.
>
> And here's the part I actually want you to sit with: the zero-violations
> number and the attempt counts don't depend on any assumption I made about
> costs. I checked that four different ways, including one where every cost is
> set to zero. They still hold. Those numbers can't be argued with — they're
> just counts.

---

## 2:30–3:05 — Breaking it on purpose

*Screen: switch to the terminal. Run `python tools/mutation_check.py` live.*

> A test suite that's all green tells you the tests pass. It doesn't tell you
> they'd catch anything if the system actually broke. So I wrote something
> whose only job is to sabotage my own rules, one at a time, and check whether
> the tests notice.
>
> *(while it runs)* All eight sabotage attempts get caught. But building this
> found something worse — my main safety test, the one proving retries never
> go over the limit, was passing without actually testing anything. Twice. It
> read the limit from the same file it was supposed to be checking, so loosening
> the limit loosened the test right along with it. I fixed that. It's in the
> commit history, not smoothed over.

---

## 3:05–3:45 — Where I'm wrong

*Screen: back to the dashboard, the sensitivity slider. Actually drag it.*

> The "worth more" claim — not the violations, the net value one — rests on
> exactly one assumption: that annoying a customer costs you something.
>
> Watch what happens if I say it costs nothing. *(drag the slider to zero)*
>
> blind retry wins. By about nine percent.
>
> That's not buried in an appendix somewhere — it's on the page, it's printed
> by the tool itself, and there's a test in the suite whose entire job is to
> make sure the *other guy* wins in that specific case. If someone quietly
> deleted that finding later, the test would fail and tell on them.
>
> The zero-violations number doesn't move, though. That one was never resting
> on this assumption in the first place.

---

## 3:45–4:20 — Not one lucky batch

*Screen: terminal, `pytest -q`, let it complete. Then the robustness section on the dashboard.*

> A hundred and fifty-three tests. But more than that — I ran this whole
> comparison fifty separate times, fifty completely fresh random batches, fifty
> thousand simulated payments total.
>
> Zero violations held in every single one. Not most — all fifty.
>
> The net-value win held in forty-seven of fifty. Not perfect, and I'm not
> going to pretend it is — the one time it didn't, I named the exact seed and
> the exact margin it lost by. A result that only shows you its good days isn't
> a result.

---

## 4:20–4:45 — Where this actually sits

> Razorpay already has a smart retry engine doing timing predictions at the
> gateway level. I'm not claiming to have beaten that. This sits one layer up —
> the stuff a gateway genuinely can't see. How tired is this specific customer
> of being contacted. What's this customer worth over time. Is this issuer
> already unhappy with us today. And a paper trail you could actually hand to
> a compliance team.

---

## 4:45–5:00 — Close

*Screen: the "what building this caught" section.*

> Everything I just showed you runs from one command, on your machine, right
> now. No cherry-picking, nothing pre-baked for the camera.
>
> Thanks for watching.

---

## If you're running long, cut in this order

1. The "why this is hard" section (0:25–1:00) — trim to two sentences.
2. "Where this sits" (4:20–4:45) — cut to one sentence.
3. **Never cut:** the refusal walkthrough, the mutation-check moment, or the
   sensitivity slider. Those three are what separate this from a demo reel.

## Delivery notes

- **Don't say "AI agent."** Everyone judging today has heard it fifty times
  already and it tells them nothing about what your system actually does.
  Say what it does instead.
- **Pause before a number, not after.** A half-second of silence before
  "fifty-nine thousand, seven hundred and fifty-five" makes it land as a fact.
  Rushing into it makes it sound like filler.
- **If you flub a line, stop, breathe, say the sentence again from its start.**
  Don't try to patch a stumble mid-sentence — it reads as nervous on camera even
  when it wasn't. A clean restart cuts easily in editing; a stumble doesn't.
- **Let the terminal output finish rendering before you talk over it.** Two
  seconds of dead air while text appears is fine. Talking over text nobody can
  read yet is not.
