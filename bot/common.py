"""Helpers shared across modules: Eastern-time clock, JSON state files, file deletes, polite HTTP, GitHub outputs."""
import json
import os
import time
from datetime import datetime, timedelta

import pytz
import requests

from . import config

EASTERN = pytz.timezone(config.TIMEZONE)
_MISSING = object()


def now_eastern():
    return datetime.now(EASTERN)


def yesterday():
    """Yesterday's date in Florida, whatever the server's timezone. The nightly scrape covers this day."""
    return (now_eastern() - timedelta(days=1)).date()


def now_iso():
    return now_eastern().isoformat()


def load_json(path, default=_MISSING):
    """Read a JSON file. A missing file returns default, or raises FileNotFoundError if none is given."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_file(path, label="file"):
    """Delete path if it exists. Returns True if a file was deleted."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            print(f"🗑️  Deleted {label}: {path}")
            return True
    except Exception as e:
        print(f"❌ Failed to delete {label} {path}: {e}")
    return False


def set_github_output(**values):
    """Expose values to later workflow steps as steps.<id>.outputs.<name>. No-op outside Actions."""
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as gh:
            for k, v in values.items():
                gh.write(f"{k}={v}\n")


class PoliteSession(requests.Session):
    """requests.Session that waits config.REQUEST_DELAY between calls and raises on HTTP errors."""

    def __init__(self):
        super().__init__()
        self.headers['User-Agent'] = config.USER_AGENT
        self._last = 0.0

    def request(self, method, url, **kwargs):
        wait = self._last + config.REQUEST_DELAY - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        kwargs.setdefault('timeout', config.REQUEST_TIMEOUT)
        try:
            r = super().request(method, url, **kwargs)
        finally:
            self._last = time.monotonic()
        r.raise_for_status()
        return r
