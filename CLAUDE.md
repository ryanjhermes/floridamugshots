# CLAUDE.md

@florida.mugshots: a sister project to `../minneapolismugshots`, rebuilt for Florida with its own look. The product
brief is `README.md`. Minneapolis is the reference for patterns (queue, slots, Pages hosting) and its "Known gotchas".

**Status (Oct 10 2026):** scrape → rank → Reels → posting is built and tested end to end locally (real Oct 9 data,
`post-next --dry-run`). It has **not run on GitHub Actions or posted to Instagram yet**. DM removal handling, news
posts and Hillsborough are not built.

## Layout

```
bot/
  __main__.py       CLI: one subcommand per job, modules imported lazily (each workflow installs only its own deps)
  config.py         Every tunable: schedule, ranking weights/keywords, colors, county captions. Keep it import-light
  common.py         Eastern clock, JSON state, PoliteSession (throttled requests), GitHub outputs
  sources/          One module per county: fetch(day, session) and photo(booking, session). Booking dict schema
                    is in sources/__init__.py; helpers in sources/record.py
  scrape.py         Nightly: all sources -> filter (adults, not removed, not already posted) -> shortlist -> photos -> rank -> queue
  ranking.py        Charge score (text) to shortlist, then + CLIP photo score; max 5 per county
  clip_model.py     CLIP distinctiveness prompts
  posting_queue.py  posting_queue.json (schema in its docstring)
  reels.py          Pillow card + ffmpeg zoom. `preview-reel` renders a sample for design work
  posting.py        Captions, preflight (slot logic), post_next with Reel -> photo fallback
  instagram.py      graph.instagram.com container -> poll -> publish
  news.py           News posts: statewide TV RSS -> zero-shot scoring -> our own card + Reel (pick, then post)
  removals.py       removed.json (hashed names) and purge
  auth.py           Token setup/check/refresh
site/               Static Pages content (about, removal policy, privacy policy for the Meta app)
fonts/              Anton + Barlow (OFL, licenses alongside)
docs/               Our docs: meta-app-setup.md, data-sources.md. NOT the Pages output (that's _site/, gitignored)
```

## Commands

```bash
python -m venv venv && venv/bin/pip install -r requirements.txt torch "transformers>=4.40,<6"
python -m bot scrape --dry-run            # Pull yesterday, print the top 10; writes nothing
python -m bot scrape [--day YYYY-MM-DD]   # Rebuild posting_queue.json + mugshots/ (Orange has only the latest day)
python -m bot make-reels                  # Reels for the unposted queue (needs ffmpeg)
python -m bot preview-reel PHOTO --out x.mp4   # Sample Reel + still, for design changes
python -m bot preflight | post-next [--dry-run] | check-queue
python -m bot news pick --dry-run [--force]   # Score today's stories and render the winner; no state change
python -m bot purge-removed | purge-unqueued
python -m bot auth check | refresh
```

**Local runs edit real state files** and pull real people's data. Test in a scratch copy, use `--dry-run`, and
don't leave scraped photos or queues lying around outside the repo's own `mugshots/`.

## How a day runs (Eastern)

```
2:30 AM  daily-scrape        yesterday's bookings → rank → queue 10 → Reels → commit → Pages
7,9,11,12,1,3,5,7,8,9         instagram-posting posts one per slot (Reel via Pages URL, photo fallback)
2, 6 PM  news-posting        best outlandish Florida crime story (if any clears the bar) → card + Reel → Pages → post
Mon      token-refresh       extends the 60-day Instagram token and stores it back as a repo secret
```

## Decisions

- **Instagram API with Instagram Login** (`graph.instagram.com`), not Facebook Login like Minneapolis: no Facebook
  Page, fewer scopes (`config.SCOPES`). The account ID is `/me` → `user_id`; there's no `debug_token`. DMs will use
  `/<user_id>/conversations` with the same token. Separate Meta app from Minneapolis.
- **Sources: Lee, Polk, Orange only** (no captcha, robots/ToS allow it). Survey of all 19 counties and why the rest
  are out: `docs/data-sources.md`. We do not automate captchas; Hillsborough etc. need a records request or a
  human-in-the-loop runner.
