"""Runway Pulse — Streamlit Dashboard"""

import sys
import json
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from storage.database import (
    get_show_stats, get_recent_shows, get_looks_per_season,
    get_looks_for_show, get_filter_options, get_filtered_looks,
    CLAUDE_COLOR_FAMILIES,
)
from config import IMAGE_DIR, MOOD_ARCHETYPES

st.set_page_config(page_title="Runway Pulse", page_icon="👔", layout="wide")


@st.cache_data(ttl=300)
def _cached_filter_options():
    return get_filter_options()

st.title("Runway Pulse")
st.caption("Menswear Trend Analysis Dashboard")

# ── Metric cards ──────────────────────────────────────────────────────────────

stats = get_show_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Shows", stats["shows"])
c2.metric("Looks", stats["looks"])
c3.metric("Downloaded Images", stats["images"])
c4.metric("Seasons", stats["seasons"])

# ── Looks per season chart ────────────────────────────────────────────────────

season_data = get_looks_per_season()
if season_data:
    st.subheader("Looks per Season")
    chart_data = {row["season_code"]: row["look_count"] for row in season_data}
    st.bar_chart(chart_data)
else:
    st.info("No look data yet. Run a scrape to populate the database.")

# ── Recent shows table ────────────────────────────────────────────────────────

st.subheader("Recent Shows")
recent = get_recent_shows(20)
if recent:
    table_data = []
    for show in recent:
        table_data.append({
            "Designer": show["designer"],
            "Season": show["season_code"] or "—",
            "Fashion Week": show["fashion_week_name"] or "—",
            "Looks": show["look_count"] or 0,
        })
    st.dataframe(table_data, use_container_width=True)
else:
    st.info("No shows scraped yet.")

# ── Sidebar filters ──────────────────────────────────────────────────────────

options = _cached_filter_options()

with st.sidebar:
    st.header("Filters")
    analyzed_only = st.toggle("Analyzed looks only", value=False)
    st.caption("Filter looks by any combination")

    # -- Metadata filters --
    st.subheader("Metadata")
    f_seasons = st.multiselect("Season", options["seasons"])
    f_fashion_weeks = st.multiselect("Fashion Week", options["fashion_weeks"])
    f_designers = st.multiselect("Designer", options["designers"])

    # -- Category --
    st.subheader("Category")
    f_categories = st.multiselect("Look Category", ["suit", "blazer", "overcoat"])

    # -- Mood --
    st.subheader("Mood")
    archetype_labels = sorted(k.replace("_", " ").title() for k in MOOD_ARCHETYPES)
    f_mood_archetypes = st.multiselect("Mood Archetype", archetype_labels)

    # Resolve archetype selections to keyword lists
    mood_keywords = []
    for label in f_mood_archetypes:
        key = label.lower().replace(" ", "_")
        mood_keywords.extend(MOOD_ARCHETYPES.get(key, []))

    # -- Color & Garment --
    st.subheader("Garments & Color")
    f_claude_colors = st.multiselect("Color (Claude AI)", sorted(CLAUDE_COLOR_FAMILIES.keys()))
    f_colors = st.multiselect("Color (CV Detection)", options["colors"])
    f_garment_types = st.multiselect("Garment Type", options["garment_types"])

    # -- Suiting Details --
    st.subheader("Suiting Details")

    suiting_options = {
        "lapel_style": ("Lapel Style", ["notch", "peak", "shawl", "none"]),
        "lapel_width": ("Lapel Width", ["slim", "medium", "wide"]),
        "gorge_height": ("Gorge Height", ["low", "medium", "high"]),
        "button_stance": ("Button Stance", ["low", "medium", "high"]),
        "shoulder_construction": ("Shoulder", ["natural", "structured", "padded", "soft"]),
        "vent_style": ("Vent Style", ["single", "double", "ventless"]),
        "construction": ("Construction", ["canvas", "half-canvas", "fused"]),
    }

    suiting_filters = {}
    for field, (label, vals) in suiting_options.items():
        selected = st.multiselect(label, vals, key=f"suit_{field}")
        if selected:
            suiting_filters[field] = selected

    f_button_count = st.multiselect("Button Count", [1, 2, 3, 4])

    # -- Fabric --
    st.subheader("Fabric")
    fabric_options = {
        "fabric_material": ("Material", ["wool", "cotton", "linen", "silk", "synthetic", "blend"]),
        "fabric_weight": ("Weight", ["light", "medium", "heavy"]),
        "fabric_texture": ("Texture", ["smooth", "textured", "napped", "crisp"]),
        "fabric_pattern": ("Pattern", ["solid", "pinstripe", "chalk-stripe", "check",
                                        "houndstooth", "plaid", "windowpane", "herringbone", "other"]),
    }

    fabric_filters = {}
    for field, (label, vals) in fabric_options.items():
        selected = st.multiselect(label, vals, key=f"fab_{field}")
        if selected:
            fabric_filters[field] = selected

    # -- Fit & Length --
    st.subheader("Fit & Silhouette")
    f_fit = st.multiselect("Fit", ["slim", "regular", "relaxed", "oversized", "boxy"])
    f_length = st.multiselect("Length", ["short", "regular", "long"])

    # -- Reset --
    if st.button("Clear All Filters"):
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# ── Look Browser ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Analyzed Look Browser" if analyzed_only else "Look Browser")

