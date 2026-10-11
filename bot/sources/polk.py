"""Polk County Sheriff's Office: Kendo/JSON endpoints behind polksheriff.org/detention/jail-inquiry.

List by booking date in one POST. Charges need the anti-forgery token from any inmate profile page;
one token works for the whole session. Photos redirect to an S3 bucket and need no token.
"""
import re
from datetime import datetime

from .record import age_on, booking, parse_level

BASE = "https://www.polksheriff.org"


def fetch(day, session):
    rows = session.post(f"{BASE}/detention/jail-inquiry/SearchJail/",
                        data={"SelectedSearchType": "BookingDate", "BookingDate": day.isoformat()},
                        headers={"X-Requested-With": "XMLHttpRequest"}).json()
    rows = [r for r in rows if not r.get("IsAka")]
    if not rows:
        return []

    profile = session.get(f"{BASE}/inmate-profile/{rows[0]['BookingNum']}").text
    token = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', profile).group(1)

    out = []
    for r in rows:
        charges = session.post(f"{BASE}/inmate/GetCharges",
                               data={"bookingNum": r["BookingNum"], "__RequestVerificationToken": token},
                               headers={"X-Requested-With": "XMLHttpRequest"}).json()
        parsed = []
        for c in sorted(charges, key=lambda c: c.get("ChgNum") or 0):
            level, degree = parse_level(c.get("ArrestDocketCharge"))
            desc = (c.get("ChargeDesc") or "").strip()
            # ChargeDesc is cut at ~32 characters; the docket text usually has the whole thing
            full = re.sub(r"\(\d+ cnts\)|\((FELONY|MISDEMEANOR)[^)]*\)", "", c.get("ArrestDocketCharge") or "")
            if " ".join(full.split()).startswith(" ".join(desc.split())):
                desc = full
            parsed.append({"desc": desc, "statute": c.get("Statute") or "",
                           "level": level, "degree": degree, "detail": c.get("ArrestDocketCharge") or ""})
        bonds = [float(c["BondAmountDue"]) for c in charges if _num(c.get("BondAmountDue"))]
        dob = datetime.strptime(r["DOB"], "%m/%d/%Y").date() if r.get("DOB") else None
        out.append(booking(
            "Polk", r["BookingNum"], day, r.get("FullName", ""),
            age=age_on(dob, day),
            sex=(r.get("RS") or "  ")[1:2].strip(),
            in_custody=not r.get("ReleaseDate"),
            agency=next((c["ArrestAgencyDesc"] for c in charges if c.get("ArrestAgencyDesc")), ""),
            bond=sum(bonds) if bonds else None,
            charges=[c for c in parsed if c["desc"]],
            _photo=[r["BookYr"], r["BookNo"]],
        ))
    return out


def _num(v):
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def photo(b, session):
    yr, no = b["_photo"]
    r = session.get(f"{BASE}/inmate/GetPhoto", params={"bookYr": yr, "bookNo": no})
    return r.content if r.headers.get("Content-Type", "").startswith(("image", "binary")) else None
