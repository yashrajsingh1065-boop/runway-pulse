"""Runway Pulse — Trend Overview Dashboard Page"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from storage.database import get_trend_snapshots, get_season_by_code

st.set_page_config(page_title="Trends — Runway Pulse", page_icon="📊", layout="wide")
st.title("Trend Overview")

# ── Sidebar: season selector ─────────────────────────────────────────────────

available_seasons = []
for code in ["FW24", "SS25", "FW25", "SS26", "FW26", "SS27"]:
    snaps = get_trend_snapshots(code)
    if snaps:
        available_seasons.append(code)

if not available_seasons:
    st.warning("No trend data yet. Run `python main.py trends aggregate --season <CODE>` first.")
    st.stop()

selected_season = st.sidebar.selectbox("Season", available_seasons, index=len(available_seasons) - 1)

# Load data
snapshots = get_trend_snapshots(selected_season)

# Group by attribute type
by_type: dict[str, list[dict]] = defaultdict(list)
for s in snapshots:
    by_type[s["attribute_type"]].append(s)

total_looks = snapshots[0]["total_looks"] if snapshots else 0

# ── Hero metrics ─────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
col1.metric("Analyzed Looks", total_looks)
col2.metric("Attribute Types", len(by_type))

# Find biggest shift
biggest_shift = None
biggest_change = 0
for s in snapshots:
    if s["change_pct"] is not None and abs(s["change_pct"]) > abs(biggest_change):
        biggest_change = s["change_pct"]
        biggest_shift = s
if biggest_shift:
    arrow = "▲" if biggest_change > 0 else "▼"
    col3.metric("Biggest Shift",
                f"{biggest_shift['attribute_value']}",
                f"{arrow} {biggest_change:+.1f}pp")
else:
    col3.metric("Biggest Shift", "—")

st.divider()

# ── Construction Profile Radar ───────────────────────────────────────────────

st.subheader("Construction Profile")

radar_fields = ["lapel_style", "shoulder_construction", "fit", "fabric_weight", "length"]
radar_available = [f for f in radar_fields if f in by_type]

if radar_available:
    # For radar: pick top value per field, show its percentage
    categories = []
    values = []
    for field in radar_available:
        items = sorted(by_type[field], key=lambda x: x["frequency"], reverse=True)
        top = items[0]
        pct = (top["frequency"] / total_looks * 100) if total_looks else 0
        categories.append(f"{field}\n({top['attribute_value']})")
        values.append(round(pct, 1))

    # Also overlay comparison season if available
    comp_season = None
    for s in snapshots:
        if s.get("compared_to_season_id"):
            # Find the comparison season code
            from storage.database import _connect
            with _connect() as conn:
                row = conn.execute("SELECT code FROM seasons WHERE id = ?",
                                   (s["compared_to_season_id"],)).fetchone()
                if row:
                    comp_season = row["code"]
            break

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill="toself",
        name=selected_season,
        line=dict(color="#c9a84c"),
    ))

    if comp_season:
        comp_snaps = get_trend_snapshots(comp_season)
        comp_by_type = defaultdict(list)
        for s in comp_snaps:
            comp_by_type[s["attribute_type"]].append(s)
        comp_total = comp_snaps[0]["total_looks"] if comp_snaps else 1

        comp_values = []
        for field in radar_available:
            items = sorted(comp_by_type.get(field, []), key=lambda x: x["frequency"], reverse=True)
            if items:
                pct = (items[0]["frequency"] / comp_total * 100)
                comp_values.append(round(pct, 1))
            else:
                comp_values.append(0)

        fig.add_trace(go.Scatterpolar(
            r=comp_values + [comp_values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=comp_season,
            line=dict(color="#4a90d9", dash="dot"),
            opacity=0.6,
        ))

    fig.update_layout(
        polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, ticksuffix="%")),
        showlegend=True,
        height=450,
        margin=dict(t=30, b=30),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Fit Distribution ─────────────────────────────────────────────────────────

if "fit" in by_type:
    st.subheader("Fit Distribution")
    fit_data = sorted(by_type["fit"], key=lambda x: x["frequency"], reverse=True)
    fig_fit = go.Figure(go.Bar(
        y=[d["attribute_value"] for d in fit_data],
        x=[d["frequency"] for d in fit_data],
        orientation="h",
        marker_color="#c9a84c",
        text=[f"{d['frequency']/total_looks*100:.0f}%" for d in fit_data],
        textposition="auto",
    ))
    fig_fit.update_layout(height=300, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_fit, use_container_width=True)

# ── Fabric Analysis ──────────────────────────────────────────────────────────

st.subheader("Fabric Analysis")
fab_col1, fab_col2 = st.columns(2)

with fab_col1:
    if "fabric_material" in by_type:
        mat_data = by_type["fabric_material"]
        fig_tree = px.treemap(
            names=[d["attribute_value"] for d in mat_data],
            parents=["" for _ in mat_data],
            values=[d["frequency"] for d in mat_data],
            title="Material",
        )
        fig_tree.update_layout(height=350, margin=dict(t=40, b=10))
        st.plotly_chart(fig_tree, use_container_width=True)

with fab_col2:
    if "fabric_pattern" in by_type:
        pat_data = sorted(by_type["fabric_pattern"], key=lambda x: x["frequency"], reverse=True)
        fig_pat = go.Figure(go.Bar(
            x=[d["attribute_value"] for d in pat_data],
            y=[d["frequency"] for d in pat_data],
            marker_color="#8b6f47",
        ))
        fig_pat.update_layout(title="Pattern", height=350, margin=dict(t=40, b=10))
        st.plotly_chart(fig_pat, use_container_width=True)

# ── Mood Archetypes ──────────────────────────────────────────────────────────

if "mood_archetype" in by_type:
    st.subheader("Mood Archetypes")
    mood_data = sorted(by_type["mood_archetype"], key=lambda x: x["frequency"], reverse=True)
    fig_mood = px.pie(
        names=[d["attribute_value"].replace("_", " ").title() for d in mood_data],
        values=[d["frequency"] for d in mood_data],
        hole=0.4,
    )
    fig_mood.update_traces(textposition="inside", textinfo="label+percent")
    fig_mood.update_layout(height=400, margin=dict(t=10, b=10))
    st.plotly_chart(fig_mood, use_container_width=True)

# ── Era References ───────────────────────────────────────────────────────────

if "era_decade" in by_type:
    st.subheader("Era References")
    era_data = sorted(by_type["era_decade"], key=lambda x: x["attribute_value"])
    fig_era = go.Figure(go.Bar(
        y=[d["attribute_value"] for d in era_data],
        x=[d["frequency"] for d in era_data],
        orientation="h",
        marker_color="#6a3d8a",
    ))
    fig_era.update_layout(height=max(200, len(era_data) * 35), margin=dict(t=10, b=10))
    st.plotly_chart(fig_era, use_container_width=True)
