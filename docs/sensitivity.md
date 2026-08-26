# Sensitivity Analysis

Every economic parameter in this project is `[ASSUMED]`. None is measured from real
merchant data, because none could be. This document reports how hard each assumption
is working, and where the conclusions stop holding.

It is written to be read by someone looking for the weak point. The weak point is
named in §3.

---

## 1. The claims, separated by what they depend on

Not all of the submission's claims rest on the same footing. Collapsing them into one
headline would be the dishonest move, so they are stated separately.

### Tier A — independent of every economic assumption

| Claim | Measured | Depends on |
|---|---|---|
| Gated agent commits **0 policy violations**; blind retry commits **2,493** | ✅ | Nothing. Violations are counted by evaluating actions against the rulebook. No cost parameter can move this number. |
| Gated agent spends **464 attempts** vs blind retry's **4,652** (10.0×) | ✅ | Nothing. These are counts of actions taken. |
| Gated agent sends **298 contacts** vs **1,768** (5.9×) | ✅ | Nothing. |
| It recovers **87%** of what blind retry recovers while doing so | ✅ | Nothing. |

Verified under four different cost models including one with all costs zeroed
(`test_zero_violations_is_independent_of_every_cost_assumption`).

**These are the claims that lead the pitch**, precisely because no assumption can
be attacked to undermine them.

### Tier B — depends on one qualitative assumption

| Claim | Depends on |
|---|---|
| Gated agent has the **highest net value** (₹335,144 vs blind retry's **−₹239,741**) | That annoying customers is not *free* — i.e. that repeated retries and repeated contact carry some non-zero customer-retention cost. |

Not on a specific magnitude. See §3.

---

## 2. What the sweeps show

Held fixed: world seed 42, 1,000 events, ₹1,113,772 at risk.

### Contact churn hazard (baseline 0.020)

```
value      fixed_t3   blind_retry   gated_agent   winner
0           236,167       313,162       369,403   gated_agent
0.005       236,167       168,642       360,838   gated_agent
0.010       236,167        24,122       352,274   gated_agent
0.020       236,167      -239,741       335,144   gated_agent
0.050       236,167      -683,542       283,755   gated_agent
```

### Retry churn hazard (baseline 0.004)

```
value      fixed_t3   blind_retry   gated_agent   winner
0           288,320      -143,597       347,864   gated_agent
0.001       275,282      -167,300       344,684   gated_agent
0.004       236,167      -239,741       335,144   gated_agent
0.008       184,015      -331,811       322,423   gated_agent
```

**Either churn parameter can go to zero on its own and the ranking survives.**

### The minor parameters carry nothing

Swept across wide ranges; the ranking never flips:

| Parameter | Range swept | Flips? |
|---|---|---|
| `penalty_per_excess_attempt` | ₹0 – ₹200 | no |
| `retry_cost` | ₹0 – ₹40 | no |
| `contact_cost` | ₹0 – ₹25 | no |
| `p_support_ticket` | 0 – 0.15 | no |

Notably the **network penalty carries only 1.8%** of the result. The compliance
argument is worth making on its own terms — regulatory exposure, MID risk, issuer
standing — not as a monetary one. The fine is not what makes blind retry expensive.

### Across worlds, priors fixed

```
seed 42:  fixed_t3  236,167   blind_retry  -239,741   gated  335,144
seed 43:  fixed_t3  202,495   blind_retry  -159,682   gated  309,024
seed 44:  fixed_t3  229,272   blind_retry  -241,093   gated  324,870
seed 45:  fixed_t3  201,866   blind_retry  -334,502   gated  281,881
seed 46:  fixed_t3  199,995   blind_retry  -335,689   gated  241,817
```

Ranking is stable across all five. Blind retry is net-negative in all five.

---

## 3. The boundary — where the net-value claim fails

**Set BOTH churn terms to zero and blind retry wins.**

```
                recovered   attempts   violations       net value
fixed_t3          294,538       2151          715         288,320
blind_retry       439,822       4652         2493         418,198   <- wins
gated_agent       383,473        464            0         382,123
```

Blind retry takes it by ₹36,075 — 9%.

So the honest statement of the net-value claim is:

> Blind retry recovers more rupees. It is worth less **provided that repeatedly
> retrying and repeatedly contacting a customer carries any customer-retention cost
> at all.** If that cost is exactly zero, blind retry is the better strategy and we
> say so.

Attribution confirms this is the only load-bearing assumption:

```
gated_agent net value minus blind_retry net value: Rs 574,885

without churn              gap becomes  Rs  -36,074   (carries 106.3%)
without network penalties  gap becomes  Rs  564,591   (carries   1.8%)
without attempt cost       gap becomes  Rs  567,346   (carries   1.3%)
without support cost       gap becomes  Rs  572,913   (carries   0.3%)
without contact cost       gap becomes  Rs  574,414   (carries   0.1%)
```

### Is "retention cost is non-zero" a safe assumption?

It is the best-supported claim in the domain literature — involuntary churn is
20–40% of total churn, and dunning research consistently finds over-contacting
converts involuntary churn into voluntary churn. But it is an assumption about the
*direction* of an effect, not a measured magnitude for any specific merchant, and it
is stated as such.

The boundary is locked by `test_ranking_flips_when_all_retention_cost_is_removed`,
which asserts blind retry wins there. If someone later changes the model so that no
longer happens, that test fails and this document is out of date — which is the
point of testing a boundary rather than only testing the happy case.

---

## 4. What would falsify this

Replay against real merchant traffic with observed retention outcomes. Specifically:

1. Measure post-recovery cancellation rates against contact and retry counts. That
   directly estimates the two churn hazards and either confirms or kills Tier B.
2. Tier A survives regardless — attempt counts and rule violations are observable
   facts, not model outputs.
3. If the retention effect turns out to be zero, the correct product response is not
   to abandon the gate. It is to keep the gate for its compliance value and relax the
   value threshold, since the constraint that mattered was never the economics.
