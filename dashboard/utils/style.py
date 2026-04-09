"""
dashboard/utils/style.py
========================
Global CSS injection, KPI card HTML renderer, and Plotly chart theme.
Call inject_css() at the top of every page to apply the shared design.
"""

import streamlit as st
import plotly.graph_objects as go

# ── Color palette ──────────────────────────────────────────────
C = {
    "primary":   "#6366f1",
    "positive":  "#10b981",
    "warning":   "#f59e0b",
    "negative":  "#ef4444",
    "neutral":   "#64748b",
    "text":      "#e2e8f0",
    "muted":     "#94a3b8",
    "bg":        "rgba(0,0,0,0)",
    "card_bg":   "#141929",
    "border":    "rgba(99,102,241,0.25)",
}

CATEGORY_PALETTE = [
    "#6366f1", "#10b981", "#f59e0b", "#ef4444",
    "#8b5cf6", "#06b6d4", "#f97316", "#ec4899",
]


def inject_css() -> None:
    """Inject the global dashboard CSS. Call at the top of every page."""
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* ── Page header ─────────────────────────────── */
    .page-header {{
        padding: 0 0 24px 0;
        border-bottom: 1px solid {C['border']};
        margin-bottom: 28px;
    }}
    .page-title {{
        font-size: 26px;
        font-weight: 800;
        color: {C['text']};
        margin: 0;
        background: linear-gradient(90deg, {C['text']} 0%, {C['primary']} 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .page-subtitle {{
        font-size: 13px;
        color: {C['muted']};
        margin: 4px 0 0 0;
    }}

    /* ── Section headers ────────────────────────── */
    .section-header {{
        font-size: 15px;
        font-weight: 700;
        color: {C['text']};
        border-left: 3px solid {C['primary']};
        padding-left: 10px;
        margin: 28px 0 14px 0;
        letter-spacing: 0.3px;
    }}

    /* ── KPI Cards ───────────────────────────────── */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 14px;
        margin-bottom: 28px;
    }}
    .kpi-card {{
        background: linear-gradient(135deg, {C['card_bg']} 0%, #1a2040 100%);
        border: 1px solid {C['border']};
        border-radius: 12px;
        padding: 18px 16px;
        text-align: center;
        transition: border-color 0.2s ease;
    }}
    .kpi-card:hover {{
        border-color: {C['primary']};
    }}
    .kpi-label {{
        font-size: 10px;
        font-weight: 700;
        color: {C['muted']};
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 8px;
    }}
    .kpi-value {{
        font-size: 22px;
        font-weight: 800;
        color: {C['text']};
        line-height: 1.1;
    }}
    .kpi-value.positive {{ color: {C['positive']}; }}
    .kpi-value.negative {{ color: {C['negative']}; }}
    .kpi-value.warning  {{ color: {C['warning']};  }}
    .kpi-sub {{
        font-size: 11px;
        color: {C['muted']};
        margin-top: 4px;
    }}

    /* ── Insight boxes ───────────────────────────── */
    .insight-box {{
        background: linear-gradient(135deg, #1e1040 0%, {C['card_bg']} 100%);
        border: 1px solid rgba(99,102,241,0.3);
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 12px;
    }}
    .insight-title {{
        font-size: 12px;
        font-weight: 700;
        color: {C['primary']};
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
    }}
    .insight-text {{ font-size: 14px; color: {C['text']}; }}

    /* ── Status badges ───────────────────────────── */
    .badge {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
    }}
    .badge-green  {{ background: rgba(16,185,129,0.15); color: {C['positive']}; }}
    .badge-red    {{ background: rgba(239,68,68,0.15);  color: {C['negative']}; }}
    .badge-yellow {{ background: rgba(245,158,11,0.15); color: {C['warning']}; }}
    .badge-indigo {{ background: rgba(99,102,241,0.15); color: {C['primary']}; }}

    /* ── Sidebar tweaks ──────────────────────────── */
    section[data-testid="stSidebar"] {{
        background-color: #0d1221 !important;
        border-right: 1px solid {C['border']};
    }}
    .sidebar-brand {{
        font-size: 15px; font-weight: 800; color: {C['text']};
        padding: 4px 0 16px 0;
        border-bottom: 1px solid {C['border']};
        margin-bottom: 16px;
    }}
    .sidebar-tagline {{
        font-size: 11px; color: {C['muted']};
        margin-top: 2px;
    }}

    /* ── Hide Streamlit branding ─────────────────── */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    </style>
    """, unsafe_allow_html=True)


# ── Plotly chart layout defaults ───────────────────────────────

def chart_layout(**overrides) -> dict:
    """Return a base Plotly layout dict merged with any overrides."""
    base = dict(
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["bg"],
        font=dict(family="Inter, sans-serif", color=C["text"], size=12),
        margin=dict(l=16, r=16, t=40, b=16),
        xaxis=dict(
            gridcolor="rgba(148,163,184,0.08)",
            linecolor="rgba(148,163,184,0.15)",
            tickfont=dict(color=C["muted"]),
        ),
        yaxis=dict(
            gridcolor="rgba(148,163,184,0.08)",
            linecolor="rgba(148,163,184,0.15)",
            tickfont=dict(color=C["muted"]),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=C["muted"], size=11),
        ),
        hoverlabel=dict(
            bgcolor="#1e293b",
            bordercolor=C["border"],
            font=dict(family="Inter", color=C["text"]),
        ),
    )
    base.update(overrides)
    return base


# ── KPI card HTML renderer ─────────────────────────────────────

def kpi_card(label: str, value: str, sub: str = "", tone: str = "normal") -> str:
    """Render a single KPI card as HTML. tone: normal|positive|negative|warning"""
    tone_class = "" if tone == "normal" else tone
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value {tone_class}">{value}</div>
        {"" if not sub else f'<div class="kpi-sub">{sub}</div>'}
    </div>
    """


def kpi_row(cards: list[tuple]) -> None:
    """
    Render a row of KPI cards.
    cards = [(label, value, sub, tone), ...]
    """
    html = '<div class="kpi-grid">'
    for item in cards:
        label, value = item[0], item[1]
        sub  = item[2] if len(item) > 2 else ""
        tone = item[3] if len(item) > 3 else "normal"
        html += kpi_card(label, value, sub, tone)
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"""
    <div class="page-header">
        <p class="page-title">{title}</p>
        <p class="page-subtitle">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str) -> None:
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


def insight_box(title: str, body: str) -> None:
    st.markdown(f"""
    <div class="insight-box">
        <div class="insight-title">{title}</div>
        <div class="insight-text">{body}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Number formatters ──────────────────────────────────────────

def fmt_inr(n, decimals: int = 0) -> str:
    """Format a number as Indian Rupees."""
    if n is None:
        return "N/A"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "N/A"
    if abs(n) >= 1_000_000:
        return f"₹{n/1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"₹{n/1_000:.1f}K"
    return f"₹{n:,.{decimals}f}"


def fmt_pct(n, decimals: int = 1) -> str:
    if n is None:
        return "N/A"
    try:
        return f"{float(n):.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


def tone_for(value: float, good_above: float = 0) -> str:
    """Return the KPI tone string based on whether value is above threshold."""
    if value > good_above:
        return "positive"
    if value == good_above:
        return "warning"
    return "negative"
