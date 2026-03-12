from __future__ import annotations

import os
import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from config import DB_PATH, FASHION_WEEKS, SEASON_PERIODS

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create all 12 tables, indexes, and seed reference data."""
    with _connect() as conn:
        conn.executescript("""
            -- Reference tables
            CREATE TABLE IF NOT EXISTS fashion_weeks (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                code    TEXT NOT NULL UNIQUE,
                city    TEXT NOT NULL,
                country TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seasons (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                code   TEXT NOT NULL UNIQUE,
                year   INTEGER NOT NULL,
                period TEXT NOT NULL
            );

            -- Core runway data
            CREATE TABLE IF NOT EXISTS shows (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id       INTEGER REFERENCES seasons(id),
                fashion_week_id INTEGER REFERENCES fashion_weeks(id),
                designer        TEXT NOT NULL,
                designer_slug   TEXT NOT NULL,
                show_date       TEXT,
                source_url      TEXT UNIQUE,
                look_count      INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS looks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id         INTEGER NOT NULL REFERENCES shows(id),
                look_number     INTEGER NOT NULL,
                image_url       TEXT,
                local_path      TEXT,
                image_hash      TEXT,
                cv_processed    INTEGER DEFAULT 0,
                claude_processed INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL,
                UNIQUE(show_id, look_number)
            );

            -- CV + Claude output (Phase 2-3)
            CREATE TABLE IF NOT EXISTS garment_attributes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                look_id      INTEGER NOT NULL REFERENCES looks(id),
                garment_type TEXT NOT NULL,
                bbox_json    TEXT,
                confidence   REAL,
                silhouette   TEXT,
                color_name   TEXT,
                color_hex    TEXT,
                color_lab_json TEXT,
                palette_json TEXT,
                fabric       TEXT,
                pattern      TEXT,
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS look_analysis (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                look_id              INTEGER NOT NULL UNIQUE REFERENCES looks(id),
                styling_notes        TEXT,
                mood                 TEXT,
                designer_intent      TEXT,
                construction         TEXT,
                suiting_details_json TEXT,
                raw_json             TEXT,
                created_at           TEXT NOT NULL
            );

            -- Trend aggregation (Phase 4)
            CREATE TABLE IF NOT EXISTS trend_snapshots (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id            INTEGER REFERENCES seasons(id),
                attribute_type       TEXT NOT NULL,
                attribute_value      TEXT NOT NULL,
                frequency            INTEGER DEFAULT 0,
                total_looks          INTEGER DEFAULT 0,
                direction            TEXT,
                change_pct           REAL,
                compared_to_season_id INTEGER REFERENCES seasons(id),
                created_at           TEXT NOT NULL
            );

            -- Street style (Phase 5)
            CREATE TABLE IF NOT EXISTS street_images (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                source        TEXT,
                url           TEXT UNIQUE,
                location      TEXT,
                captured_date TEXT,
                local_path    TEXT,
                image_hash    TEXT,
                cv_processed  INTEGER DEFAULT 0,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS street_garment_attributes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                street_image_id INTEGER NOT NULL REFERENCES street_images(id),
                garment_type    TEXT NOT NULL,
                bbox_json       TEXT,
                confidence      REAL,
                silhouette      TEXT,
                color_name      TEXT,
                color_hex       TEXT,
                color_lab_json  TEXT,
                palette_json    TEXT,
                fabric          TEXT,
                pattern         TEXT,
                created_at      TEXT NOT NULL
            );

            -- Adoption + Reports + News (Phase 5-6)
            CREATE TABLE IF NOT EXISTS adoption_metrics (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                attribute_type   TEXT NOT NULL,
                attribute_value  TEXT NOT NULL,
                origin_season_id INTEGER REFERENCES seasons(id),
                runway_freq      INTEGER DEFAULT 0,
                street_freq      INTEGER DEFAULT 0,
                lag_weeks        INTEGER,
                penetration_pct  REAL,
                geography_json   TEXT,
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reports (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id      INTEGER REFERENCES seasons(id),
                title          TEXT NOT NULL,
                focus_area     TEXT,
                narrative      TEXT,
                pdf_path       TEXT,
                notion_page_id TEXT,
                created_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fashion_news (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source       TEXT,
                url          TEXT UNIQUE,
                title        TEXT NOT NULL,
                body         TEXT,
                published_at TEXT,
                fetched_at   TEXT NOT NULL
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_shows_season ON shows(season_id);
            CREATE INDEX IF NOT EXISTS idx_shows_designer ON shows(designer_slug);
            CREATE INDEX IF NOT EXISTS idx_looks_show ON looks(show_id);
            CREATE INDEX IF NOT EXISTS idx_looks_hash ON looks(image_hash);
            CREATE INDEX IF NOT EXISTS idx_garment_look ON garment_attributes(look_id);
            CREATE INDEX IF NOT EXISTS idx_garment_type ON garment_attributes(garment_type);
            CREATE INDEX IF NOT EXISTS idx_trend_season ON trend_snapshots(season_id);
            CREATE INDEX IF NOT EXISTS idx_trend_attr ON trend_snapshots(attribute_type, attribute_value);
            CREATE INDEX IF NOT EXISTS idx_street_hash ON street_images(image_hash);
            CREATE INDEX IF NOT EXISTS idx_street_garment ON street_garment_attributes(street_image_id);
        """)

        # Seed fashion weeks
        for key, fw in FASHION_WEEKS.items():
            conn.execute(
                "INSERT OR IGNORE INTO fashion_weeks (name, code, city, country) VALUES (?, ?, ?, ?)",
                (fw["name"], fw["code"], fw["city"], fw["country"]),
            )

        # Seed seasons FW24 through SS27 (8 seasons)
        for year in range(2024, 2028):
            for prefix, info in SEASON_PERIODS.items():
                code = f"{prefix}{str(year)[2:]}"
                conn.execute(
                    "INSERT OR IGNORE INTO seasons (code, year, period) VALUES (?, ?, ?)",
                    (code, year, info["period"]),
                )

    logger.info("Database initialized")


# ── Phase 1 CRUD ──────────────────────────────────────────────────────────────


def get_or_create_show(
    season_id: int,
    fashion_week_id: int | None,
    designer: str,
    designer_slug: str,
    source_url: str,
    show_date: str | None = None,
) -> int:
    """Insert a show if source_url is new, return the show id."""
    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM shows WHERE source_url = ?", (source_url,)
        ).fetchone()
        if existing:
            return existing["id"]
        cur = conn.execute(
            """INSERT INTO shows (season_id, fashion_week_id, designer, designer_slug,
                                  show_date, source_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (season_id, fashion_week_id, designer, designer_slug, show_date, source_url, _now()),
        )
        return cur.lastrowid


def save_look(show_id: int, look_number: int, image_url: str) -> int | None:
    """Insert a look. Returns look id or None if duplicate."""
    with _connect() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO looks (show_id, look_number, image_url, created_at)
                   VALUES (?, ?, ?, ?)""",
                (show_id, look_number, image_url, _now()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_look_local_path(look_id: int, local_path: str, image_hash: str) -> None:
    """Set the local file path and hash after image download."""
    with _connect() as conn:
        conn.execute(
            "UPDATE looks SET local_path = ?, image_hash = ? WHERE id = ?",
            (local_path, image_hash, look_id),
        )


def look_hash_exists(image_hash: str) -> bool:
    """Check if an image with this hash already exists."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM looks WHERE image_hash = ? LIMIT 1", (image_hash,)
        ).fetchone()
        return row is not None


def get_show_stats() -> dict:
    """Return aggregate counts for the dashboard."""
    with _connect() as conn:
        shows = conn.execute("SELECT COUNT(*) FROM shows").fetchone()[0]
        looks = conn.execute("SELECT COUNT(*) FROM looks").fetchone()[0]
        images = conn.execute("SELECT COUNT(*) FROM looks WHERE local_path IS NOT NULL").fetchone()[0]
        seasons = conn.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
        fashion_weeks = conn.execute("SELECT COUNT(*) FROM fashion_weeks").fetchone()[0]
    return {
        "shows": shows,
        "looks": looks,
        "images": images,
        "seasons": seasons,
        "fashion_weeks": fashion_weeks,
    }


def get_recent_shows(limit: int = 20) -> list[dict]:
    """Return recent shows with season and fashion week info."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT s.id, s.designer, s.designer_slug, s.source_url, s.look_count,
                      s.show_date, s.created_at,
                      se.code as season_code,
                      fw.name as fashion_week_name
               FROM shows s
               LEFT JOIN seasons se ON se.id = s.season_id
               LEFT JOIN fashion_weeks fw ON fw.id = s.fashion_week_id
               ORDER BY s.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_looks_for_show(show_id: int) -> list[dict]:
    """Return all looks for a show, ordered by look number."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, look_number, image_url, local_path, image_hash,
                      cv_processed, claude_processed
               FROM looks WHERE show_id = ?
               ORDER BY look_number""",
            (show_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_season_by_code(code: str) -> dict | None:
    """Lookup a season by its code (e.g. 'FW25')."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM seasons WHERE code = ?", (code,)
        ).fetchone()
    return dict(row) if row else None


def get_fashion_week_by_key(key: str) -> dict | None:
    """Lookup a fashion week by its config key (e.g. 'paris')."""
    fw = FASHION_WEEKS.get(key)
    if not fw:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM fashion_weeks WHERE code = ?", (fw["code"],)
        ).fetchone()
    return dict(row) if row else None


def update_show_look_count(show_id: int, count: int) -> None:
    """Update the look_count on a show."""
    with _connect() as conn:
        conn.execute(
            "UPDATE shows SET look_count = ? WHERE id = ?",
            (count, show_id),
        )


def get_looks_per_season() -> list[dict]:
    """Return look counts grouped by season code for charting."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT se.code as season_code, COUNT(l.id) as look_count
               FROM looks l
               JOIN shows s ON s.id = l.show_id
               JOIN seasons se ON se.id = s.season_id
               GROUP BY se.code
               ORDER BY se.year, se.period"""
        ).fetchall()
    return [dict(r) for r in rows]


