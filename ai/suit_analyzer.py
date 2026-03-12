"""Claude Batch API analyzer for suit/blazer looks."""

from __future__ import annotations

import json
import base64
import logging
from pathlib import Path

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_SUIT_SYSTEM,
    CLAUDE_SUIT_MAX_TOKENS,
    CLAUDE_TEMPERATURE,
)
from storage.database import get_suit_blazer_looks, save_look_analysis

logger = logging.getLogger(__name__)


def _build_batch_requests(looks: list[dict]) -> list[dict]:
    """Build Batch API request objects for each look."""
    requests = []
    for look in looks:
        local_path = look["local_path"]
        if not local_path or not Path(local_path).exists():
            logger.warning("Look %d: no local image, skipping batch", look["id"])
            continue

        # Read and base64 encode the image
        image_data = Path(local_path).read_bytes()
        b64 = base64.standard_b64encode(image_data).decode("utf-8")

        # Determine media type
        suffix = Path(local_path).suffix.lower()
        media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        media_type = media_types.get(suffix, "image/jpeg")

        designer = look.get("designer", "Unknown")
        season = look.get("season_code", "Unknown")
        categories = look.get("look_categories", "")

        requests.append({
            "custom_id": f"look-{look['id']}",
            "params": {
                "model": CLAUDE_MODEL,
                "max_tokens": CLAUDE_SUIT_MAX_TOKENS,
                "temperature": CLAUDE_TEMPERATURE,
                "system": CLAUDE_SUIT_SYSTEM,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"Designer: {designer}\n"
                                    f"Season: {season}\n"
                                    f"Look #{look.get('look_number', '?')}\n"
                                    f"CV categories: {categories}\n\n"
                                    "Analyze this runway look. Return JSON only."
                                ),
                            },
                        ],
                    }
                ],
            },
        })

    return requests


def submit_batch(season_code: str) -> str | None:
    """Submit a Claude Batch API request for all suit/blazer looks in a season.

    Returns the batch ID or None if no looks to process.
    """
    looks = get_suit_blazer_looks(season_code)
    if not looks:
        logger.info("No suit/blazer looks found for %s", season_code)
        return None

    logger.info("Building batch for %d suit/blazer looks in %s", len(looks), season_code)
    requests = _build_batch_requests(looks)
    if not requests:
        logger.warning("No valid images for batch submission")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    batch = client.messages.batches.create(requests=requests)

    logger.info("Batch submitted: %s (%d requests)", batch.id, len(requests))
    return batch.id


def check_batch_status(batch_id: str) -> dict:
    """Check the status of a batch."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    batch = client.messages.batches.retrieve(batch_id)
    return {
        "id": batch.id,
        "processing_status": batch.processing_status,
        "request_counts": {
            "processing": batch.request_counts.processing,
            "succeeded": batch.request_counts.succeeded,
            "errored": batch.request_counts.errored,
            "canceled": batch.request_counts.canceled,
            "expired": batch.request_counts.expired,
        },
    }


def fetch_batch_results(batch_id: str) -> dict:
    """Fetch results from a completed batch and save to DB.

    Returns stats dict with counts.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Check status first
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        return {"status": batch.processing_status, "saved": 0, "errors": 0}

    saved = 0
    errors = 0

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id  # "look-{id}"
        look_id = int(custom_id.split("-", 1)[1])

        if result.result.type != "succeeded":
            logger.warning("Look %d: batch result type=%s", look_id, result.result.type)
            errors += 1
            continue

        message = result.result.message
        text = ""
        for block in message.content:
            if block.type == "text":
                text += block.text

        try:
            analysis = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from potential markdown wrapping
            stripped = text.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                json_lines = [l for l in lines if not l.startswith("```")]
                try:
                    analysis = json.loads("\n".join(json_lines))
                except json.JSONDecodeError:
                    logger.error("Look %d: failed to parse JSON response", look_id)
                    errors += 1
                    continue
            else:
                logger.error("Look %d: failed to parse JSON response", look_id)
                errors += 1
                continue

        save_look_analysis(look_id, analysis)
        saved += 1

    return {"status": "ended", "saved": saved, "errors": errors}


def list_batches() -> list[dict]:
    """List recent batches."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    batches = client.messages.batches.list(limit=10)
    return [
        {
            "id": b.id,
            "processing_status": b.processing_status,
            "created_at": b.created_at if hasattr(b, "created_at") else "unknown",
            "request_counts": {
                "processing": b.request_counts.processing,
                "succeeded": b.request_counts.succeeded,
                "errored": b.request_counts.errored,
            },
        }
        for b in batches.data
    ]
