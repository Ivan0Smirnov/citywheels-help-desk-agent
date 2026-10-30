from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from citywheels.bookings import get_booking

# README: answers must be reproducible, so "now" is fixed at 2026-06-10 09:00 Europe/Warsaw.
NOW = datetime(2026, 6, 10, 9, 0, tzinfo=timezone(timedelta(hours=2)))

_CENT = Decimal("0.01")


def _eur(value) -> Decimal:
    return Decimal(str(value))


def calculate_refund(booking: dict, now: datetime) -> dict:
    """Refund for cancelling `booking` at `now`, per data/policies/cancellations.md.

    `now` must be timezone-aware. A confirmed booking whose start has already passed falls under
    "less than 24 hours": the documents do not cover it, and this is the literal reading.
    """
    if booking["status"] != "confirmed":
        return {
            "booking_id": booking["id"],
            "cancellable": False,
            "status": booking["status"],
            "reason": "status_not_cancellable",
            "total_refund_eur": 0.0,
        }

    time_to_start = datetime.fromisoformat(booking["start"]) - now
    # Compare timedeltas, not float hours: bookings sit exactly on the 48h and 24h boundaries.
    if time_to_start >= timedelta(hours=48):
        percent = 100
    elif time_to_start >= timedelta(hours=24):
        percent = 50
    else:
        percent = 0

    rental_refund = (_eur(booking["rental_price_eur"]) * percent / 100).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
    deposit_refund = _eur(booking["deposit_eur"]).quantize(_CENT)
    return {
        "booking_id": booking["id"],
        "cancellable": True,
        "hours_before_start": round(time_to_start / timedelta(hours=1), 1),
        "refund_percent": percent,
        "rental_price_eur": booking["rental_price_eur"],
        "rental_refund_eur": float(rental_refund),
        "booking_fee_refunded_eur": 0.0,
        "deposit_refund_eur": float(deposit_refund),
        "total_refund_eur": float(rental_refund + deposit_refund),
        "refund_method": booking["paid_with"],
    }


def refund_for_booking(booking_id: str, now: datetime = NOW) -> dict:
    """Model-facing tool: the model passes only an id, so it cannot supply prices or dates."""
    booking = get_booking(booking_id)
    if not booking["found"]:
        return booking
    return calculate_refund(booking, now)
