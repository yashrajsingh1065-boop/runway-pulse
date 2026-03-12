"""Keyword-based mood → archetype classification."""

from __future__ import annotations

from config import MOOD_ARCHETYPES


def classify_mood(mood: str | None) -> str:
    """Map a free-text mood descriptor to one of ~14 archetypes.

    Uses substring matching on lowercase mood text.
    Most keyword hits wins; ties broken by dict insertion order.
    Returns 'other' if no keywords match.
    """
    if not mood:
        return "other"

    mood_lower = mood.lower()
    best_archetype = "other"
    best_hits = 0

    for archetype, keywords in MOOD_ARCHETYPES.items():
        hits = sum(1 for kw in keywords if kw in mood_lower)
        if hits > best_hits:
            best_hits = hits
            best_archetype = archetype

    return best_archetype
