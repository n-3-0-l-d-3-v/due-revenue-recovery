# Domain Primer — Revenue Recovery in Indian Payments

Reference document for the Razorpay AI Buildathon, Track 03.
Purpose: understand the money, the failure modes, and the constraints *before* writing code.
Every number here is sourced; see `## Sources` at the bottom.

---

## Part 1 — Who is actually in a payment

A CS student's mental model of a payment is `POST /pay -> 200 OK`. The real thing has five parties, and revenue leaks in the gaps between them.

| Party | Role | Example |
|---|---|---|
| **Customer** | Holds the money | Has a card / UPI / bank account |
| **Issuer** (issuing bank) | Bank that gave the customer the card/account. **Decides approve or decline.** | HDFC, SBI, ICICI |
| **Network** | Rails between issuer and acquirer. Sets the rulebook. | Visa, Mastercard, RuPay, NPCI (for UPI) |
| **Acquirer** | Bank that holds the *merchant's* money | Axis, ICICI |
| **PSP / Gateway** | Orchestrates all of the above so the merchant doesn't have to | **Razorpay**, Stripe, PayU |
| **Merchant** | Wants the money | The business using Razorpay |

**The single most important thing to internalise:** the *issuer* decides whether a payment succeeds. Razorpay does not. The merchant does not. So "recovering" a failed payment means changing the conditions under which the issuer is asked again — different time, different instrument, different amount — or asking the customer to act. You cannot force money to move.

---

## Part 2 — Payment lifecycle, and where money leaks

```
order created -> payment attempted -> authorized -> captured -> settled
                       |                   |            |
                    FAILED             not captured   refunded /
                  (leak #1)             (leak #2)     charged back
                                                       (leak #3)
```

- **Authorized** — the issuer has put a *hold* on the customer's funds. The money has NOT moved to the merchant. The hold expires (typically within days).
- **Captured** — the merchant claims the held funds. **This is the step that actually takes the money.**
- **Settled** — Razorpay transfers the captured money to the merchant's bank account, minus fees, on a settlement cycle (T+2 style).

**Auto-capture vs manual capture** matters enormously, and the windows are concrete:

- Auto-capture applies to payments authorized within **2 days** of creation; manual capture within **3 days**.
- Payments left in `authorized` are **auto-refunded to the customer** (docs cite 3–5 days depending on the page; treat 5 days as the outer bound and verify against your own account settings).
- `automatic_expiry_period` / `manual_expiry_period` are configurable per merchant.

**Correction worth internalising:** the money does *not* vanish into nowhere — Razorpay returns it to the customer. So the loss is not embezzled float, it is **a won sale that un-wins itself**, plus a customer who sees a debit followed by a refund and files a support ticket. That is still real, quantifiable loss (lost revenue + support cost + trust damage), but state it accurately or you will be corrected in the panel.

**Late authorization** is the closely-related Razorpay concept and a genuinely good recovery target: the bank confirms after the customer has already given up. Razorpay polls for **3 days** to catch these. This produces the classic *"Transaction Failed, Money Debited"* complaint — a real, named, expensive problem that merchants feel directly.

### The five leak points we care about

| # | Leak | What it looks like | Recoverable? |
|---|---|---|---|
| 1 | **Failed payment** | Attempt made, issuer/gateway declined | Sometimes — depends entirely on *why* |
| 2 | **Uncaptured authorization** | Authorized, never captured, auth window closing | **Almost always — pure operational miss** |
| 3 | **Abandoned checkout** | Order created, no payment attempted | Sometimes — needs customer nudge |
| 4 | **Failed mandate / renewal** | Recurring autopay bounced | Often — but heavily regulated |
| 5 | **Involuntary churn** | Renewal failed, subscription lapsed, customer gone | Time-sensitive; value decays fast |

Leak #2 is the sleeper. Almost no competing submission will address it, and it is the easiest money in the list.

---

## Part 3 — The failure taxonomy (the core of the project)

Razorpay returns a structured error on failure:

