from datetime import datetime, timedelta, timezone

import pytest

from citywheels.refund import NOW, calculate_refund, refund_for_booking


def make_booking(start, **overrides):
    booking = {
        "id": "CW-0001",
        "status": "confirmed",
        "start": start.isoformat(),
        "rental_price_eur": 40.0,
        "booking_fee_eur": 2.0,
        "deposit_eur": 50.0,
        "paid_with": "card",
    }
    booking.update(overrides)
    return booking


@pytest.mark.parametrize(
    "booking_id, percent, rental_refund, deposit_refund, total, method",
    [
        ("CW-1001", 100, 40.0, 50.0, 90.0, "card"),  # 73h before start
        ("CW-1002", 50, 40.0, 300.0, 340.0, "card"),  # 33h
        ("CW-1003", 0, 0.0, 50.0, 50.0, "card"),  # 6h: deposit still comes back
        ("CW-1004", 100, 23.0, 50.0, 73.0, "voucher"),  # 240h, paid with voucher
        ("CW-1007", 100, 36.0, 150.0, 186.0, "card"),  # exactly 48h
        ("CW-1009", 100, 119.0, 50.0, 169.0, "card"),  # 121h
        ("CW-1010", 50, 20.0, 150.0, 170.0, "card"),  # exactly 24h
    ],
)
def test_cancellable_data_bookings(
    booking_id, percent, rental_refund, deposit_refund, total, method
):
    result = refund_for_booking(booking_id)

    assert result["cancellable"] is True
    assert result["refund_percent"] == percent
    assert result["rental_refund_eur"] == rental_refund
    assert result["deposit_refund_eur"] == deposit_refund
    assert result["booking_fee_refunded_eur"] == 0.0
    assert result["total_refund_eur"] == total
    assert result["refund_method"] == method


@pytest.mark.parametrize(
    "booking_id, status",
    [("CW-1005", "cancelled"), ("CW-1006", "completed"), ("CW-1008", "in_progress")],
)
def test_not_cancellable_data_bookings(booking_id, status):
    assert refund_for_booking(booking_id) == {
        "booking_id": booking_id,
        "cancellable": False,
        "status": status,
        "reason": "status_not_cancellable",
        "total_refund_eur": 0.0,
    }


@pytest.mark.parametrize(
    "time_to_start, percent",
    [
        (timedelta(hours=48), 100),
        (timedelta(hours=48) - timedelta(seconds=1), 50),
        (timedelta(hours=24), 50),
        (timedelta(hours=24) - timedelta(seconds=1), 0),
        (-timedelta(hours=3), 0),
    ],
    ids=["48h", "48h-1s", "24h", "24h-1s", "start-passed"],
)
def test_boundaries(time_to_start, percent):
    result = calculate_refund(make_booking(NOW + time_to_start), NOW)

    assert result["refund_percent"] == percent
    assert result["deposit_refund_eur"] == 50.0


def test_booking_fee_is_never_refunded():
    result = calculate_refund(make_booking(NOW + timedelta(days=5), booking_fee_eur=2.0), NOW)

    assert result["booking_fee_refunded_eur"] == 0.0
    assert result["total_refund_eur"] == 40.0 + 50.0


def test_rental_refund_rounds_half_up_to_cents():
    booking = make_booking(NOW + timedelta(hours=30), rental_price_eur=12.35)

    # float arithmetic gives round(6.175, 2) == 6.17
    assert calculate_refund(booking, NOW)["rental_refund_eur"] == 6.18


def test_now_in_utc_gives_same_result():
    now_utc = datetime(2026, 6, 10, 7, 0, tzinfo=timezone.utc)

    assert refund_for_booking("CW-1007", now=now_utc) == refund_for_booking("CW-1007")


def test_refund_for_unknown_booking():
    assert refund_for_booking("CW-9999") == {
        "found": False,
        "booking_id": "CW-9999",
        "reason": "not_found",
    }


def test_refund_for_invalid_id():
    assert refund_for_booking("hello")["reason"] == "invalid_id"
