"""Razorpay test-mode client.

Three safety properties, in order of importance:

1. **Test mode is enforced, not assumed.** The client refuses to construct
   unless the key ID carries the `rzp_test_` prefix. A live key in this codebase
   would be a system that can move real money, and no amount of care elsewhere
   compensates for that being possible at all.

2. **Dry run is the default.** Writes are suppressed unless `RECOUP_DRY_RUN` is
   explicitly set false. The failure mode of a recovery system is doing something
   real by accident, so the safe state is the default state.

3. **Customer notifications are hard-off.** Payment links are created with SMS
   and email disabled at the call site, every time. Test mode does not guarantee
   a test recipient — an email address in a fixture can be a real person's.

Idempotency is by deterministic `receipt` / `reference_id`, derived from the
event and action, so a replayed decision reuses the same reference.
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
            dry_run = os.getenv("RECOUP_DRY_RUN", "true").strip().lower() != "false"

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
            "receipt": reference,  # deterministic — the idempotency handle
            "notes": notes or {},
        }
        if self.dry_run:
            self._record("order.create", reference, True, "DRY RUN — not sent")
            return {"id": f"order_dryrun_{reference}", "status": "created", "dry_run": True}

        result = self._client.order.create(payload)
        self._record("order.create", reference, True, result.get("id", ""))
        return result

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
        if self.dry_run:
            self._record("payment_link.create", reference, True, "DRY RUN — not sent")
            return {
                "id": f"plink_dryrun_{reference}",
                "short_url": f"https://rzp.io/i/dryrun-{reference}",
                "status": "created",
                "dry_run": True,
            }

        result = self._client.payment_link.create(payload)
        self._record("payment_link.create", reference, True, result.get("short_url", ""))
        return result

    def capture_payment(self, payment_id: str, amount: Decimal) -> dict:
        """Capture an authorised payment before its window closes."""
        if self.dry_run:
            self._record("payment.capture", payment_id, True, "DRY RUN — not sent")
            return {"id": payment_id, "status": "captured", "dry_run": True}

        result = self._client.payment.capture(payment_id, int(amount * 100), {"currency": "INR"})
        self._record("payment.capture", payment_id, True, result.get("status", ""))
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
