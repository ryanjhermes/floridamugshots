"""posting_queue.json: what's queued, what's posted, and the photos behind it.

    {
      "created_at": "<ISO time of the last nightly rebuild>", "day": "YYYY-MM-DD (bookings date)",
      "entries": [{"id": 1, "data": {<booking, see sources/__init__.py> + photo, reel, score...},
                   "posted": false, "posted_at": null}, ...]
    }

A person removed on request keeps their posted entry with empty data, so slot timing still sees the post.
"""
import os
from datetime import datetime, timedelta

from . import config, removals
from .common import delete_file, load_json, now_eastern, now_iso, save_json


def load():
    """The queue dict. Raises FileNotFoundError if there is none yet."""
    return load_json(config.QUEUE_FILE)


def save(q):
    save_json(config.QUEUE_FILE, q)


def build(top, day):
    """Nightly rebuild: the day's picks, plus entries posted in the last 24h (so slot timing and
    'already posted' survive). Unposted leftovers from the previous night are dropped."""
    try:
        old = load()["entries"]
    except FileNotFoundError:
        old = []
    cutoff = now_eastern() - timedelta(hours=24)
    kept = [e for e in old if e.get("posted") and e.get("posted_at")
            and datetime.fromisoformat(e["posted_at"]) >= cutoff]
    new_photos = {b.get("photo") for b in top}
    for e in old:
        if not e.get("posted") and e["data"].get("photo") not in new_photos:  # a same-day re-run reuses paths
            delete_file(e["data"].get("photo"), label="stale mugshot")

    entries = kept + [{"data": b, "posted": False, "posted_at": None} for b in top]
    for n, e in enumerate(entries, 1):
        e["id"] = n
    save({"created_at": now_iso(), "day": day.isoformat(), "entries": entries})
    print(f"✅ Queue saved: {len(top)} new, {len(kept)} posted in the last 24h kept")


def next_to_post():
    """The next unposted entry that isn't on the removal list, or None."""
    try:
        q = load()
    except FileNotFoundError:
        print("📭 No posting queue found")
        return None
    removed = removals.load()
    pending = [e for e in q["entries"] if not e["posted"] and not removals.is_removed(e["data"].get("name"), removed)]
    if not pending:
        print("✅ Nothing left to post")
        return None
    print(f"📊 {len(pending)} left in queue; next: {pending[0]['data']['id']}")
    return pending[0]


def mark_posted(entry_id, media_id=None):
    """Mark an entry posted now and delete its photo (the Reel lives only on Pages)."""
    q = load()
    for e in q["entries"]:
        if e["id"] == entry_id:
            e["posted"], e["posted_at"] = True, now_iso()
            if media_id:
                e["data"]["media_id"] = media_id  # dms.py / insights look posts up by this
            delete_file(e["data"].get("photo"), label="posted mugshot")
            e["data"]["photo"] = None
    save(q)


def purge_unqueued():
    """Delete every photo not needed by an unposted entry. Skips if the queue can't be read,
    so a broken scrape never wipes upcoming posts."""
    try:
        keep = {os.path.basename(e["data"].get("photo") or "") for e in load()["entries"] if not e.get("posted")}
    except Exception as e:
        print(f"⚠️  Queue unreadable, skipping photo purge: {e}")
        return
    deleted = 0
    if os.path.isdir(config.MUGSHOTS_DIR):
        for fn in os.listdir(config.MUGSHOTS_DIR):
            if fn.lower().endswith((".jpg", ".jpeg", ".png")) and fn not in keep:
                os.remove(os.path.join(config.MUGSHOTS_DIR, fn))
                deleted += 1
    print(f"🧹 Purged {deleted} photos not in the queue (kept {len(keep) - ('' in keep)})")


def check():
    try:
        q = load()
    except FileNotFoundError:
        print("📭 No posting queue found. Run 'python -m bot scrape' to create one")
        return
    pending = [e for e in q["entries"] if not e["posted"]]
    print(f"📊 Queue for bookings on {q.get('day')} (built {q.get('created_at')}): "
          f"{len(q['entries']) - len(pending)} posted, {len(pending)} pending")
    for e in pending:
        d = e["data"]
        print(f"   #{e['id']:<3} {d['id']:<16} score {d.get('score', 0):.2f}  reel: {'yes' if d.get('reel') else 'no'}")
