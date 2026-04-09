"""
dashboard/app.py
================
Page 1: Executive Overview
Entry point for the Profit Leakage & True Unit Economics Analyzer dashboard.
Shows the portfolio-level profit waterfall, KPI summary, and monthly trend.
"""

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.db import load_waterfall, load_monthly_trend, load_fact_items
from utils.style import (
    C, CATEGORY_PALETTE, inject_css, page_header, section_header,
    kpi_row, insight_box, chart_layout, fmt_inr, fmt_pct, tone_for,
)

# ── Page config ────────────────────────────────────────────────
st.set_page_config(page_title="Executive Overview", page_icon="🏢", layout="wide")
inject_css()

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-brand">📉 Profit Leakage Analyzer<div class="sidebar-tagline">True Unit Economics</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Executive Summary**")
    st.info(
        "This tool diagnoses profit leakage across the portfolio by moving beyond Gross Margin. "
        "It allocates hidden operational costs (freight, returns, gateway fees, and CAC) down to the item level."
    )
    st.markdown("**Key Business Assumptions:**")
    with st.expander("View Allocation Rules", expanded=False):
        st.markdown(
            "• **CAC:** Allocated 100% to a customer's first order. Repeat orders have $0 CAC.\n\n"
            "• **Order Fees:** Gateway fees & discounts are proportionally distributed to line items based on revenue share.\n\n"
            "• **Returns:** Assumes a standard reverse freight cost equals forward shipping, plus a 10% restocking penalty."
        )

    st.markdown("**Navigation**")
    st.page_link("app.py",                                   label="📊 Executive Overview",      icon=None)
    st.page_link("pages/2_📦_Category_Profitability.py",     label="📦 Category Profitability",  icon=None)
    st.page_link("pages/3_👤_Customer_Profitability.py",     label="👤 Customer Profitability",  icon=None)
    st.page_link("pages/4_🔍_Order_Diagnostics.py",          label="🔍 Order Diagnostics",       icon=None)
    st.page_link("pages/5_📣_Marketing_CAC.py",              label="📣 Marketing & CAC",         icon=None)

    st.markdown("---")
    st.caption("Data: analytics.rpt_profit_waterfall")

# ── Load data ──────────────────────────────────────────────────
try:
    wf  = load_waterfall().iloc[0]
    mth = load_monthly_trend()
    df  = load_fact_items()
except Exception as e:
    st.error(f"⚠️ Could not connect to database. Run the pipeline first.\n\n`{e}`")
    st.stop()

# ── Page header ────────────────────────────────────────────────
page_header(
    "Executive Overview",
    "Portfolio-level profit leakage analysis — where does every rupee of revenue go?"
)

# ── KPI Row 1: Revenue waterfall milestones ────────────────────
section_header("Key Performance Indicators")
kpi_row([
    ("Total Revenue",        fmt_inr(wf.step_01_item_revenue),    "gross top-line", "normal"),
    ("Total COGS",           fmt_inr(wf.step_02_less_cogs),       "cost of goods",  "warning"),
    ("Logistics Cost",       fmt_inr(wf.step_03_less_logistics),  "freight total",  "warning"),
    ("Payment Fees",         fmt_inr(wf.step_04_less_payment_fees),"gateway fees",  "warning"),
    ("Discounts",            fmt_inr(wf.step_05_less_discounts),  "order discounts","warning"),
    ("Return Costs",         fmt_inr(wf.step_06_less_return_costs),"reverse+restock","warning"),
])

kpi_row([
    ("Contribution Margin",  fmt_inr(wf.step_07_contribution_margin),
                             fmt_pct(wf.cm_margin_pct) + " of revenue",
                             tone_for(float(wf.step_07_contribution_margin))),
    ("CAC Spend",            fmt_inr(wf.step_08_less_cac),        "acquisition cost", "warning"),
    ("Net Profit",           fmt_inr(wf.step_09_net_profit),
                             fmt_pct(wf.net_margin_pct) + " net margin",
                             tone_for(float(wf.step_09_net_profit))),
    ("Profit Leaked",        fmt_inr(wf.total_profit_leaked),
                             fmt_pct(wf.leakage_pct) + " of revenue",
                             "negative"),
    ("Total Orders",         f"{int(wf.total_orders):,}",          "delivered+returned", "normal"),
    ("Loss-Making Items",    f"{int(wf.loss_making_line_items):,}",
                             fmt_pct(wf.pct_items_losing_money) + " of items",
                             "negative" if float(wf.pct_items_losing_money) > 10 else "warning"),
])

