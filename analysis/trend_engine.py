"""Core trend aggregation: extract attributes, populate snapshots, direction scoring."""

from __future__ import annotations

import json
import re
import logging
from collections import Counter

from config import TREND_CATEGORICAL_FIELDS, TREND_STABLE_THRESHOLD
from storage.database import (
    get_analyzed_looks_for_season,
    get_season_by_code,
    get_color_data_for_season,
    save_trend_snapshots,
    clear_trend_snapshots,
    get_trend_snapshots,
    update_trend_directions,
)
from analysis.mood_clusters import classify_mood
from analysis.color_aggregator import normalize_color

logger = logging.getLogger(__name__)


def _parse_era(era_ref: str | None) -> list[str]:
    """Extract decade references like '1980s', '1990s' from era_references text."""
    if not era_ref:
        return []
    return re.findall(r"\d{4}s", era_ref)


def extract_season_attributes(season_code: str) -> tuple[dict[str, Counter], int]:
    """Load all raw_json for a season and count attribute frequencies.

    Returns (counters_by_type, total_looks).
    """
    rows = get_analyzed_looks_for_season(season_code)
    total = len(rows)
    if total == 0:
        return {}, 0

    counters: dict[str, Counter] = {}

    # Initialize counters for all attribute types
    for field in TREND_CATEGORICAL_FIELDS:
        counters[field] = Counter()
    counters["mood_archetype"] = Counter()
    counters["era_decade"] = Counter()
    counters["color_claude"] = Counter()

    for row in rows:
        try:
            data = json.loads(row["raw_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        # 16 categorical fields
        for field in TREND_CATEGORICAL_FIELDS:
            val = data.get(field)
            if val is not None:
                counters[field][str(val).lower()] += 1

        # Mood archetype
        mood = data.get("mood") or row.get("mood")
        archetype = classify_mood(mood)
        counters["mood_archetype"][archetype] += 1

        # Era references
        eras = _parse_era(data.get("era_references"))
        for era in eras:
            counters["era_decade"][era] += 1

        # Claude-reported primary color
        color = normalize_color(data.get("color_primary"))
        if color:
            counters["color_claude"][color] += 1

    # CV-detected jacket/coat colors
    cv_colors = get_color_data_for_season(season_code)
    counters["color_cv"] = Counter()
    for c in cv_colors:
        normalized = normalize_color(c["color_name"])
        if normalized:
            counters["color_cv"][normalized] += 1

    return counters, total


def aggregate_season(season_code: str) -> int:
    """Aggregate attributes for a season into trend_snapshots. Idempotent.

    Returns the number of snapshot rows created.
    """
    season = get_season_by_code(season_code)
    if not season:
        raise ValueError(f"Season '{season_code}' not found")

    # Clear existing (idempotent)
    cleared = clear_trend_snapshots(season_code)
    if cleared:
        logger.info(f"Cleared {cleared} existing snapshots for {season_code}")

    counters, total = extract_season_attributes(season_code)
    if total == 0:
        logger.warning(f"No analyzed looks found for {season_code}")
        return 0

    snapshots = []
    for attr_type, counter in counters.items():
        for value, freq in counter.items():
            snapshots.append({
                "attribute_type": attr_type,
                "attribute_value": value,
                "frequency": freq,
                "total_looks": total,
            })

    count = save_trend_snapshots(season["id"], snapshots)
    logger.info(f"Saved {count} trend snapshots for {season_code} ({total} looks)")
    return count


def compare_seasons(current_code: str, previous_code: str) -> list[dict]:
    """Compare two seasons and compute direction scores.

    Updates the trend_snapshots table with direction + change_pct.
    Returns the list of comparison results.
    """
    current_season = get_season_by_code(current_code)
    previous_season = get_season_by_code(previous_code)
    if not current_season or not previous_season:
        raise ValueError(f"Season not found: {current_code} or {previous_code}")

    current_snaps = get_trend_snapshots(current_code)
    previous_snaps = get_trend_snapshots(previous_code)

    if not current_snaps:
        raise ValueError(f"No snapshots for {current_code}. Run aggregate first.")
    if not previous_snaps:
        raise ValueError(f"No snapshots for {previous_code}. Run aggregate first.")

    # Build lookup: (attr_type, attr_value) -> pct
    def _build_pct_map(snaps):
        m = {}
        for s in snaps:
            total = s["total_looks"] or 1
            pct = (s["frequency"] / total) * 100
            m[(s["attribute_type"], s["attribute_value"])] = pct
        return m

    cur_map = _build_pct_map(current_snaps)
    prev_map = _build_pct_map(previous_snaps)

    all_keys = set(cur_map.keys()) | set(prev_map.keys())
    results = []

    for key in all_keys:
        attr_type, attr_value = key
        cur_pct = cur_map.get(key, 0.0)
        prev_pct = prev_map.get(key, 0.0)
        change = cur_pct - prev_pct

        if prev_pct == 0 and cur_pct > 0:
            direction = "new"
        elif cur_pct == 0 and prev_pct > 0:
            direction = "gone"
        elif abs(change) < TREND_STABLE_THRESHOLD:
            direction = "stable"
        elif change > 0:
            direction = "up"
        else:
            direction = "down"

        results.append({
            "attribute_type": attr_type,
            "attribute_value": attr_value,
            "current_pct": round(cur_pct, 1),
            "previous_pct": round(prev_pct, 1),
            "change_pct": round(change, 1),
            "direction": direction,
        })

    # Update DB — only rows in the current season
    updates_for_current = [
        r for r in results if cur_map.get((r["attribute_type"], r["attribute_value"]), 0) > 0
    ]
    # For "gone" values (in previous but not current), insert them with freq=0
    gone_inserts = []
    for r in results:
        if r["direction"] == "gone":
            gone_inserts.append({
                "attribute_type": r["attribute_type"],
                "attribute_value": r["attribute_value"],
                "frequency": 0,
                "total_looks": current_snaps[0]["total_looks"] if current_snaps else 0,
            })

    if gone_inserts:
        from storage.database import save_trend_snapshots
        save_trend_snapshots(current_season["id"], gone_inserts)

    # Now update all directions
    all_updates = []
    for r in results:
        all_updates.append({
            "attribute_type": r["attribute_type"],
            "attribute_value": r["attribute_value"],
            "direction": r["direction"],
            "change_pct": r["change_pct"],
        })

    update_trend_directions(current_season["id"], previous_season["id"], all_updates)
    logger.info(f"Compared {current_code} vs {previous_code}: {len(results)} attributes")

    return results
