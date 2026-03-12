"""K-means color extraction from garment bounding box crops."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from PIL import Image
from sklearn.cluster import MiniBatchKMeans
from skimage import color as skcolor

from config import COLOR_CLUSTER_K

logger = logging.getLogger(__name__)

# Named color map — representative colors for fashion garments
_COLOR_NAMES = {
    "black":      (0, 0, 0),
    "white":      (255, 255, 255),
    "navy":       (0, 0, 128),
    "charcoal":   (54, 69, 79),
    "grey":       (128, 128, 128),
    "light grey": (192, 192, 192),
    "tan":        (210, 180, 140),
    "beige":      (245, 245, 220),
    "camel":      (193, 154, 107),
    "brown":      (101, 67, 33),
    "burgundy":   (128, 0, 32),
    "olive":      (85, 107, 47),
    "forest green": (34, 139, 34),
    "teal":       (0, 128, 128),
    "royal blue": (65, 105, 225),
    "powder blue": (176, 224, 230),
    "red":        (220, 20, 60),
    "pink":       (255, 182, 193),
    "lavender":   (186, 147, 216),
    "cream":      (255, 253, 208),
    "ivory":      (255, 255, 240),
    "gold":       (212, 175, 55),
    "rust":       (183, 65, 14),
    "coral":      (255, 127, 80),
}


def _nearest_color_name(rgb: tuple[int, int, int]) -> str:
    """Find the closest named color by Euclidean distance."""
    best_name = "unknown"
    best_dist = float("inf")
    for name, ref in _COLOR_NAMES.items():
        dist = sum((a - b) ** 2 for a, b in zip(rgb, ref)) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _rgb_to_lab(rgb: tuple[int, int, int]) -> list[float]:
    """Convert single RGB to CIELAB."""
    arr = np.array([[rgb]], dtype=np.float64) / 255.0
    lab = skcolor.rgb2lab(arr)[0][0]
    return [round(float(v), 2) for v in lab]


def extract_colors(
    image: Image.Image,
    bbox: list[float],
    k: int | None = None,
) -> dict[str, Any]:
    """Extract dominant color + palette from a bounding box crop.

    Args:
        image: full PIL image
        bbox: [x1, y1, x2, y2] bounding box
        k: number of clusters (default from config)

    Returns:
        dict with keys: dominant_hex, dominant_name, dominant_lab, palette
    """
    k = k or COLOR_CLUSTER_K
    x1, y1, x2, y2 = [int(c) for c in bbox]
    crop = image.crop((x1, y1, x2, y2))

    # Downsample for speed
    crop.thumbnail((128, 128))
    pixels = np.array(crop).reshape(-1, 3)

    if len(pixels) < k:
        k = max(1, len(pixels))

    kmeans = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=3, batch_size=256)
    kmeans.fit(pixels)

    # Sort clusters by frequency (most common first)
    labels, counts = np.unique(kmeans.labels_, return_counts=True)
    order = np.argsort(-counts)

    palette = []
    for idx in order:
        center = kmeans.cluster_centers_[labels[idx]]
        rgb = tuple(int(c) for c in center)
        palette.append({
            "hex": _rgb_to_hex(rgb),
            "name": _nearest_color_name(rgb),
            "lab": _rgb_to_lab(rgb),
            "pct": round(float(counts[idx]) / len(pixels) * 100, 1),
        })

    dominant = palette[0]
    return {
        "dominant_hex": dominant["hex"],
        "dominant_name": dominant["name"],
        "dominant_lab": dominant["lab"],
        "palette": palette,
    }
