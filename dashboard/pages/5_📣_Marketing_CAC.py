"""
Page 5: Marketing & CAC
Channel-level CAC analysis, funnel conversion, and impact of acquisition
cost on first-order profitability vs. repeat-order profitability.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go
import streamlit as st

from utils.db import load_cac_by_channel, load_fact_items
from utils.style import (
    C, CATEGORY_PALETTE, inject_css, page_header, section_header,
    kpi_row, insight_box, chart_layout, fmt_inr, fmt_pct, tone_for,
)

st.set_page_config(page_title="Marketing & CAC", page_icon="📣", layout="wide")
inject_css()

with st.sidebar:
    st.markdown('<div class="sidebar-brand">📉 Profit Leakage Analyzer<div class="sidebar-tagline">True Unit Economics</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.caption("All channels shown. Spend estimates from config/settings.yaml.")

try:
    cac_df = load_cac_by_channel()
    fact   = load_fact_items()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

page_header("Marketing & CAC Analysis",
            "True cost of customer acquisition — and its impact on unit economics")

# ── KPIs ───────────────────────────────────────────────────────
total_cac   = cac_df["total_cac_spend"].sum()
total_cust  = cac_df["new_customers"].sum()
avg_cac     = total_cac / total_cust if total_cust else 0
best_chan    = cac_df.loc[cac_df["total_net_profit"].idxmax(), "channel"]
avg_ltv_cac = cac_df["ltv_cac_ratio"].dropna().median()

kpi_row([
    ("Total CAC Spend",      fmt_inr(total_cac),             "estimated",        "warning"),
    ("New Customers",        f"{int(total_cust):,}",         "first-orders",     "normal"),
    ("Blended CAC",          fmt_inr(avg_cac),               "per new customer",  "warning"),
    ("Best Channel",         best_chan,                       "by net profit",    "positive"),
    ("Median LTV/CAC",       f"{avg_ltv_cac:.2f}×" if avg_ltv_cac else "N/A",
                             "portfolio median",             tone_for(avg_ltv_cac or 0, 3)),
])

# ── Row 1: CAC by Channel + First-Order Net Margin ────────────
section_header("CAC vs First-Order Profitability by Channel")
c1, c2 = st.columns(2)

with c1:
    cac_colors = [
        C["positive"] if v >= 0 else C["negative"]
        for v in cac_df["first_order_net_profit"]
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Estimated CAC (₹)",
        x=cac_df["channel"],
        y=cac_df["estimated_cac"],
        marker_color="rgba(239,68,68,0.6)",
        hovertemplate="<b>%{x}</b><br>CAC: ₹%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="First-Order Net Profit (₹)",
        x=cac_df["channel"],
        y=cac_df["first_order_net_profit"],
        mode="markers+lines",
        marker=dict(size=10, color=C["positive"], symbol="diamond"),
        line=dict(color=C["positive"], width=2),
        hovertemplate="<b>%{x}</b><br>1st Order Profit: ₹%{y:,.0f}<extra></extra>",
        yaxis="y2",
    ))
    fig.update_layout(
        **chart_layout(height=360, title="CAC vs First-Order Net Profit"),
        barmode="group",
        yaxis=dict(title="CAC (₹)", tickprefix="₹", tickformat=",",
                   gridcolor="rgba(148,163,184,0.08)"),
        yaxis2=dict(title="Net Profit (₹)", overlaying="y", side="right",
                    tickprefix="₹", tickformat=",", gridcolor="rgba(0,0,0,0)",
                    tickfont=dict(color=C["positive"])),
    )
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with c2:
    # LTV/CAC ratio bars
    ltv_colors = [
        C["positive"] if v >= 3 else C["warning"] if v >= 1 else C["negative"]
        for v in cac_df["ltv_cac_ratio"].fillna(0)
    ]
    fig2 = go.Figure(go.Bar(
        x=cac_df["channel"],
        y=cac_df["ltv_cac_ratio"],
        marker_color=ltv_colors,
        text=[f"{v:.2f}×" if v else "N/A" for v in cac_df["ltv_cac_ratio"]],
        textposition="outside",
        textfont=dict(size=12, color=C["text"]),
        hovertemplate="<b>%{x}</b><br>LTV/CAC: %{y:.2f}×<extra></extra>",
    ))
    fig2.add_hline(y=3, line_color=C["positive"], line_dash="dash", line_width=1.5,
                   annotation_text="Healthy (3×)", annotation_font_color=C["positive"])
    fig2.add_hline(y=1, line_color=C["negative"], line_dash="dot", line_width=1,
                   annotation_text="Break-even (1×)", annotation_font_color=C["negative"])
    fig2.update_layout(
        **chart_layout(height=360, title="LTV / CAC Ratio by Channel"),
        yaxis_title="LTV / CAC Ratio",
    )
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

# ── Row 2: Marketing Funnel + Revenue per New Customer ────────
section_header("Marketing Funnel — Leads → Deals → Customers")
c3, c4 = st.columns([2, 1])

with c3:
    funnel_df = cac_df[cac_df["total_mql_leads"] > 0].copy()
    if len(funnel_df):
        fig3 = go.Figure()
        funnel_stages = [
            ("MQL Leads",   "total_mql_leads",  "rgba(99,102,241,0.4)"),
            ("Deals Closed","total_deals",       "rgba(245,158,11,0.6)"),
            ("New Customers","new_customers",    "rgba(16,185,129,0.6)"),
        ]
        x_pos = list(range(len(funnel_df)))
        for name, col, color in funnel_stages:
            fig3.add_trace(go.Bar(
                name=name, x=funnel_df["channel"], y=funnel_df[col],
                marker_color=color,
                text=funnel_df[col].astype(int),
                textposition="auto",
                textfont=dict(size=10),
                hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{y:,}}<extra></extra>",
            ))
        fig3.update_layout(
            **chart_layout(height=360, title="Lead Funnel by Channel"),
            barmode="group",
        )
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No MQL lead data available — check that staging.stg_channel_summary is populated.")

with c4:
    # Channel conversion rates
    funnel_df2 = cac_df[cac_df["total_mql_leads"] > 0].copy()
    if len(funnel_df2):
        section_header("Conversion Rates")
        for _, row in funnel_df2.iterrows():
            rate = row["lead_conversion_rate_pct"]
            bar_w = int(min(rate * 6, 100))
            color = C["positive"] if rate > 15 else C["warning"] if rate > 5 else C["negative"]
            st.markdown(f"""
            <div style='margin:8px 0'>
                <div style='display:flex;justify-content:space-between;
                            font-size:12px;color:{C["muted"]};margin-bottom:3px'>
                    <span>{row['channel']}</span>
                    <span style='color:{color};font-weight:600'>{rate:.1f}%</span>
                </div>
                <div style='background:rgba(255,255,255,0.05);border-radius:4px;height:6px'>
                    <div style='background:{color};width:{bar_w}%;height:6px;border-radius:4px'></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ── Row 3: First-Order vs Repeat-Order Profitability ──────────
