"""Render 9:16 Reels for queued bookings: Pillow draws the card, ffmpeg animates the photo.

The Florida look, deliberately unlike Minneapolis (centered, black, yellow/red DejaVu):
Gulf-teal gradient, sunset-coral accents, sand text, Anton + Barlow, left-aligned layout, rounded photo
with a slow zoom-OUT and a degree chip per charge. No text on the photo.
County, date and bond live in the caption, not on the Reel.

Layers, bottom to top: background card (gradient + all text) -> zooming photo -> overlay (rounded corners,
border). Text stays clear of Instagram's Reel UI: nothing below y=1640 or right of x=940 under y=1000.
Reels are written to reels/ and served only from GitHub Pages (never committed).
"""
import os
import subprocess
import tempfile
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import config, posting_queue

W, H, FPS = 1080, 1920, 30
MARGIN = 90
PX, PY, PW, PH = 90, 250, 720, 900       # Photo window (mugshots are 4:5)
RADIUS, BORDER = 36, 8
C = config.COLORS


@lru_cache(maxsize=None)
def font(name, size):
    return ImageFont.truetype(os.path.join(config.FONTS_DIR, name), size)


def display_name(name):
    """'LAST, FIRST MIDDLE' -> 'FIRST LAST' (suffix kept)."""
    last, _, rest = name.partition(",")
    parts = rest.split()
    suffix = [p for p in parts[1:] if p.rstrip(".") in ("JR", "SR", "II", "III", "IV")]
    return " ".join(parts[:1] + [last.strip()] + suffix) if parts else name


def chip(charge):
    """Short level label and its color: F1/F2/F3/F, M1/M2/M, CAP, LIFE, or '?'."""
    level, degree = charge.get("level", ""), charge.get("degree", "")
    if degree in ("CAPITAL", "LIFE"):
        return ("CAP" if degree == "CAPITAL" else "LIFE"), C["felony"]
    n = {"FIRST": "1", "SECOND": "2", "THIRD": "3"}.get(degree, "")
    if level == "Felony":
        return "F" + n, C["felony"]
    if level == "Misdemeanor":
        return "M" + n, C["misdemeanor"]
    return "•", C["other"]


def _fit(draw, text, name, size, max_w, min_size=40):
    while size > min_size and draw.textlength(text, font=font(name, size)) > max_w:
        size -= 4
    return font(name, size)


def _ellipsize(draw, text, f, max_w):
    if draw.textlength(text, font=f) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _canvas(w, h):
    """Gulf-teal gradient with the sunset band across the top edge."""
    img = Image.new("RGB", (w, h))
    top, bottom = C["bg_top"], C["bg_bottom"]
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    for x in range(w):
        t = x / (w - 1)
        d.line([(x, 0), (x, 14)], fill=tuple(round(C["accent"][i] + (C["misdemeanor"][i] - C["accent"][i]) * t)
                                             for i in range(3)))
    return img, d


def _header(d, y, size=92):
    """FLORIDA (sand) MUGSHOTS (coral), baseline at y. Returns the x where it ends."""
    hf = font("Anton-Regular.ttf", size)
    d.text((MARGIN, y), "FLORIDA", font=hf, fill=C["text"], anchor="ls")
    x = MARGIN + d.textlength("FLORIDA ", font=hf)
    d.text((x, y), "MUGSHOTS", font=hf, fill=C["accent"], anchor="ls")
    return x + d.textlength("MUGSHOTS", font=hf)


def _pill(d, x, y, text, fill=None, size=34):
    """Rounded label with its top-left at (x, y). Returns the x where it ends."""
    pf = font("Barlow-ExtraBold.ttf", size)
    tw = d.textlength(text, font=pf)
    d.rounded_rectangle([x, y, x + tw + 56, y + 64], radius=32, fill=fill or C["accent"])
    d.text((x + 28, y + 32), text, font=pf, fill=C["accent_text"], anchor="lm")
    return x + tw + 56