# ── Build filter dict ─────────────────────────────────────────────────────────

filters = {}
if f_seasons:
    filters["seasons"] = f_seasons
if f_fashion_weeks:
    filters["fashion_weeks"] = f_fashion_weeks
if f_designers:
    filters["designers"] = f_designers
if f_categories:
    filters["categories"] = f_categories
if mood_keywords:
    filters["mood_keywords"] = mood_keywords
if f_claude_colors:
    filters["claude_colors"] = f_claude_colors
if f_colors:
    filters["colors"] = f_colors
if f_garment_types:
    filters["garment_types"] = f_garment_types
if f_button_count:
    filters["button_count"] = f_button_count
if f_fit:
    filters["fit"] = f_fit
if f_length:
    filters["length"] = f_length
filters.update(suiting_filters)
filters.update(fabric_filters)

# ── Query & Display ──────────────────────────────────────────────────────────

looks = get_filtered_looks(filters, analyzed_only=analyzed_only)

active_count = sum(1 for v in filters.values() if v)
label = "analyzed looks" if analyzed_only else "looks"
if active_count:
    st.info(f"Showing **{len(looks)}** {label} matching **{active_count}** active filter{'s' if active_count > 1 else ''}.")
else:
    st.info(f"Showing all **{len(looks)}** {label}. Use the sidebar filters to narrow results.")

if looks:
    # Pagination
    PER_PAGE = 40
    total_pages = max(1, (len(looks) + PER_PAGE - 1) // PER_PAGE)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    st.caption(f"Page {page} of {total_pages}")
    page_looks = looks[(page - 1) * PER_PAGE : page * PER_PAGE]

    # Image grid with details
    cols_per_row = 4
    for i in range(0, len(page_looks), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx < len(page_looks):
                look = page_looks[idx]
                img_path = Path(look["local_path"]) if look["local_path"] else None
                if img_path and not img_path.is_absolute():
                    img_path = Path(__file__).parent.parent / img_path

                with col:
                    if img_path and img_path.exists():
                        st.image(str(img_path), use_container_width=True)
                    elif look.get("image_url"):
                        st.image(look["image_url"], use_container_width=True)
                    else:
                        st.caption("(image missing)")

                    st.markdown(f"**{look['designer']}** — Look {look['look_number']}")
                    st.caption(f"{look['season_code']} · {look['fashion_week_name'] or '—'}")

                    if look.get("mood"):
                        st.markdown(f"*{look['mood']}*")

                    has_analysis = look.get("raw_json") is not None
                    if has_analysis:
                        with st.expander("Details"):
                            if look.get("designer_intent"):
                                st.markdown(f"**Intent:** {look['designer_intent']}")
                            if look.get("styling_notes"):
                                st.markdown(f"**Styling:** {look['styling_notes']}")

                            raw = json.loads(look["raw_json"])
                            detail_fields = [
                                ("Lapel", "lapel_style"), ("Lapel Width", "lapel_width"),
                                ("Gorge", "gorge_height"), ("Buttons", "button_count"),
                                ("Shoulder", "shoulder_construction"), ("Vent", "vent_style"),
                                ("Construction", "construction"), ("Fit", "fit"),
                                ("Length", "length"),
                                ("Material", "fabric_material"), ("Weight", "fabric_weight"),
                                ("Texture", "fabric_texture"), ("Pattern", "fabric_pattern"),
                            ]
                            details_text = " · ".join(
                                f"{lbl}: {raw[key]}"
                                for lbl, key in detail_fields
                                if raw.get(key) and raw[key] != "unknown"
                            )
                            if details_text:
                                st.caption(details_text)

                            if look.get("look_categories"):
                                cats = json.loads(look["look_categories"]) if isinstance(look["look_categories"], str) else look["look_categories"]
                                st.caption(f"Categories: {', '.join(cats)}")
else:
    st.warning("No looks match the current filters. Try broadening your selection.")

