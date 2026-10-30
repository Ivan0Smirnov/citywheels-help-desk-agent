import json

import pytest

from citywheels.bookings import get_booking


def test_returns_booking_with_all_fields():
    result = get_booking("CW-1002")

    assert result == {
        "found": True,
        "id": "CW-1002",
        "status": "confirmed",
        "bike_type": "e-bike",
        "bikes": 2,
        "start": "2026-06-11T18:00:00+02:00",
        "end": "2026-06-12T18:00:00+02:00",
        "add_ons": [],
        "rental_price_eur": 80.0,
        "booking_fee_eur": 2.0,
        "deposit_eur": 300.0,
        "paid_with": "card",
    }


def test_unknown_id_is_not_found():
    assert get_booking("CW-9999") == {
        "found": False,
        "booking_id": "CW-9999",
        "reason": "not_found",
    }


def test_id_is_normalized():
    result = get_booking(" cw-1002 ")

    assert result["found"] is True
    assert result["id"] == "CW-1002"


@pytest.mark.parametrize("booking_id", ["hello", "", "   ", "1002", None])
def test_invalid_id(booking_id):
    assert get_booking(booking_id) == {
        "found": False,
        "booking_id": booking_id,
        "reason": "invalid_id",
    }


def test_reads_bookings_from_given_path(tmp_path):
    path = tmp_path / "bookings.json"
    path.write_text(json.dumps([{"id": "CW-0001", "status": "confirmed"}]), encoding="utf-8")

    assert get_booking("CW-0001", bookings_path=path) == {
        "found": True,
        "id": "CW-0001",
        "status": "confirmed",
    }
    assert get_booking("CW-1002", bookings_path=path)["reason"] == "not_found"
