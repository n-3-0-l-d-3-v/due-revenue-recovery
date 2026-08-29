"""Razorpay test-mode client.

Three safety properties, in order of importance:

1. **Test mode is enforced, not assumed.** The client refuses to construct
   unless the key ID carries the `rzp_test_` prefix. A live key in this codebase
   would be a system that can move real money, and no amount of care elsewhere
   compensates for that being possible at all.

2. **Dry run is the default.** Writes are suppressed unless `DUE_DRY_RUN` is
   explicitly set false. The failure mode of a recovery system is doing something
   real by accident, so the safe state is the default state.

3. **Customer notifications are hard-off.** Payment links are created with SMS
   and email disabled at the call site, every time. Test mode does not guarantee
   a test recipient — an email address in a fixture can be a real person's.

**Idempotency is enforced client-side, because the API does not enforce it.**

Verified against the live sandbox: creating two orders with an identical
`receipt` succeeds twice and produces two distinct order ids. Razorpay does not
treat `receipt` as a dedup key — it is a merchant-side label. Anyone assuming
otherwise (as this module's first version did) has written a double-charge:
a network timeout on the first call, a retry, and the customer is billed twice.

So this client keeps its own reference -> response map and returns the cached
result rather than re-calling. `receipt` is still set, because it is what makes
a duplicate *identifiable* in the dashboard afterwards — but it is a forensic
aid, not a guarantee.

Known limitation, stated rather than hidden: the map is in-process. A restart
loses it, and a second worker never had it. Production needs it in the same
durable store as the ledger, keyed by (event_id, action), written *before* the
outbound call and cleared only on a confirmed terminal response.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import razorpay
from dotenv import load_dotenv

load_dotenv()

TEST_PREFIX = "rzp_test_"


class NotTestModeError(RuntimeError):
    pass


@dataclass
class ApiCall:
    """One outbound call, recorded for the audit trail and the demo."""

    at: datetime
    method: str
    dry_run: bool
    reference: str
    ok: bool
    detail: str = ""


@dataclass
class RazorpayClient:
    dry_run: bool = True
    calls: list[ApiCall] = field(default_factory=list)
    _client: Any = None
    key_id: str = ""
    # reference -> prior response. The API will happily create duplicates, so
    # this is the only thing standing between a retried call and a double charge.
    _seen: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_env(cls, dry_run: bool | None = None) -> RazorpayClient:
        key_id = os.getenv("RAZORPAY_KEY_ID", "")
        key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        if not key_id or not key_secret:
            raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — see .env.example")
        if not key_id.startswith(TEST_PREFIX):
            raise NotTestModeError(
                f"key id does not start with '{TEST_PREFIX}'. This project only "
                "operates against Razorpay test mode; refusing to construct a client."
            )
        if dry_run is None:
            dry_run = os.getenv("DUE_DRY_RUN", "true").strip().lower() != "false"

        return cls(
            dry_run=dry_run,
            _client=razorpay.Client(auth=(key_id, key_secret)),
            key_id=key_id,
        )

    # -- reads (always executed; they move nothing) -----------------------

    def ping(self) -> dict:
        result = self._client.order.all({"count": 1})
        self._record("order.all", "-", True, f"{result.get('count', 0)} orders visible")
        return result

    def fetch_payment(self, payment_id: str) -> dict:
        result = self._client.payment.fetch(payment_id)
        self._record("payment.fetch", payment_id, True, result.get("status", "?"))
        return result

    # -- writes (suppressed in dry run) -----------------------------------

    def create_order(self, amount: Decimal, reference: str, notes: dict | None = None) -> dict:
        """Amount is in rupees here; Razorpay's API takes paise."""
        payload = {
            "amount": int(amount * 100),
            "currency": "INR",
            # Forensic label, NOT a dedup key — verified: Razorpay accepts
            # duplicate receipts and mints a new order each time. Idempotency is
            # enforced by _replay() below.
            "receipt": reference,
            "notes": notes or {},
        }
        cached = self._replay("order.create", reference)
        if cached is not None:
            return cached

        if self.dry_run:
            self._record("order.create", reference, True, "DRY RUN — not sent")
            return self._remember(
                reference, {"id": f"order_dryrun_{reference}", "status": "created", "dry_run": True}
            )

        result = self._client.order.create(payload)
        self._record("order.create", reference, True, result.get("id", ""))
        return self._remember(reference, result)

    def create_payment_link(
        self, amount: Decimal, reference: str, description: str
    ) -> dict:
        """Create a recovery payment link.

        `notify` is hard-coded off. A recovery system whose demo can email a real
        person because a fixture contained a real address is not a safe demo.
        Delivery is the merchant's job and is out of scope here.
        """
        payload = {
            "amount": int(amount * 100),
            "currency": "INR",
            "description": description[:255],
            "reference_id": reference,
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
        }
        cached = self._replay("payment_link.create", reference)
        if cached is not None:
            return cached

        if self.dry_run:
            self._record("payment_link.create", reference, True, "DRY RUN — not sent")
            return self._remember(
                reference,
                {
                    "id": f"plink_dryrun_{reference}",
                    "short_url": f"https://rzp.io/i/dryrun-{reference}",
                    "status": "created",
                    "dry_run": True,
                },
            )

        result = self._client.payment_link.create(payload)
        self._record("payment_link.create", reference, True, result.get("short_url", ""))
        return self._remember(reference, result)

    def capture_payment(self, payment_id: str, amount: Decimal) -> dict:
        """Capture an authorised payment before its window closes."""
        if self.dry_run:
            self._record("payment.capture", payment_id, True, "DRY RUN — not sent")
            return {"id": payment_id, "status": "captured", "dry_run": True}

        result = self._client.payment.capture(payment_id, int(amount * 100), {"currency": "INR"})
        self._record("payment.capture", payment_id, True, result.get("status", ""))
        return result

    # -- idempotency -------------------------------------------------------

    def _replay(self, method: str, reference: str) -> dict | None:
        """Return the prior response for this reference, if we already made it."""
        prior = self._seen.get(reference)
        if prior is None:
            return None
        self._record(method, reference, True, f"IDEMPOTENT REPLAY -> {prior.get('id', '?')}")
        return dict(prior, idempotent_replay=True)

    def _remember(self, reference: str, result: dict) -> dict:
        self._seen[reference] = result
        return result

    # -- bookkeeping -------------------------------------------------------

    def _record(self, method: str, reference: str, ok: bool, detail: str) -> None:
        self.calls.append(
            ApiCall(
                at=datetime.now(),
                method=method,
                dry_run=self.dry_run,
                reference=reference,
                ok=ok,
                detail=detail,
            )
        )

    @property
    def mode(self) -> str:
        return "DRY RUN" if self.dry_run else "LIVE (test-mode sandbox)"


def idempotency_reference(event_id: str, action: str) -> str:
    """Deterministic reference for an (event, action) pair.

    Replaying a decision reuses this reference instead of creating a second
    order. Razorpay's `receipt` is the dedup handle, so identical replays are
    identifiable rather than silently duplicated.
    """
    return f"rcp_{event_id}_{action}"[:39]  # Razorpay receipt cap is 40 chars
