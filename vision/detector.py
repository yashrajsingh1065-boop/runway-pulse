"""Pipeline orchestrator: detect garments → categorize → extract color → persist."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PIL import Image
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from vision.fashionpedia import detect
from vision.category_mapper import derive_look_categories
from vision.color_extractor import extract_colors
from storage.database import (
    get_unprocessed_looks,
    get_unprocessed_looks_for_show,
    save_garment_attributes,
    update_look_categories,
    mark_look_cv_processed,
)

logger = logging.getLogger(__name__)


def process_look(look: dict) -> dict:
    """Run full CV pipeline on a single look.

    Args:
        look: dict with keys id, local_path

    Returns:
        dict with keys: look_id, detections, categories
    """
    look_id = look["id"]
    local_path = look["local_path"]

    if not local_path or not Path(local_path).exists():
        logger.warning("Look %d: no local image at %s", look_id, local_path)
        mark_look_cv_processed(look_id)
        return {"look_id": look_id, "detections": [], "categories": []}

    image = Image.open(local_path).convert("RGB")

    # Step 1: detect garments
    detections = detect(image)

    # Step 2: extract color for each detection
    for det in detections:
        color_data = extract_colors(image, det["bbox"])
        det["color_hex"] = color_data["dominant_hex"]
        det["color_name"] = color_data["dominant_name"]
        det["color_lab"] = color_data["dominant_lab"]
        det["palette"] = color_data["palette"]

    # Step 3: derive categories
    categories = derive_look_categories(detections)

    # Step 4: persist
    save_garment_attributes(look_id, detections)
    if categories:
        update_look_categories(look_id, categories)
    mark_look_cv_processed(look_id)

    return {"look_id": look_id, "detections": detections, "categories": categories}


def process_season(season_code: str) -> dict:
    """Process all unprocessed looks for a season."""
    looks = get_unprocessed_looks(season_code)
    return _process_batch(looks, label=f"Season {season_code}")


def process_show(show_id: int) -> dict:
    """Process all unprocessed looks for a single show."""
    looks = get_unprocessed_looks_for_show(show_id)
    return _process_batch(looks, label=f"Show #{show_id}")


def _process_batch(looks: list[dict], label: str) -> dict:
    """Process a batch of looks with progress bar."""
    total = len(looks)
    if total == 0:
        logger.info("%s: no unprocessed looks found", label)
        return {"processed": 0, "detections": 0, "suit": 0, "blazer": 0, "overcoat": 0}

    logger.info("%s: processing %d looks", label, total)

    stats = {"processed": 0, "detections": 0, "suit": 0, "blazer": 0, "overcoat": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task(f"[cyan]{label}", total=total)

        for look in looks:
            result = process_look(look)
            stats["processed"] += 1
            stats["detections"] += len(result["detections"])
            for cat in result["categories"]:
                if cat in stats:
                    stats[cat] += 1
            progress.advance(task)

    return stats
