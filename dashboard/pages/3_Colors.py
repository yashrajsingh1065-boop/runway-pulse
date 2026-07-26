"""Runway Pulse — Color Analysis Dashboard Page"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go

from storage.database import get_trend_snapshots
from analysis.color_aggregator import get_hex

st.set_page_config(page_title="Colors — Runway Pulse", page_icon="🎨", layout="wide")
st.title("Color Analysis")

# ── Sidebar: season selector ─────────────────────────────────────────────────

available_seasons = []
for code in ["FW24", "SS25", "FW25", "SS26", "FW26", "SS27"]:
    snaps = get_trend_snapshots(code)
    if snaps:
        available_seasons.append(code)

if not available_seasons:
    st.warning("No trend data yet. Run `python main.py trends aggregate` first.")
    st.stop()

selected = st.sidebar.selectbox("Season", available_seasons, index=len(available_seasons) - 1)
snapshots = get_trend_snapshots(selected)

# Extract color data
claude_colors = [s for s in snapshots if s["attribute_type"] == "color_claude"]
cv_colors = [s for s in snapshots if s["attribute_type"] == "color_cv"]
total_looks = snapshots[0]["total_looks"] if snapshots else 1

# Sort by frequency
claude_colors.sort(key=lambda x: x["frequency"], reverse=True)
cv_colors.sort(key=lambda x: x["frequency"], reverse=True)

# ── Color Palette Swatches ───────────────────────────────────────────────────

st.subheader("Color Palette — Claude Analysis")

if claude_colors:
    max_freq = claude_colors[0]["frequency"]
    swatch_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;">'
    for c in claude_colors[:20]:
        hex_val = get_hex(c["attribute_value"])
        height = max(30, int(80 * c["frequency"] / max_freq))
        pct = c["frequency"] / total_looks * 100
        swatch_html += (
            f'<div style="text-align:center;">'
            f'<div style="width:60px;height:{height}px;background:{hex_val};'
            f'border:1px solid #444;border-radius:4px;" '
            f'title="{c["attribute_value"]}: {c["frequency"]} ({pct:.0f}%)"></div>'
            f'<div style="font-size:10px;margin-top:4px;color:#aaa;">'
            f'{c["attribute_value"]}<br>{c["frequency"]}</div>'
            f'</div>'
        )
    swatch_html += '</div>'
    st.markdown(swatch_html, unsafe_allow_html=True)
else:
    st.info("No Claude color data available.")

st.divider()

# ── Distribution Bar Chart ───────────────────────────────────────────────────

st.subheader("Color Distribution")

col1, col2 = st.columns(2)

with col1:
    st.caption("Claude-Reported Colors")
    if claude_colors:
        fig_claude = go.Figure(go.Bar(
            y=[c["attribute_value"] for c in claude_colors[:15]],
            x=[c["frequency"] for c in claude_colors[:15]],
            orientation="h",
            marker_color=[get_hex(c["attribute_value"]) for c in claude_colors[:15]],
            marker_line=dict(color="#444", width=1),
            text=[f'{c["frequency"]/total_looks*100:.0f}%' for c in claude_colors[:15]],
            textposition="auto",
        ))
        fig_claude.update_layout(
            height=max(300, len(claude_colors[:15]) * 30),
            margin=dict(t=10, b=10, l=100),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_claude, use_container_width=True)

with col2:
    st.caption("CV-Detected Colors (Jacket/Coat)")
    if cv_colors:
        fig_cv = go.Figure(go.Bar(
            y=[c["attribute_value"] for c in cv_colors[:15]],
            x=[c["frequency"] for c in cv_colors[:15]],
            orientation="h",
            marker_color=[get_hex(c["attribute_value"]) for c in cv_colors[:15]],
            marker_line=dict(color="#444", width=1),
            text=[str(c["frequency"]) for c in cv_colors[:15]],
            textposition="auto",
        ))
        fig_cv.update_layout(
            height=max(300, len(cv_colors[:15]) * 30),
            margin=dict(t=10, b=10, l=100),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_cv, use_container_width=True)
    else:
        st.info("No CV color data.")

st.divider()

# ── Season Comparison ────────────────────────────────────────────────────────

st.subheader("Season Color Comparison")

compare_options = [s for s in available_seasons if s != selected]
if compare_options:
    compare_to = st.selectbox("Compare to", compare_options, index=0)
    comp_snaps = get_trend_snapshots(compare_to)
    comp_claude = {s["attribute_value"]: s for s in comp_snaps if s["attribute_type"] == "color_claude"}
    comp_total = comp_snaps[0]["total_looks"] if comp_snaps else 1

    # Merge all color names
    all_colors = set()
    for c in claude_colors:
        all_colors.add(c["attribute_value"])
    for v in comp_claude.values():
        all_colors.add(v["attribute_value"])

    # Sort by current frequency
    cur_map = {c["attribute_value"]: c["frequency"] for c in claude_colors}
    sorted_colors = sorted(all_colors, key=lambda x: cur_map.get(x, 0), reverse=True)[:15]

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        name=selected,
        x=sorted_colors,
        y=[cur_map.get(c, 0) / total_looks * 100 for c in sorted_colors],
        marker_color="#c9a84c",
    ))
    fig_comp.add_trace(go.Bar(
        name=compare_to,
        x=sorted_colors,
        y=[comp_claude.get(c, {}).get("frequency", 0) / comp_total * 100 for c in sorted_colors],
        marker_color="#4a90d9",
    ))
    fig_comp.update_layout(
        barmode="group",
        height=400,
        margin=dict(t=10, b=10),
        yaxis_title="% of looks",
    )
    st.plotly_chart(fig_comp, use_container_width=True)
else:
    st.info("Need a second season for comparison.")
