from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from config import IMAGE_DIR, IMAGE_DOWNLOAD_WORKERS, IMAGE_DOWNLOAD_TIMEOUT
from storage.database import update_look_local_path, look_hash_exists

logger = logging.getLogger(__name__)


class ImageStore:
    """Download and deduplicate runway images with SHA256 hashing."""

    def __init__(self, workers: int = IMAGE_DOWNLOAD_WORKERS):
        self.workers = workers

    def _build_path(self, season_code: str, designer_slug: str, look_number: int) -> Path:
        """Build: data/images/{season}/{designer}/{look:03d}.jpg"""
        path = IMAGE_DIR / season_code / designer_slug
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{look_number:03d}.jpg"

    def _download_one(
        self,
        image_url: str,
        look_id: int,
        season_code: str,
        designer_slug: str,
        look_number: int,
    ) -> bool:
        """Download a single image. Returns True if saved, False if skipped/failed."""
        try:
            resp = requests.get(image_url, timeout=IMAGE_DOWNLOAD_TIMEOUT, stream=True)
            resp.raise_for_status()

            content = resp.content
            image_hash = hashlib.sha256(content).hexdigest()

            if look_hash_exists(image_hash):
                logger.debug("Skipping duplicate image (hash %s): %s", image_hash[:12], image_url)
                return False

            local_path = self._build_path(season_code, designer_slug, look_number)
            local_path.write_bytes(content)

            rel_path = str(local_path.relative_to(IMAGE_DIR.parent.parent))
            update_look_local_path(look_id, rel_path, image_hash)

            logger.info("Downloaded look %d: %s", look_number, local_path.name)
            return True

        except requests.RequestException as exc:
            logger.warning("Failed to download %s: %s", image_url, type(exc).__name__)
            return False

    def download_batch(
        self,
        items: list[dict],
        season_code: str,
        designer_slug: str,
    ) -> dict:
        """
        Download a batch of images in parallel.

        Each item in `items` should have: look_id, look_number, image_url

        Returns {"downloaded": int, "skipped": int, "failed": int}
        """
        stats = {"downloaded": 0, "skipped": 0, "failed": 0}

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {}
            for item in items:
                future = executor.submit(
                    self._download_one,
                    item["image_url"],
                    item["look_id"],
                    season_code,
                    designer_slug,
                    item["look_number"],
                )
                futures[future] = item

            for future in as_completed(futures):
                result = future.result()
                if result is True:
                    stats["downloaded"] += 1
                elif result is False:
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1

        return stats