```
code        BAD_REQUEST_ERROR | GATEWAY_ERROR | SERVER_ERROR
source      customer | business | bank | gateway | network
step        payment_initiation | payment_authentication | payment_authorization | payment_response
reason      insufficient_funds | card_expired | payment_timed_out | ...
description human-readable
metadata    payment_id, order_id
```

`source` + `step` + `reason` together tell you **who failed, where, and why** — and therefore what the correct recovery action is. This triple is the input to our entire decision engine.

### The critical split: technical decline vs business decline

- **Technical decline** — infrastructure broke. Bank down, gateway down, network timeout. *The customer was willing and able to pay.* → **Retry is highly likely to work.**
- **Business decline** — the issuer deliberately said no. No funds, wrong PIN, limit hit, card blocked. *Retrying the identical request will usually fail identically.* → **Retry must be conditional.**

On UPI in India, NPCI data attributes **81.7% of failures to business decline** and **18.26% to technical decline**. So the naive "just retry everything" strategy attacks the smaller slice while burning attempts on the larger one.

### Card failure reasons (Razorpay), classified by what to actually do

| Reason | Source | Recovery strategy |
|---|---|---|
| `bank_technical_error` | Customer's bank | **Retry** once issuer health recovers |
| `gateway_technical_error` | Gateway | **Retry**, ideally via alternate route |
| `payment_timed_out` | Customer (10 min limit) | **Retry** — send a fresh payment link |
| `insufficient_funds` | Customer account | **Delay** retry — salary-day / month-start timing |
| `transaction_limit_exceeded` | Card/bank limit | **Delay** to next day, or switch instrument |
| `payment_cancelled` | Customer action | **Nudge**, don't auto-retry |
| `authentication_failed` (OTP) | Customer action | **Nudge** with fresh link |
| `incorrect_cvv` | Customer action | **Nudge** — needs human input |
| `card_expired` | Card status | **TERMINAL for retry** — must update instrument |
| `card_not_enrolled` | Bank | **TERMINAL** — customer must enable online txns |
| `card_disabled_for_online_payments` | Bank | **TERMINAL** — customer must act |
| `debit_instrument_inactive` | Bank | **TERMINAL** — customer must activate |
| `debit_instrument_blocked` | Bank/customer | **TERMINAL** — do not retry |
| `payment_risk_check_failed` | Bank (fraud flag) | **TERMINAL** — retrying looks like an attack |
| `card_declined` / `payment_failed` | Bank, no reason given | **Ambiguous** — cap at 1 cautious retry |

### UPI failure reasons

| Reason | Source | Recovery strategy |
|---|---|---|
| `bank_technical_error` | UPI provider down | **Retry** after downtime clears |
| `partner_bank_downtime` | Partner bank | **Retry** later |
| `partner_bank_technical_issues` | Partner bank | **Retry** later |
| `gateway_technical_error` | Gateway | **Retry** |
| `credit_failed` | System | **Retry** |
| `payment_collect_request_expired` | 10-min timeout | **Retry** with fresh collect request |
| `payment_timed_out` | Timeout | **Retry** |
| `insufficient_funds` | Customer account | **Delay** retry |
| `payment_declined` | Bank | **Cautious** single retry |
| `payment_cancelled` | Customer | **Nudge** |
| `customer_bank_account_mismatch` | Customer | **Nudge** — wrong account selected |
| `invalid_vpa` | UPI system | **TERMINAL** — VPA must be fixed |
| `vpa_resolution_failed` | UPI system | **TERMINAL** — escalate |

**These two tables are the intellectual core of the submission.** Everyone else's project treats a failure as a boolean. Ours treats it as a diagnosis with a matched treatment plan.

---

## Part 4 — Recurring payments in India, and the law

Recurring payments (subscriptions, SIPs, OTT, insurance) run on a **mandate**: standing permission to debit. In India this is tightly regulated by the RBI, and the rules directly constrain what a recovery agent may do.

**RBI e-mandate framework — the rules that bind us:**

