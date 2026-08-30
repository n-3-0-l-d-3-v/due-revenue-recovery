# Demonstration Guide — what to show, how, and when

This is the run-of-show. It tells you what's on screen at every moment and why.
The words themselves live in `docs/pitch-script.md` — keep both open side by side
while you rehearse, then close this one and just talk once you're on take three.

Total runtime target: **5:00**. Realistic first take: **6:00–6:30**. That's normal.

---

## What you're actually proving, in order

A panel watching dozens of these will forget most of what they see. They will not
forget a moment where something visibly breaks and then gets caught. Structure
the whole five minutes around three such moments:

1. **A rule refuses real money, on screen, with its citation.** (0:55–1:40)
2. **You break your own safety system on purpose, and the tests catch it.** (2:30–3:05)
3. **You show the exact number where your own argument stops holding.** (3:35–4:05)

Everything else is context that makes those three moments land. If you're
short on rehearsal time, protect these three and compress everything around them.

---

## Before you record — a 15-minute setup, not optional

**Windows, not tabs.** Arrange four things you can alt-tab between with zero
searching:

| # | What | State it should be in when you start |
|---|---|---|
| 1 | Terminal A | `cd` into the repo, font size bumped to ~18pt, dark theme, ready to run `python demo.py --judge` |
| 2 | Terminal B | Same repo, ready to run `python tools/mutation_check.py` |
| 3 | Browser | The live dashboard open: `https://n-3-0-l-d-3-v.github.io/due-revenue-recovery/` — pre-scrolled to the top |
| 4 | Terminal C | Ready to run `pytest -q` |

**Run everything once, silently, before you record anything.** Not to memorize —
to catch a stale number, a slow first-import, a font that's too small on the
recording resolution. If a number in the terminal doesn't match what you're about
to say, fix that before touching the mic.

**Turn off everything that can pop up.** Notifications, Slack, email, chat apps,
your phone within camera/mic range. One Windows notification banner mid-take
means the take is dead.

**Decide your window/monitor resolution now and don't change it mid-recording.**
1920×1080 minimum. If you're recording your own screen, hide the taskbar.

---

## The five acts

### Act 1 — Open on the dashboard, not the terminal (0:00–0:30)

**Show:** Browser, the live Due Ledger page, already scrolled to the summary
strip (the four stat cards: violations, attempts, contacts, net value).

**Why the dashboard first, not a terminal:** the first four seconds decide
whether a tired judge leans in or checks their phone. A polished page with real
numbers reads as "this person finished something." A terminal prompt reads as
"this is still in progress." Save the terminal for when you need to prove the
numbers are live, not for the cold open.

**Do:** Say the opening line (script has it verbatim) while the cursor sits
still on the violations card. Don't scroll yet — let the number breathe for two
full seconds before you move.

---

### Act 2 — The real problem, fast (0:30–0:55)

**Show:** Stay on the dashboard, scroll slowly to the "What actually happens to
1,000 failed payments" table as you talk.

**Do not** switch to reading from `docs/domain-primer.md` here — that document
is for you, not for camera. The panel doesn't need the full taxonomy; they need
the one sentence that makes them understand why "just retry it" is wrong.

---

### Act 3 — The refusal, in full (0:55–1:45)

**Show:** Scroll to the "One real refusal, in full" section on the dashboard.
Let the ₹5,283 figure sit on screen before you start talking about it.

**This is proof moment #1.** Point (cursor, not finger) at each gate row as you
mention it: the passes, then the DEFER, then the BLOCK. The visual sequence of
green → green → green → blue → red is doing work your words don't have to.

**Do not rush this section even though it's dense.** It's the single best piece
of evidence you have that the system reasons about individual money, not just
aggregate statistics.

---

### Act 4 — The comparison and the tiers (1:45–2:30)

**Show:** Scroll up to the four-strategy table, then down to the Tier A / Tier B
cards.

**Do:** Let the ₹565,138 gap sit on screen in silence for one full second before
you say the number. Silence before a number makes it land as important; talking
over it makes it sound like filler.

---

### Act 5 — Break it on camera (2:30–3:15)

**Switch to Terminal B.** Run `python tools/mutation_check.py` live. Do **not**
run this ahead of time and paste in a screenshot — the panel needs to see the
command execute in real time, because that's what separates "I claim my tests
work" from "watch my tests work."

**This is proof moment #2**, and it's the strongest thing in the whole demo.
While it runs (it takes a few seconds), keep talking — don't sit in dead air
waiting for output. The script has exact words for this gap.

---

### Act 6 — Where you're wrong (3:15–4:00)

**Show:** Back to the browser, the sensitivity slider section. **Actually drag
the slider** — don't just show a screenshot of two positions. Watch it flip
from green ("Recoup wins" — update to "Due wins" once you relabel it, see note
below) to red ("blind retry wins") as you pull it left.

**This is proof moment #3.** It is the single highest-credibility thirty seconds
available to you, because almost nobody voluntarily shows the panel the exact
spot where their own pitch is wrong. Do not cut this to save time. If you must
cut something, cut Act 2 instead.

