"""
Page 4: Order-Level Diagnostics
Loss-making orders, root cause analysis, and item-level drill-down.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go
import streamlit as st

from utils.db import load_loss_making_orders, load_fact_items
from utils.style import (
    C, inject_css, page_header, section_header,
    kpi_row, insight_box, chart_layout, fmt_inr, fmt_pct,
)

st.set_page_config(page_title="Order Diagnostics", page_icon="🔍", layout="wide")
inject_css()

with st.sidebar:
    st.markdown('<div class="sidebar-brand">📉 Profit Leakage Analyzer<div class="sidebar-tagline">True Unit Economics</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Filters**")

try:
    loss_df = load_loss_making_orders()
    fact    = load_fact_items()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Filters
all_cats   = sorted(fact["category"].unique())
all_chans  = sorted(fact["order_channel"].unique())
sel_cats   = st.sidebar.multiselect("Category", all_cats, default=all_cats)
sel_chans  = st.sidebar.multiselect("Channel", all_chans, default=all_chans)
show_sev   = st.sidebar.selectbox("Min Loss Severity", ["All", "High", "Severe"], index=0)

loss_df = loss_df[loss_df["primary_category"].isin(sel_cats)]
loss_df = loss_df[loss_df["order_channel"].isin(sel_chans)]
if show_sev == "High":
    loss_df = loss_df[loss_df["order_net_margin_pct"] < -20]
elif show_sev == "Severe":
    loss_df = loss_df[loss_df["order_net_margin_pct"] < -50]

page_header("Order Diagnostics", "Loss-making orders — root causes and cost drill-downs")

# ── KPIs ───────────────────────────────────────────────────────
total_loss_orders = len(loss_df)
total_loss_amt    = loss_df["order_net_profit"].sum()
total_all_orders  = fact["order_id"].nunique()
avg_loss_per_order = loss_df["order_net_profit"].mean() if len(loss_df) else 0

kpi_row([
    ("Loss-Making Orders",   f"{total_loss_orders:,}",
                             f"{total_loss_orders/total_all_orders*100:.1f}% of all orders", "negative"),
    ("Total Net Loss",       fmt_inr(total_loss_amt),        "combined loss",   "negative"),
    ("Avg Loss per Order",   fmt_inr(avg_loss_per_order),    "per order",       "negative"),
    ("Returned Orders",      f"{loss_df['return_flag'].sum():,}",
                             "in loss set",                  "warning"),
    ("First-Order Losses",   f"{loss_df['is_first_order'].sum():,}",
                             "high CAC impact",              "warning"),
])

# ── Root Cause Distribution + Loss by Channel ──────────────────
section_header("Root Cause Analysis")
c1, c2 = st.columns(2)

with c1:
    cause_counts = loss_df["loss_root_cause"].value_counts().reset_index()
    cause_counts.columns = ["cause", "count"]
    colors = [C["negative"] if i == 0 else C["warning"] if i == 1 else C["neutral"]
              for i in range(len(cause_counts))]
    fig = go.Figure(go.Bar(
        x=cause_counts["count"],
        y=cause_counts["cause"],
        orientation="h",
        marker_color=colors,
        text=cause_counts["count"],
        textposition="auto",
        hovertemplate="<b>%{y}</b><br>Orders: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **chart_layout(height=320, title="Loss Root Cause Distribution"),
        xaxis_title="Number of Loss Orders",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with c2:
    if len(loss_df):
        chan_loss = (
            loss_df.groupby("order_channel")
            .agg(orders=("order_id", "count"), total_loss=("order_net_profit", "sum"))
            .reset_index().sort_values("total_loss")
        )
        fig2 = go.Figure(go.Bar(
            x=chan_loss["total_loss"],
            y=chan_loss["order_channel"],
            orientation="h",
            marker_color=C["negative"],
            text=[fmt_inr(v) for v in chan_loss["total_loss"]],
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Total Loss: ₹%{x:,.0f}<extra></extra>",
        ))
        fig2.update_layout(
            **chart_layout(height=320, title="Total Loss by Channel"),
            xaxis_tickprefix="₹", xaxis_tickformat=",",
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

# ── Severity Distribution ──────────────────────────────────────
section_header("Loss Severity Distribution")
if len(loss_df):
    sev_counts = loss_df["loss_severity"].value_counts().reset_index()
    sev_counts.columns = ["severity", "count"]
    sev_colors = {
        "Severe   (>50% loss)":   C["negative"],
        "High     (20-50% loss)": "#f97316",
        "Moderate (5-20% loss)":  C["warning"],
        "Marginal (<5% loss)":    C["neutral"],
    }
    c3, c4 = st.columns([1, 2])
    with c3:
        fig3 = go.Figure(go.Pie(
            labels=sev_counts["severity"],
            values=sev_counts["count"],
            marker=dict(
                colors=[sev_colors.get(s, C["muted"]) for s in sev_counts["severity"]],
                line=dict(color="#0a0f1e", width=2)
            ),
            hole=0.5,
            textinfo="label+percent",
            textfont=dict(size=11, color=C["text"]),
            hovertemplate="<b>%{label}</b><br>Count: %{value}<extra></extra>",
        ))
        fig3.update_layout(**chart_layout(height=280, showlegend=False,
                           title=dict(text="By Severity", font=dict(size=13))))
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
    with c4:
        insight_box("What this means",
            "Severe losses (>50%) are typically caused by high CAC on small first orders "
            "or expensive returns on low-margin products. High losses (20-50%) often combine "
            "thin gross margins with above-average logistics costs.")
        insight_box("Action Priority",
            "Focus on Severe + High categories first. These have the most immediate impact on "
            "net profit if the root cause (CAC, returns, or COGS) can be addressed.")

# ── Loss Order Table ───────────────────────────────────────────
section_header(f"Loss-Making Orders ({total_loss_orders:,} orders) — Sorted by Largest Loss")

if len(loss_df):
    table_df = loss_df[[
        "order_id", "order_date", "primary_category", "order_channel",
        "customer_segment", "return_flag", "is_first_order",
        "order_revenue", "order_net_profit", "order_net_margin_pct",
        "loss_root_cause", "loss_severity"
    ]].copy()
    table_df.columns = [
        "Order ID", "Date", "Category", "Channel", "Segment",
        "Returned", "First Order", "Revenue", "Net Profit", "Net Margin%",
        "Root Cause", "Severity"
    ]
    table_df["Revenue"]    = table_df["Revenue"].apply(fmt_inr)
    table_df["Net Profit"] = table_df["Net Profit"].apply(fmt_inr)
    table_df["Net Margin%"]= table_df["Net Margin%"].apply(lambda x: f"{x:.1f}%")
    st.dataframe(table_df, use_container_width=True, hide_index=True, height=320)

# ── Order Drill-Down ───────────────────────────────────────────
section_header("Order Item Drill-Down")
st.caption("Select an order to see the cost breakdown across its line items.")

# Let user pick from loss-making OR all orders
drill_scope = st.radio("Show orders from", ["Loss-Making Only", "All Orders"], horizontal=True)
if drill_scope == "Loss-Making Only":
    order_pool = loss_df["order_id"].tolist()
else:
    order_pool = sorted(fact["order_id"].unique())

if order_pool:
    sel_order = st.selectbox("Select Order ID", order_pool)
    order_items = fact[fact["order_id"] == sel_order].copy()

    if len(order_items):
        c5, c6 = st.columns(2)
        with c5:
            # Cost breakdown waterfall per order
            costs = [
                ("Revenue",     order_items["item_revenue"].sum(),    "absolute"),
                ("− COGS",     -order_items["item_cogs"].sum(),       "relative"),
                ("− Logistics", -order_items["logistics_cost"].sum(), "relative"),
                ("− Fees",     -order_items["payment_fee"].sum(),     "relative"),
                ("− Discount",  -order_items["discount_allocated"].sum(), "relative"),
                ("− Returns",  -order_items["return_cost"].sum(),     "relative"),
                ("= CM",        None,                                 "total"),
                ("− CAC",      -order_items["cac_allocation"].sum(),  "relative"),
                ("= Net Profit",None,                                 "total"),
            ]
            fig_dd = go.Figure(go.Waterfall(
                orientation="v",
                measure=[c[2] for c in costs],
                x=[c[0] for c in costs],
                y=[float(c[1]) if c[1] is not None else None for c in costs],
                connector=dict(line=dict(color=C["border"], width=1, dash="dot")),
                increasing=dict(marker=dict(color=C["positive"])),
                decreasing=dict(marker=dict(color=C["negative"])),
                totals=dict(marker=dict(color=C["primary"])),
                hovertemplate="<b>%{x}</b><br>₹%{y:,.2f}<extra></extra>",
            ))
            fig_dd.update_layout(
                **chart_layout(height=320, title=f"Order {sel_order} — Cost Waterfall"),
                showlegend=False,
            )
            st.plotly_chart(fig_dd, use_container_width=True, config={"displayModeBar": False})

        with c6:
            item_tbl = order_items[[
                "order_item_id", "category", "item_revenue", "item_cogs",
                "logistics_cost", "payment_fee", "return_cost",
                "contribution_margin", "cac_allocation", "net_profit"
            ]].copy()
            item_tbl.columns = [
                "#", "Category", "Revenue", "COGS", "Logistics",
                "Fee", "Return", "CM", "CAC", "Net Profit"
            ]
            for col in ["Revenue", "COGS", "Logistics", "Fee", "Return", "CM", "CAC", "Net Profit"]:
                item_tbl[col] = item_tbl[col].apply(lambda x: fmt_inr(x, 2))
            st.dataframe(item_tbl, use_container_width=True, hide_index=True, height=320)
