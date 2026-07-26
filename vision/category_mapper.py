"""Map Fashionpedia detections to suit/blazer categories."""

from __future__ import annotations

import math
from config import SUIT_COLOR_MATCH_THRESHOLD


def _avg_color_from_detection(det: dict) -> tuple[int, int, int] | None:
    """Extract average RGB color from a detection's color_hex."""
    hex_val = det.get("color_hex")
    if not hex_val or len(hex_val) != 7:
        return None
    try:
        r = int(hex_val[1:3], 16)
        g = int(hex_val[3:5], 16)
        b = int(hex_val[5:7], 16)
        return (r, g, b)
    except ValueError:
        return None


def _colors_match(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> bool:
    """Check if two RGB colors are within the Euclidean distance threshold."""
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))
    return dist <= SUIT_COLOR_MATCH_THRESHOLD


def derive_look_categories(detections: list[dict]) -> list[str]:
    """Derive suit/blazer/overcoat categories from a look's detections.

    Args:
        detections: list of dicts with keys: label, label_id, score, bbox, color_hex (optional)

    Returns:
        list of category strings, e.g. ["suit"], ["blazer"], ["suit", "overcoat"]
    """
    categories = []

    jackets = [d for d in detections if d["label"] == "jacket"]
    lapels = [d for d in detections if d["label"] == "lapel"]
    pants_list = [d for d in detections if d["label"] == "pants"]
    coats = [d for d in detections if d["label"] == "coat"]

    has_lapel = len(lapels) > 0

    for jacket in jackets:
        if not has_lapel:
            continue  # jacket without lapel = not a blazer

        # Check for suit: jacket + lapel + matching pants
        is_suit = False
        jacket_color = _avg_color_from_detection(jacket)
        for pants in pants_list:
            pants_color = _avg_color_from_detection(pants)
            if jacket_color and pants_color and _colors_match(jacket_color, pants_color):
                is_suit = True
                break

        if is_suit and "suit" not in categories:
            categories.append("suit")
        elif not is_suit and "blazer" not in categories:
            categories.append("blazer")

    # Coat with lapel = overcoat (stored but not primary focus)
    for coat in coats:
        if has_lapel and "overcoat" not in categories:
            categories.append("overcoat")

    return categories
