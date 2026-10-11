"""News posts: the most outlandish Florida crime story, at config.NEWS_HOURS (2 PM and 6 PM Eastern).

Ported from minneapolismugshots/bot/news.py with three changes:
- Statewide: config.NEWS_FEEDS covers Miami, Tampa Bay, Orlando and Jacksonville TV stations.
- Florida flavor: stories reading as gators/boats/golf carts/"Florida Man" get config.NEWS_FLAVOR_BONUS.
- Our own card, not the outlet's photo. News photos belong to the station (or AP/Getty), so we render a
  headline card in the Florida look and only include the lead image when CLIP says it's a booking photo,
  which is a public record.

Two steps, because Instagram fetches media by URL and Pages must be redeployed in between:
python -m bot news pick [--dry-run|--force]  # Score, pick, render news/<slug>.jpg + .mp4, save as pending
python -m bot news post                       # Post the pending story (after Pages is deployed)

Scoring: zero-shot NLI (MoritzLaurer/deberta-v3-base-zeroshot-v2.0, ~700 MB, MIT, CPU). Each label is scored
on its own (multi_label) and a story's score is its strongest interesting label, plus the flavor bonus.
Stories that don't read as crime/arrest news score 0. Works on transformers 4 and 5 (no pipeline API).
"""
import html
import io
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from . import config
from .common import EASTERN, load_json, now_eastern, now_iso, save_json, set_github_output

MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
CRIME_LABEL = "about a crime, an arrest or a police investigation"
# Gates: stations' feeds carry national stories, and "shocking" alone would pick mass shootings every day
ELSEWHERE_LABEL = "about something that happened outside Florida, in another state or country"
TRAGEDY_LABEL = "about a tragedy in which people were killed"
# Edit these to change what counts as worth posting: label -> weight. A story's score is its best weighted label.
# "shocking" is down-weighted: on its own it rates every hit-and-run 0.8 (tested Oct 10)
INTERESTING_LABELS = {
    "bizarre or weird": 1,
    "funny or absurd": 1,
    "outlandish behavior": 1,
    "unbelievable": 1,
    "gross or disgusting": 1,
    "embarrassing": 1,
    "shocking or extreme": 0.4,
}
FLAVOR_LABELS = [
    "about alligators, sharks, snakes or other wildlife",
    "about boats, beaches, golf carts or theme parks",
    "a classic 'Florida Man' story",
]
NS = {"media": "http://search.yahoo.com/mrss/", "content": "http://purl.org/rss/1.0/modules/content/"}


def _clean(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def _image(item):
    for tag in ("enclosure", "media:content", "media:thumbnail"):
        el = item.find(tag, NS)
        if el is not None and el.get("url") and "image" in (el.get("type") or el.get("medium") or "image"):
            return el.get("url")
    m = re.search(r'<img[^>]+src="([^"]+)"', item.findtext("content:encoded", "", NS))
    return m.group(1) if m else None


def fetch_stories(now):
    """Stories from the last 24h across all feeds: [{url, title, description, image, source, region}]"""
    stories, seen_titles = [], set()
    for source, region, url in config.NEWS_FEEDS:
        try:
            r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=config.REQUEST_TIMEOUT)
            r.raise_for_status()
            items = ET.fromstring(r.content).iter("item")
        except Exception as e:
            print(f"⚠️  {source} feed failed: {e}")
            continue
        n = 0
        for item in items:
            try:
                published = parsedate_to_datetime(item.findtext("pubDate"))
            except Exception:
                continue
            if published.tzinfo is None:  # "-0000" dates parse naive; they're UTC
                published = published.replace(tzinfo=timezone.utc)
            title = _clean(item.findtext("title"))
            if now - published > timedelta(days=1) or not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())  # Same AP story on two stations
            desc = _clean(item.findtext("description")) or _clean(item.findtext("content:encoded", "", NS))
            desc = re.split(r"\*\*|\[\.\.\.\]|\[…\]|The post .* appeared first on", desc)[0].strip()
            stories.append({"url": item.findtext("link", "").strip(), "title": title, "description": desc[:400],
                            "image": _image(item), "source": source, "region": region})
            n += 1
        print(f"📰 {source}: {n} stories in the last 24h")
    return stories