1. **24-hour pre-debit notification.** The issuer must notify the customer at least 24 hours before the debit, including merchant name, amount, date/time, and reference. → *An agent cannot fire an autopay retry on impulse. It must schedule, notify, wait out the window, then debit.*
2. **Customer can opt out** of any specific transaction after receiving that notification. → *Consent state can change between decision and execution. Re-check before acting.*
3. **AFA (Additional Factor of Authentication)** — required for e-mandate transactions above **₹15,000**. Insurance premiums, mutual fund subscriptions, and credit card bill payments are exempt up to **₹1,00,000**. → *Amount determines whether a retry can be silent or needs the customer in the loop.*
4. **Post-transaction notification** is mandatory, with grievance redressal details.
5. **No customer charges** for using the e-mandate facility.

**Razorpay's own subscription retry behaviour:** on a T+3 cycle, it retries once per day for 3 days (excluding the charge date). If all retries fail, the subscription moves to **`halted`**.

That `halted` state is a business decision point: it's where a merchant permanently loses a paying customer, and where a smarter recovery layer earns its keep.

---

## Part 5 — Why you cannot just retry

This is the section that makes the project interesting. Retrying is not free.

### Card network retry limits — real financial penalties

- Visa and Mastercard cap you at **15 retry attempts per card per 30-day window**.
- Reattempts should stay under **9 within any 24-hour window**.
- Exceeding limits triggers penalties **starting at $5,000/month**, escalating to **$50,000–$100,000** at high volume. On merchant statements it appears as `VI NEVER APPROVE REATTEMPT FEE`.
- Mastercard's **MAC 03 "Do Not Try Again"** response: retrying after it incurs **$0.10 per attempt** under the Excessive Attempts program.

So a blind-retry agent is not merely inelegant — **it is a system that generates fines.** Our policy gate exists to make that structurally impossible, and we can demonstrate it on camera.

### The other constraints

- **Customer trust / contact fatigue.** Six dunning emails in a week doesn't recover the payment; it causes voluntary churn on top of the involuntary kind. Contact frequency needs a hard cap.
- **Issuer trust.** Hammering an issuer with declines degrades your reputation with that issuer and quietly lowers approval rates on *good* future transactions.
- **Fraud-flag interaction.** Retrying a `payment_risk_check_failed` looks like card-testing behaviour. You risk being classified as the attacker.
- **Cost per attempt.** Every retry, SMS, and email costs money. Chasing ₹40 with ₹60 of effort is a loss booked as a win.
- **Consent and DND.** Contacting someone who opted out is a compliance breach, not an optimisation.

---

## Part 6 — The economics of a single recovery decision

Every decision reduces to one inequality:

```
Expected value of acting = P(recovery | reason, instrument, timing, history) × amount_at_risk
Cost of acting           = attempt_cost + contact_cost + penalty_risk + churn_risk

ACT only if  EV > Cost  AND  every policy gate passes.
```

Three things fall directly out of this, and they are what lift the project above the median:

1. **`P(recovery)` is not a constant — it depends on *when* you retry.** An `insufficient_funds` failure on the 28th has a far better chance on the 1st (salary day) than four hours later. Learning the best timing per (issuer × reason × hour × amount band) is a **contextual bandit** problem.
2. **Some customers would have paid anyway.** Spending a nudge on them is wasted, and spending one on a lost cause is also wasted. You only want the **persuadables**. This is **uplift modelling** — estimating the *causal* effect of the intervention, not just the outcome probability.
3. **Attempts and contacts are a finite budget** (network caps, fatigue caps). Allocating a fixed budget across a batch to maximise recovered rupees is a **knapsack problem**.

Naive project: "retry failed payments."
This project: "allocate a constrained intervention budget to maximise expected recovered revenue, subject to regulatory and network constraints, with every decision auditable."

---

## Part 7 — Vocabulary you must be fluent in for the panel

