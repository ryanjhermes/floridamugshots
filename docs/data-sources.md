# Florida booking data sources (survey, Oct 10 2026)

19 counties checked with a few polite requests each. "Recent list" means we can get the day's bookings without
knowing names. Re-check before building: sheriffs change these sites often, and since Houston v. Maricopa (9th
Cir. 2024) some, like Leon in Jan 2025, have stopped publishing mugshots.

## Use (no captcha, robots/ToS allow, recent list, photos)

| County | ~Bookings/day | How |
|---|---|---|
| **Lee** | ~45 | Open JSON: `sheriffleefl.org/public-api/bookings/q?limit=&offset=&startBooking=YYYY-M-D&toBooking=YYYY-M-D` (photo inline as base64); charges/bond at `/public-api/bookings/{bookingNumber}/charges`. No degree field |
| **Polk** | ~85 | POST `polksheriff.org/detention/jail-inquiry/SearchJail/` (`SelectedSearchType=BookingDate&BookingDate=YYYY-MM-DD`). Per booking: GET `/inmate-profile/{BookingNum}` for the antiforgery token, then `/inmate/GetCharges` (POST, has statute → derive degree) and `/inmate/GetPhoto?bookYr=&bookNo=`. ~3 requests/booking, so throttle |
| **Orange** | ~100 | Daily PDF `netapps.ocfl.net/BestJail/PDF/bookings.pdf` (prior 24h, regenerated ~01:00 ET; charges with felony/misdemeanor degree, agency). Photo via `/BestJail/Home/getInmateDetails/{bookingNo}` (base64), one call per chosen booking only. NetScaler in front |

## Maybe later

| County | Blocker |
|---|---|
| Pinellas | Blazor Server (SignalR) app: needs Playwright, so it's fragile |
| Marion | Legacy WebForms, "Recent" POST returned nothing without full browser state |
| Brevard | Clean date-range HTML, but **no photos** |

## Don't

| County | Why |
|---|---|
| Osceola | Easy HTML with photos, but `robots.txt: Disallow: /` |
| Volusia | ToS bans "publishing on-line" the data |
| Palm Beach | hCaptcha + `Disallow: /` + ToS bans redistribution |
| Miami-Dade, Duval, Seminole, Escambia | Captcha (reCAPTCHA / AWS WAF) |
| Hillsborough | reCAPTCHA + new bookings hidden from listings for 24h |
| Broward | Name-only search + Cloudflare Turnstile + protected images |
| Sarasota, Manatee | Revize behind Cloudflare challenge |
| Leon, Pasco | No public mugshots/roster online |

Captcha'd or ToS-restricted counties are reachable only by a Ch. 119 public-records request for a recurring
booking extract. No statewide feed exists (FDLE is paid per-name, no photos).

## Legal constraint that shapes the design

Fla. Stat. § 901.43: a publisher of booking photos for commercial gain must remove one free within 10 days of a
written request. Penalties are $1,000/day for not removing and $5,000/day for republishing, and violations count
under FDUTPA. Removals must be permanent across all sources (hashed list, as in Minneapolis `removed.json`).