# ── Profit Waterfall Chart ──────────────────────────────────────
section_header("Profit Cascade — Revenue to Net Profit")

waterfall_labels = [
    "Revenue", "− COGS", "− Logistics", "− Payment Fees",
    "− Discounts", "− Returns", "Contribution Margin", "− CAC", "Net Profit"
]
waterfall_values = [
    wf.step_01_item_revenue,
    -wf.step_02_less_cogs,
    -wf.step_03_less_logistics,
    -wf.step_04_less_payment_fees,
    -wf.step_05_less_discounts,
    -wf.step_06_less_return_costs,
    None,   # total for CM
    -wf.step_08_less_cac,
    None,   # total for Net Profit
]
waterfall_measure = [
    "absolute", "relative", "relative", "relative",
    "relative", "relative", "total", "relative", "total"
]
waterfall_text = [
    fmt_inr(wf.step_01_item_revenue),
    fmt_inr(wf.step_02_less_cogs),
    fmt_inr(wf.step_03_less_logistics),
    fmt_inr(wf.step_04_less_payment_fees),
    fmt_inr(wf.step_05_less_discounts),
    fmt_inr(wf.step_06_less_return_costs),
    fmt_inr(wf.step_07_contribution_margin) + f" ({wf.cm_margin_pct}%)",
    fmt_inr(wf.step_08_less_cac),
    fmt_inr(wf.step_09_net_profit) + f" ({wf.net_margin_pct}%)",
]

fig_wf = go.Figure(go.Waterfall(
    orientation="v",
    measure=waterfall_measure,
    x=waterfall_labels,
    y=[float(v) if v is not None else None for v in waterfall_values],
    text=waterfall_text,
    textposition="outside",
    textfont=dict(color=C["text"], size=11),
    connector=dict(line=dict(color="rgba(148,163,184,0.3)", width=1, dash="dot")),
    increasing=dict(marker=dict(color=C["positive"])),
    decreasing=dict(marker=dict(color=C["negative"])),
    totals=dict(marker=dict(color=C["primary"])),
    hovertemplate="<b>%{x}</b><br>₹%{y:,.0f}<extra></extra>",
))
fig_wf.update_layout(
    **chart_layout(title=None, height=420, showlegend=False),
    yaxis_tickprefix="₹",
    yaxis_tickformat=",",
)
st.plotly_chart(fig_wf, use_container_width=True, config={"displayModeBar": False})

# ── Monthly Trend ──────────────────────────────────────────────
section_header("Monthly Trend — Revenue vs Net Profit")

col1, col2 = st.columns([3, 1])
with col1:
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Bar(
        x=mth["month_label"], y=mth["total_revenue"],
        name="Revenue", marker_color="rgba(99,102,241,0.35)",
        hovertemplate="<b>%{x}</b><br>Revenue: ₹%{y:,.0f}<extra></extra>",
    ))
    fig_trend.add_trace(go.Scatter(
        x=mth["month_label"], y=mth["total_contribution_margin"],
        name="Contribution Margin", mode="lines+markers",
        line=dict(color=C["warning"], width=2),
        marker=dict(size=6, color=C["warning"]),
        hovertemplate="<b>%{x}</b><br>CM: ₹%{y:,.0f}<extra></extra>",
    ))
    fig_trend.add_trace(go.Scatter(
        x=mth["month_label"], y=mth["total_net_profit"],
        name="Net Profit", mode="lines+markers",
        line=dict(color=C["positive"], width=2.5),
        marker=dict(size=7, color=C["positive"]),
        hovertemplate="<b>%{x}</b><br>Net Profit: ₹%{y:,.0f}<extra></extra>",
    ))
    fig_trend.update_layout(
        **chart_layout(height=340),
        barmode="overlay",
        xaxis_title=None, yaxis_title=None,
        yaxis_tickprefix="₹", yaxis_tickformat=",",
    )
    fig_trend.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

