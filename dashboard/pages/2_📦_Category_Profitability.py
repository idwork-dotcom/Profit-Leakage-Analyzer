"""
Page 2: Category Profitability
Breaks down profit leakage by product category with full cost waterfall.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.db import load_category_profitability, load_fact_items
from utils.style import (
    C, CATEGORY_PALETTE, inject_css, page_header, section_header,
    kpi_row, insight_box, chart_layout, fmt_inr, fmt_pct,
)

st.set_page_config(page_title="Category Profitability", page_icon="📦", layout="wide")
inject_css()

with st.sidebar:
    st.markdown('<div class="sidebar-brand">📉 Profit Leakage Analyzer<div class="sidebar-tagline">True Unit Economics</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Filters**")

try:
    cat_df = load_category_profitability()
    fact   = load_fact_items()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Sidebar filters
all_cats = sorted(cat_df["category"].unique())
sel_cats = st.sidebar.multiselect("Categories", all_cats, default=all_cats)
if sel_cats:
    cat_df = cat_df[cat_df["category"].isin(sel_cats)]
    fact   = fact[fact["category"].isin(sel_cats)]

page_header("Category Profitability", "Which categories drive profit — and which drain it?")

# ── KPIs ───────────────────────────────────────────────────────
best_cat  = cat_df.loc[cat_df["total_net_profit"].idxmax(), "category"]
worst_cat = cat_df.loc[cat_df["total_net_profit"].idxmin(), "category"]
best_nm   = cat_df["total_net_profit"].max()
worst_nm  = cat_df["total_net_profit"].min()

kpi_row([
    ("Best Category",    best_cat,             fmt_inr(best_nm),       "positive"),
    ("Worst Category",   worst_cat,            fmt_inr(worst_nm),      "negative"),
    ("Avg Net Margin",   fmt_pct(cat_df["avg_net_margin_pct"].mean()), "", "normal"),
    ("Avg Return Rate",  fmt_pct(cat_df["return_rate_pct"].mean()),    "", "warning"),
    ("Categories",       str(len(cat_df)),     "in selection",         "normal"),
])

# ── Row 1: Net Profit Bar + Margin Comparison ─────────────────
section_header("Net Profit & Margin by Category")
c1, c2 = st.columns(2)

with c1:
    colors = [C["positive"] if v >= 0 else C["negative"] for v in cat_df["total_net_profit"]]
    fig = go.Figure(go.Bar(
        x=cat_df["category"],
        y=cat_df["total_net_profit"],
        marker_color=colors,
        text=[fmt_inr(v) for v in cat_df["total_net_profit"]],
        textposition="outside",
        textfont=dict(size=11, color=C["text"]),
        hovertemplate="<b>%{x}</b><br>Net Profit: ₹%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(**chart_layout(height=340, title="Net Profit by Category"))
    fig.add_hline(y=0, line_color=C["muted"], line_dash="dot", line_width=1)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with c2:
    fig2 = go.Figure()
    metrics = [
        ("Gross Margin", "gross_margin_pct",  C["neutral"]),
        ("CM %",         "cm_pct",            C["warning"]),
        ("Net Margin %", "avg_net_margin_pct", C["positive"]),
    ]
    for name, col, color in metrics:
        fig2.add_trace(go.Bar(
            name=name, x=cat_df["category"], y=cat_df[col],
            marker_color=color,
            hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{y:.1f}}%<extra></extra>",
        ))
    fig2.update_layout(
        **chart_layout(height=340, title="Margin Waterfall by Category"),
        barmode="group",
        yaxis_ticksuffix="%",
    )
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

# ── Row 2: Stacked Cost Breakdown ─────────────────────────────
section_header("Cost Structure Breakdown")

cost_cols = [
    ("COGS",          "total_cogs",          C["neutral"]),
    ("Logistics",     "total_logistics_cost", C["warning"]),
    ("Payment Fees",  "total_payment_fees",   "#f97316"),
    ("Discounts",     "total_discounts",      "#8b5cf6"),
    ("Return Cost",   "total_return_cost",    C["negative"]),
    ("CAC Spend",     "total_cac_spend",      C["primary"]),
]

fig3 = go.Figure()
for name, col, color in cost_cols:
    fig3.add_trace(go.Bar(
        name=name, x=cat_df["category"], y=cat_df[col],
        marker_color=color,
        hovertemplate=f"<b>%{{x}}</b><br>{name}: ₹%{{y:,.0f}}<extra></extra>",
    ))
# Net profit overlay
fig3.add_trace(go.Scatter(
    name="Net Profit", x=cat_df["category"], y=cat_df["total_net_profit"],
    mode="markers+lines", marker=dict(size=10, color=C["positive"], symbol="diamond"),
    line=dict(color=C["positive"], width=2, dash="dot"),
    hovertemplate="<b>%{x}</b><br>Net Profit: ₹%{y:,.0f}<extra></extra>",
    yaxis="y2",
))
fig3.update_layout(
    **chart_layout(height=380, title="Cost Stacks vs Net Profit"),
    barmode="stack",
    yaxis_tickprefix="₹", yaxis_tickformat=",",
    yaxis2=dict(
        overlaying="y", side="right",
        tickprefix="₹", tickformat=",",
        gridcolor="rgba(0,0,0,0)",
        tickfont=dict(color=C["positive"]),
    )
)
fig3.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

# ── Row 3: Category Detail Table + Insights ────────────────────
section_header("Category Detail Summary")
c3, c4 = st.columns([2, 1])

with c3:
    display_df = cat_df[[
        "category", "total_revenue", "total_gross_profit", "gross_margin_pct",
        "total_contribution_margin", "cm_pct", "total_cac_spend",
        "total_net_profit", "avg_net_margin_pct", "return_rate_pct", "profitability_tier"
    ]].copy()
    display_df.columns = [
        "Category", "Revenue", "Gross Profit", "Gross%",
        "Contribution Margin", "CM%", "CAC Spend",
        "Net Profit", "Net Margin%", "Return Rate%", "Tier"
    ]
    for col in ["Revenue", "Gross Profit", "Contribution Margin", "CAC Spend", "Net Profit"]:
        display_df[col] = display_df[col].apply(fmt_inr)
    for col in ["Gross%", "CM%", "Net Margin%", "Return Rate%"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}%")

    st.dataframe(display_df, use_container_width=True, hide_index=True,
                 column_config={"Tier": st.column_config.TextColumn(width="medium")})

with c4:
    section_header("Key Insights")
    high_leak = cat_df.loc[cat_df["leakage_pct"].idxmax()]
    high_ret  = cat_df.loc[cat_df["return_rate_pct"].idxmax()]
    high_cac  = cat_df.loc[cat_df["cac_pct"].idxmax()]

    insight_box("Highest Leakage",
        f"<b>{high_leak['category']}</b> leaks {high_leak['leakage_pct']:.1f}% of revenue "
        f"(₹{high_leak['profit_leaked_abs']:,.0f})")
    insight_box("Highest Return Rate",
        f"<b>{high_ret['category']}</b> has {high_ret['return_rate_pct']:.1f}% return rate, "
        f"adding ₹{high_ret['total_return_cost']:,.0f} in reverse costs")
    insight_box("Highest CAC %",
        f"<b>{high_cac['category']}</b> spends {high_cac['cac_pct']:.1f}% of revenue on acquisition")
    insight_box("Primary Cost Driver",
        f"The most common primary cost is: <b>{cat_df['primary_cost_driver'].mode().iloc[0]}</b>")