def _background(b):
    img, d = _canvas(W, H)
    _header(d, 130)

    # Name
    y = PY + PH + 110
    name = display_name(b["name"]).upper()
    nf = _fit(d, name, "Anton-Regular.ttf", 96, W - 2 * MARGIN - 60)
    d.text((MARGIN, y), name, font=nf, fill=C["text"], anchor="ls")

    # Charges: chip + description, one line each, in queue order (headline charge first), max 3
    cf, chf = font("Barlow-SemiBold.ttf", 36), font("Barlow-ExtraBold.ttf", 30)
    charges = b["charges"]
    y += 40
    for c in charges[:3]:
        label, color = chip(c)
        d.rounded_rectangle([MARGIN, y, MARGIN + 86, y + 50], radius=12, fill=color)
        d.text((MARGIN + 43, y + 25), label, font=chf, fill=C["accent_text"], anchor="mm")
        desc = c["desc"].upper() + (f" (x{c['count']})" if c.get("count", 1) > 1 else "")
        d.text((MARGIN + 108, y + 25), _ellipsize(d, desc, cf, 940 - MARGIN - 108), font=cf,
               fill=C["text"], anchor="lm")
        y += 66
    if len(charges) > 3:
        d.text((MARGIN + 108, y + 14), f"+{len(charges) - 3} MORE", font=font("Barlow-Bold.ttf", 30),
               fill=C["muted"], anchor="lm")
    return img


def _overlay(bg, b):
    """Transparent layer above the photo: background in the rounded-off corners, and a border. Nothing on the photo itself."""
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = Image.new("L", (PW, PH), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, PW - 1, PH - 1], radius=RADIUS, fill=255)
    corners = bg.crop((PX, PY, PX + PW, PY + PH)).convert("RGBA")
    corners.putalpha(mask.point(lambda v: 255 - v))
    over.paste(corners, (PX, PY))
    d = ImageDraw.Draw(over)
    d.rounded_rectangle([PX, PY, PX + PW - 1, PY + PH - 1], radius=RADIUS, outline=C["accent"], width=BORDER)

    return over


def render(b, photo, out_path, seconds=config.REEL_SECONDS):
    frames = seconds * FPS
    with tempfile.TemporaryDirectory() as tmp:
        bg = _background(b)
        bg.save(f"{tmp}/bg.png")
        _overlay(bg, b).save(f"{tmp}/over.png")
        # Cover-scale the photo to 2x the window, then zoom out from 1.12 to 1.0 over the clip
        zoom = (f"[1:v]scale={PW * 2}:{PH * 2}:force_original_aspect_ratio=increase,crop={PW * 2}:{PH * 2},"
                f"zoompan=z='max(1.12-0.12*on/{frames},1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={PW}x{PH}:fps={FPS}[p]")
        graph = f"{zoom};[0:v][p]overlay={PX}:{PY}[a];[a][2:v]overlay=0:0,format=yuv420p[v]"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-t", str(seconds), "-i", f"{tmp}/bg.png",
            "-i", photo,
            "-loop", "1", "-t", str(seconds), "-i", f"{tmp}/over.png",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", graph, "-map", "[v]", "-map", "3:a",
            "-t", str(seconds), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", out_path,
        ], check=True)
    return out_path


def build_queue_reels():
    """Render a Reel for each unposted entry and record it as 'reel'. A failure leaves that entry
    without one, so posting falls back to the still photo."""
    q = posting_queue.load()
    os.makedirs(config.REELS_DIR, exist_ok=True)
    for e in q["entries"]:
        d = e["data"]
        d.pop("reel", None)
        if e.get("posted") or not d.get("photo") or not os.path.exists(d["photo"]):
            continue
        out = os.path.join(config.REELS_DIR, f"{d['id']}.mp4")
        try:
            render(d, d["photo"], out)
            d["reel"] = out
            print(f"🎬 Reel: {out}")
        except Exception as ex:
            print(f"⚠️  Reel failed for {d['id']}: {ex}")
    posting_queue.save(q)
    # Pages serves everything in reels/, so drop Reels of posted or removed people
    current = {os.path.basename(e["data"]["reel"]) for e in q["entries"] if e["data"].get("reel")}
    for fn in os.listdir(config.REELS_DIR):
        if fn not in current:
            os.remove(os.path.join(config.REELS_DIR, fn))


def _wrap(d, text, f, max_w):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=f) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


