"""Download images for looks already in the database (no re-scraping needed)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import get_looks_for_show, get_recent_shows, get_season_by_code
from ingestion.image_store import ImageStore

logger = logging.getLogger(__name__)


def download_images_for_season(season_code: str) -> dict:
    """Download all missing images for shows in a given season."""
    from storage.database import _connect

    season = get_season_by_code(season_code)
    if not season:
        logger.error("Season %s not found", season_code)
        return {"downloaded": 0, "skipped": 0, "failed": 0}

    store = ImageStore()
    totals = {"downloaded": 0, "skipped": 0, "failed": 0}

    with _connect() as conn:
        shows = conn.execute(
            """SELECT s.id, s.designer, s.designer_slug, se.code as season_code
               FROM shows s
               JOIN seasons se ON se.id = s.season_id
               WHERE s.season_id = ?""",
            (season["id"],),
        ).fetchall()

    for show in shows:
        looks = get_looks_for_show(show["id"])
        pending = [
            {"look_id": l["id"], "look_number": l["look_number"], "image_url": l["image_url"]}
            for l in looks
            if l["image_url"] and not l["local_path"]
        ]
        if not pending:
            continue

        logger.info("%s: %d images to download", show["designer"], len(pending))
        stats = store.download_batch(pending, show["season_code"], show["designer_slug"])
        for k in totals:
            totals[k] += stats[k]
        logger.info(
            "%s: %d downloaded, %d skipped, %d failed",
            show["designer"], stats["downloaded"], stats["skipped"], stats["failed"],
        )

    return totals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    code = sys.argv[1] if len(sys.argv) > 1 else "FW25"
    result = download_images_for_season(code)
    print(f"\nDone: {result['downloaded']} downloaded, {result['skipped']} skipped, {result['failed']} failed")
