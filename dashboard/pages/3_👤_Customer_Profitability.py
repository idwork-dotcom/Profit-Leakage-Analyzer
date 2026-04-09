"""
Page 3: Customer Profitability
Most / least profitable customers, LTV analysis, and segment concentration.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.db import load_customer_profitability
from utils.style import (
    C, CATEGORY_PALETTE, inject_css, page_header, section_header,
    kpi_row, insight_box, chart_layout, fmt_inr, fmt_pct, tone_for,
)

st.set_page_config(page_title="Customer Profitability", page_icon="👤", layout="wide")
inject_css()

with st.sidebar:
    st.markdown('<div class="sidebar-brand">📉 Profit Leakage Analyzer<div class="sidebar-tagline">True Unit Economics</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Filters**")

try:
    cust = load_customer_profitability()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Sidebar filters
all_segs  = sorted(cust["customer_segment"].dropna().unique())
all_chans = sorted(cust["acquisition_channel"].dropna().unique())
sel_segs  = st.sidebar.multiselect("Customer Segment", all_segs, default=all_segs)
sel_chans = st.sidebar.multiselect("Acquisition Channel", all_chans, default=all_chans)

if sel_segs:
    cust = cust[cust["customer_segment"].isin(sel_segs)]
if sel_chans:
    cust = cust[cust["acquisition_channel"].isin(sel_chans)]

page_header("Customer Profitability", "LTV, CAC payback, and true per-customer unit economics")

# ── KPIs ───────────────────────────────────────────────────────
total_pos  = (cust["total_net_profit"] > 0).sum()
total_neg  = (cust["total_net_profit"] < 0).sum()
avg_ltv_cac = cust["ltv_cac_ratio"].dropna().median()

kpi_row([
    ("Total Customers",        f"{len(cust):,}",                    "in selection",         "normal"),
    ("Profitable Customers",   f"{total_pos:,}",
                               f"{total_pos/len(cust)*100:.0f}%",   "positive"),
    ("Loss-Making Customers",  f"{total_neg:,}",
                               f"{total_neg/len(cust)*100:.0f}%",   "negative"),
    ("Median LTV/CAC",         f"{avg_ltv_cac:.2f}x" if avg_ltv_cac else "N/A",
                               ">3× is healthy",                    tone_for(avg_ltv_cac or 0, 3)),
    ("Avg Net Profit / Customer", fmt_inr(cust["total_net_profit"].mean()), "",
                               tone_for(cust["total_net_profit"].mean())),
])

# ── Row 1: Top / Bottom Customers ─────────────────────────────
section_header("Most & Least Profitable Customers")
c1, c2 = st.columns(2)

top_n    = cust.nlargest(12, "total_net_profit")
bottom_n = cust.nsmallest(12, "total_net_profit")

with c1:
    fig = go.Figure(go.Bar(
        x=top_n["total_net_profit"],
        y=top_n["customer_id"].str[-6:],  # last 6 chars as short label
        orientation="h",
        marker_color=C["positive"],
        text=[fmt_inr(v) for v in top_n["total_net_profit"]],
        textposition="auto",
        textfont=dict(size=10),
        hovertemplate="<b>%{y}</b><br>Net Profit: ₹%{x:,.0f}<extra></extra>",
        customdata=top_n[["customer_segment", "acquisition_channel"]].values,
    ))
    fig.update_layout(
        **chart_layout(height=360, title="Top 12 — Most Profitable"),
        xaxis_tickprefix="₹", xaxis_tickformat=",",
        yaxis=dict(tickfont=dict(size=11, color=C["muted"])),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with c2:
    colors_b = [C["negative"]] * len(bottom_n)
    fig2 = go.Figure(go.Bar(
        x=bottom_n["total_net_profit"],
        y=bottom_n["customer_id"].str[-6:],
        orientation="h",
        marker_color=colors_b,
        text=[fmt_inr(v) for v in bottom_n["total_net_profit"]],
        textposition="auto",
        textfont=dict(size=10),
        hovertemplate="<b>%{y}</b><br>Net Profit: ₹%{x:,.0f}<extra></extra>",
    ))
    fig2.update_layout(
        **chart_layout(height=360, title="Bottom 12 — Least Profitable"),
        xaxis_tickprefix="₹", xaxis_tickformat=",",
        yaxis=dict(tickfont=dict(size=11, color=C["muted"])),
    )
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

# ── Row 2: Revenue vs Net Profit Scatter + Segment Donut ──────
section_header("Customer Scatter — Revenue vs Net Profit")
c3, c4 = st.columns([3, 2])

with c3:
    seg_colors = {"Mass": C["neutral"], "Mid Value": C["warning"], "High Value": C["positive"]}
    scatter = go.Figure()
    for seg, grp in cust.groupby("customer_segment"):
        scatter.add_trace(go.Scatter(
            x=grp["total_revenue"],
            y=grp["total_net_profit"],
            mode="markers",
            name=seg,
            marker=dict(
                size=grp["total_orders"].clip(2, 15) * 1.5,
                color=seg_colors.get(seg, C["primary"]),
                opacity=0.7,
                line=dict(width=0.5, color="rgba(255,255,255,0.3)"),
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Revenue: ₹%{x:,.0f}<br>"
                "Net Profit: ₹%{y:,.0f}<br>"
                "Orders: %{marker.size:.0f}<extra></extra>"
            ),
            customdata=grp[["customer_id"]].values,
        ))
    scatter.add_hline(y=0, line_color=C["muted"], line_dash="dot", line_width=1,
                      annotation_text="Break-even", annotation_font_color=C["muted"])
    scatter.add_vline(x=cust["total_revenue"].median(), line_color=C["border"],
                      line_dash="dash", line_width=1)
    scatter.update_layout(
        **chart_layout(height=380, title="Revenue vs Net Profit (bubble = order count)"),
        xaxis_title="Total Revenue (₹)", yaxis_title="Net Profit (₹)",
        xaxis_tickprefix="₹", xaxis_tickformat=",",
        yaxis_tickprefix="₹", yaxis_tickformat=",",
    )
    st.plotly_chart(scatter, use_container_width=True, config={"displayModeBar": False})

with c4:
    # Segment contribution to total net profit
    seg_agg = cust.groupby("customer_segment")["total_net_profit"].sum().reset_index()
    fig_pie = go.Figure(go.Pie(
        labels=seg_agg["customer_segment"],
        values=seg_agg["total_net_profit"].clip(lower=0),
        marker=dict(
            colors=[C["neutral"], C["warning"], C["positive"]],
            line=dict(color="#0a0f1e", width=2)
        ),
        hole=0.55,
        hovertemplate="<b>%{label}</b><br>Net Profit: ₹%{value:,.0f}<br>%{percent}<extra></extra>",
        textinfo="label+percent",
        textfont=dict(color=C["text"], size=12),
    ))
    fig_pie.update_layout(
        **chart_layout(height=280, showlegend=False,
                       title=dict(text="Net Profit Share by Segment",
                                  font=dict(size=13, color=C["muted"]))),
    )
    st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

    # Segment summary table
    seg_summary = cust.groupby("customer_segment").agg(
        Customers=("customer_id", "count"),
        Revenue=("total_revenue", "sum"),
        Net_Profit=("total_net_profit", "sum"),
    ).reset_index()
    seg_summary["Net Margin"] = (
        seg_summary["Net_Profit"] / seg_summary["Revenue"] * 100
    ).round(1).astype(str) + "%"
    seg_summary["Revenue"]    = seg_summary["Revenue"].apply(fmt_inr)
    seg_summary["Net Profit"] = seg_summary["Net_Profit"].apply(fmt_inr)
    seg_summary = seg_summary.drop(columns=["Net_Profit"])
    seg_summary.columns = ["Segment", "Customers", "Revenue", "Net Profit", "Net Margin"]
    st.dataframe(seg_summary, use_container_width=True, hide_index=True)

# ── Row 3: LTV / CAC Analysis ──────────────────────────────────
section_header("LTV / CAC Ratio by Acquisition Channel")

ltv_agg = (
    cust.dropna(subset=["acquisition_channel"])
    .groupby("acquisition_channel")
    .agg(
        customers=("customer_id", "count"),
        avg_ltv_cac=("ltv_cac_ratio", "median"),
        total_net_profit=("total_net_profit", "sum"),
        total_cac=("total_cac_paid", "sum"),
    )
    .reset_index()
    .sort_values("avg_ltv_cac", ascending=False)
)

colors_ltv = [
    C["positive"] if v >= 3 else C["warning"] if v >= 1 else C["negative"]
    for v in ltv_agg["avg_ltv_cac"]
]

fig_ltv = go.Figure(go.Bar(
    x=ltv_agg["acquisition_channel"],
    y=ltv_agg["avg_ltv_cac"],
    marker_color=colors_ltv,
    text=[f"{v:.1f}×" for v in ltv_agg["avg_ltv_cac"]],
    textposition="outside",
    textfont=dict(size=12, color=C["text"]),
    hovertemplate="<b>%{x}</b><br>Median LTV/CAC: %{y:.2f}×<extra></extra>",
))
fig_ltv.add_hline(y=3, line_color=C["positive"], line_dash="dash", line_width=1.5,
                  annotation_text="Healthy (3×)", annotation_font_color=C["positive"])
fig_ltv.add_hline(y=1, line_color=C["negative"], line_dash="dot", line_width=1,
                  annotation_text="Break-even (1×)", annotation_font_color=C["negative"])
fig_ltv.update_layout(
    **chart_layout(height=320, title="Median LTV/CAC Ratio by Acquisition Channel"),
    yaxis_title="LTV / CAC Ratio",
)
st.plotly_chart(fig_ltv, use_container_width=True, config={"displayModeBar": False})
