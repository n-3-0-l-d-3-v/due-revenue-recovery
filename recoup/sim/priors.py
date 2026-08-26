"""Generative priors for the simulator.

This file IS the credibility argument. Anyone evaluating this project can read it
and see exactly what world we assumed. Every constant is tagged:

    [CITED]    derived from published data — source on the line above
    [DERIVED]  computed from a CITED value plus a stated rule
    [ASSUMED]  our judgement. No source exists. Sensitivity analysis sweeps these.

If a number is ASSUMED, the sensitivity harness must vary it. Claims that survive
only at one setting of an ASSUMED parameter are not claims we make.
"""

from __future__ import annotations

from decimal import Decimal

from recoup.core.models import (
    ActionType,
    DeclineClass,
    Instrument,
    RootCause,
)

# ---------------------------------------------------------------------------
# Instrument mix
# ---------------------------------------------------------------------------

# [CITED] UPI dominates Indian digital retail payments by volume; cards and
# netbanking form the remainder. NPCI product statistics.
# https://www.npci.org.in/what-we-do/upi/product-statistics
ONE_TIME_INSTRUMENT_MIX: dict[Instrument, float] = {
    Instrument.UPI: 0.62,
    Instrument.CARD: 0.26,
    Instrument.NETBANKING: 0.12,
}

# [ASSUMED] Recurring mandates split between UPI Autopay and card/bank e-mandate.
# UPI Autopay has grown fast but e-mandate remains significant for higher ticket sizes.
RECURRING_INSTRUMENT_MIX: dict[Instrument, float] = {
    Instrument.UPI_AUTOPAY: 0.58,
    Instrument.EMANDATE: 0.42,
}