with col2:
    # Monthly averages
    section_header("Avg Monthly")
    avg_rev = mth["total_revenue"].mean()
    avg_np  = mth["total_net_profit"].mean()
    avg_nm  = mth["avg_net_margin_pct"].mean()
    best_m  = mth.loc[mth["total_net_profit"].idxmax(), "month_label"]
    worst_m = mth.loc[mth["total_net_profit"].idxmin(), "month_label"]

    kpi_row([(  "Avg Monthly Revenue", fmt_inr(avg_rev),  "", "normal")])
    kpi_row([(  "Avg Monthly Profit",  fmt_inr(avg_np),   "", tone_for(avg_np))])
    kpi_row([(  "Avg Net Margin",      fmt_pct(avg_nm),   "", tone_for(avg_nm))])
    insight_box("Best Month",  best_m)
    insight_box("Worst Month", worst_m)

# ── Cost breakdown mini section ─────────────────────────────────
section_header("Where Revenue Leaks")

rev = float(wf.step_01_item_revenue)
leak_items = [
    ("COGS",          float(wf.step_02_less_cogs),           C["neutral"]),
    ("Logistics",     float(wf.step_03_less_logistics),      C["warning"]),
    ("Payment Fees",  float(wf.step_04_less_payment_fees),   "#f97316"),
    ("Discounts",     float(wf.step_05_less_discounts),      "#8b5cf6"),
    ("Returns",       float(wf.step_06_less_return_costs),   C["negative"]),
    ("CAC",           float(wf.step_08_less_cac),            C["primary"]),
    ("Net Profit",    float(wf.step_09_net_profit),          C["positive"]),
]

fig_leak = go.Figure(go.Pie(
    labels=[i[0] for i in leak_items],
    values=[abs(i[1]) for i in leak_items],
    marker=dict(colors=[i[2] for i in leak_items],
                line=dict(color="#0a0f1e", width=2)),
    hole=0.55,
    hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
    textinfo="label+percent",
    textfont=dict(color=C["text"], size=11),
))
fig_leak.update_layout(
    **chart_layout(height=340, showlegend=False,
                   title=dict(text="Revenue Allocation", font=dict(size=13, color=C["muted"]))),
    annotations=[dict(
        text=f"<b>{fmt_pct(wf.leakage_pct)}</b><br><span style='font-size:10px'>leaked</span>",
        x=0.5, y=0.5, font=dict(size=14, color=C["text"]),
        showarrow=False
    )],
)

c1, c2, c3 = st.columns(3)
with c1:
    st.plotly_chart(fig_leak, use_container_width=True, config={"displayModeBar": False})
with c2:
    # Cost as % of revenue table
    st.markdown("**Cost as % of Revenue**")
    for label, val, _ in leak_items:
        pct = val / rev * 100 if rev else 0
        bar_w = int(min(pct * 4, 100))
        color = C["positive"] if label == "Net Profit" else C["negative"]
        st.markdown(f"""
        <div style='margin:6px 0'>
            <div style='display:flex;justify-content:space-between;font-size:12px;
                        color:{C["muted"]};margin-bottom:3px'>
                <span>{label}</span><span style='color:{color}'>{pct:.1f}%</span>
            </div>
            <div style='background:rgba(255,255,255,0.05);border-radius:4px;height:5px'>
                <div style='background:{color};width:{bar_w}%;height:5px;
                            border-radius:4px'></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
with c3:
    section_header("Quick Stats")
    total_cust  = df["customer_id"].nunique()
    ret_rate    = df["return_flag"].mean() * 100
    first_ord   = df["is_first_order"].sum()
    leak_count  = df["is_profit_leak"].sum()
    insight_box("Total Customers",       f"{total_cust:,} unique customers")
    insight_box("Return Rate",           f"{ret_rate:.1f}% of orders returned")
    insight_box("First-Time Orders",    f"{first_ord:,} ({first_ord/len(df)*100:.0f}% of items)")
    insight_box("Loss-Making Items",    f"{leak_count:,} items with negative net profit")
