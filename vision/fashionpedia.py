"""YOLOS-Fashionpedia model wrapper with lazy singleton loading."""

from __future__ import annotations

import logging
from typing import Any

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForObjectDetection

from config import FASHIONPEDIA_MODEL, CV_DEVICE, CV_CONFIDENCE_MIN

logger = logging.getLogger(__name__)

# Fashionpedia class labels we care about
FASHIONPEDIA_LABELS = {
    0: "shirt",
    4: "jacket",
    5: "vest",
    6: "pants",
    9: "coat",
    16: "tie",
    19: "belt",
    23: "shoe",
    29: "lapel",
}

_model = None
_processor = None
_device = None


def _resolve_device() -> str:
    if CV_DEVICE != "auto":
        return CV_DEVICE
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model():
    global _model, _processor, _device
    if _model is not None:
        return

    _device = _resolve_device()
    logger.info("Loading YOLOS-Fashionpedia on %s ...", _device)

    _processor = AutoImageProcessor.from_pretrained(FASHIONPEDIA_MODEL)
    _model = AutoModelForObjectDetection.from_pretrained(FASHIONPEDIA_MODEL)
    _model.to(_device)
    _model.eval()

    logger.info("Model loaded on %s", _device)


def detect(image: Image.Image, confidence_threshold: float | None = None) -> list[dict[str, Any]]:
    """Run detection on a PIL image. Returns list of {label_id, label, score, bbox}."""
    _load_model()
    threshold = confidence_threshold or CV_CONFIDENCE_MIN

    inputs = _processor(images=image, return_tensors="pt")
    inputs = {k: v.to(_device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = _model(**inputs)

    target_sizes = torch.tensor([image.size[::-1]], device=_device)
    results = _processor.post_process_object_detection(
        outputs, threshold=threshold, target_sizes=target_sizes.tolist()
    )[0]

    detections = []
    for score, label_id, box in zip(
        results["scores"].cpu().tolist(),
        results["labels"].cpu().tolist(),
        results["boxes"].cpu().tolist(),
    ):
        if label_id not in FASHIONPEDIA_LABELS:
            continue
        detections.append({
            "label_id": label_id,
            "label": FASHIONPEDIA_LABELS[label_id],
            "score": round(score, 4),
            "bbox": [round(c, 1) for c in box],  # [x1, y1, x2, y2]
        })

    return detections
