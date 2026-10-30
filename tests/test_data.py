import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BOOKING_FIELDS = {
    "id",
    "status",
    "bike_type",
    "bikes",
    "start",
    "end",
    "add_ons",
    "rental_price_eur",
    "booking_fee_eur",
    "deposit_eur",
    "paid_with",
}


def test_bookings_json_is_a_list_of_bookings_with_ids():
    bookings = json.loads((DATA_DIR / "bookings.json").read_text(encoding="utf-8"))

    assert isinstance(bookings, list) and bookings
    for booking in bookings:
        assert BOOKING_FIELDS <= booking.keys(), booking.get("id")
    ids = [booking["id"] for booking in bookings]
    assert len(ids) == len(set(ids))


def test_policy_documents_exist():
    for name in ("prices.md", "cancellations.md", "faq.md"):
        path = DATA_DIR / "policies" / name
        assert path.read_text(encoding="utf-8").strip(), name
