"""People who asked to be taken down. Every stage (scrape, queue, posting, Pages) skips them.

Fla. Stat. § 901.43: removal must be free, within 10 days of a written request, and a removed photo
must never be republished ($5,000/day). So removal is permanent and keyed by name across all counties.
Stored in removed.json as name hashes, so the public repo doesn't list who asked.
"""
import hashlib
from datetime import datetime, timezone

from . import config
from .common import delete_file, load_json, save_json


def _key(name):
    return hashlib.sha256(" ".join((name or "").upper().replace(",", " ").split()).encode()).hexdigest()


def load():
    return load_json(config.REMOVED_FILE, {})


def is_removed(name, removed=None):
    return bool(name) and _key(name) in (load() if removed is None else removed)


def add(name):
    removed = load()
    removed[_key(name)] = datetime.now(timezone.utc).date().isoformat()
    save_json(config.REMOVED_FILE, removed)


def purge():
    """Strip removed people from the queue and mugshots/. Returns how many entries were dropped."""
    removed = load()
    q = load_json(config.QUEUE_FILE, None)
    if not removed or not q:
        return 0
    dropped, entries = 0, []
    for e in q["entries"]:
        if not is_removed(e["data"].get("name"), removed):
            entries.append(e)
            continue
        dropped += 1
        delete_file(e["data"].get("photo"), label="mugshot")
        delete_file(e["data"].get("reel"), label="Reel")
        if e.get("posted"):
            entries.append({**e, "data": {}})  # Keep the post time so slot timing still sees it
    q["entries"] = entries
    save_json(config.QUEUE_FILE, q)
    return dropped
