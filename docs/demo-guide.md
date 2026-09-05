# Production Script — what's on screen, second by second

This is the second script. `docs/pitch-script.md` is what you *say*, word for
word. This is what the viewer *sees* while you say it — synced to the exact
same timestamps, so the two documents are two tracks of one video, not two
separate plans that happen to both exist.

The governing rule for this document: **every claim gets a visual answer, not
a slide.** A pitch video that cuts to a static screenshot while a voice talks
over it is a conference talk with extra steps. Nothing here is "show a page
and read from it" — every beat below is either a live command producing output
in real time, an on-screen overlay that answers the exact objection a judge is
forming as you speak, or a visible before/after (a slider moving, a number
flipping, a test going from green to red and back).

**Format:** screen recording (OBS, free) at 1920×1080, 60fps if your recorder
supports it. **No webcam, no face, anywhere in the video.** Your real voice
carries the whole thing — that's the credibility signal — but the visual
layer is pure screen content, edited like a product launch, not a recorded
call. That's a deliberate style choice, not a compromise: it puts 100% of the
screen's attention on the terminal and dashboard, which is where the actual
proof lives.

**Editing tool:** DaVinci Resolve (free, no watermark, handles the kinetic
text and transitions below natively) or CapCut (free, faster to learn, fine
for everything here). Either is enough — nothing in this plan needs a paid
tool.

---

## The visual identity (build once, before you touch a single take)

A "startup pitch" video reads as premium because of four consistent choices
running underneath everything, not because of any one flashy moment. Decide
these first and reuse them everywhere — inconsistency is what makes an edit
look amateur, not any individual choice being wrong.

- **One color pair.** Pick an accent color (green suits this project's
  compliance-safety framing) and one danger color for BLOCK/violation states.
  Use them nowhere else — every green thing on screen should mean "compliant"
  and every red thing should mean "violation," with no exceptions, so the
  color itself starts carrying meaning by minute two.
- **One typeface for every overlay.** A single clean sans (Inter, Space
  Grotesk, or Manrope — all free) for every number, chip, and caption in the
  video. Mixing fonts between overlays is the single fastest way to make an
  edit look thrown together.
- **Kinetic typography, not static text boxes.** Every overlay in the table
  below should *enter* with motion — a fast slide-up-and-settle or a quick
  scale-in, roughly 200–300ms, never an instant hard cut into existence — and
  exit the same way. This is the actual difference between "pitch video" and
  "screen recording with captions."
- **Cut style: quick zoom or whip-pan between beats, not hard cuts.** A short
  (150–250ms) zoom-punch or motion blur transition between each numbered
  section below sells "produced" harder than almost anything else on this
  list, and both editors above have a built-in transition for it.

