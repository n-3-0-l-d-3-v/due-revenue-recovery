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

**~715 spoken words, tightened to land inside 4:00–4:45.** Almost every
point from the earlier version is still here, just said more economically.
Two smaller ones moved rather than disappeared: the "11 rules is a pattern,
not a finished rulebook" point and the tamper-evident/external-anchor detail
are now on-screen text in `docs/demo-guide.md` instead of spoken lines —
still in the video, just not narrated, which is how a couple of minutes get
saved without actually cutting content.

At a calm, natural pace this runs roughly 4:15–4:30 of talking; real
recording adds a bit more (a breath, a pause while a terminal loads), which
is where the room to 4:45 comes from. Do one full recorded take before
touching the video edit and check where you land. If you're still over, use
the cut list near the bottom — a couple of sentences can come out cleanly
without the rest sounding choppy.

---

## 0:00–0:20 — Cold open

> Here's the same batch of data run through two systems: a thousand failed
> payments, about eleven lakh rupees at stake.
>
> A simple retry bot — basically what most "AI revenue recovery" tools
> actually are — recovers about fifty-nine thousand, seven hundred and
> fifty-five rupees more than mine, but breaks a card-network or RBI rule
> two thousand four hundred and ninety-three times to get there. Mine
> breaks zero. That trade-off is what this project's about.

---

## 0:20–0:55 — The problem

> A failed payment isn't really one problem. It's five different problems.
>
> A card can decline. A checkout can get abandoned. A subscription can
> bounce. And two you've probably never heard of: a payment the bank
> already approved but the merchant forgot to collect, and one approved
> after the customer's already given up. Those two are almost thirteen
> percent of the money at risk, with nothing to retry — you just go
> collect it.
>
> On UPI, about eighty-two percent of failures are the bank saying no on
> purpose, and legally, some of those can't even be retried.

---

## 0:55–1:40 — How it decides what to do

> Every payment at risk goes through the same four steps.
>
> First, it figures out what actually happened, not just the error code —
> ninety-four percent of the time a lookup against Razorpay's own
> documentation, the rest genuinely guessed, since the bank doesn't say why.
>
> Then, before anything else, it checks a set of rules — eleven right now,
> covering attempt limits, RBI's notice period, consent, and contact
> fatigue.
>
> Only then does it check whether acting is worth it, weighing the odds
> against every real cost, including losing the customer for good.
>
> Whatever it decides gets saved into a record chained with hashes, so it
> can't quietly be edited later.

---

## 1:40–2:15 — One real example

> Here's one actual case. Five thousand two hundred and eighty-three
> rupees, insufficient funds. Seven rules get checked, and six of them
> pass. Then it hits one: this customer had opted out of being contacted.
>
> So it's blocked, and that's the end of it. It doesn't matter that the
> money is technically sitting right there — consent comes before the
> profit calculation, not after it.

---

## 2:15–2:50 — Comparing the strategies

> I ran four strategies against the same batch, using the same code to
> score all of them. People usually call the simple, no-diagnosis approach
> "blind retry", and blind retry wins on raw recovery — but makes four
> thousand six hundred and fifty-two attempts against my four hundred and
> forty-one, six times the customer contacts, and two thousand four
> hundred and ninety-three violations against zero for mine.
>
> Those numbers don't depend on any cost assumption — I checked that four
> ways, including zero cost, and they don't change.

---

## 2:50–3:25 — Testing it by trying to break it

> A test suite that's all green just proves the tests pass, not that
> they'd catch it if something actually broke. So I built a tool that
> breaks my own safety rules on purpose and checks if the tests notice.
>
> *(mutation check runs)* All eight break attempts got caught. Building
> this also found something worse first: my main safety test was passing
> without actually testing anything, twice — both fixed now, both right
> there in the commit history.

---

## 3:25–3:55 — Where the claim stops holding

> The claim that my approach is worth more rests on one assumption: that
> repeatedly contacting a customer costs something, even a little.
>
> So let's see what happens if that cost is zero. *(drag the slider to
> zero)*
>
> The simple retry strategy wins there, by about nine percent, and that's
> printed right on the page, with a test making sure it stays that way.

---

## 3:55–4:20 — Checking it wasn't just luck

> A hundred and sixty tests back this up, including fifty random batches
> with zero violations across every one, plus one built to be a worst
> case, which also held up.
>
> I also tried a Claude model for the toughest declines, but measured its
> real ceiling first, and it wasn't enough better to be worth calling an
> API for.
>
> This whole system is also deliberately not a free-acting agent — where
> one wrong move could mean a real fine, the right call is something
> bounded a safe agent operates inside of, not something acting alone.

---

## 4:20–4:45 — Closing

> Razorpay already does smart retry timing at the gateway level — I'm not
> claiming to have beaten that. This works one layer above it, on parts a
> gateway can't actually see.
>
> Every number I've shown you comes from one command you can run yourself,
> right now. Thanks for watching.

---

## If you're still over time, cut in this order

1. The line about UPI declines being on-purpose, in the problem section.
2. The Claude-classifier sentence in "checking it wasn't just luck" — the
   bounded-agent point after it can stand on its own.
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
  first real take comes in past 4:45, trim using the list above instead of
  speeding up.
