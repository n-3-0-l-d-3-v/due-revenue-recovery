# Recoup — a revenue recovery control plane

**Razorpay AI Buildathon 2026 · Track 03: AI Revenue Recovery**

Recoup turns every at-risk rupee into a bounded, policy-gated recovery decision — and
proves in a replayable audit trail that no action ever breached a card-network attempt
cap or an RBI e-mandate rule.

## The core design rule

**The policy gate runs before the learner. Always.**

```
RiskEvent
  → Diagnose            reason code → root cause (evidence-linked)
  → Enumerate actions   retry / delay / nudge / instrument-switch / terminal
  → POLICY GATE         filters to the permitted set — hard constraints only
  → Score EV            net value, over permitted actions only
  → Execute             re-validate the gate at execution time, then act
  → Ledger              hash-chained decision record
```

A learner may only ever choose from the permitted set, so **learning cannot generate a
fine or a compliance breach.** Decisions are re-validated at execution time, because
consent is stateful — a customer can opt out after the RBI pre-debit notification.

## Claim discipline

Two vocabularies, never blurred:

- **Proven** — compliance gates, audit integrity, replay determinism, throughput.
- **Simulated under stated priors** — every recovery-rate and rupee figure.

## Data handling

No PAN ever enters this system. Instruments are identified by a salted token.
Test-mode Razorpay keys only.

## Status

Day 0. Core models and the hash-chained decision record have landed.
