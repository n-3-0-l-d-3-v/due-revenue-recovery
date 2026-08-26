"""Batch generator.

Two ideas make this simulator defensible rather than decorative:

1. **Latent state lives outside RiskEvent.** `RiskEvent` stays production-shaped —
   it carries only what a real ingestion pipeline would see. Everything the oracle
   needs to answer "would this action have worked?" lives in `SimWorld`. A
   strategy under evaluation is handed events, never the latent world.

2. **Outages are correlated.** One issuer degrading takes many payments with it,
   for a stretch of hours. Sampling failures independently would make the batch
   easier than reality and would flatter any strategy that reacts to issuer health
   — including ours. Correlated outages are what make the counterfactual honest.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from recoup.core.models import (
    DeclineClass,
    EventType,
    FailureSource,
    FailureStep,
    Instrument,
    RiskEvent,
    RootCause,
)
from recoup.sim import priors


# ---------------------------------------------------------------------------
# Latent world
# ---------------------------------------------------------------------------


@dataclass
class Outage:
    issuer: str
    day: date
    start_hour: int
    end_hour: int
    severity: float

    def covers(self, when: datetime) -> bool:
        return when.date() == self.day and self.start_hour <= when.hour < self.end_hour


@dataclass
class Customer:
    customer_id: str
    issuer: str
    ltv: Decimal
    salary_day: int
    success_days: list[int]
    contacts_this_week: int = 0
    consent_active: bool = True


@dataclass
class LatentEvent:
    """Hidden truth the oracle consults. Never visible to a strategy."""

    event_id: str
    seed: int
    root_cause: RootCause
    decline_class: DeclineClass
    # Day of month the customer's balance actually recovers. Only meaningful for
    # INSUFFICIENT_FUNDS — this is what makes retry timing a real decision.
    funds_available_day: int | None = None
    # Whether this customer would respond to outreach at all, given infinite patience.
    responds_to_nudge: bool = False
    # Whether the obligation behind the payment is still valid (order not cancelled).
    obligation_valid: bool = True


@dataclass
class SimWorld:
    """The generated world. Hand `events` to a strategy; keep the rest here."""

    seed: int
    events: list[RiskEvent] = field(default_factory=list)
    customers: dict[str, Customer] = field(default_factory=dict)
    latent: dict[str, LatentEvent] = field(default_factory=dict)
    outages: list[Outage] = field(default_factory=list)

    def outage_at(self, issuer: str, when: datetime) -> Outage | None:
        for o in self.outages:
            if o.issuer == issuer and o.covers(when):
                return o
        return None

    @property
    def amount_at_risk(self) -> Decimal:
        return sum((e.amount for e in self.events), Decimal("0"))


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------


def _weighted(rng: random.Random, weights: dict) -> object:
    keys = list(weights.keys())
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _amount(rng: random.Random) -> Decimal:
    raw = math.exp(rng.gauss(priors.AMOUNT_LOGNORM_MU, priors.AMOUNT_LOGNORM_SIGMA))
    clamped = min(max(raw, float(priors.AMOUNT_MIN)), float(priors.AMOUNT_MAX))
    return Decimal(str(round(clamped, 2)))


def _error_source(root_cause: RootCause) -> FailureSource:
    if root_cause in (RootCause.ISSUER_DOWN,):
        return FailureSource.BANK
    if root_cause in (RootCause.GATEWAY_DOWN,):
        return FailureSource.GATEWAY
    if root_cause in (
        RootCause.INSTRUMENT_EXPIRED,
        RootCause.INSTRUMENT_BLOCKED,
        RootCause.INSTRUMENT_NOT_ENABLED,
        RootCause.INSUFFICIENT_FUNDS,
        RootCause.LIMIT_EXCEEDED,
        RootCause.RISK_BLOCKED,
    ):
        return FailureSource.BANK
    return FailureSource.CUSTOMER


def _error_step(root_cause: RootCause) -> FailureStep:
    if root_cause in (RootCause.AUTH_FAILED,):
        return FailureStep.PAYMENT_AUTHENTICATION
    if root_cause in (RootCause.TIMEOUT, RootCause.CUSTOMER_ABANDONED):
        return FailureStep.PAYMENT_INITIATION
    if root_cause in (RootCause.ISSUER_DOWN, RootCause.GATEWAY_DOWN):
        return FailureStep.PAYMENT_RESPONSE
    return FailureStep.PAYMENT_AUTHORIZATION


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _build_outages(rng: random.Random, start: date, days: int) -> list[Outage]:
    outages: list[Outage] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for issuer in priors.ISSUERS:
            if rng.random() >= priors.ISSUER_OUTAGE_DAY_PROB:
                continue
            duration = rng.randint(*priors.ISSUER_OUTAGE_HOURS)
            start_hour = rng.randint(0, max(0, 23 - duration))
            outages.append(
                Outage(
                    issuer=issuer,
                    day=day,
                    start_hour=start_hour,
                    end_hour=start_hour + duration,
                    severity=rng.uniform(*priors.ISSUER_OUTAGE_SEVERITY),
                )
            )
    return outages


def _build_customers(rng: random.Random, n: int) -> dict[str, Customer]:
    customers: dict[str, Customer] = {}
    for i in range(n):
        cid = f"cust_{i:05d}"
        salary_day = rng.choice([1, 1, 1, 2, 2, 3, 5, 7, 28, 30])
        # Observed history clusters around the true salary day, with noise. Thin
        # history is realistic and is why the calendar prior needs a fallback.
        history_len = rng.choice([0, 0, 1, 2, 3, 4, 5])
        success_days = [
            max(1, min(28, salary_day + rng.randint(-2, 3))) for _ in range(history_len)
        ]
        customers[cid] = Customer(
            customer_id=cid,
            issuer=rng.choice(priors.ISSUERS),
            ltv=Decimal("0"),  # set once we know ticket size
            salary_day=salary_day,
            success_days=success_days,
            contacts_this_week=rng.choices([0, 1, 2], weights=[0.78, 0.17, 0.05])[0],
            consent_active=rng.random() > 0.04,
        )
    return customers


def _hidden_cause(
    rng: random.Random,
    *,
    outage_active: bool,
    amount: Decimal,
    prior_attempts: int,
    occurred_at: datetime,
) -> RootCause:
    """Sample the real cause behind a generic decline, conditioned on context.

    The conditioning is the point. If the hidden cause were drawn from the base
    rates alone it would be independent of everything a diagnoser can observe,
    the task would be unlearnable, and no diagnoser could beat the majority class.
    Real generic declines do carry signal — an outage in progress genuinely raises
    the odds that a bare "declined" is that outage — and the simulator has to
    reproduce that or the accuracy number measures nothing.
    """
    weights = dict(priors.AMBIGUOUS_HIDDEN_CAUSE)

    active: list[str] = []
    if outage_active:
        active.append("issuer_outage_active")
    if amount >= priors.AMBIGUOUS_HIGH_AMOUNT:
        active.append("amount_high")
    if prior_attempts >= priors.AMBIGUOUS_MANY_ATTEMPTS:
        active.append("many_prior_attempts")
    if occurred_at.day >= 25 or occurred_at.day <= 5:
        active.append("late_month")
    if occurred_at.hour < 6:
        active.append("odd_hour")

    for signal in active:
        for cause, mult in priors.AMBIGUOUS_CONTEXT_MULTIPLIERS[signal].items():
            weights[cause] = weights.get(cause, 0.0) * mult

    return _weighted(rng, weights)  # type: ignore[return-value]


def _instrument_history(
    rng: random.Random, cause: RootCause, amount: Decimal
) -> tuple[int, Decimal | None]:
    """Recent success history on this instrument, consistent with the true cause.

    Returns (recent_success_count, max_recent_success_amount).

    The consistency is what creates the signal. A blocked instrument clears
    nothing; a per-transaction ceiling means no larger charge ever cleared. Both
    are things a merchant can observe in their own data, which is why adding them
    is a realism fix rather than a way to flatter the number.
    """
    p_none = priors.P_NO_RECENT_SUCCESS.get(cause, 0.15)
    if rng.random() < p_none:
        return 0, None

    count = rng.choices([1, 2, 3, 4, 5], weights=[0.30, 0.26, 0.20, 0.14, 0.10])[0]

    if rng.random() < priors.P_LARGER_SUCCESS_EXISTS.get(cause, 0.5):
        # A larger charge cleared before — rules out a ceiling at this amount.
        top = amount * Decimal(str(round(rng.uniform(1.10, 3.0), 3)))
    else:
        # Only smaller charges cleared.
        top = amount * Decimal(str(round(rng.uniform(0.15, 0.95), 3)))

    return count, top.quantize(Decimal("0.01"))


def _pick_reason(
    rng: random.Random, instrument: Instrument, decline_class: DeclineClass
) -> str:
    table = (
        priors.TECHNICAL_REASON_WEIGHTS
        if decline_class is DeclineClass.TECHNICAL
        else priors.BUSINESS_REASON_WEIGHTS
    )
    weights = table.get(instrument)
    if not weights:
        weights = table[Instrument.CARD]
    return str(_weighted(rng, weights))


def generate_batch(
    n_events: int = 1000,
    seed: int = 42,
    start: date | None = None,
    days: int = 30,
    batch_id: str = "batch_001",
) -> SimWorld:
    """Generate a batch of at-risk events plus the latent world behind them.

    Deterministic in `seed`: same seed, same world, so counterfactual strategies
    are compared against an identical reality.
    """
    rng = random.Random(seed)
    start = start or date(2026, 8, 1)

    world = SimWorld(seed=seed)
    world.outages = _build_outages(rng, start, days)
    world.customers = _build_customers(rng, max(1, n_events // 3))
    customer_ids = list(world.customers)

    for i in range(n_events):
        event_id = f"evt_{i:06d}"
        customer = world.customers[rng.choice(customer_ids)]

        occurred_at = datetime.combine(
            start + timedelta(days=rng.randint(0, days - 1)),
            datetime.min.time(),
        ) + timedelta(hours=rng.randint(0, 23), minutes=rng.randint(0, 59))

        event_type = EventType(str(_weighted(rng, priors.EVENT_TYPE_MIX)))
        recurring = event_type in (
            EventType.FAILED_MANDATE,
            EventType.HALTED_SUBSCRIPTION,
        )
        instrument: Instrument = _weighted(  # type: ignore[assignment]
            rng,
            priors.RECURRING_INSTRUMENT_MIX
            if recurring
            else priors.ONE_TIME_INSTRUMENT_MIX,
        )

        amount = _amount(rng)
        ltv_multiple = (
            priors.LTV_MULTIPLE_RECURRING if recurring else priors.LTV_MULTIPLE_ONE_TIME
        )
        customer.ltv = (amount * Decimal(str(ltv_multiple))).quantize(Decimal("0.01"))

        error_code: str | None = None
        error_reason: str | None = None
        decline_class = DeclineClass.UNKNOWN
        auth_expires_at: datetime | None = None

        # Drawn before diagnosis so the hidden cause behind a generic decline can
        # be conditioned on the same attempt history a diagnoser will observe.
        prior_24h = rng.choices([0, 1, 2], weights=[0.72, 0.21, 0.07])[0]
        prior_30d_seed = prior_24h + rng.choices(
            [0, 1, 2, 3], weights=[0.6, 0.24, 0.11, 0.05]
        )[0]

        if event_type in (EventType.UNCAPTURED_AUTH, EventType.LATE_AUTHORIZATION):
            # Not a failure at all — the bank approved. This is an operational miss,
            # and it is invisible in every failure-shaped dashboard.
            root_cause = RootCause.UNCAPTURED
            # Razorpay auto-refunds uncaptured authorisations; 5 days is the outer bound.
            auth_expires_at = occurred_at + timedelta(days=5)
        elif event_type is EventType.ABANDONED_CHECKOUT:
            root_cause = RootCause.CUSTOMER_ABANDONED
            decline_class = DeclineClass.BUSINESS
        else:
            # An outage in progress forces a technical decline; otherwise sample.
            outage = world.outage_at(customer.issuer, occurred_at)
            if outage and rng.random() < outage.severity:
                decline_class = DeclineClass.TECHNICAL
            else:
                decline_class = _weighted(rng, priors.DECLINE_CLASS_SPLIT)  # type: ignore[assignment]

            error_reason = _pick_reason(rng, instrument, decline_class)
            root_cause, mapped_class, _evidence = priors.REASON_TO_ROOT_CAUSE[error_reason]
            decline_class = mapped_class
            error_code = (
                "GATEWAY_ERROR"
                if decline_class is DeclineClass.TECHNICAL
                else "BAD_REQUEST_ERROR"
            )

        # --- latent truth -------------------------------------------------
        # An ambiguous decline carries a hidden real cause. The issuer refused
        # without saying why, so the observable code is AMBIGUOUS_DECLINE and the
        # system must infer what actually happened. This is the only subset where
        # diagnosis is a prediction rather than a lookup, and therefore the only
        # subset where accuracy means anything.
        if root_cause is RootCause.AMBIGUOUS_DECLINE:
            root_cause = _hidden_cause(
                rng,
                outage_active=world.outage_at(customer.issuer, occurred_at) is not None,
                amount=amount,
                prior_attempts=prior_30d_seed,
                occurred_at=occurred_at,
            )

        success_count, max_success = _instrument_history(rng, root_cause, amount)

        funds_day: int | None = None
        if root_cause is RootCause.INSUFFICIENT_FUNDS:
            # Balance genuinely recovers on this customer's salary day. A retry
            # before it fails no matter how many times you try.
            funds_day = customer.salary_day
        latent = LatentEvent(
            event_id=event_id,
            seed=rng.randrange(2**31),
            root_cause=root_cause,
            decline_class=decline_class,
            funds_available_day=funds_day,
            responds_to_nudge=rng.random() < 0.38,
            obligation_valid=rng.random() > 0.06,
        )
        world.latent[event_id] = latent

        world.events.append(
            RiskEvent(
                event_id=event_id,
                batch_id=batch_id,
                occurred_at=occurred_at,
                event_type=event_type,
                amount=amount,
                instrument=instrument,
                instrument_token=f"tok_{abs(hash((customer.customer_id, instrument))) % 10**12:012d}",
                issuer=customer.issuer,
                customer_id=customer.customer_id,
                order_id=f"order_{i:06d}",
                payment_id=f"pay_{i:06d}" if error_reason or auth_expires_at else None,
                subscription_id=f"sub_{i:06d}" if recurring else None,
                error_code=error_code,
                error_source=_error_source(root_cause) if error_reason else None,
                error_step=_error_step(root_cause) if error_reason else None,
                error_reason=error_reason,
                prior_attempts_24h=prior_24h,
                prior_attempts_30d=prior_30d_seed,
                recent_success_count=success_count,
                max_recent_success_amount=max_success,
                contacts_this_week=customer.contacts_this_week,
                consent_active=customer.consent_active,
                obligation_valid=latent.obligation_valid,
                auth_expires_at=auth_expires_at,
                customer_ltv=customer.ltv,
                customer_success_days=list(customer.success_days),
                # Ground truth, for measuring diagnosis quality. The gate and the
                # scorer must never read these.
                truth_root_cause=root_cause,
                truth_recoverable=priors.BASE_RECOVERY_PROB.get(root_cause, 0.0) > 0.0
                or root_cause in priors.TERMINAL_FOR_RETRY_SWITCHABLE,
            )
        )

    return world
