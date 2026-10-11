"""Hourly posting: decide whether this run posts (preflight), then post the next queued booking.

Posts go out as a Reel when one was rendered (reels.py), falling back to the still photo.
The caption's "LAST, FIRST" line (third line) is the name as booked; DM removal handling will match on it, so keep it.
"""
import os
from datetime import date, datetime

from . import config, instagram, posting_queue
from .common import EASTERN, load_json, now_eastern

LEVEL_SHORT = {"Felony": "F", "Misdemeanor": "M"}


def _charge(c):
    tag = LEVEL_SHORT.get(c.get("level", ""), "")
    if tag:
        tag += {"FIRST": "1", "SECOND": "2", "THIRD": "3"}.get(c.get("degree", ""), "")
        tag = {"CAPITAL": "Capital felony", "LIFE": "Life felony"}.get(c.get("degree", ""), tag)
    count = f" x{c['count']}" if c.get("count", 1) > 1 else ""
    return f"- {c['desc'].capitalize()}{count}" + (f" ({tag})" if tag else "")


def caption(d):
    county = config.COUNTIES[d["county"]]
    booked = date.fromisoformat(d["booked"])
    man = {"M": " #FloridaMan", "F": " #FloridaWoman"}.get(d.get("sex", ""), "")
    lines = [
        f"{d['county'].upper()} COUNTY ARREST",
        "",
        d["name"] + (f" ({d['age']})" if d.get("age") else ""),
        "Charges:",
        *[_charge(c) for c in d["charges"][:6]],
    ]
    if len(d["charges"]) > 6:
        lines.append(f"- …and {len(d['charges']) - 6} more")
    if d.get("bond"):
        lines.append(f"Bond: ${d['bond']:,.0f}")
    if d.get("agency"):
        lines.append(f"Arrested by: {d['agency'].title()}")
    lines += [
        f"Booked: {booked.strftime('%b')} {booked.day}, {booked.year}",
        "",
        f"Source: {county['source']} public booking records (Fla. Stat. ch. 119).",
        "",
        f"#FloridaMugshots #Florida{man} #Arrested #PublicRecord {county['tags']}",
    ]
    return "\n".join(lines)


def preflight():
    """What this posting run should do: ('post' | '', reason).

    Scheduled runs post if nothing has gone out since the most recent config.POSTING_HOURS slot
    started, so a run GitHub starts late still posts, and missed slots don't pile up into a burst.
    Manual runs post whatever is pending."""
    try:
        q = load_json(config.QUEUE_FILE)
    except Exception as e:
        return "", f"no_queue ({type(e).__name__})"

    now = now_eastern()
    posted = [datetime.fromisoformat(e["posted_at"]).astimezone(EASTERN)
              for e in q["entries"] if e.get("posted") and e.get("posted_at")]
    pending = sum(1 for e in q["entries"] if not e.get("posted"))

    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return ("post", "manual") if pending else ("", "manual_nothing_pending")
    started = [h for h in config.POSTING_HOURS if h <= now.hour]
    if not started:
        return "", f"before_first_slot_{now.hour}"
    slot_start = now.replace(hour=started[-1], minute=0, second=0, microsecond=0)
    if any(t >= slot_start for t in posted):
        return "", f"slot_{started[-1]}_already_posted"
    return ("post", f"slot_{started[-1]}") if pending else ("", "queue_empty")


def post_next(dry_run=False):
    """Post the next queued entry and mark it posted. False if posting failed (the workflow then fails)."""
    entry = posting_queue.next_to_post()
    if not entry:
        return True
    d = entry["data"]
    text = caption(d)
    image_url = f"{config.PAGES_URL}/{config.MUGSHOTS_DIR}/{os.path.basename(d.get('photo') or '')}"
    video_url = f"{config.PAGES_URL}/{config.REELS_DIR}/{os.path.basename(d['reel'])}" if d.get("reel") else None
    print(f"📱 Posting {d['id']}\n🎬 {video_url or '(no Reel)'}\n🖼️  {image_url}\n📝 Caption:\n{text}\n")
    if dry_run:
        print("🧪 Dry run: nothing posted, queue untouched")
        return True

    media_id = None
    for kind, kwargs in (("Reel", {"video_url": video_url}), ("photo", {"image_url": image_url})):
        if kind == "Reel" and not video_url:
            continue
        try:
            media_id = instagram.post(text, **kwargs)
            break
        except Exception as e:
            print(f"⚠️  {kind} post failed: {e}")
    if not media_id:
        print(f"❌ Failed to post {d['id']}")
        return False
    posting_queue.mark_posted(entry["id"], media_id)
    return True
