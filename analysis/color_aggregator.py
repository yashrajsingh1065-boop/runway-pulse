"""Color normalization and hex lookup for trend aggregation."""

from __future__ import annotations

# Canonical color names → representative hex values
COLOR_HEX_MAP = {
    "black": "#1a1a1a",
    "charcoal": "#36454f",
    "dark grey": "#555555",
    "grey": "#808080",
    "light grey": "#b0b0b0",
    "silver": "#c0c0c0",
    "white": "#f5f5f5",
    "off-white": "#faf0e6",
    "cream": "#fffdd0",
    "ivory": "#fffff0",
    "beige": "#d4be9c",
    "tan": "#d2b48c",
    "camel": "#c19a6b",
    "brown": "#6b4226",
    "dark brown": "#3b2010",
    "chocolate": "#3b1e08",
    "cognac": "#9a463d",
    "burgundy": "#6c1d35",
    "maroon": "#5c1528",
    "wine": "#722f37",
    "red": "#cc2020",
    "dark red": "#8b0000",
    "rust": "#b7410e",
    "terracotta": "#cc6644",
    "orange": "#e07020",
    "burnt orange": "#cc5500",
    "mustard": "#c4a000",
    "gold": "#c9a84c",
    "yellow": "#e0c040",
    "olive": "#6b7531",
    "dark green": "#1b4d2e",
    "forest green": "#228b22",
    "green": "#2d7c2d",
    "sage": "#8a9a5b",
    "khaki": "#bdb76b",
    "teal": "#008080",
    "navy": "#1b2a4a",
    "dark navy": "#0c1428",
    "dark blue": "#1a2f5a",
    "blue": "#2c5f9e",
    "medium blue": "#4682b4",
    "light blue": "#7eb8da",
    "sky blue": "#87ceeb",
    "powder blue": "#b0d4e8",
    "cobalt": "#0047ab",
    "royal blue": "#2050a0",
    "indigo": "#3b0082",
    "purple": "#6a3d8a",
    "lavender": "#b08fc7",
    "plum": "#5c2d50",
    "mauve": "#b08a9a",
    "pink": "#e090a0",
    "blush": "#dca0a0",
    "coral": "#e07060",
    "peach": "#f0b090",
    "nude": "#d4a68c",
    "taupe": "#8b7e6e",
    "slate": "#6a7b8b",
    "steel": "#71797e",
    "pewter": "#8e9196",
    "medium grey": "#999999",
}


def normalize_color(raw_color: str | None) -> str | None:
    """Normalize a free-text color string to a canonical name.

    Strips whitespace, lowercases, and matches against known canonical names.
    Returns the canonical name if found, otherwise the cleaned raw string.
    """
    if not raw_color:
        return None

    cleaned = raw_color.strip().lower()
    if not cleaned or cleaned == "null" or cleaned == "none":
        return None

    # Exact match
    if cleaned in COLOR_HEX_MAP:
        return cleaned

    # Substring match — find the best (longest matching) canonical name
    best_match = None
    best_len = 0
    for canonical in COLOR_HEX_MAP:
        if canonical in cleaned and len(canonical) > best_len:
            best_match = canonical
            best_len = len(canonical)

    return best_match or cleaned


def get_hex(color_name: str | None) -> str:
    """Return hex code for a canonical color name, or a neutral grey for unknowns."""
    if not color_name:
        return "#808080"
    return COLOR_HEX_MAP.get(color_name, "#808080")