**Music:** a single instrumental track underneath the whole video, ducked to
roughly 15–20% volume the instant your voice starts (both editors above have
an audio-ducking / sidechain feature — use it, don't ride the fader by hand).
Free, no-attribution sources: YouTube Audio Library, or Pixabay Music. Pick
something low-key and rhythmic, not dramatic — it should disappear under your
voice, not compete with it. Confirm the buildathon's submission terms don't
forbid third-party music before you lock the final export; if in doubt, use
a track explicitly marked royalty-free/CC0 from either source above.

**Opening sting (silent, ~2 seconds, before the 0:00 mark below starts):** a
title card — project name, one-line tagline, nothing else — that animates in
and out before your voice begins. This sits *before* the pitch script's
0:00, so it doesn't eat into your spoken content. The script itself now
targets ~4:30 spoken (with a built-in margin against the 5:00 cap, since
real recording always runs longer than a silent read) — see the timing math
at the top of `docs/pitch-script.md` before you record.

**Closing card (silent, ~2 seconds, after "thanks for watching"):** same
title treatment, plus the repo and dashboard URLs as plain, legible text —
this is the frame a judge screenshots if they want to find you again later,
so it needs to hold still and be readable, not animate the whole time it's
on screen.

---

## The overlay system (build these once, reuse throughout)

Four recurring overlay types. Build them as a template in your editor before
you touch a single take — reusing one visual language across the whole video
is what makes it read as "produced," not "screen-recorded."

| Overlay | Looks like | Appears when |
|---|---|---|
| **Citation chip** | Small pill, top-right: `RBI · Auto-debit notice, 2019` or `Visa · Core Rules 5.7.2` | Any time a rule is named on screen or spoken |
| **Counter flip** | A number that visibly ticks from one value to another (not a hard cut) | Every headline figure — recovered, violations, attempts |
| **Verdict tag** | Green `PASS` / blue `DEFER` / red `BLOCK`, appearing next to the gate row it belongs to, timed to the word | The refusal walkthrough, Act 3 |
| **"Answered" tick** | A small checkmark + one-line label that appears bottom-left when an objection gets addressed, e.g. ✓ *"tested at zero cost too"* | Every place this guide marks **[ACK]** below |

The **[ACK] overlay is the whole premium-vs-amateur difference.** It is how
you make the video itself argue "I already thought of your objection" instead
of hoping the judge notices you handled it. Use it only at the moments marked
below — this guide places about nine across five minutes, each tied to a real
honesty point (a limitation, a boundary, a bug found and fixed), not to a
flex. More than that reads as noise; fewer and a graded criterion about
acknowledging risk goes unanswered on screen.

---

## Pre-record checklist (15 minutes, not optional)

| # | Window | State before you hit record |
|---|---|---|
| 1 | Terminal A | Repo root, font ~20pt, dark theme, history cleared, ready for `python demo.py --judge` |
| 2 | Terminal B | Same repo, ready for `python tools/mutation_check.py` |
| 3 | Browser | Live dashboard, pre-scrolled to top: `https://n-3-0-l-d-3-v.github.io/due-revenue-recovery/` |
| 4 | Terminal C | Ready for `pytest -q` |
| 5 | Editor | This file and the pitch script open side by side, for rehearsal only — closed before the real take |

Run every command once, silently, before recording anything — you're checking
for a stale number or a slow first-import, not memorizing. Turn off every
notification source in camera or mic range. Lock your resolution before the
first take and don't change it mid-project — cutting between two resolutions
is the single most obvious "this was assembled carelessly" tell.

---

## 0:00–0:20 — Cold open

**Visual:** Split screen, built in post, not live: left half is the dashboard's
four-strategy table already fully rendered and still; right half is a
terminal mid-way through `python demo.py --judge` actively printing.

**Motion:** As you say "eleven lakh rupees," the ₹1,113,772 figure on the left
does a kinetic counter-flip up from ₹0 — the digits should visibly roll, not
snap. As you say "fifty-nine thousand, seven hundred and fifty-five," the
delta number does the same flip, landing in red with a fast scale-in punch on
the final frame.

**Why split-screen and not just the dashboard:** the right side proves within
the first five seconds that the left side isn't a mockup — a viewer's very
first instinct with any polished number is "is that real or design," and this
answers it before they finish forming the thought.

**[ACK]** none yet — this beat is establishing stakes, not answering doubts.

---

## 0:20–0:50 — The problem nobody names correctly

**Visual:** Full-screen dashboard, scrolled to the "what actually happens to
1,000 failed payments" breakdown. As each cause is named in voice, that row
highlights (background tint, not a hard box) — synced word-for-word, not
scrolled past.

**Motion:** When you say "almost thirteen percent... never even failed," the
uncaptured-authorization row visually detaches slightly from the rest of the
list (a small vertical offset, held for one second) before rejoining — a
silent visual argument that this category doesn't belong with the others.

**[ACK]** As you say "some of them you're legally not allowed to retry at
all," fire the citation chip: `RBI · Auto-debit notice, 2019`. This is the
first proof that "legally not allowed" isn't a rhetorical flourish — it's a
named regulation, on screen, the instant you say it.

---

## 0:50–1:35 — How it actually decides

**Visual:** Not the dashboard. Cut to a clean four-box flow diagram (build
once, animate stage-by-stage): `DIAGNOSE → GATE → SCORE → LEDGER`. Each box
lights up as you reach that word in the script — this is the one moment in
the video that is intentionally not a live terminal, because the point being
made is architectural, not numerical, and a diagram teaches structure faster
than scrolled text does.

**Motion:** On "ninety-four percent... table lookup," a small annotation
appears under the DIAGNOSE box: `94% cited · 6% inferred`. On "eleven hard
rules," the GATE box visibly expands to show a scrollable list of rule titles
(real ones, pulled from `rules.yaml`, not placeholder text) before collapsing
back.

**[ACK]** On "eleven isn't the claim, the pattern is," the GATE box gets a
small `+1 rule = 1 file` annotation — pre-empting "is that enough rules"
before a judge finishes forming the thought.

**[ACK]** On "nothing downstream is even allowed to see an option the
rulebook already killed," show a one-frame code excerpt (real, from
`due/core/policy/engine.py`) of the `permitted` set being passed forward —
proving the architectural claim with actual source, not an assertion about it.