| Term | Meaning |
|---|---|
| **Dunning** | The structured process of recovering failed payments via retries + customer outreach |
| **Involuntary churn** | Customer lost because payment failed, not because they chose to leave |
| **Voluntary churn** | Customer actively cancelled |
| **Smart / adaptive retry** | Retrying at algorithmically chosen times rather than fixed intervals |
| **Card updater (ABU/VAU)** | Network service that auto-refreshes stored card details when a card is reissued |
| **Authorization** | Issuer holds funds; money has not moved |
| **Capture** | Merchant claims held funds; money moves |
| **Settlement** | Payout from PSP to merchant bank, net of fees |
| **Chargeback** | Customer disputes; money forcibly reversed |
| **Mandate / e-mandate** | Standing permission to auto-debit |
| **AFA** | Additional Factor of Authentication (India-specific) |
| **Pre-debit notification** | Mandatory 24h warning before an autopay debit |
| **Technical decline** | Infrastructure failure |
| **Business decline** | Deliberate issuer refusal |
| **MRR** | Monthly Recurring Revenue |
| **Halted subscription** | Razorpay state after all retries are exhausted |

### Benchmarks worth quoting

- Failed payments cost SaaS businesses **5–15% of recurring revenue monthly**.
- Involuntary churn is **20–40% of total churn**; median annual rate **1.25%**.
- Dunning recovery: **~49% annually** (Recurly); best-in-class **70–85%**.
- By method: smart retry alone **~40%**, card updater **~25%**, emails **+15–20%**; **all three combined ~70%**.
- Razorpay reports smart retry tools recovering **up to 57%** of initially failed subscription attempts. **Treat this as vendor marketing**, not a benchmark — it is a ceiling figure that varies enormously by vertical and failure mix. Quote it only with that caveat attached, and always segment by reason code.
- Razorpay's own **Intelligent Retry Engine** (beta) claims **+8% debit collections over baseline** — a far more sober and more credible number than most vendor claims, and a better one to reason against.
- UPI system-wide technical decline fell from 8–10% (2016) to **~0.8% (2025)**; blended merchant success rates sit around **92–96%**.

**Read that last line carefully — it's the honest framing of our problem.** UPI infrastructure is excellent now. So recovery is *not* about infrastructure failure; it's about the 4–8% of business declines, timing, and customer action. Saying this in the pitch signals we didn't just recycle a stale statistic.

---

## Part 8 — Loopholes and gotchas (panel-interview ammunition)

These are the non-obvious things. Knowing them is what makes someone sound like they've worked in payments rather than read about them.

1. **Retry success rate is not the metric. Net recovered value is.** A system with a 60% retry success rate that burned 5× the attempts can be worth *less* than a 45% system that fired once. Always report recovered rupees **and** attempts spent.

2. **Uncaptured authorizations are silent revenue loss.** The payment never "failed," so it appears in no failure report — the auth simply expires and Razorpay refunds the customer. Mature billing stacks do handle this; the claim to make is that it is **under-monitored by mid-market merchants and largely absent from competing hackathon submissions**, not that the industry has never thought of it.

3. **A retry that succeeds may still be a loss.** If retrying annoyed the customer into cancelling next month, you traded ₹500 now for ₹6,000 of lifetime value. Recovery must be evaluated against churn risk.

4. **Consent is stateful and can change mid-flight.** A customer can opt out after the pre-debit notification. Checking consent at decision time and acting hours later is a compliance bug.

5. **"Do not try again" codes are legally distinct from "try later" codes.** Treating them alike is what generates network fines. The taxonomy is not cosmetic — it is the compliance boundary.

6. **Idempotency is a money-safety property, not an engineering nicety.** A retried API call without an idempotency key can double-charge a real customer. In payments, at-least-once delivery plus non-idempotent handlers equals fraud complaints.

7. **Timing beats persistence.** One well-timed retry frequently outperforms five poorly-timed ones, because most business declines are *transient states of the customer's balance*, not permanent facts.

8. **Aggregate recovery rate hides the truth.** Recovery rates on `bank_technical_error` and on `card_expired` describe wildly different populations. Always segment by reason, or the number is noise.

