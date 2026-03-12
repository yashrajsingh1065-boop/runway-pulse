import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "runway_pulse.db"
IMAGE_DIR = DATA_DIR / "images"

# ── Claude API ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS  = 4096
CLAUDE_TEMPERATURE = 0.3

# ── Dashboard ──────────────────────────────────────────────────────────────────
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8501"))
LOG_LEVEL      = os.environ.get("LOG_LEVEL", "INFO").upper()

# ── Fashion Weeks ──────────────────────────────────────────────────────────────
FASHION_WEEKS = {
    "paris":       {"name": "Paris Fashion Week",       "code": "PFW",  "city": "Paris",       "country": "France"},
    "milan":       {"name": "Milan Fashion Week",       "code": "MFW",  "city": "Milan",       "country": "Italy"},
    "london":      {"name": "London Fashion Week",      "code": "LFW",  "city": "London",      "country": "United Kingdom"},
    "new-york":    {"name": "New York Fashion Week",    "code": "NYFW", "city": "New York",    "country": "United States"},
    "florence":    {"name": "Pitti Uomo",               "code": "PU",   "city": "Florence",    "country": "Italy"},
    "tokyo":       {"name": "Tokyo Fashion Week",       "code": "TFW",  "city": "Tokyo",       "country": "Japan"},
    "seoul":       {"name": "Seoul Fashion Week",       "code": "SFW",  "city": "Seoul",       "country": "South Korea"},
    "copenhagen":  {"name": "Copenhagen Fashion Week",  "code": "CPFW", "city": "Copenhagen",  "country": "Denmark"},
    "shanghai":    {"name": "Shanghai Fashion Week",    "code": "SHFW", "city": "Shanghai",    "country": "China"},
    "mumbai":      {"name": "Lakme Fashion Week",       "code": "LKFW", "city": "Mumbai",      "country": "India"},
}

# ── Season Periods ─────────────────────────────────────────────────────────────
SEASON_PERIODS = {
    "FW": {"period": "fall", "label": "Fall/Winter"},
    "SS": {"period": "spring", "label": "Spring/Summer"},
}

# ── Vogue URL Patterns ────────────────────────────────────────────────────────
VOGUE_BASE_URL = "https://www.vogue.com/fashion-shows"
VOGUE_SEASON_URL = VOGUE_BASE_URL + "/{period}-{year}-menswear"
VOGUE_SHOW_URL   = VOGUE_BASE_URL + "/{season_slug}/{designer_slug}"

# ── Scraper Settings ──────────────────────────────────────────────────────────
SCRAPER_DOWNLOAD_DELAY   = 2
SCRAPER_CONCURRENT       = 4
SCRAPER_ROBOTSTXT_OBEY   = True
SCRAPER_USER_AGENT       = "RunwayPulse/1.0 (fashion research; +https://github.com/runway-pulse)"
IMAGE_DOWNLOAD_WORKERS   = 6
IMAGE_DOWNLOAD_TIMEOUT   = 30

# ── CV Models & Thresholds (Phase 2) ────────────────────────────────────────
FASHIONPEDIA_MODEL       = "valentinafeve/yolos-fashionpedia"
CV_DEVICE                = "auto"  # "auto" | "mps" | "cpu"
CV_CONFIDENCE_MIN        = 0.5
CV_GARMENT_IOU_THRESHOLD = 0.4
COLOR_CLUSTER_K          = 5
SUIT_COLOR_MATCH_THRESHOLD = 30  # max Euclidean RGB distance for "matching" jacket+pants

# ── Claude Suit Analysis (Batch API) ────────────────────────────────────────
CLAUDE_SUIT_SYSTEM = """You are an expert menswear analyst specializing in tailoring and suiting construction.
Analyze the runway look image and provide detailed suiting analysis.
Return ONLY valid JSON with no markdown formatting.

Required JSON schema:
{
  "lapel_style": "notch|peak|shawl|none",
  "lapel_width": "slim|medium|wide",
  "gorge_height": "low|medium|high",
  "button_stance": "low|medium|high",
  "button_count": 1-4,
  "shoulder_construction": "natural|structured|padded|soft",
  "vent_style": "single|double|ventless|unknown",
  "construction": "canvas|half-canvas|fused|unknown",
  "visible_handwork": true/false,
  "lining": "full|half|unlined|unknown",
  "fabric_material": "wool|cotton|linen|silk|synthetic|blend|unknown",
  "fabric_weight": "light|medium|heavy",
  "fabric_texture": "smooth|textured|napped|crisp",
  "fabric_pattern": "solid|pinstripe|chalk-stripe|check|houndstooth|plaid|windowpane|herringbone|other",
  "fit": "slim|regular|oversized|relaxed|boxy",
  "length": "short|regular|long",
  "proportions_notes": "brief note on proportions",
  "color_primary": "confirmed/corrected primary color",
  "color_secondary": "secondary color if any or null",
  "mood": "1-3 word mood descriptor",
  "designer_intent": "1-2 sentence interpretation",
  "styling_notes": "1-2 sentence styling observations",
  "era_references": "decade/era references or null",
  "confidence": 0.0-1.0
}"""
CLAUDE_SUIT_MAX_TOKENS   = 1000

# ── Trend Aggregation (Phase 4) ───────────────────────────────────────────
TREND_STABLE_THRESHOLD = 2.0  # percentage points — below this is "stable"

TREND_CATEGORICAL_FIELDS = [
    "lapel_style", "lapel_width", "gorge_height", "button_stance",
    "button_count", "shoulder_construction", "vent_style", "construction",
    "visible_handwork", "lining", "fabric_material", "fabric_weight",
    "fabric_texture", "fabric_pattern", "fit", "length",
]

MOOD_ARCHETYPES = {
    "quiet_luxury": ["quiet", "understated", "luxe", "discreet", "stealth", "wealth", "subtle elegance", "effortless", "whisper"],
    "power_dressing": ["power", "commanding", "authoritative", "boss", "corporate", "executive", "assertive", "sharp"],
    "deconstructed": ["deconstruct", "raw edge", "unfinished", "exposed seam", "asymmetric", "undone", "dismantled"],
    "utilitarian": ["utilitarian", "workwear", "utility", "functional", "industrial", "military", "cargo", "uniform"],
    "mediterranean": ["mediterranean", "riviera", "coastal", "linen", "sun", "breezy", "resort", "leisure"],
    "romantic": ["romantic", "poetic", "dreamy", "soft", "flowing", "delicate", "ethereal", "gentle"],
    "dark_edge": ["dark", "goth", "noir", "brooding", "somber", "moody", "shadow", "black"],
    "streetwear_fusion": ["street", "urban", "hip-hop", "skate", "casual", "sporty", "athleisure", "hoodie"],
    "minimalist": ["minimal", "clean", "pared", "simple", "stripped", "restrained", "austere", "reductive"],
    "retro_revival": ["retro", "vintage", "nostalgic", "throwback", "revival", "heritage", "classic revival"],
    "avant_garde": ["avant", "experimental", "conceptual", "abstract", "sculptural", "radical", "provocative"],
    "relaxed_ease": ["relaxed", "easy", "laid-back", "nonchalant", "slouch", "loose", "comfort"],
    "futurist": ["futur", "tech", "cyber", "metallic", "neo", "space", "digital", "synthetic"],
    "refined_classic": ["refined", "classic", "traditional", "timeless", "elegant", "sophisticated", "polished", "tailored"],
}
