"""Lee County Sheriff's Office: open JSON API behind sheriffleefl.org/arrest-search/.

One list call per 100 bookings (photos inline as base64), then one charges call per booking.
The API has no felony/misdemeanor field; court location stands in (Circuit Court = felony).
"""
import base64
from datetime import datetime, timedelta

from .record import age_on, booking

API = "https://www.sheriffleefl.org/public-api/bookings"
PAGE = 100


def _d(day):
    return f"{day.year}-{day.month}-{day.day}"  # the API takes unpadded dates; toBooking is exclusive


def _date(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None


def fetch(day, session):
    rows, offset = [], 0
    while True:
        page = session.get(f"{API}/q", params={"limit": PAGE, "offset": offset, "startBooking": _d(day),
                                               "toBooking": _d(day + timedelta(days=1))}).json()
        rows += page
        if len(page) < PAGE:
            break
        offset += PAGE

    out = []
    for r in rows:
        if _date(r.get("bookingDate")) != day:
            continue
        name = f"{r.get('surName', '')}, {r.get('givenName', '')} {r.get('middleName', '')} {r.get('suffixName', '')}"
        charges = session.get(f"{API}/{r['bookingNumber']}/charges").json()
        bonds = [float(c["bondAmount"]) for c in charges if (c.get("bondAmount") or "").replace(".", "").isdigit()]
        out.append(booking(
            "Lee", r["bookingNumber"], day, name,
            age=age_on(_date(r.get("birthDate")), day),
            sex=r.get("sex", ""),
            in_custody=bool(r.get("inCustody")),
            agency=next((c.get("arrestingAgencyName", "") for c in charges if c.get("arrestingAgencyName")), ""),
            bond=sum(bonds) if bonds else None,
            charges=[{"desc": c.get("offenseDescription", "").strip(), "statute": c.get("offenseCode", ""),
                      "level": {"Circuit Court": "Felony", "County Court": "Misdemeanor"}.get(c.get("courtLocation"), ""),
                      "degree": "", "detail": ""} for c in charges if c.get("offenseDescription")],
            _photo=r.get("image") or None,
        ))
    return out


def photo(b, session):
    return base64.b64decode(b["_photo"]) if b.get("_photo") else None