9. **The exception list is a feature, not an embarrassment.** A system claiming 100% automated handling is lying or unsafe. An honest "these 23 need a human, and here's why" is what a payments team trusts — and the buildathon bar explicitly asks for it.

10. **Recovering money you should not have charged is negative value.** If the customer already cancelled, or the item was out of stock, "recovery" is a future refund plus a dispute. Recovery must be gated on the underlying obligation still being valid.

---

## Part 9 — Where Razorpay already plays (and where the gap is)

**State this openly in the README.** Pretending the overlap doesn't exist reads as ignorance; naming it reads as domain awareness.

### CRITICAL — read before writing a single line of the pitch

Razorpay launched an **Intelligent Retry Engine** (beta) at Global Fintech Fest 2026, as part of its **Intelligent Revenue-Protect** stack for UPI Autopay. Their own marketing explicitly attacks fixed-interval retries for "not understanding user context, bank availability, or merchant priorities," and reports **+8% debit collections over baseline**. The stack targets three moments: mandate-registration drop-off, debit-time retry, and churn signals.

**This means the sentence "Razorpay's retry is fixed-schedule and dumb" is now false.** Saying it to a panel that may include people who shipped Intelligent Retry Engine would be a self-inflicted wound. Delete that framing from every draft.

Razorpay currently ships:
- **Optimizer / Smart Routing** — dynamic multi-gateway routing; reroutes failures at the gateway layer.
- **Intelligent Retry Engine (beta)** — context-aware retry timing for UPI Autopay debits.
- **Subscriptions retry** — T+3 daily retries on the standard path, then `halted`.
- **Downtime API** — issuer/gateway health signals merchants can consume.
- **Late-authorisation handling** — polls banks for 3 days; auto-refunds uncaptured auths.

### Reframe: build *toward* their roadmap, not against it

The correct read is that this is **good news**. Razorpay is investing here, which proves the problem is real and strategically live for them. An intern candidate who independently arrived at the same problem space — and then went one layer further — is far more interesting than one who picked something Razorpay does not care about.

What their stack, by its own description, does **not** cover — **the merchant policy layer**:

- It optimises the **individual debit attempt**. It does not do **portfolio allocation** — spending a finite attempt-and-contact budget across a whole batch of at-risk payments to maximise total recovered value.
- It is **PSP-side**, so it is structurally blind to **merchant-side economics**: contact fatigue, customer LTV, churn risk from over-contacting, cost per outreach.
- It does not emit a **merchant-facing, replayable audit trail** proving that every action stayed inside Visa/Mastercard attempt caps and RBI e-mandate rules.
- It optimises **success rate**, not **net recovered value** after attempt cost, contact cost, penalty risk, and churn risk.
- It covers UPI Autopay debits; it does not unify **uncaptured authorizations, abandoned checkouts, and one-time payment failures** into one recovery portfolio.
- It stops at `halted`. It has **no post-`halted` playbook**.

**Positioning line (use this one):** *Razorpay's Intelligent Retry Engine optimises the debit attempt at the gateway layer. This optimises the merchant's recovery portfolio — allocating a constrained, compliance-bounded budget across every at-risk rupee, and proving in an audit trail that no action ever breached a network or RBI limit.*

### Extra actions most systems skip (build these)

- **Instrument switch** — recovery is not only "retry the same card." Prompt for a different instrument, a VPA fix, or a card-updater (ABU/VAU) refresh.
- **Post-`halted` playbook** — pause offer, instrument-update flow, win-back sequence with different copy, or clean human hand-off. Native tooling ends at `halted`; this is genuinely open ground.
- **Salary-cycle-aware timing** — for `insufficient_funds` and limit breaches, weight retries toward the 1st–5th of the month. High ROI, India-specific, and works as a hard-coded prior *before* any learned model exists.

---

## Part 10 — Limits of this analysis, and what would falsify it

Include a version of this section in the README. Stating limits precisely is a credibility *gain* with payments engineers, who have seen a hundred demos that claim certainty they cannot possibly have.

