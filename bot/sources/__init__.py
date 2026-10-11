"""County booking sources. Each module exposes:

    fetch(day, session) -> [booking, ...]   every booking on that date (Eastern), charges included
    photo(booking, session) -> bytes | None  the booking photo, called only for shortlisted bookings

A booking is a plain dict (it ends up in posting_queue.json):

    id            "lee-1033699" (county + booking number; also the photo/Reel filename, never the name)
    county        key of config.COUNTIES
    booking_number, booked ("YYYY-MM-DD"), name ("LAST, FIRST MIDDLE"), age (int | None), sex ("M"/"F"/"")
    charges       [{"desc", "statute", "level": "Felony"/"Misdemeanor"/"", "degree": "THIRD"/""/..., "detail"}]
    bond          total dollars (float) or None when the source doesn't publish it
    agency        arresting agency
    in_custody    bool

Keys starting with "_" are source-private (e.g. an inline photo) and are dropped before saving.
Survey notes, endpoints and what each county blocks: docs/data-sources.md.
"""
from . import lee, orange, polk

SOURCES = {"Lee": lee, "Polk": polk, "Orange": orange}