- **Two-stage ranking** so we fetch only ~50 photos a night: charges first (degree + keyword list in config), then
  CLIP on the shortlist. Boring charges (VOP, FTA, suspended license...) score near zero even when their docket
  text mentions a serious charge.
- **Florida flavor is the top priority** (Ryan, Oct 10): wildlife, boats/water, golf carts/beaches/theme parks and
  weird-public-behavior charges outscore even murder (`fl-*` categories in `config.CHARGE_KEYWORDS`, plus statute
  chapters 379/327). Charges with a child or other vulnerable victim never get that bonus.
- **Domestic violence stays in** (Ryan's call), ranked like any other battery/assault.
- **Repeat limit:** up to 2 picks a day per headline-charge category, then −0.3 each. Keep "attractive" in the CLIP prompts.
- **Filenames are `county-booking#`, never names.** Addresses and DOBs are never stored. Under-18s and unknown ages
  are skipped.
- **Removal is permanent** (Fla. Stat. § 901.43, $5,000/day for republishing): hashed name in removed.json, checked
  at scrape and at post time, and purge deletes the photo and Reel.
- **Mugshot Reel look** (Ryan, Oct 11): black background, everything centered, no header text. Rounded photo with a
  coral border and zoom-out, name in Anton, charges in Barlow with a degree chip (none when the level is unknown).
  No age. News cards keep the teal gradient and header. No text on the photo, no emojis or disclaimer/removal lines in captions, and no county/date/bond pill or booking number (Ryan, Oct 10). Colors live in `config.COLORS`.

- **News posts use our own card, not the station's photo** (copyright: station/AP/Getty images). The story's lead
  image is shown only if CLIP says it's a booking photo. Stories are gated to Florida crime news, "shocking" is
  down-weighted (alone it rates every hit-and-run 0.8) and deaths are penalized; Florida flavor adds a bonus.
  Many days nothing clears `NEWS_MIN_SCORE`, which is intended. The NLI model is called directly (no
  transformers pipeline), so it works on transformers 5, unlike Minneapolis.

## Rules the code depends on

- Caption line 3, `LAST, FIRST MIDDLE (age)`, is the name as booked. DM removal matching will key on it.
- Pages is replaced wholesale on every deploy, so any workflow that deploys must run `make-reels` first.
- Posting uses Reels already on Pages, rendered at the last deploy. Pushing a change to `bot/reels.py`, `fonts/`
  or `site/` triggers rebuild-reels.yml, which re-renders the queue and redeploys; without it, a design change
  only shows after the next nightly scrape.
- Everything that edits the queue shares the `queue-state` concurrency group and checks out `ref: main`.

## Gotchas

- **Lee:** `toBooking` is exclusive and dates are unpadded (`2026-10-9`). No felony/misdemeanor field; court
  location stands in. Each count is a separate charge row (merged in `record.booking`).
- **Polk:** one anti-forgery token from any `/inmate-profile/` page works for the whole session. `ChargeDesc` is
  cut at ~32 chars; the docket text has the full charge. Many charges have no level (scored as "unknown" = 1 pt).
- **Orange:** the PDF is regenerated ~1:07 AM and only covers the latest day. Photos (`getInmateDetails`, POST
  with body `id=`) are empty once someone is released, so released bookings drop out at the photo stage.

- **News feeds:** Local 10 (WPLG Miami) returns 403 to GitHub runners (fine locally), so it's not in
  `NEWS_FEEDS`. Scoring ~90 stories takes ~4 min on a runner.

## Environment (`.env` locally; repo secrets in CI)

`IG_ACCESS_TOKEN`, `IG_USER_ID` (posting); `IG_APP_ID`, `IG_APP_SECRET` (OAuth fallback only); `PAGES_URL`
(optional, defaults to `https://ryanjhermes.github.io/floridamugshots`). CI also needs `GH_SECRETS_PAT` for
token-refresh. Meta app setup: `docs/meta-app-setup.md`.