### The circularity problem — state it before a judge does

Our data is synthetic. **We wrote the generator, so we defined the causal structure.** That means:

| Component | Is the synthetic-data critique fatal? |
|---|---|
| Policy gate (network caps, RBI windows, consent) | **No** — compliance is correct-by-construction and verifiable on any input |
| Audit trail + deterministic replay | **No** — an integrity property, data-independent |
| Reason → strategy taxonomy | **No** — derived from documented Razorpay error semantics and network rules, not learned |
| Uncaptured-auth / late-auth detection | **No** — detection of a known state, not a prediction |
| Net-value accounting | **No** — arithmetic over explicitly stated cost assumptions |
| **Bandit timing learning** | **Partly** — it can only prove the mechanism works, not that the timing insight is true |
| **Uplift model** | **Yes, most exposed** — "measured causal lift" on self-generated data is circular |

Note the intellectual consistency point: this is the *same* objection that ruled out fraud detection on synthetic data for Track 02. Honesty requires applying it to ourselves.

### The protocol that makes the simulator credible anyway

1. **Seed priors from published external data**, never from invented numbers: the NPCI technical-vs-business decline split, documented Razorpay reason-code semantics, published dunning benchmarks, real network attempt caps.
2. **Publish the generative parameters** openly in the repo. A reader can inspect exactly what world we assumed.
3. **Run sensitivity analysis.** Show the policy layer beats fixed T+3 across a *range* of assumptions, and name the region where it stops winning. This converts "you rigged it" into "here are the conditions under which this holds."
4. **Separate claim types explicitly.** Say "*proven*" only for compliance, audit integrity, and throughput. Say "*simulated under stated priors*" for every recovery-rate figure. Never blur the two.
5. **Name the falsifier out loud:** *"Replay this against real merchant traffic. If the reason-conditioned timing priors don't hold, the bandit layer degrades to the fixed schedule — and the policy and audit layers still work."* A system that degrades gracefully to the status quo is a safe system.

### Presentation risk

This primer is a **working reference for the builder, not a document for judges.** The submission's README and 5-minute video must be short, concrete, and system-shaped. If the deliverable reads like a research paper, it signals someone who studied the problem rather than someone who shipped. Keep the depth in the repo; keep the pitch in rupees, screenshots, and one blocked-violation demo.

---

## Sources

- Razorpay Intelligent Retry Engine / Revenue-Protect — https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/
- Razorpay payment capture settings — https://razorpay.com/docs/payments/payments/capture-settings/
- Razorpay late authorisation handling — https://razorpay.com/docs/payments/payments/late-authorisation/
- Razorpay card error codes — https://razorpay.com/docs/errors/payments/cards/
- Razorpay UPI error codes — https://razorpay.com/docs/errors/payments/upi/
- Razorpay subscription payment retries — https://razorpay.com/docs/payments/subscriptions/payment-retries/
- Razorpay Optimizer — https://razorpay.com/optimizer-intelligent-payments-routing/
- Visa/Mastercard retry rules and penalties — https://www.slickerhq.com/resources/blog/visa-mastercard-payment-retry-rules
- RBI e-mandate framework — https://www.chargebee.com/docs/payments/2.0/others/rbi-e-mandate
- RBI 24h pre-debit notification — https://www.aninews.in/news/business/rbi-tightens-auto-debit-rules-24-hour-prior-alert-now-mandatory-for-recurring-payments20260421202816/
- UPI success rate benchmarks — https://productgrowth.in/insights/fintech/upi-payment-success-rates/
- NPCI decline split (business vs technical) — https://www.business-standard.com/amp/article/economy-policy/insufficient-balance-wrong-pin-top-reasons-for-failed-digital-transactions-121122700487_1.html
- Involuntary churn and dunning benchmarks — https://recurly.com/blog/failed-payment-recovery-data-based-strategy/
- Involuntary churn statistics — https://www.dunningcompare.com/stats/involuntary-churn-statistics-2026
