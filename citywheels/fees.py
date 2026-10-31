import math
from decimal import Decimal

# Hourly prices and the late-return rule from data/policies/prices.md ("Bike rental",
# "Late return"); tests/test_fees.py checks they still match that document.
HOURLY_PRICE_EUR = {"city": Decimal("4"), "e-bike": Decimal("9"), "kids": Decimal("2")}
LATE_MULTIPLIER = Decimal("1.5")


def calculate_late_fee(bike_type: str, hours_late: float) -> dict:
    """Late return fee for one bike: 1.5 x the hourly price for every started hour of delay."""
    if bike_type not in HOURLY_PRICE_EUR:
        return {"error": f"unknown bike type {bike_type!r}; use city, e-bike or kids"}
    started_hours = max(0, math.ceil(hours_late))
    per_hour = LATE_MULTIPLIER * HOURLY_PRICE_EUR[bike_type]
    return {
        "bike_type": bike_type,
        "hours_late": hours_late,
        "started_hours": started_hours,
        "fee_per_started_hour_eur": float(per_hour),
        "late_fee_eur": float(per_hour * started_hours),
        "per_bike": True,
        "taken_from": "deposit",
    }