**Note:** the dashboard still has some references to a prior working name in
a few in-page strings (e.g. `sensWinner.textContent`). Do a find-and-replace
pass for "Recoup" → "Due" across the whole HTML file before your final take —
grep the file for the old name and fix anything you find; don't rely on memory.

---

### Act 7 — The receipts (4:00–4:40)

**Show:** Terminal C, run `pytest -q`, let it finish (153 passed).
Then Terminal A one more time: `python demo.py --robustness` — you don't need
to wait for the whole 50-seed run on camera; run the first ~10 seconds of output
showing it's actually executing, then cut to the final summary (edited, not
faked — the same run, just trimmed in post).

**Do:** Say the GitHub Pages URL and the repo URL out loud, once, clearly. A
judge who wants to check you later needs to have heard it, not just seen small
text in a corner.

---

### Act 8 — Close (4:40–5:00)

**Show:** Back to the dashboard, scroll to the "What building this actually
caught" timeline. End on that, not on a title card.

**Why end here:** it's the section that most directly answers "is this a real
engineer or a student who found a good template." Let the last thing the panel
sees be evidence, not a logo.

---

## Recording mechanics

- **Record in segments, not one continuous take**, if your tool allows clean
  cuts. Act 5 (mutation check) and Act 7 (pytest) are the easiest to re-record
  in isolation if you flub a line — you don't need to redo the whole five
  minutes because of one word in the middle.
- **Audio matters more than people expect.** A decent USB mic or headset mic
  beats a laptop's built-in one by a wide margin. Judges will forgive a slightly
  soft video; they won't forgive audio they have to strain to hear.
- **Record a few seconds of silence at the very start and end of each segment**
  before you cut. Makes editing transitions much less painful.
- **Watch the first full assembly once with sound off.** If you can't follow
  what's happening from the screen alone, the screen sequencing is wrong — fix
  that before touching the script.
- **Watch it a second time with sound only**, eyes closed. If a number doesn't
  land as a number when you can't see it, slow down around it.

---

## What to cut, in this exact order, if you're over 5:00

1. Act 2 (the "why just retrying is wrong" context) — trim to one sentence.
2. Act 8's closing timeline — cut to the two strongest entries instead of all
   of them.
3. The full robustness output in Act 7 — state the 50/50 and 47/50 numbers
   verbally instead of showing the terminal run.
4. **Never cut:** Acts 3, 5, and 6 — the three proof moments. If you're still
   over time after cutting everything above, the fix is talking faster and
   pausing less, not removing more content.

---

## The submission package — what actually goes in, and how

A strong buildathon submission is not "send everything you built." It's a small,
correctly-labeled set of things a busy panelist can act on in under two minutes
without asking you a single clarifying question.

### What to submit

1. **The GitHub repository URL.**
   `https://github.com/n-3-0-l-d-3-v/due-revenue-recovery`
   Make sure `main` is the branch a visitor lands on, and that the README is
   what you want the first eyes on the project to see — it's your cover page.

2. **The live dashboard URL**, separately, even though it's linked from the
   README. Panels skim; don't make them find it.
   `https://n-3-0-l-d-3-v.github.io/due-revenue-recovery/`

3. **The video file or link.** If the platform wants a file upload, export at
   1080p, H.264, under whatever size cap they state — check this *before* your
   final render, not after. If it wants a YouTube/Drive link, set sharing to
   "anyone with the link" and test that link from a private/incognito window
   logged out of your own account, to make sure a stranger can actually open it.

4. **One line of context in the submission form itself**, if there's a
   free-text field — not a re-explanation of the whole project, just enough
   that someone triaging hundreds of entries knows what track and what
   makes this one worth a closer look. Something like: *"Track 03 — a
   policy-gated payment recovery engine. 153 tests, a live interactive
   dashboard, and an honest sensitivity analysis showing exactly where the
   core claim stops holding."* Adjust to their actual form fields; don't
   pad it.

### What not to submit

- **Don't attach the domain primer, build plan, or internal working docs**
  as separate deliverables. They're valuable — that's why they live in
  `docs/` in the repo, where anyone curious can find them — but leading with
  them signals "research notebook," not "shipped system." Let the README and
  the dashboard be what's pushed at the panel; let the deeper docs be what
  rewards someone who clicks in.
- **Don't send a zip file of the code** if a Git URL is accepted. A zip loses
  the commit history, and the commit history — 96 commits showing real bugs
  found and fixed in sequence — is itself part of your evidence.
- **Don't over-explain in writing what the video already shows.** If the
  submission form has an optional long-form description field, resist filling
  it with a full essay. Two or three sentences plus the links is more
  professional than a wall of text — it signals you trust your own work to
  speak for itself.

### The last thing to do before you hit submit

Do one full cold run-through as if you were a panelist who has never spoken to
you: open the repo link in a private browser window, open the dashboard link in
another, watch the video once at 1x speed on a phone-sized window (a lot of
early screening happens on a phone or a small laptop, not a monitor). If
anything is confusing, broken, or too small to read at that size, that's the
fix to make — not a bigger feature, a smaller polish pass.
