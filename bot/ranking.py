"""Which of the day's bookings are worth posting.

Two stages, so we only download photos we might use:
1. charge_score (text only, every booking): most serious charge's level/degree + config.CHARGE_KEYWORDS bonus,
   a little for extra charges and big bonds, minus config.BORING_PENALTY when every charge is boring
   (probation violations, failure to appear, suspended license...). The top config.SHORTLIST_SIZE get photos.
2. rank (shortlist with photos): config.TEXT_WEIGHT x charge score + config.PHOTO_WEIGHT x CLIP
   distinctiveness, each rescaled 0..1 within the day, at most config.MAX_PER_COUNTY per county.
If CLIP can't run, the photo term is 0 and ranking is by charges alone.
"""
import math
import re

from . import config

_KEYWORDS = [(re.compile(p), pts) for p, pts in config.CHARGE_KEYWORDS]
_BORING = re.compile(config.BORING_CHARGES)


def charge_points(c):
    text = f"{c['desc']} {c.get('detail', '')}".upper()
    if _BORING.search(text):
        return 0.25  # "FTA ... FELONY BATTERY" is a missed court date, not a battery arrest
    degree = config.DEGREE_POINTS.get((c["level"], c["degree"])) or config.DEGREE_POINTS.get((c["level"], ""), 0)
    return degree + max((pts for rx, pts in _KEYWORDS if rx.search(text)), default=0)


def charge_score(b):
    charges = b["charges"]
    if not charges:
        return -math.inf
    score = max(charge_points(c) for c in charges)
    score += 0.3 * min(len(charges) - 1, 4)
    if b.get("bond"):
        score += 0.5 * min(max(math.log10(b["bond"]) - 3, 0), 3)   # $10k = +0.5 ... $1M+ = +1.5
    if all(_BORING.search(f"{c['desc']} {c.get('detail', '')}".upper()) for c in charges):
        score -= config.BORING_PENALTY
    return score


def shortlist(bookings, n=config.SHORTLIST_SIZE):
    for b in bookings:
        b["charge_score"] = round(charge_score(b), 2)
    return sorted((b for b in bookings if b["charges"]), key=lambda b: -b["charge_score"])[:n]


def _rescale(values):
    lo, hi = min(values.values(), default=0), max(values.values(), default=0)
    return {k: (v - lo) / (hi - lo) if hi > lo else 0 for k, v in values.items()}


def rank(bookings, n=config.QUEUE_SIZE):
    """Top n bookings (each must have 'photo'), best first. Adds photo_score and score to each."""
    raw = {}
    try:
        # torch/transformers are optional: ranking falls back to charges alone if they're missing
        from .clip_model import score_mugshots
        raw = score_mugshots([b["photo"] for b in bookings])
    except Exception as e:
        print(f"⚠️  Photo ranking unavailable, using charges only: {e}")

    text = _rescale({b["id"]: b["charge_score"] for b in bookings})
    photo = _rescale({b["id"]: raw.get(b["photo"], 0) for b in bookings})
    for b in bookings:
        b["photo_score"] = round(photo[b["id"]], 2)
        b["score"] = round(config.TEXT_WEIGHT * text[b["id"]] + config.PHOTO_WEIGHT * photo[b["id"]], 3)

    picked, per_county = [], {}
    for b in sorted(bookings, key=lambda b: -b["score"]):
        if per_county.get(b["county"], 0) < config.MAX_PER_COUNTY:
            picked.append(b)
            per_county[b["county"]] = per_county.get(b["county"], 0) + 1
        if len(picked) == n:
            break

    for i, b in enumerate(picked, 1):
        top = max(b["charges"], key=charge_points)
        print(f"🏆 #{i} {b['id']:<16} score {b['score']:.2f} (charges {b['charge_score']}, photo {b['photo_score']:.2f})"
              f" | {top['level'] or '?'} {top['degree']} {top['desc'][:50]}")
    return picked
