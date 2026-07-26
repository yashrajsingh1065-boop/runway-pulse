"""Runway Pulse — Season Comparison Dashboard Page"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from storage.database import get_trend_snapshots, get_season_by_code

st.set_page_config(page_title="Season Compare — Runway Pulse", page_icon="⚖️", layout="wide")
st.title("Season Comparison")

# ── Sidebar: season selectors ────────────────────────────────────────────────

available_seasons = []
for code in ["FW24", "SS25", "FW25", "SS26", "FW26", "SS27"]:
    snaps = get_trend_snapshots(code)
    if snaps:
        available_seasons.append(code)

if len(available_seasons) < 2:
    st.warning("Need at least 2 seasons with trend data. Run aggregation with --compare-to.")
    st.stop()

current = st.sidebar.selectbox("Current Season", available_seasons, index=len(available_seasons) - 1)
prev_options = [s for s in available_seasons if s != current]
previous = st.sidebar.selectbox("Compare To", prev_options, index=0)

# Load data
cur_snaps = get_trend_snapshots(current)
prev_snaps = get_trend_snapshots(previous)

cur_total = cur_snaps[0]["total_looks"] if cur_snaps else 1
prev_total = prev_snaps[0]["total_looks"] if prev_snaps else 1

# Build comparison maps
cur_map = {}
for s in cur_snaps:
    key = (s["attribute_type"], s["attribute_value"])
    cur_map[key] = s

prev_map = {}
for s in prev_snaps:
    key = (s["attribute_type"], s["attribute_value"])
    prev_map[key] = s

# Compute comparisons
all_keys = set(cur_map.keys()) | set(prev_map.keys())
comparisons = []
for key in all_keys:
    attr_type, attr_value = key
    c = cur_map.get(key)
    p = prev_map.get(key)
    cur_pct = (c["frequency"] / cur_total * 100) if c else 0
    prev_pct = (p["frequency"] / prev_total * 100) if p else 0
    change = cur_pct - prev_pct

    if prev_pct == 0 and cur_pct > 0:
        direction = "new"
    elif cur_pct == 0 and prev_pct > 0:
        direction = "gone"
    elif abs(change) < 2.0:
        direction = "stable"
    elif change > 0:
        direction = "up"
    else:
        direction = "down"

    comparisons.append({
        "type": attr_type,
        "value": attr_value,
        "cur_pct": round(cur_pct, 1),
        "prev_pct": round(prev_pct, 1),
        "change": round(change, 1),
        "direction": direction,
    })

# ── Direction Summary Cards ──────────────────────────────────────────────────

dir_counts = defaultdict(int)
for c in comparisons:
    dir_counts[c["direction"]] += 1

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("▲ UP", dir_counts.get("up", 0))
c2.metric("▼ DOWN", dir_counts.get("down", 0))
c3.metric("— STABLE", dir_counts.get("stable", 0))
c4.metric("★ NEW", dir_counts.get("new", 0))
c5.metric("✕ GONE", dir_counts.get("gone", 0))

st.divider()

# ── Top Movers Table ─────────────────────────────────────────────────────────

st.subheader("Top Movers")
movers = sorted(comparisons, key=lambda x: abs(x["change"]), reverse=True)[:20]

dir_emoji = {"up": "🟢 ▲", "down": "🔴 ▼", "stable": "🟡 —", "new": "🔵 ★", "gone": "⚪ ✕"}

mover_df = pd.DataFrame([{
    "Attribute": m["type"],
    "Value": m["value"],
    f"{current} %": m["cur_pct"],
    f"{previous} %": m["prev_pct"],
    "Change (pp)": m["change"],
    "Direction": dir_emoji.get(m["direction"], m["direction"]),
} for m in movers])
st.dataframe(mover_df, use_container_width=True, hide_index=True)

st.divider()

# ── Movement Heatmap ─────────────────────────────────────────────────────────

st.subheader("Movement Heatmap")

# Group by attribute type for heatmap
attr_types = sorted(set(c["type"] for c in comparisons))
selected_types = st.multiselect(
    "Attribute types to show",
    attr_types,
    default=[t for t in ["fit", "fabric_material", "fabric_pattern", "lapel_style",
                          "shoulder_construction", "mood_archetype"] if t in attr_types],
)

if selected_types:
    filtered = [c for c in comparisons if c["type"] in selected_types]
    # Build heatmap data
    types_list = []
    values_list = []
    changes_list = []
    for c in sorted(filtered, key=lambda x: (x["type"], -abs(x["change"]))):
        types_list.append(c["type"])
        values_list.append(c["value"])
        changes_list.append(c["change"])

    # Create a matrix
    unique_values = list(dict.fromkeys(values_list))  # preserve order
    unique_types = list(dict.fromkeys(types_list))

    z_matrix = []
    for t in unique_types:
        row = []
        for v in unique_values:
            match = [c for c in filtered if c["type"] == t and c["value"] == v]
            row.append(match[0]["change"] if match else None)
        z_matrix.append(row)

    fig_heat = go.Figure(go.Heatmap(
        z=z_matrix,
        x=unique_values,
        y=unique_types,
        colorscale=[[0, "#cc2020"], [0.5, "#1a1a1a"], [1, "#2d7c2d"]],
        zmid=0,
        text=[[f"{v:.1f}pp" if v is not None else "" for v in row] for row in z_matrix],
        texttemplate="%{text}",
        colorbar=dict(title="Change (pp)"),
    ))
    fig_heat.update_layout(height=max(300, len(unique_types) * 50), margin=dict(t=10, b=10))
    st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ── Per-Attribute Grouped Bars ───────────────────────────────────────────────

st.subheader("Per-Attribute Comparison")

for attr_type in attr_types:
    with st.expander(attr_type.replace("_", " ").title()):
        items = [c for c in comparisons if c["type"] == attr_type]
        items.sort(key=lambda x: x["cur_pct"], reverse=True)
        items = items[:15]  # top 15 per type

        vals = [i["value"] for i in items]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name=current,
            x=vals,
            y=[i["cur_pct"] for i in items],
            marker_color="#c9a84c",
        ))
        fig.add_trace(go.Bar(
            name=previous,
            x=vals,
            y=[i["prev_pct"] for i in items],
            marker_color="#4a90d9",
        ))
        fig.update_layout(
            barmode="group",
            height=350,
            margin=dict(t=10, b=10),
            yaxis_title="% of looks",
        )
        st.plotly_chart(fig, use_container_width=True)