def _classifier():
    """(text, labels) -> {label: 0..1 entailment probability}, each label judged on its own.
    Calls the NLI model directly instead of transformers' zero-shot pipeline, which v5 removed."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).eval()
    entail = next(i for i, l in model.config.id2label.items() if l.lower().startswith("entail"))

    def classify(text, labels):
        enc = tok([text] * len(labels), [f"This news story is {l}." for l in labels],
                  return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            probs = model(**enc).logits.softmax(dim=-1)[:, entail]
        return dict(zip(labels, probs.tolist()))
    return classify


def score_stories(stories):
    """Set story['score'] (0 if not crime news). Any model failure scores everything 0, so nothing posts."""
    from .ranking import _best_keyword
    try:
        classify = _classifier()
    except Exception as e:
        print(f"⚠️  Could not load {MODEL_NAME}: {e}")
        for s in stories:
            s["score"], s["flavor"] = 0.0, False
        return
    labels = [ELSEWHERE_LABEL, TRAGEDY_LABEL] + list(INTERESTING_LABELS) + FLAVOR_LABELS
    for s in stories:
        text = f"{s['title']}. {s['description']}"
        s["score"], s["flavor"] = 0.0, False
        # Cheap gate first (1 label), so the full set only runs on crime stories
        if re.search(r"/(national|world|politics|us-news)/", s["url"]) or \
                classify(text, [CRIME_LABEL])[CRIME_LABEL] < config.NEWS_MIN_CRIME:
            continue
        sc = classify(text, labels)
        if sc[ELSEWHERE_LABEL] >= 0.7:
            continue
        keyword = _best_keyword({"desc": s["title"], "detail": s["description"], "statute": ""})[0] or ""
        s["flavor"] = max(sc[l] for l in FLAVOR_LABELS) >= 0.7 or keyword.startswith("fl-")
        s["score"] = (max(sc[l] * w for l, w in INTERESTING_LABELS.items()) + (config.NEWS_FLAVOR_BONUS if s["flavor"] else 0)
                      - config.NEWS_TRAGEDY_PENALTY * sc[TRAGEDY_LABEL])


def _mugshot(story, path):
    """Download the story's lead image to path if it's a booking photo. Returns path or None."""
    if not story.get("image"):
        return None
    try:
        from PIL import Image
        from .clip_model import _share, MUGSHOT_PROMPTS, NOT_MUGSHOT_PROMPTS
        raw = requests.get(story["image"], headers={"User-Agent": config.USER_AGENT}, timeout=30).content
        Image.open(io.BytesIO(raw)).convert("RGB").save(path, "JPEG", quality=92)
        if _share(path, MUGSHOT_PROMPTS, NOT_MUGSHOT_PROMPTS) >= config.NEWS_MUGSHOT_MIN:
            return path
    except Exception as e:
        print(f"⚠️  Lead image check failed: {e}")
    if os.path.exists(path):
        os.remove(path)
    return None


def caption(s):
    tags = "#FloridaMugshots #FloridaNews #Florida" + (" #FloridaMan" if s.get("flavor") else "")
    return "\n".join([
        s["title"],
        "",
        s["description"],
        "",
        f"{s['region']} · Source: {s['source']}",
        s["url"],
        "",
        f"{tags} {config.REGION_TAGS.get(s['region'], '')}".strip(),
    ])


def _slot_taken(state, now):
    """True if a story already posted (or is pending) in the current NEWS_HOURS slot."""
    started = [h for h in config.NEWS_HOURS if h <= now.hour]
    if not started:
        return True
    slot = now.replace(hour=started[-1], minute=0, second=0, microsecond=0)
    times = [p["posted_at"] for p in state["posted"]] + ([state["pending"]["picked_at"]] if state.get("pending") else [])
    return any(datetime.fromisoformat(t).astimezone(EASTERN) >= slot for t in times)


def pick(dry_run=False, force=False):
    now = now_eastern()
    state = load_json(config.NEWS_STATE_FILE, {"posted": [], "pending": None})
    if not force and not dry_run:
        if now.hour not in config.NEWS_HOURS:
            print(f"⏭️  Not a news hour ({now.hour}:00 Eastern; posts at {config.NEWS_HOURS})")
            return
        if _slot_taken(state, now):
            print("⏭️  This news slot already has a story")
            return

    done = {p["url"] for p in state["posted"]}
    stories = [s for s in fetch_stories(now) if s["url"] not in done]
    if not stories:
        print("📭 No new stories")
        return
    score_stories(stories)
    stories.sort(key=lambda s: s["score"], reverse=True)
    for s in stories[:15]:
        print(f"   {s['score']:.2f}{' 🐊' if s['flavor'] else '  '} {s['source']:<20} {s['title'][:90]}")

    best = stories[0]
    if best["score"] < config.NEWS_MIN_SCORE:
        print(f"😴 Nothing outlandish enough (best {best['score']:.2f} < {config.NEWS_MIN_SCORE})")
        return

    from . import reels
    os.makedirs(config.NEWS_DIR, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", best["title"].lower()).strip("-")[:60]
    photo = _mugshot(best, os.path.join(config.NEWS_DIR, f"{slug}-photo.jpg"))
    best["card"] = reels.render_news_card(best, photo, os.path.join(config.NEWS_DIR, f"{slug}.jpg"))
    best["reel"] = reels.render_news_reel(best["card"], os.path.join(config.NEWS_DIR, f"{slug}.mp4"))
    print(f"🗞️  Picked: {best['title']}\n🖼️  {best['card']}\n🎬 {best['reel']}\n📝 Caption:\n{caption(best)}")
    if dry_run:
        print("🧪 Dry run: state untouched")
        return
    best["picked_at"] = now_iso()
    state["pending"] = best
    save_json(config.NEWS_STATE_FILE, state)
    set_github_output(ready="1")


def post():
    """Post the pending story: Reel, falling back to the card image. False if both fail."""
    from . import instagram
    state = load_json(config.NEWS_STATE_FILE, {"posted": [], "pending": None})
    s = state.get("pending")
    if not s:
        print("📭 No pending story")
        return True
    base = f"{config.PAGES_URL}/{config.NEWS_DIR}"
    media_id = None
    for kind, kwargs in (("Reel", {"video_url": f"{base}/{os.path.basename(s['reel'])}"}),
                         ("card", {"image_url": f"{base}/{os.path.basename(s['card'])}"})):
        try:
            media_id = instagram.post(caption(s), **kwargs)
            break
        except Exception as e:
            print(f"⚠️  {kind} post failed: {e}")
    if not media_id:
        return False
    state["posted"] = (state["posted"] + [{"url": s["url"], "title": s["title"], "score": round(s["score"], 3),
                                           "posted_at": now_iso(), "media_id": media_id}])[-300:]
    state["pending"] = None
    save_json(config.NEWS_STATE_FILE, state)
    return True
