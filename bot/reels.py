"""Render 9:16 Reels for queued bookings: Pillow draws the card, ffmpeg animates the photo.

The Florida look, deliberately unlike Minneapolis (centered, black, yellow/red DejaVu):
Gulf-teal gradient, sunset-coral accents, sand text, Anton + Barlow, left-aligned layout, rounded photo
with a slow zoom-OUT, a tilted charge-level stamp on the photo, and a degree chip per charge.

Layers, bottom to top: background card (gradient + all text) -> zooming photo -> overlay (rounded corners,
border, stamp). Text stays clear of Instagram's Reel UI: nothing below y=1640 or right of x=940 under y=1000.
Reels are written to reels/ and served only from GitHub Pages (never committed).
"""
import os
import subprocess
import tempfile
from datetime import date
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import config, posting_queue

W, H, FPS = 1080, 1920, 30
MARGIN = 90
PX, PY, PW, PH = 90, 330, 720, 900       # Photo window (mugshots are 4:5)
RADIUS, BORDER = 36, 8
C = config.COLORS
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


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


def _background(b):
    img = Image.new("RGB", (W, H))
    top, bottom = C["bg_top"], C["bg_bottom"]
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    # Sunset band across the top edge
    for x in range(W):
        t = x / (W - 1)
        d.line([(x, 0), (x, 14)], fill=tuple(round(C["accent"][i] + (C["misdemeanor"][i] - C["accent"][i]) * t)
                                             for i in range(3)))

    # Header: FLORIDA (sand) MUGSHOTS (coral)
    hf = font("Anton-Regular.ttf", 92)
    d.text((MARGIN, 130), "FLORIDA", font=hf, fill=C["text"], anchor="ls")
    d.text((MARGIN + d.textlength("FLORIDA ", font=hf), 130), "MUGSHOTS", font=hf, fill=C["accent"], anchor="ls")

    # Pill: county, booking date, bond
    booked = date.fromisoformat(b["booked"])
    pill = [f"{b['county'].upper()} COUNTY", f"{MONTHS[booked.month - 1]} {booked.day}"]
    if b.get("bond"):
        pill.append(f"BOND ${b['bond']:,.0f}")
    pill_text = "  •  ".join(pill)
    pf = font("Barlow-ExtraBold.ttf", 34)
    tw = d.textlength(pill_text, font=pf)
    d.rounded_rectangle([MARGIN, 190, MARGIN + tw + 56, 254], radius=32, fill=C["accent"])
    d.text((MARGIN + 28, 222), pill_text, font=pf, fill=C["accent_text"], anchor="lm")

    # Booking number, running down the empty column right of the photo
    label = f"BOOKING #{b['booking_number']}" if b.get("booking_number") else ""
    if label:
        lf = font("Barlow-Bold.ttf", 30)
        strip = Image.new("RGBA", (int(d.textlength(label, font=lf)) + 4, 40), (0, 0, 0, 0))
        ImageDraw.Draw(strip).text((0, 20), label, font=lf, fill=C["muted"] + (255,), anchor="lm")
        strip = strip.rotate(-90, expand=True)
        img.paste(strip, (PX + PW + 40, PY + 140), strip)

    # Name + age
    y = PY + PH + 110
    name = display_name(b["name"]).upper()
    nf = _fit(d, name, "Anton-Regular.ttf", 96, W - 2 * MARGIN - 140)
    d.text((MARGIN, y), name, font=nf, fill=C["text"], anchor="ls")
    if b.get("age"):
        d.text((MARGIN + d.textlength(name + "  ", font=nf), y), f"{b['age']}", font=font("Anton-Regular.ttf", 56),
               fill=C["muted"], anchor="ls")

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
    """Transparent layer above the photo: background in the rounded-off corners, a border, and the stamp."""
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = Image.new("L", (PW, PH), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, PW - 1, PH - 1], radius=RADIUS, fill=255)
    corners = bg.crop((PX, PY, PX + PW, PY + PH)).convert("RGBA")
    corners.putalpha(mask.point(lambda v: 255 - v))
    over.paste(corners, (PX, PY))
    d = ImageDraw.Draw(over)
    d.rounded_rectangle([PX, PY, PX + PW - 1, PY + PH - 1], radius=RADIUS, outline=C["accent"], width=BORDER)

    worst = min(b["charges"], key=lambda c: {"Felony": 0, "Misdemeanor": 1}.get(c.get("level", ""), 2))
    text = (worst.get("level") or "BOOKED").upper()
    sf = font("Anton-Regular.ttf", 60)
    tw = int(d.textlength(text, font=sf))
    stamp = Image.new("RGBA", (tw + 70, 110), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    color = chip(worst)[1]
    sd.rounded_rectangle([4, 4, tw + 66, 106], radius=14, fill=C["bg_bottom"] + (235,), outline=color + (255,), width=7)
    sd.text(((tw + 70) / 2, 80), text, font=sf, fill=color + (255,), anchor="ms")
    stamp = stamp.rotate(-8, expand=True, resample=Image.BICUBIC)
    over.alpha_composite(stamp, (PX + PW - stamp.width + 90, PY - 50))
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


SAMPLE = {
    "id": "sample-1", "booking_number": "1033699", "county": "Lee", "booked": "2026-10-09", "name": "SAMPLE, JORDAN ALEX", "age": 34,
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
