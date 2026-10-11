"""Every tunable in one place: schedule, ranking weights, look, file paths, URLs.

Keep this free of heavy imports: every workflow imports it, and the posting workflow installs only
requests, python-dotenv and pytz. Paths are relative to the repo root (run `python -m bot ...` from there).
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- State files (committed by the workflows, except reels/) ---
QUEUE_FILE = "posting_queue.json"    # What's queued and posted (see posting_queue.py)
MUGSHOTS_DIR = "mugshots"            # Photos for queued posts, served by Pages. Named county-booking#.jpg, never by name
REELS_DIR = "reels"                  # Rendered Reels, Pages only (gitignored)
REMOVED_FILE = "removed.json"        # Hashed names of people who asked to be taken down (Fla. Stat. § 901.43)
FONTS_DIR = "fonts"

# --- Instagram API with Instagram Login (no Facebook Page involved) ---
GRAPH_API = "https://graph.instagram.com/v23.0"
GRAPH_API_UNVERSIONED = "https://graph.instagram.com"   # token exchange/refresh endpoints are unversioned
OAUTH_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://api.instagram.com/oauth/access_token"

# Everything the bot will do: post, read/answer DMs, moderate comments, measure what performs
SCOPES = [
    "instagram_business_basic",
    "instagram_business_content_publish",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
    "instagram_business_manage_insights",
]

# Must exactly match a redirect URI saved in the app dashboard (Business login settings)
REDIRECT_URI = os.getenv("IG_REDIRECT_URI", "https://ryanhermes.com/")

ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
USER_ID = os.getenv("IG_USER_ID", "")
APP_ID = os.getenv("IG_APP_ID", "")
APP_SECRET = os.getenv("IG_APP_SECRET", "")

# Instagram only accepts media by public URL, so photos and Reels are served from GitHub Pages
PAGES_URL = os.getenv("PAGES_URL", "https://ryanjhermes.github.io/floridamugshots").rstrip("/")

# --- Schedule (Eastern time: all three counties are Eastern) ---
TIMEZONE = "US/Eastern"
# One post per slot; QUEUE_SIZE should match so each night's picks are gone by bedtime. See posting.preflight
POSTING_HOURS = [7, 9, 11, 12, 13, 15, 17, 19, 20, 21]
QUEUE_SIZE = 10

# --- Scraping (scrape.py and sources/) ---
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
REQUEST_DELAY = 0.75     # Seconds between requests to the same site; keep it polite
REQUEST_TIMEOUT = 30
MIN_AGE = 18             # Never post anyone under 18 (or of unknown age if the source has no age at all)

# --- Ranking (ranking.py) ---
SHORTLIST_SIZE = 50      # Best by charge text get their photos fetched and scored by CLIP
MAX_PER_COUNTY = 5       # Keep the day's 10 from being all one county
TEXT_WEIGHT, PHOTO_WEIGHT = 0.6, 0.4   # Final score = weights x (charge score, CLIP distinctiveness), each 0..1

# Points for the most serious charge's level/degree
DEGREE_POINTS = {
    ("Felony", "CAPITAL"): 5, ("Felony", "LIFE"): 4.5, ("Felony", "FIRST"): 3, ("Felony", "SECOND"): 2.5,
    ("Felony", "THIRD"): 2, ("Felony", ""): 2, ("Misdemeanor", "FIRST"): 0.75, ("Misdemeanor", "SECOND"): 0.5,
    ("Misdemeanor", ""): 0.5,
    ("", ""): 1,  # Level unknown (common in Polk): between a misdemeanor and a felony
}
# (category, regex, bonus points). Regex is matched against the upper-cased charge description + docket text;
# the highest match per charge counts. Category is what the repeat limit counts (REPEAT_LIMIT).
# This is the "would people stop scrolling for this" list; tune it from insights.
# Florida flavor sits at the top on purpose: a gator or airboat charge should beat almost anything.
CHARGE_KEYWORDS = [
    ("fl-wildlife", r"ALLIGATOR|\bGATORS?\b|CROCODILE|MANATEE|PYTHON|IGUANA|SHARK|SEA TURTLE|MARINE TURTLE|"
                    r"PELICAN|FLAMINGO|PANTHER|\bBEARS?\b|WILDLIFE|\bFWC\b|FISH AND WILDLIFE|\bGAME\b|SNOOK|"
                    r"REDFISH|\bHUNT", 8),
    ("fl-water", r"AIRBOAT|\bBOAT|VESSEL|JET ?SKI|WATERCRAFT|\bBUI\b|MARINE|SWAMP|CANAL|MANGROVE", 7),
    ("fl-life", r"GOLF CART|LAWN ?MOWER|\bMOPED|SCOOTER|\bBEACH|THEME PARK|DISNEY|UNIVERSAL|SEAWORLD|"
                r"FIREWORK|HURRICANE|SPRING BREAK|FLORIDA MAN", 7),
    ("fl-weird", r"NAKED|NUDITY|EXPOSURE|INDECENT|BODILY FLUID|\bSPIT|URINAT|FECES|MISSILE|"
                 r"THROW.*(DEADLY|MISSILE|OBJECT)", 6),
    ("sex-offense", r"LEWD|VOYEUR|SEXUAL", 2),
    ("murder", r"MURDER|HOMICIDE", 5),
    ("animal", r"ANIMAL|\bDOGS?\b|\bCATS?\b|HORSE|LIVESTOCK|\bCOCK ?FIGHT|\bROOSTER", 4.5),
    ("violent-major", r"MANSLAUGHTER|KIDNAP|CARJACK|HOME ?INVASION", 4),
    ("armed", r"ARMED ROBBERY|ROBBERY.*(FIREARM|WEAPON)|SHOOT|DISCHARG.*FIREARM|FIRE(ARM)? INTO", 3.5),
    ("arson", r"ARSON|EXPLOSIVE|BOMB|HOAX", 3),
    ("agg-battery", r"AGG(RAVATED)?\.? (BATTERY|ASSAULT|STALKING)|DEADLY WEAPON", 2.5),
    ("officer", r"(BATTERY|ASSAULT).*(LEO|OFFICER|FIREFIGHTER|EMS|DEPUTY)|(LEO|OFFICER).*(BATTERY|ASSAULT)", 2.5),
    ("flee", r"FLEE|ELUD|HIGH SPEED|RESIST.*WITH VIOL", 2),
    ("trafficking", r"TRAFFICK|SMUGGL|RACKETEER|ORGANIZED FRAUD|EXPLOIT", 2),
    ("dui-serious", r"DUI.*(MANSLAUGHTER|SERIOUS|INJURY|DAMAGE)", 2),
    ("theft", r"ROBBERY|BURGLARY|STRONG ARM|GRAND THEFT.*(MOTOR|VEHICLE)", 1.5),
    ("fraud", r"IMPERSONAT|FALSE (REPORT|INFO|ID)|BRIBE", 1.5),
    ("dui", r"DUI|DWI|UNDER THE INFLUENCE", 0.75),
    ("battery", r"BATTERY|ASSAULT|STALK|THREAT", 0.75),
]
# Charges with a child victim never get the playful fl-* bonus (a lewd act on a minor is not "Florida flavor")
FLAVOR_EXCLUDE = r"CHILD|MINOR|JUVENILE|UNDER (1[0-8]|EIGHTEEN|SIXTEEN)|ELDERLY|DISABLED"
# Statute chapter prefixes -> (category, points), for charges whose description doesn't say it
STATUTE_KEYWORDS = [
    ("fl-wildlife", r"^379\.", 8),    # Fish and wildlife conservation
    ("fl-water", r"^327\.", 7),       # Vessel safety (boating under the influence etc.)
    ("animal", r"^828\.", 4.5),       # Animal cruelty
]
# At most this many of the day's picks share a headline-charge category; each one past it loses REPEAT_PENALTY
# (on the 0..1 final score), so a third meth trafficking only makes it on a slow day.
REPEAT_LIMIT = 2
REPEAT_PENALTY = 0.3
# Charges that make a booking boring on their own. A booking where every charge matches loses BORING_PENALTY.
BORING_CHARGES = (r"VIOLATION OF PROBATION|\bVOP\b|PROBATION|FAILURE TO APPEAR|\bFTA\b|\bWRIT\b|\bHOLD\b|\bWARRANT\b|"
                  r"OUT OF COUNTY|CONTEMPT|COMMUNITY CONTROL|SUSPENDED|REVOKED|NO VALID|DRIVING WHILE LIC|"
                  r"WITHOUT A? ?VALID|PRETRIAL RELEASE|CHILD SUPPORT|TRESPASS|OPEN CONTAINER|LOITER")
BORING_PENALTY = 3

# --- Posts ---
DISCLAIMER = "An arrest is not a conviction. Charges are allegations, and everyone is presumed innocent until proven guilty in court."
REMOVAL_NOTE = "Want this taken down? DM us. Removal is always free."
REEL_SECONDS = 8

# The Florida look (reels.py). Deliberately unlike Minneapolis (black / yellow / red, DejaVu)
COLORS = {
    "bg_top": (10, 52, 64),       # deep Gulf teal
    "bg_bottom": (6, 22, 33),     # night navy
    "accent": (255, 111, 82),     # sunset coral
    "accent_text": (20, 20, 24),
    "text": (247, 236, 214),      # sand
    "muted": (143, 196, 196),     # sea glass
    "felony": (255, 111, 82),
    "misdemeanor": (255, 196, 92),  # citrus
    "other": (143, 196, 196),
}

# Per-county caption details: source credit and hashtags
COUNTIES = {
    "Lee": {"source": "Lee County Sheriff's Office", "tags": "#LeeCounty #FortMyers #CapeCoral #SWFL"},
    "Polk": {"source": "Polk County Sheriff's Office", "tags": "#PolkCounty #Lakeland #WinterHaven #CentralFlorida"},
    "Orange": {"source": "Orange County Corrections", "tags": "#OrangeCounty #Orlando #CentralFlorida"},
}