# ── Phase 2 CRUD ──────────────────────────────────────────────────────────────


def migrate_phase2() -> None:
    """Add look_categories column if not present."""
    with _connect() as conn:
        # Check if column already exists
        cols = [r[1] for r in conn.execute("PRAGMA table_info(looks)").fetchall()]
        if "look_categories" not in cols:
            conn.execute("ALTER TABLE looks ADD COLUMN look_categories TEXT")
            logger.info("Added look_categories column to looks table")
        else:
            logger.info("look_categories column already exists")


def get_unprocessed_looks(season_code: str) -> list[dict]:
    """Return looks not yet CV-processed for a given season."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT l.id, l.look_number, l.local_path, l.image_url,
                      s.designer, s.designer_slug, se.code as season_code
               FROM looks l
               JOIN shows s ON s.id = l.show_id
               JOIN seasons se ON se.id = s.season_id
               WHERE se.code = ? AND l.cv_processed = 0 AND l.local_path IS NOT NULL
               ORDER BY s.id, l.look_number""",
            (season_code,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_unprocessed_looks_for_show(show_id: int) -> list[dict]:
    """Return looks not yet CV-processed for a single show."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT l.id, l.look_number, l.local_path, l.image_url,
                      s.designer, s.designer_slug
               FROM looks l
               JOIN shows s ON s.id = l.show_id
               WHERE l.show_id = ? AND l.cv_processed = 0 AND l.local_path IS NOT NULL
               ORDER BY l.look_number""",
            (show_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_garment_attributes(look_id: int, detections: list[dict]) -> None:
    """Save detected garment attributes for a look."""
    with _connect() as conn:
        for det in detections:
            conn.execute(
                """INSERT INTO garment_attributes
                   (look_id, garment_type, bbox_json, confidence,
                    color_name, color_hex, color_lab_json, palette_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    look_id,
                    det["label"],
                    json.dumps(det["bbox"]),
                    det["score"],
                    det.get("color_name"),
                    det.get("color_hex"),
                    json.dumps(det.get("color_lab")) if det.get("color_lab") else None,
                    json.dumps(det.get("palette")) if det.get("palette") else None,
                    _now(),
                ),
            )


def update_look_categories(look_id: int, categories: list[str]) -> None:
    """Set the look_categories JSON array on a look."""
    with _connect() as conn:
        conn.execute(
            "UPDATE looks SET look_categories = ? WHERE id = ?",
            (json.dumps(categories), look_id),
        )


def mark_look_cv_processed(look_id: int) -> None:
    """Mark a look as CV-processed."""
    with _connect() as conn:
        conn.execute(
            "UPDATE looks SET cv_processed = 1 WHERE id = ?",
            (look_id,),
        )


def get_detection_stats() -> dict:
    """Return garment detection statistics."""
    with _connect() as conn:
        total_detections = conn.execute("SELECT COUNT(*) FROM garment_attributes").fetchone()[0]

        type_counts = conn.execute(
            """SELECT garment_type, COUNT(*) as cnt
               FROM garment_attributes
               GROUP BY garment_type
               ORDER BY cnt DESC"""
        ).fetchall()

        cv_processed = conn.execute(
            "SELECT COUNT(*) FROM looks WHERE cv_processed = 1"
        ).fetchone()[0]

        total_looks = conn.execute("SELECT COUNT(*) FROM looks").fetchone()[0]

        # Category counts from look_categories
        cat_rows = conn.execute(
            "SELECT look_categories FROM looks WHERE look_categories IS NOT NULL"
        ).fetchall()
        cat_counts: dict[str, int] = {}
        for row in cat_rows:
            cats = json.loads(row[0])
            for c in cats:
                cat_counts[c] = cat_counts.get(c, 0) + 1

    return {
        "total_detections": total_detections,
        "cv_processed": cv_processed,
        "total_looks": total_looks,
        "garment_types": {r[0]: r[1] for r in type_counts},
        "categories": cat_counts,
    }


def get_suit_blazer_looks(season_code: str) -> list[dict]:
    """Return suit/blazer looks for a season (for Claude batch analysis)."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT l.id, l.look_number, l.local_path, l.look_categories,
                      s.designer, s.designer_slug, se.code as season_code
               FROM looks l
               JOIN shows s ON s.id = l.show_id
               JOIN seasons se ON se.id = s.season_id
               WHERE se.code = ?
                 AND l.cv_processed = 1
                 AND l.claude_processed = 0
                 AND l.look_categories IS NOT NULL
                 AND (l.look_categories LIKE '%suit%' OR l.look_categories LIKE '%blazer%')
               ORDER BY s.id, l.look_number""",
            (season_code,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_look_analysis(look_id: int, analysis: dict) -> None:
    """Save Claude analysis results for a look."""
    with _connect() as conn:
        # Build suiting details subset
        suiting_keys = [
            "lapel_style", "lapel_width", "gorge_height", "button_stance",
            "button_count", "shoulder_construction", "vent_style",
        ]
        suiting_details = {k: analysis.get(k) for k in suiting_keys if k in analysis}

        conn.execute(
            """INSERT OR REPLACE INTO look_analysis
               (look_id, styling_notes, mood, designer_intent, construction,
                suiting_details_json, raw_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                look_id,
                analysis.get("styling_notes"),
                analysis.get("mood"),
                analysis.get("designer_intent"),
                analysis.get("construction"),
                json.dumps(suiting_details) if suiting_details else None,
                json.dumps(analysis),
                _now(),
            ),
        )
        conn.execute(
            "UPDATE looks SET claude_processed = 1 WHERE id = ?",
            (look_id,),
        )


# ── Phase 4 CRUD ──────────────────────────────────────────────────────────────


def get_analyzed_looks_for_season(season_code: str) -> list[dict]:
    """Return all look_analysis rows (with raw_json) for a season."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT la.id, la.look_id, la.mood, la.raw_json
               FROM look_analysis la
               JOIN looks l ON l.id = la.look_id
               JOIN shows s ON s.id = l.show_id
               JOIN seasons se ON se.id = s.season_id
               WHERE se.code = ? AND la.raw_json IS NOT NULL
               ORDER BY la.id""",
            (season_code,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_trend_snapshots(season_id: int, snapshots: list[dict]) -> int:
    """Bulk-insert trend snapshot rows. Returns count inserted."""
    now = _now()
    with _connect() as conn:
        for snap in snapshots:
            conn.execute(
                """INSERT INTO trend_snapshots
                   (season_id, attribute_type, attribute_value, frequency, total_looks, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (season_id, snap["attribute_type"], snap["attribute_value"],
                 snap["frequency"], snap["total_looks"], now),
            )
    return len(snapshots)


def get_trend_snapshots(season_code: str) -> list[dict]:
    """Return all trend_snapshot rows for a season."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT ts.*
               FROM trend_snapshots ts
               JOIN seasons se ON se.id = ts.season_id
               WHERE se.code = ?
               ORDER BY ts.attribute_type, ts.frequency DESC""",
            (season_code,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_trend_snapshots(season_code: str) -> int:
    """Delete all trend_snapshot rows for a season. Returns count deleted."""
    with _connect() as conn:
        season = conn.execute(
            "SELECT id FROM seasons WHERE code = ?", (season_code,)
        ).fetchone()
        if not season:
            return 0
        cur = conn.execute(
            "DELETE FROM trend_snapshots WHERE season_id = ?",
            (season["id"],),
        )
        return cur.rowcount


# ── Claude color family mapping ──────────────────────────────────────────────
# Maps free-text color_primary values to normalized color families via keywords.
CLAUDE_COLOR_FAMILIES = {
    "Black":      ["black", "noir"],
    "Navy":       ["navy", "indigo"],
    "Charcoal":   ["charcoal", "slate"],
    "Grey":       ["grey", "gray", "heather"],
    "White":      ["white"],
    "Cream/Ivory":["cream", "ivory", "ecru", "off-white", "oatmeal"],
    "Beige/Sand": ["beige", "sand", "stone", "greige"],
    "Camel/Tan":  ["camel", "tan", "khaki", "cognac"],
    "Brown":      ["brown", "chocolate", "tobacco", "amber"],
    "Burgundy":   ["burgundy", "oxblood", "aubergine", "plum", "wine", "maroon"],
    "Red":        ["red", "crimson", "coral", "scarlet"],
    "Orange/Rust":["orange", "rust", "terracotta", "burnt"],
    "Yellow/Gold":["yellow", "gold", "mustard", "ochre", "chartreuse"],
    "Green":      ["green", "olive", "sage", "forest", "teal", "emerald", "mint"],
    "Blue":       ["blue", "cobalt", "cyan", "periwinkle", "powder", "denim"],
    "Purple":     ["purple", "lavender", "lilac", "mauve", "violet"],
    "Pink":       ["pink", "rose", "blush", "salmon", "fuchsia"],
    "Metallic":   ["metallic", "silver", "iridescent"],
    "Multi":      ["multi", "patchwork", "print"],
    "Taupe":      ["taupe"],
}


def classify_claude_color(color_text: str) -> str:
    """Map a free-text Claude color_primary value to a color family."""
    if not color_text:
        return "Unknown"
    lower = color_text.lower()
    for family, keywords in CLAUDE_COLOR_FAMILIES.items():
        for kw in keywords:
            if kw in lower:
                return family
    return "Other"


def get_filter_options() -> dict:
    """Return all distinct values for each filterable field."""
    with _connect() as conn:
        seasons = [r[0] for r in conn.execute(
            """SELECT DISTINCT se.code FROM seasons se
               JOIN shows s ON s.season_id = se.id
               JOIN looks l ON l.show_id = s.id
               ORDER BY se.year, se.period"""
        ).fetchall()]

        fashion_weeks = [r[0] for r in conn.execute(
            """SELECT DISTINCT fw.name FROM fashion_weeks fw
               JOIN shows s ON s.fashion_week_id = fw.id
               ORDER BY fw.name"""
        ).fetchall()]

        designers = [r[0] for r in conn.execute(
            """SELECT DISTINCT s.designer FROM shows s
               JOIN looks l ON l.show_id = s.id
               ORDER BY s.designer"""
        ).fetchall()]

        colors = [r[0] for r in conn.execute(
            """SELECT DISTINCT color_name FROM garment_attributes
               WHERE color_name IS NOT NULL ORDER BY color_name"""
        ).fetchall()]

        garment_types = [r[0] for r in conn.execute(
            """SELECT DISTINCT garment_type FROM garment_attributes
               ORDER BY garment_type"""
        ).fetchall()]

    return {
        "seasons": seasons,
        "fashion_weeks": fashion_weeks,
        "designers": designers,
        "colors": colors,
        "garment_types": garment_types,
    }


def get_filtered_looks(filters: dict, analyzed_only: bool = True) -> list[dict]:
    """Return looks matching all provided filters, with analysis + show metadata.

    filters keys (all optional):
        seasons, fashion_weeks, designers — list[str]
        categories — list[str] e.g. ["suit", "blazer"]
        mood_keywords — list[str] (substring match on mood)
        colors — list[str] (color_name in garment_attributes)
        garment_types — list[str]
        lapel_style, lapel_width, gorge_height, button_stance,
        shoulder_construction, vent_style, construction,
        fabric_material, fabric_weight, fabric_texture, fabric_pattern,
        fit, length — list[str] (values from raw_json)
        button_count — list[int]
    analyzed_only: if True, only return looks with analysis data.
                   if False, return all looks (LEFT JOIN analysis).
    """
    clauses = []
    params: list = []

    la_join = "JOIN" if analyzed_only else "LEFT JOIN"
    base = f"""
        SELECT DISTINCT l.id, l.look_number, l.local_path, l.image_url, l.look_categories,
               s.designer, se.code as season_code, fw.name as fashion_week_name,
               la.mood, la.designer_intent, la.styling_notes, la.construction,
               la.raw_json
        FROM looks l
        JOIN shows s ON s.id = l.show_id
        JOIN seasons se ON se.id = s.season_id
        LEFT JOIN fashion_weeks fw ON fw.id = s.fashion_week_id
        {la_join} look_analysis la ON la.look_id = l.id
    """

    # Only show looks with images
    clauses.append("l.local_path IS NOT NULL")

    # Join garment_attributes only if color/garment filters are active
    needs_ga = any(filters.get(k) for k in ("colors", "garment_types"))
    if needs_ga:
        base += " JOIN garment_attributes ga ON ga.look_id = l.id"

    if filters.get("seasons"):
        placeholders = ",".join("?" * len(filters["seasons"]))
        clauses.append(f"se.code IN ({placeholders})")
        params.extend(filters["seasons"])

    if filters.get("fashion_weeks"):
        placeholders = ",".join("?" * len(filters["fashion_weeks"]))
        clauses.append(f"fw.name IN ({placeholders})")
        params.extend(filters["fashion_weeks"])

    if filters.get("designers"):
        placeholders = ",".join("?" * len(filters["designers"]))
        clauses.append(f"s.designer IN ({placeholders})")
        params.extend(filters["designers"])

    if filters.get("categories"):
        cat_clauses = []
        for cat in filters["categories"]:
            cat_clauses.append("l.look_categories LIKE ?")
            params.append(f"%{cat}%")
        clauses.append(f"({' OR '.join(cat_clauses)})")

    if filters.get("mood_keywords"):
        mood_clauses = []
        for kw in filters["mood_keywords"]:
            mood_clauses.append("LOWER(la.mood) LIKE ?")
            params.append(f"%{kw}%")
        clauses.append(f"({' OR '.join(mood_clauses)})")

    if filters.get("colors"):
        placeholders = ",".join("?" * len(filters["colors"]))
        clauses.append(f"ga.color_name IN ({placeholders})")
        params.extend(filters["colors"])

    if filters.get("claude_colors"):
        # Expand color families to keyword LIKE matches on color_primary in raw_json
        color_clauses = []
        for family in filters["claude_colors"]:
            keywords = CLAUDE_COLOR_FAMILIES.get(family, [])
            for kw in keywords:
                color_clauses.append("LOWER(json_extract(la.raw_json, '$.color_primary')) LIKE ?")
                params.append(f"%{kw}%")
        if color_clauses:
            clauses.append(f"({' OR '.join(color_clauses)})")

    if filters.get("garment_types"):
        placeholders = ",".join("?" * len(filters["garment_types"]))
        clauses.append(f"ga.garment_type IN ({placeholders})")
        params.extend(filters["garment_types"])

    # Suiting detail filters from raw_json
    json_fields = [
        "lapel_style", "lapel_width", "gorge_height", "button_stance",
        "shoulder_construction", "vent_style", "construction",
        "fabric_material", "fabric_weight", "fabric_texture", "fabric_pattern",
        "fit", "length",
    ]
    for field in json_fields:
        vals = filters.get(field)
        if vals:
            json_clauses = []
            for v in vals:
                json_clauses.append(f"json_extract(la.raw_json, '$.{field}') = ?")
                params.append(v)
            clauses.append(f"({' OR '.join(json_clauses)})")

    if filters.get("button_count"):
        placeholders = ",".join("?" * len(filters["button_count"]))
        clauses.append(f"CAST(json_extract(la.raw_json, '$.button_count') AS INTEGER) IN ({placeholders})")
        params.extend(filters["button_count"])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    query = base + where + " ORDER BY se.code, s.designer, l.look_number"

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_color_data_for_season(season_code: str) -> list[dict]:
    """Return garment_attributes color data for jacket/coat garments in a season."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT ga.color_name, ga.color_hex
               FROM garment_attributes ga
               JOIN looks l ON l.id = ga.look_id
               JOIN shows s ON s.id = l.show_id
               JOIN seasons se ON se.id = s.season_id
               WHERE se.code = ?
                 AND ga.garment_type IN ('jacket', 'coat')
                 AND ga.color_name IS NOT NULL
               ORDER BY ga.id""",
            (season_code,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_trend_directions(season_id: int, compared_to_season_id: int,
                            updates: list[dict]) -> int:
    """Update direction + change_pct on trend_snapshot rows."""
    with _connect() as conn:
        for u in updates:
            conn.execute(
                """UPDATE trend_snapshots
                   SET direction = ?, change_pct = ?, compared_to_season_id = ?
                   WHERE season_id = ? AND attribute_type = ? AND attribute_value = ?""",
                (u["direction"], u["change_pct"], compared_to_season_id,
                 season_id, u["attribute_type"], u["attribute_value"]),
            )
    return len(updates)
