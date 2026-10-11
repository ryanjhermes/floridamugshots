"""Nightly pull: every source's bookings for one day -> filter -> shortlist -> photos -> rank -> queue.

python -m bot scrape                  # Yesterday (Eastern), rebuild posting_queue.json and mugshots/
python -m bot scrape --dry-run        # Same pull and ranking, photos to a temp dir, queue untouched
python -m bot scrape --day 2026-10-08 # Another day (Orange only ever has the latest day)

One county failing never stops the others.
"""
import io
import os
import tempfile
from datetime import date

from . import config, posting_queue, ranking, removals
from .common import PoliteSession, yesterday
from .sources import SOURCES


def _save_photo(raw, path):
    """Write raw image bytes as an RGB JPEG. Returns False if the bytes aren't a usable image."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return False
    if img.width < 100 or img.height < 100:
        return False
    img.save(path, "JPEG", quality=92)
    return True


def run(day=None, dry_run=False):
    day = date.fromisoformat(day) if isinstance(day, str) else day or yesterday()
    print(f"📅 Bookings for {day}")

    sessions, bookings = {}, []
    for county, source in SOURCES.items():
        sessions[county] = PoliteSession()
        try:
            got = source.fetch(day, sessions[county])
            print(f"🌴 {county}: {len(got)} bookings")
            bookings += got
        except Exception as e:
            print(f"❌ {county} failed, continuing without it: {type(e).__name__}: {e}")

    removed = removals.load()
    try:
        posted = {e["data"].get("id") for e in posting_queue.load()["entries"] if e.get("posted")}
    except FileNotFoundError:
        posted = set()
    eligible = [b for b in bookings
                if b["age"] is not None and b["age"] >= config.MIN_AGE and b["id"] not in posted
                and not removals.is_removed(b["name"], removed)]
    print(f"✅ {len(eligible)} eligible of {len(bookings)} (adults with known age, not removed or already posted)")

    photo_dir = tempfile.mkdtemp(prefix="fl-mugshots-") if dry_run else config.MUGSHOTS_DIR
    os.makedirs(photo_dir, exist_ok=True)
    with_photo = []
    for b in ranking.shortlist(eligible):
        try:
            raw = SOURCES[b["county"]].photo(b, sessions[b["county"]])
        except Exception as e:
            print(f"⚠️  Photo failed for {b['id']}: {e}")
            raw = None
        path = os.path.join(photo_dir, f"{b['id']}.jpg")
        if raw and _save_photo(raw, path):
            b["photo"] = path
            with_photo.append(b)
    print(f"📸 {len(with_photo)} shortlisted bookings have a photo")

    top = ranking.rank(with_photo)
    for b in top:
        for k in [k for k in b if k.startswith("_")]:
            del b[k]
        b["charges"].sort(key=ranking.charge_points, reverse=True)  # Headline charge first in Reel and caption
    if dry_run:
        print(f"🧪 Dry run: queue untouched, photos in {photo_dir}")
        return top
    keep = {b["photo"] for b in top}
    for b in with_photo:
        if b["photo"] not in keep:
            os.remove(b["photo"])
    posting_queue.build(top, day)
    return top
