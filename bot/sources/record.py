"""Helpers that build the booking dict described in sources/__init__.py."""
import re
from datetime import date

DEGREES = ["CAPITAL", "LIFE", "FIRST", "SECOND", "THIRD"]


def parse_level(text):
    """('Felony'|'Misdemeanor'|'', degree word or '') from text like 'FELONY / THIRD DEGREE' or '(MISDEMEANOR)'."""
    t = (text or "").upper()
    level = "Felony" if "FELONY" in t else "Misdemeanor" if "MISD" in t else ""
    degree = next((d for d in DEGREES if re.search(rf"\b{d}\b", t)), "")
    if degree in ("CAPITAL", "LIFE"):
        level = "Felony"
    return level, degree


def age_on(birth, on):
    """Whole years between two dates, or None."""
    if not birth or not on:
        return None
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def booking(county, booking_number, booked, name, **fields):
    b = {"id": f"{county.lower()}-{booking_number}", "county": county, "booking_number": str(booking_number),
         "booked": booked.isoformat() if isinstance(booked, date) else booked, "name": " ".join(name.split()),
         "age": None, "sex": "", "charges": [], "bond": None, "agency": "", "in_custody": True}
    b.update(fields)
    # Tidy descriptions and merge repeats (Lee lists each count separately) into one charge with a count
    merged = {}
    for c in b["charges"]:
        c["desc"] = " ".join(c["desc"].split()).strip(" -;,")
        key = (c["desc"], c["statute"])
        if key in merged:
            merged[key]["count"] += 1
        else:
            merged[key] = {**c, "count": 1}
    b["charges"] = list(merged.values())
    return b