NEWS_W, NEWS_H = 1080, 1350   # 4:5 feed card; the Reel puts it on a 9:16 canvas


def render_news_card(s, photo, out_path):
    """News card JPEG: header, NEWS + region/source pills, optional booking photo, headline, summary, credit."""
    img, d = _canvas(NEWS_W, NEWS_H)
    _header(d, 120, 80)
    x = _pill(d, MARGIN, 160, "NEWS")
    _pill(d, x + 16, 160, f"{s['region'].upper()}  •  {s['source'].upper()}", fill=C["muted"])

    y, max_w = 270, NEWS_W - 2 * MARGIN
    if photo:
        pw, ph = 400, 500
        p = Image.open(photo).convert("RGB")
        scale = max(pw / p.width, ph / p.height)
        p = p.resize((round(p.width * scale), round(p.height * scale)))
        p = p.crop(((p.width - pw) // 2, (p.height - ph) // 2, (p.width - pw) // 2 + pw, (p.height - ph) // 2 + ph))
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=28, fill=255)
        img.paste(p, (MARGIN, y), mask)
        d.rounded_rectangle([MARGIN, y, MARGIN + pw - 1, y + ph - 1], radius=28, outline=C["accent"], width=6)
        y += ph + 40

    # Headline: largest Anton size that fits the room left above the summary
    room = NEWS_H - y - 330
    title = s["title"].upper()
    for size in range(112, 55, -6):
        hf = font("Anton-Regular.ttf", size)
        lines = _wrap(d, title, hf, max_w)
        if len(lines) * size * 1.08 <= room:
            break
    for line in lines:
        y += round(size * 1.08)
        d.text((MARGIN, y), line, font=hf, fill=C["text"], anchor="ls")

    # Summary, up to 4 lines
    sf = font("Barlow-SemiBold.ttf", 36)
    summary = _wrap(d, s["description"], sf, max_w)
    if len(summary) > 4:
        summary = summary[:4]
        summary[-1] = _ellipsize(d, summary[-1] + " …", sf, max_w)
    y += 40
    for line in summary:
        y += 46
        d.text((MARGIN, y), line, font=sf, fill=C["muted"], anchor="ls")

    d.line([(MARGIN, NEWS_H - 90), (MARGIN + 120, NEWS_H - 90)], fill=C["accent"], width=6)
    d.text((MARGIN, NEWS_H - 50), f"SOURCE: {s['source'].upper()}  •  FULL STORY IN CAPTION",
           font=font("Barlow-Bold.ttf", 28), fill=C["text"], anchor="ls")
    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_news_reel(card, out_path, seconds=config.REEL_SECONDS):
    """9:16 Reel: the card centered on the gradient canvas, slowly zooming in."""
    frames = seconds * FPS
    with tempfile.TemporaryDirectory() as tmp:
        frame, _ = _canvas(W, H)
        frame.paste(Image.open(card), (0, (H - NEWS_H) // 2 - 60))
        frame.resize((W * 2, H * 2)).save(f"{tmp}/frame.png")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", f"{tmp}/frame.png",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", f"[0:v]zoompan=z='1+0.05*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                               f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p[v]",
            "-map", "[v]", "-map", "1:a", "-t", str(seconds), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", out_path,
        ], check=True)
    return out_path


SAMPLE = {
    "id": "sample-1", "county": "Lee", "booked": "2026-10-09", "name": "SAMPLE, JORDAN ALEX", "age": 34,
    "bond": 25000.0, "charges": [
        {"desc": "Aggravated battery with a deadly weapon", "level": "Felony", "degree": "SECOND"},
        {"desc": "Resisting officer without violence", "level": "Misdemeanor", "degree": "FIRST"},
        {"desc": "Possession of cannabis under 20 grams", "level": "Misdemeanor", "degree": "FIRST"},
        {"desc": "Driving while license suspended", "level": "", "degree": ""},
    ],
}


def preview(photo, out_path):
    """Render the sample booking with any photo, plus a still of the middle frame, for design work."""
    render(SAMPLE, photo, out_path)
    still = out_path.rsplit(".", 1)[0] + ".png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "4", "-i", out_path, "-frames:v", "1", still],
                   check=True)
    print(f"🎬 {out_path}\n🖼️  {still}")