**[ACK]** On "tamper-evident, not tamper-proof... the real fix is already
built in," the LEDGER box gets a one-line annotation: `Ledger.head → external
anchor (ready)`. This is the moment that answers "isn't an editable log a
security hole" before anyone gets to ask it out loud.

---

## 1:35–2:10 — One real refusal

**Visual:** Cut live to the dashboard's refusal walkthrough section. This is
proof moment #1 — treat it as the first real "camera stops lying to you"
beat.

**Motion:** Move the cursor (not a finger, not a laser pointer graphic — the
actual cursor) down each gate row in sequence as you narrate: pass, pass,
pass, pass, pass, pass — then DEFER tag animates in — then, on "this customer
opted out," the BLOCK tag animates in with a distinct color and a half-second
pause before you continue. The **sequence of colors is doing the persuasion**;
slow down here rather than talking over the animation.

**[ACK]** The line "consent overrides the profit calculation" gets the
✓-answered overlay: *"blocked with ₹5,283 sitting on the table — verified live"*.
This is the single strongest proof-of-seriousness beat in the entire video;
do not compress it.

---

## 2:10–2:45 — The comparison, and the split that matters

**Visual:** Scroll to the four-strategy table, then to the Tier A / Tier B
cards immediately below it. No cuts — one continuous scroll, so the viewer
feels the two things are one argument, not two slides.

**Motion:** Counter-flip on ₹565,138 as you name it. On "nobody can argue with
a count," the four Tier A numbers (violations, attempts, contacts, recovery %)
each get a small locked-padlock icon appearing next to them, one at a time —
a visual metaphor for "assumption-free," landing exactly on the words that
make the claim.

**[ACK]** As you say "I checked that four different ways," a small strip of
four tick marks appears and fills in left to right: *seed sweep · scale test ·
adversarial batch · zero-cost sweep*. This single overlay pre-empts "did you
just check this once" without needing a spoken sentence to do it.

---

## 2:45–3:15 — Breaking it on purpose

**Visual:** Hard cut to Terminal B, full-screen, no overlay chrome at all —
this is the one moment the video should look like a real terminal and nothing
else, because that rawness is the credibility signal.

**Do:** Run `python tools/mutation_check.py` **live, on camera, in real time.**
Never a pasted screenshot here — a judge who has sat through five other
buildathon videos has already learned to distrust a static "test results"
slide, and this is the beat that separates you from that pile.

**Motion:** While the eight mutations run, let the terminal output itself be
the visual — no overlay competing with it. The moment it finishes, freeze-frame
for one full second on `8/8 caught` before cutting away.

**[ACK]** Immediately after the freeze, a caption card (2 seconds, plain
text, no graphic): *"this tool also found two of my own tests were passing
without testing anything — fixed in the commit history."* This is the
strongest self-critical beat in the video and it needs zero embellishment —
let the plain statement do the work.

---

## 3:15–3:45 — Where I'm wrong

**Visual:** Cut to the dashboard's sensitivity slider. **Drag it live, on
camera** — never a before/after screenshot pair.

**Motion:** As the slider moves left, the winner label visibly flips from
green ("Due wins") to red ("blind retry wins") in real time, in sync with you
saying "blind retry wins, by about nine percent." Hold on the red state for a
beat before continuing — do not immediately drag it back.

**[ACK]** While the red state holds, the ✓-answered overlay fires:
*"published, not hidden — this exact boundary is in the README and locked by
a test."* This is proof moment #3 and arguably the single highest-credibility
thirty seconds in the whole submission, because almost no other team will
voluntarily show a judge the spot where their own pitch fails. Do not cut this
under any time pressure.

---

## 3:45–4:10 — Not luck, and not just rules

**Visual:** Terminal C, `pytest -q` already run, output visible (160 passed).
Then a quick cut to a small pre-rendered chart: 50 dots, one per seed, 49 of
them one color, 1 (seed 18) a different color and labeled — built once in
advance since the full 50-seed sweep takes too long to run live.

**Motion:** On "quadruple the normal outage rate," a small stat card slides in:
`4x issuer outage · 0 violations` — answering "how hard did you actually push
it" with a number instead of an adjective.

**[ACK]** On "forty-six point six... forty-eight point seven... I cut it," show
three bars (majority-class floor, heuristic, theoretical ceiling) with the gap
between the last two visually tiny compared to the gap before it — the chart
itself argues "not worth it" before you finish the sentence.

---

## 4:10–4:30 — Close

**Visual:** Back to the dashboard, scrolled to the "what building this
actually caught" timeline.

**Motion:** Let the final line land on a completely still frame — no scroll,
no animation — for the last two seconds. A video that keeps moving through its
own closing line reads as unfinished; stillness reads as confidence.

**Do:** Say the repo URL and dashboard URL out loud, once, clearly, while both
appear as plain on-screen text (not a stylized card — just legible text a
judge could pause and read). Cut straight from this still frame into the
closing title card described above — no fade to black in between, it kills
the momentum you just built.

---

## Recording mechanics

- **Record in segments, not one continuous take.** The mutation-check and
  pytest beats are the easiest to re-shoot in isolation if you flub a line —
  you should never need to redo all five minutes for one word in the middle.
- **Audio quality matters more than video polish.** A judge will forgive
  slightly soft video; they will not forgive audio they have to strain to
  hear. A USB or headset mic beats a laptop mic by a wide margin.
- **Leave a few seconds of silence at the start and end of every segment**
  before cutting — it makes editing transitions painless later.
- **Watch the full assembly once with sound off.** If you can't follow what's
  happening from the visuals alone, the sequencing is wrong — fix that before
  touching the script again.
- **Watch it a second time with sound only, eyes closed.** If a number doesn't
  land as a number without seeing it, slow your pacing around it.
- **Do the edit pass — music, transitions, kinetic text — last, on the whole
  assembled cut, not per segment as you go.** Applying the visual identity
  once at the end is what makes it look like one consistent piece of work
  instead of nine separately styled clips stitched together.

---

## What to cut, in this exact order, if you're over 5:00

1. The 0:20–0:50 problem section — trim the row-highlight animation, keep the
   spoken content and the single citation chip.
2. The closing timeline in the last beat — show two entries instead of all of
   them.
3. The 50-seed chart in the 3:45–4:10 beat — state the numbers verbally instead
   of showing the chart.
4. **Never cut:** the refusal walkthrough (1:35–2:10), the live mutation check
   (2:45–3:15), or the live sensitivity slider (3:15–3:45). Those three
   sequences, plus their **[ACK]** overlays, are the entire case for hiring
   you rather than just the entire case for the product.

---

## The submission package — what actually goes in, and how

A strong buildathon submission is not "send everything you built." It's a
small, correctly-labeled set of things a busy panelist can act on in under two
minutes without asking a single clarifying question.

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
   that someone triaging hundreds of entries knows what track and what makes
   this one worth a closer look. Something like: *"Track 03 — a policy-gated
   payment recovery engine. 160 tests, a live interactive dashboard, and an
   honest sensitivity analysis showing exactly where the core claim stops
   holding."* Adjust to their actual form fields; don't pad it.

### What not to submit

- **Don't attach the domain primer, build plan, FAQ, or other internal working
  docs as separate deliverables.** They're valuable — that's why they live in
  `docs/`, where anyone curious can find them — but leading with them signals
  "research notebook," not "shipped system." Let the README and the dashboard
  be what's pushed at the panel; let the deeper docs reward someone who clicks
  in.
- **Don't send a zip file of the code** if a Git URL is accepted. A zip loses
  the commit history, and the commit history — real bugs found and fixed in
  sequence, not smoothed over — is itself part of your evidence.
- **Don't over-explain in writing what the video already shows.** If the
  submission form has an optional long-form description field, resist filling
  it with a full essay. Two or three sentences plus the links is more
  professional than a wall of text — it signals you trust your own work to
  speak for itself.

### The last thing to do before you hit submit

Do one full cold run-through as if you were a panelist who has never spoken to
you: open the repo link in a private browser window, open the dashboard link
in another, watch the video once at 1x speed on a phone-sized window (a lot of
early screening happens on a phone or a small laptop, not a monitor). If
anything is confusing, broken, or too small to read at that size, that's the
fix to make — not a bigger feature, a smaller polish pass.
