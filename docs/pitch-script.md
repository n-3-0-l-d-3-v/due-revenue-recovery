# What to say — word for word (final)

This is the finished script. Read it aloud a few times before recording — not to
sound like you're reading, but to find the handful of words that don't sit right
in your mouth and swap them for ones that do. **The numbers do not move.** Every
figure below is exact on purpose — a rounded number sounds like a guess, an
exact one sounds like a measurement, and you measured everything here.

Companion doc: `docs/demo-guide.md` has the shot-by-shot visual plan — what's on
screen at every second, including on-screen text that carries some of the detail
so you don't have to say every number out loud.

**~850 spoken words. At a confident, slightly brisk pace, that's 4:55–5:10.**

---

## 0:00–0:20 — Cold open

> Same batch. A thousand failed payments. Eleven lakh rupees on the line.
>
> A blind retry bot — which, stripped of the buzzwords, is what most "AI
> revenue recovery" actually is — recovers fifty-nine thousand, seven hundred
> and fifty-five rupees more than mine does.
>
> And to get there, it breaks a card network rule or an RBI rule two thousand
> four hundred and ninety-three times. Mine: zero.
>
> Five minutes. I'll show you why that trade is the whole point.

---

## 0:20–0:55 — The problem nobody names correctly

> A failed payment isn't one problem. It's five.
>
> A card gets declined. A checkout gets abandoned. A subscription bounces. And
> two you've probably never heard named: an authorization the bank already
> approved that the merchant forgot to collect, and one that arrives late,
> after the customer already gave up. Almost thirteen percent of the money at
> risk in this batch is those last two. There's nothing to retry. You just go
> get it.
>
> And for the ones that did fail: on UPI, eighty-two percent of declines are the
> bank saying no *on purpose*. Wrong PIN, empty account, blocked card. Retry
> that and you get the same "no" again. Some of them you're legally not allowed
> to retry at all.

---

## 0:55–1:45 — How it actually decides

> So here's the engine. Every at-risk rupee goes through the same four steps.
>
> Diagnose — what actually happened, not just the error code. Ninety-four
> percent of the time that's a direct lookup against Razorpay's own
> documentation. The rest genuinely has to be inferred, because the bank
> literally didn't say why.
>
> Then — before anything else — a rulebook. Eleven hard rules today: Visa and
> Mastercard's attempt caps, RBI's twenty-four-hour notice window for auto-pay,
> consent, contact fatigue. Eleven isn't the claim — the pattern is. Every rule
> is the same shape, so rule twelve is one file, not a rewrite. And nothing
> downstream is even allowed to see an option the rulebook already killed.
>
> Only then does it ask if acting is worth it — probability of success against
> every real cost, including the risk of losing the customer for good.
>
> And every decision — acted on, refused, or deferred — gets sealed into a
> hash-chained record, forever. Tamper-evident, not tamper-proof — same limit
> any log has, Git included — and the real fix, publishing that chain's head
> outside my own control, is already built in.

---

## 1:45–2:25 — One real refusal

> Five thousand two hundred and eighty-three rupees. Insufficient funds. Seven
> rules checked. Six pass. Then: this customer opted out.
>
> Blocked. Full stop. Doesn't matter that it's real money sitting right there —
> consent isn't a variable in the profit calculation. It overrides the profit
> calculation.

---

## 2:25–3:00 — The comparison, and the split that matters

> Four strategies, same thousand events, same code grading all of them.
>
> Blind retry wins on raw recovery. It loses everywhere else. Four thousand six
> hundred and fifty-two attempts against mine's four hundred and forty-one. Six
> times the customer contacts. Two thousand four hundred and ninety-three
> violations against zero.
>
> So say it plainly: blind retry wins the recovery number and loses the trade.
>
> Here's the part worth sitting with: the violation count, the attempt count,
> the contact count — those don't depend on a single assumption I made about
> cost. I checked that four different ways, including a version where every
> cost is set to zero. They don't move. Those are just counts. Nobody can argue
> with a count.

---

## 3:00–3:35 — Breaking it on purpose

> A green test suite proves the tests pass. It doesn't prove they'd catch
> anything if the system actually broke. So I built something whose only job is
> to sabotage my own rules and see if the suite notices.
>
> *(mutation check runs)* Eight for eight, caught. But building that tool found
> something worse first: my main safety test — the one proving retries never
> exceed the limit — was passing without testing anything. Twice. Once because
> it checked the limit against the same file it was supposed to be validating.
> Fixed both. It's in the commit history, not smoothed over.

---

## 3:35–4:05 — Where I'm wrong

> The "worth more" claim rests on exactly one assumption: that annoying a
> customer costs something, even a little.
>
> Watch what happens if it costs nothing. *(drag the slider to zero)*
>
> Blind retry wins. By about nine percent.
>
> That's not in an appendix. It's on the page, printed by the tool itself, with
> a test whose entire job is making sure the *other guy* wins right there. The
> violation count doesn't move, though — that one was never resting on this in
> the first place.

---

## 4:05–4:35 — Not luck, and not just rules

> A hundred and sixty tests. Fifty separate random batches, fifty thousand
> simulated payments — zero violations in every single one. Then a batch built
> on purpose to be hostile, and it held there too.
>
> I also built a Claude classifier for the failures where the bank gives no
> reason at all. Then I measured its ceiling before trusting it: forty-six
> point six percent against a theoretical best of forty-eight point seven.
> Barely two points of room. Not worth the API call. I cut it.
>
> And this whole thing is deliberately not a free-acting agent. In a domain
> where one wrong autonomous move is a real fine, the responsible build is the
> bounded core a safe agent sits inside — not something that acts first and
> explains later.

---

## 4:35–5:00 — Close

> Razorpay already has smart retry timing at the gateway. I'm not claiming to
> have beaten that. This sits one layer up — the merchant's whole portfolio,
> the parts a gateway structurally cannot see.
>
> Every number I just showed you runs from one command, right now, on your
> machine. Nothing pre-baked. Nothing cherry-picked.
>
> Thanks for watching.

---

## If you're over time, cut in this order

1. The five-leak-points detail in the problem section — trim to one sentence.
2. "Not luck, and not just rules" — cut the adversarial-batch line, keep the
   robustness number and the AI-cut story.
3. **Never cut:** the refusal walkthrough, the mutation-check moment, or the
   sensitivity slider. Those three are the whole demo.

## Delivery notes

- **Don't say "AI agent."** Say what it does instead — everyone judging today
  has heard the phrase and it tells them nothing.
- **Pause before a number, not after.** Half a second of silence before "fifty-
  nine thousand, seven hundred and fifty-five" makes it land as a fact, not
  filler.
- **Let the terminal finish rendering before you talk over it.** Two seconds of
  quiet while text appears is fine. Talking over text nobody can read yet isn't.
- **If you flub a line, stop, breathe, restart the sentence.** A clean restart
  cuts easily; a mid-sentence patch reads as nervous even when it wasn't.
