import json
import re
from pathlib import Path

DEFAULT_BOOKINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "bookings.json"

_BOOKING_ID = re.compile(r"CW-\d+")


def get_booking(booking_id: str, bookings_path: Path = DEFAULT_BOOKINGS_PATH) -> dict:
    """Return the booking as {"found": True, **booking}, or {"found": False, "booking_id", "reason"}.

    Never raises on customer input: the id comes from the model as a JSON value, so it may not
    even be a string. A missing or corrupt bookings file does raise, because reporting every
    booking as "not found" would hide a broken deployment.
    """
    if not isinstance(booking_id, str):
        return {"found": False, "booking_id": booking_id, "reason": "invalid_id"}
    normalized = booking_id.strip().upper()
    if not _BOOKING_ID.fullmatch(normalized):
        return {"found": False, "booking_id": booking_id, "reason": "invalid_id"}

    bookings = json.loads(Path(bookings_path).read_text(encoding="utf-8"))
    for booking in bookings:
        if booking["id"] == normalized:
            return {"found": True, **booking}
    return {"found": False, "booking_id": normalized, "reason": "not_found"}