section_header("First-Order vs. Repeat-Order Economics")
c5, c6 = st.columns(2)

with c5:
    # Compare CM and Net Profit for first vs. repeat orders per channel
    fo_fact = fact.groupby(["order_channel", "is_first_order"]).agg(
        avg_cm=("contribution_margin", "mean"),
        avg_np=("net_profit", "mean"),
        orders=("order_id", "nunique"),
    ).reset_index()

    first  = fo_fact[fo_fact["is_first_order"] == True]
    repeat = fo_fact[fo_fact["is_first_order"] == False]

    fig4 = go.Figure()
    for grp, name, color, dash in [
        (first,  "Avg CM — First Order",   C["warning"],  "solid"),
        (first,  "Avg NP — First Order",   C["negative"], "solid"),
        (repeat, "Avg CM — Repeat Order",  C["positive"], "dash"),
        (repeat, "Avg NP — Repeat Order",  C["primary"],  "dash"),
    ]:
        col = "avg_cm" if "CM" in name else "avg_np"
        fig4.add_trace(go.Scatter(
            x=grp["order_channel"], y=grp[col], name=name,
            mode="markers+lines",
            marker=dict(size=9, color=color),
            line=dict(color=color, width=2, dash=dash),
            hovertemplate=f"<b>%{{x}}</b><br>{name}: ₹%{{y:,.0f}}<extra></extra>",
        ))
    fig4.add_hline(y=0, line_color=C["muted"], line_dash="dot", line_width=1)
    fig4.update_layout(
        **chart_layout(height=340, title="First vs Repeat Order Economics by Channel"),
        yaxis_tickprefix="₹", yaxis_tickformat=",",
        yaxis_title="Avg per-item (₹)",
    )
    fig4.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})

with c6:
    section_header("Channel Scorecard")
    for _, row in cac_df.iterrows():
        tier_color = {
            "High Value Channel": C["positive"],
            "Moderate Value":     C["warning"],
            "Breakeven":          C["neutral"],
            "Loss Channel":       C["negative"],
        }.get(row.get("channel_tier", ""), C["muted"])
        ltv_display = f"{row['ltv_cac_ratio']:.2f}×" if row.get("ltv_cac_ratio") else "N/A"
        st.markdown(f"""
        <div style='background:#141929;border:1px solid rgba(99,102,241,0.2);
                    border-radius:10px;padding:12px 16px;margin-bottom:10px'>
            <div style='display:flex;justify-content:space-between;align-items:center'>
                <div>
                    <span style='font-weight:700;color:{C["text"]};font-size:14px'>{row['channel']}</span>
                    <span style='margin-left:8px;padding:2px 8px;border-radius:20px;font-size:10px;
                                 font-weight:600;background:rgba(255,255,255,0.08);
                                 color:{tier_color}'>{row.get('channel_tier','')}</span>
                </div>
                <div style='text-align:right'>
                    <div style='font-size:12px;color:{C["muted"]}'>LTV/CAC</div>
                    <div style='font-weight:700;color:{tier_color};font-size:15px'>{ltv_display}</div>
                </div>
            </div>
            <div style='display:flex;gap:20px;margin-top:8px'>
                <div><span style='font-size:10px;color:{C["muted"]}'>CAC</span>
                     <div style='font-size:13px;color:{C["text"]}'>{fmt_inr(row.get('estimated_cac', 0))}</div></div>
                <div><span style='font-size:10px;color:{C["muted"]}'>Net Profit</span>
                     <div style='font-size:13px;color:{C["positive"] if row["total_net_profit"] >= 0 else C["negative"]}'>{fmt_inr(row["total_net_profit"])}</div></div>
                <div><span style='font-size:10px;color:{C["muted"]}'>New Customers</span>
                     <div style='font-size:13px;color:{C["text"]}'>{int(row["new_customers"]):,}</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
