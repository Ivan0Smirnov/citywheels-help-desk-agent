from pathlib import Path

import pytest

from citywheels.fees import HOURLY_PRICE_EUR, calculate_late_fee

PRICES = Path(__file__).resolve().parent.parent / "data" / "policies" / "prices.md"


@pytest.mark.parametrize(
    "bike_type, hours_late, started, fee",
    [
        ("city", 2, 2, 12.0),  # 1.5 x 4 EUR x 2
        ("city", 1.25, 2, 12.0),  # every started hour counts
        ("e-bike", 0.5, 1, 13.5),  # 1.5 x 9 EUR
        ("kids", 3, 3, 9.0),  # 1.5 x 2 EUR x 3
        ("city", 0, 0, 0.0),  # on time
        ("city", -1, 0, 0.0),  # early is not negative
    ],
)
def test_late_fee(bike_type, hours_late, started, fee):
    result = calculate_late_fee(bike_type, hours_late)

    assert result["started_hours"] == started
    assert result["late_fee_eur"] == fee
    assert result["taken_from"] == "deposit"


def test_unknown_bike_type():
    assert "error" in calculate_late_fee("tandem", 1)


def test_hourly_prices_match_the_price_list():
    text = PRICES.read_text(encoding="utf-8")

    assert "charged 1.5 times the hourly price for every started hour of delay" in text
    for bike_type, price in HOURLY_PRICE_EUR.items():
        assert f"(`{bike_type}`) | {price} EUR |" in text
