"""
dashboard/utils/db.py
=====================
Database connection and cached data loaders for the dashboard.
All query results are cached for 5 minutes (ttl=300) to avoid
repeated DB hits on widget interactions.
"""

from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from sqlalchemy import create_engine

# ── Resolve project config ─────────────────────────────────────
_DASHBOARD_DIR  = Path(__file__).resolve().parent.parent
_PROJECT_ROOT   = _DASHBOARD_DIR.parent
_CONFIG_PATH    = _PROJECT_ROOT / "config" / "settings.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


@st.cache_resource
def get_engine():
    """Singleton DB engine — created once per Streamlit session."""
    cfg = _load_config()
    db  = cfg["database"]
    return create_engine(
        f"postgresql+psycopg2://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['name']}"
    )


# ── Data loaders (one per analytics table) ─────────────────────

@st.cache_data(ttl=300)
def load_waterfall() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM analytics.rpt_profit_waterfall", get_engine())


@st.cache_data(ttl=300)
def load_monthly_trend() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM analytics.summary_by_month ORDER BY order_month",
        get_engine()
    )


@st.cache_data(ttl=300)
def load_category_profitability() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM analytics.rpt_category_profitability ORDER BY total_net_profit DESC",
        get_engine()
    )


@st.cache_data(ttl=300)
def load_loss_making_orders() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM analytics.rpt_loss_making_orders ORDER BY order_net_profit ASC",
        get_engine()
    )


@st.cache_data(ttl=300)
def load_customer_profitability() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM analytics.rpt_customer_profitability ORDER BY total_net_profit DESC",
        get_engine()
    )


@st.cache_data(ttl=300)
def load_cac_by_channel() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM analytics.rpt_cac_by_channel ORDER BY total_net_profit DESC",
        get_engine()
    )


@st.cache_data(ttl=300)
def load_fact_items() -> pd.DataFrame:
    """Full fact table — filtered client-side for performance on small dataset."""
    return pd.read_sql("""
        SELECT
            order_id, order_item_id, customer_id, product_id,
            category, customer_segment, order_channel,
            order_date, order_month, month_label,
            item_revenue, item_cogs, logistics_cost, payment_fee,
            discount_allocated, return_cost, gross_profit, gross_margin_pct,
            contribution_margin, contribution_margin_pct,
            cac_allocation, net_profit, net_margin_pct,
            return_flag, is_first_order, is_profit_leak,
            customer_order_seq
        FROM analytics.fact_order_items
        ORDER BY order_date DESC
    """, get_engine())
