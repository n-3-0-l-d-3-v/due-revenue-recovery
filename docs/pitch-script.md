# What to say — word for word (final)

This is the finished script, written to sound like a normal explanation, not
a hyped-up pitch. Read it aloud a few times before recording — not to sound
like you're reading, but to find the words that don't feel natural in your
mouth and swap them for ones that do. **The numbers do not move.** Every
figure below is exact on purpose — a rounded number sounds like a guess, an
exact one sounds like a measurement, and you measured everything here.

Companion doc: `docs/demo-guide.md` has the shot-by-shot visual plan — what's
on screen at every second, including on-screen text that carries some of the
detail so you don't have to say every number out loud.

**~615 spoken words, tightened to fit a hard 4:00 max.** Almost every point
from earlier versions is still here, said more economically. Two smaller
ones moved rather than disappeared: the "11 rules is a pattern, not a
finished rulebook" point and the tamper-evident/external-anchor detail are
now on-screen text in `docs/demo-guide.md` instead of spoken lines — still
in the video, just not narrated. The Claude-classifier detail (the ceiling
measurement before deciding not to use it) moved the same way — it's a
production-script overlay now, not a spoken line, since the bounded-agent
point right after it covers the same ground on its own.

At a calm, natural pace this runs roughly 3:50–4:00 of talking; real
recording adds a small amount on top (a breath, a couple of seconds while a
terminal loads), so this is genuinely tight against 4:00, not comfortably
under it. Do one full recorded take before touching the video edit and
check exactly where you land — if it's still over, use the cut list near
the bottom rather than speeding up your delivery.

---

## 0:00–0:15 — Cold open

> Here's the same batch run through two systems: a thousand failed
> payments, about eleven lakh rupees at stake.
>
> A simple retry bot — basically what most "AI revenue recovery" tools
> are — recovers fifty-nine thousand, seven hundred and fifty-five rupees
> more than mine, but breaks a card-network or RBI rule two thousand four
> hundred and ninety-three times doing it. Mine breaks zero — that
> trade-off is what this project's about.

---

## 0:15–0:45 — The problem

> A failed payment isn't one problem. It's five.
>
> A card can decline, a checkout can get abandoned, a subscription can
> bounce, and there are two you've probably never heard of: a payment the
> bank approved but the merchant forgot to collect, and one approved after
> the customer gave up. Those two are almost thirteen percent of the money
> at risk, and there's nothing to retry.
>
> On UPI, about eighty-two percent of failures are the bank saying no on
> purpose, and some of those can't legally be retried.

---

## 0:45–1:20 — How it decides what to do

> Every payment at risk goes through four steps: it figures out what
> actually happened, not just the error code (ninety-four percent of the
> time a lookup against Razorpay's docs, the rest genuinely guessed), it
> checks a set of rules (eleven right now, covering attempt limits, RBI's
> notice period, consent, and contact fatigue), it weighs whether acting
> is worth it against every real cost, including losing the customer for
> good, and it saves the decision into a record chained with hashes, so it
> can't be quietly edited later.

---

## 1:20–1:50 — One real example

> Here's one actual case. Five thousand two hundred and eighty-three
> rupees, insufficient funds. Seven rules get checked, and six of them
> pass. Then it hits one: this customer had opted out of being contacted.
>
> So it's blocked, and that's the end of it. It doesn't matter that the
> money is technically sitting right there — consent comes before the
> profit calculation, not after it.

---

## 1:50–2:20 — Comparing the strategies

> I ran four strategies against the same batch, using the same code to
> score them. People call the simple approach "blind retry", and blind retry wins on raw recovery — but makes four thousand six hundred and
> fifty-two attempts against my four hundred and forty-one, six times the
> contacts, and two thousand four hundred and ninety-three violations
> against zero.
>
> Those numbers don't depend on any cost assumption; I checked four ways,
> including zero cost, and they don't move.

---

## 2:20–2:50 — Testing it by trying to break it

> A green test suite proves the tests pass, not that they'd catch a real
> break. So I built a tool that breaks my own safety rules and checks if
> the tests notice.
>
> *(mutation check runs)* All eight break attempts got caught. Building
> this also found something worse: my main safety test was passing
> without testing anything, twice — both fixed now, both in the commit
> history.

---

## 2:50–3:15 — Where the claim stops holding

> My "worth more" claim rests on one assumption: that repeatedly contacting
> a customer costs something, even a little.
>
> So let's see what happens if that cost is zero. *(drag the slider to
> zero)*
>
> The simple strategy wins there, by about nine percent, printed right on
> the page, with a test making sure it stays that way.

---

## 3:15–3:35 — Checking it wasn't just luck

> A hundred and sixty tests back this up, including fifty random batches
> with zero violations every time, plus a worst-case batch, which also
> held up.
>
> This is also deliberately not a free-acting agent — where one wrong move
> could mean a real fine, the right call is something bounded a safe agent
> operates inside of.

---

## 3:35–4:00 — Closing

> Razorpay already does smart retry timing at the gateway — I'm not
> claiming to beat that. This works one layer above it, on parts a gateway
> can't see.
>
> Every number here comes from one command you can run yourself, right
> now. Thanks for watching.

---

## If you're still over time, cut in this order

1. The line about UPI declines being on-purpose, in the problem section.
2. The "eleven right now, covering..." rule list in "how it decides" — say
   just "a set of rules" and let the on-screen list carry the detail.
3. **Never cut:** the one real example, the mutation-check moment, or the
   sensitivity slider. Those three carry most of the actual proof.

## Delivery notes

- **Don't say "AI agent."** Just describe what it does — everyone judging
  today has already heard that phrase, and it doesn't tell them anything.
- **Pause slightly before a number, not after.** A short pause before
  "fifty-nine thousand, seven hundred and fifty-five" makes it land as a
  real fact instead of filler.
- **Let the terminal finish before you keep talking.** A couple of seconds
  of quiet while text appears on screen is fine. Talking over text nobody
  can read yet isn't.
- **If you mess up a line, stop, take a breath, and start that sentence
  again.** A clean restart is easy to cut later; trying to patch a sentence
  mid-way through usually sounds more nervous, not less.
- **Time an actual recorded take, not a silent read-through.** Reading
  silently in your head always goes faster than speaking out loud. If your
  first real take comes in past 4:00, trim using the list above instead of
  speeding up.
