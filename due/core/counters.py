"""Attempt and contact counters.

These are the state behind the money-safety gates. If they are wrong, the system
generates fines — so the semantics matter more than the implementation.

**Single-node invariant.** This is an in-process store with strong consistency by
virtue of being one process. Every counter read in `PolicyEngine.evaluate` sees
every write that preceded it. That is sufficient for a single-worker deployment
and for the demo, and it is stated rather than assumed.

**What breaks when distributed** (documented deliberately, not built):
attempt counters become a shared, contended resource. Two workers reading
`count_in_window` concurrently can each see 14 attempts and each decide a 15th is
safe, producing 16. The fix is not eventual consistency with reconciliation —
by the time you reconcile, the fine exists. It needs either a compare-and-set
reservation (increment first, act second, release on failure) or partitioning by
instrument token so one token is only ever handled by one worker. The reservation
approach is preferable because it degrades safely: a crashed worker leaks a
reserved attempt, which costs one lost recovery rather than one fine.

Historical attempts observed at ingestion are kept separate from attempts this
system makes. Totals are the sum. Conflating them would let a busy prior history
silently consume our own budget without anyone noticing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Attempt:
    token: str
    at: datetime
    payment_id: str | None
    merchant_initiated: bool


@dataclass
class AttemptCounter:
    """Counts authorisation attempts and outbound contacts within time windows."""

    _attempts: dict[str, list[Attempt]] = field(default_factory=lambda: defaultdict(list))
    _contacts: dict[str, list[datetime]] = field(default_factory=lambda: defaultdict(list))
    _merchant_retries: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # -- writes ------------------------------------------------------------

    def record_attempt(
        self,
        token: str,
        at: datetime,
        payment_id: str | None = None,
        merchant_initiated: bool = True,
    ) -> None:
        self._attempts[token].append(
            Attempt(token=token, at=at, payment_id=payment_id, merchant_initiated=merchant_initiated)
        )
        if merchant_initiated and payment_id:
            self._merchant_retries[payment_id] += 1

    def record_contact(self, customer_id: str, at: datetime) -> None:
        self._contacts[customer_id].append(at)

    # -- reads -------------------------------------------------------------

    def attempts_in_window(self, token: str, now: datetime, window: timedelta) -> int:
        """Attempts this system has made on `token` within the trailing window."""
        cutoff = now - window
        return sum(1 for a in self._attempts.get(token, ()) if a.at > cutoff)

    def contacts_in_window(self, customer_id: str, now: datetime, window: timedelta) -> int:
        cutoff = now - window
        return sum(1 for t in self._contacts.get(customer_id, ()) if t > cutoff)

    def merchant_retries(self, payment_id: str | None) -> int:
        if payment_id is None:
            return 0
        return self._merchant_retries.get(payment_id, 0)

    # -- totals ------------------------------------------------------------

    def total_attempts_24h(self, token: str, now: datetime, observed_prior: int = 0) -> int:
        """Historical attempts seen at ingestion plus ours. This is what the gate reads."""
        return observed_prior + self.attempts_in_window(token, now, timedelta(hours=24))

    def total_attempts_30d(self, token: str, now: datetime, observed_prior: int = 0) -> int:
        return observed_prior + self.attempts_in_window(token, now, timedelta(days=30))

    def total_contacts_week(self, customer_id: str, now: datetime, observed_prior: int = 0) -> int:
        return observed_prior + self.contacts_in_window(customer_id, now, timedelta(days=7))

    def reset(self) -> None:
        self._attempts.clear()
        self._contacts.clear()
        self._merchant_retries.clear()
