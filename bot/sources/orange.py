"""Orange County Corrections: the nightly booking-report PDF, plus photos from the BestJail web app.

The PDF covers the 24 hours from midnight of one day and is regenerated around 1 AM, so only the
latest day is available (no backfill). It has charge degree and agency but no bond. Photos come from
getInmateDetails, which returns nothing once a person is released, so released bookings have no photo.
"""
import base64
import io
import re
from datetime import datetime

from .record import booking, parse_level

PDF_URL = "https://netapps.ocfl.net/BestJail/PDF/bookings.pdf"
APP = "https://netapps.ocfl.net/BestJail/Home"

PERSON = re.compile(r"^(?P<name>[A-Z][A-Z'\-. ]*, [A-Z'\-. ]+?) (?P<bk>\d{8}) \S+ / (?P<sex>[MF]) (?P<age>\d+) (?P<rest>.*)$")
CASE = re.compile(r"^CASE: (?:(?P<case>\d\S*) )?(?P<agency>.*)$")
CHARGE = re.compile(r"^(?P<statute>\S+) (?P<level>(?:FELONY|MISDEMEANOR) / (?:[A-Z]+ )?DEGREE) (?P<desc>.+)$")
OTHER_CHARGE = re.compile(r"^(?P<statute>\S*\d\S*) (?P<desc>[A-Z].+)$")
REPORT_DATE = re.compile(r"BEGINNING AT MIDNIGHT (\d{1,2}/\d{1,2}/\d{4})")
RELEASED = re.compile(r"\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2}[AP]M")


def fetch(day, session):
    import pdfplumber  # Only the scrape workflow installs it

    pdf = session.get(PDF_URL).content
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        lines = [l.strip() for page in doc.pages for l in (page.extract_text() or "").splitlines()]

    report = next((REPORT_DATE.search(l) for l in lines if REPORT_DATE.search(l)), None)
    report_day = datetime.strptime(report.group(1), "%m/%d/%Y").date() if report else None
    if report_day != day:
        print(f"⚠️  Orange PDF covers {report_day}, not {day}; it only ever has the latest day")
        return []

    out, current, seen_case = [], None, False
    for line in lines:
        if "Page:" in line:
            continue
        if m := PERSON.match(line):
            current = booking("Orange", m["bk"], day, m["name"], age=int(m["age"]), sex=m["sex"],
                              in_custody=not RELEASED.search(m["rest"]))
            out.append(current)
            seen_case = False
        elif current is None:
            continue
        elif m := CASE.match(line):
            current["agency"] = current["agency"] or m["agency"].strip()
            seen_case = True
        elif m := CHARGE.match(line):
            level, degree = parse_level(m["level"])
            current["charges"].append({"desc": m["desc"].strip(), "statute": m["statute"], "level": level,
                                       "degree": degree, "detail": ""})
        elif seen_case and (m := OTHER_CHARGE.match(line)):
            current["charges"].append({"desc": m["desc"].strip(), "statute": m["statute"], "level": "",
                                       "degree": "", "detail": ""})
    return out


def photo(b, session):
    if not b.get("in_custody"):
        return None
    if not session.cookies.get_dict(domain="netapps.ocfl.net"):
        session.get(f"{APP}/Inmates")  # Session cookies for the app's load balancer
    rows = session.post(f"{APP}/getInmateDetails/{b['booking_number']}", data={"id": ""},
                        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{APP}/Inmates"}).json()
    image = rows[0].get("IMAGE") if rows else None
    return base64.b64decode(image) if image else None
