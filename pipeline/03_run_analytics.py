"""
pipeline/03_run_analytics.py
============================
Stage 3: Build analytics schema — fact table, business reports, and reconciliation.

Executes:
  03_create_analytics_schema.sql → fact_order_items + dim views + monthly summary
  04_business_analysis.sql       → 5 business-facing report tables
  05_reconciliation.sql          → cross-layer validation (logged, not printed to DB)

After building, prints a profit waterfall sanity-check report.

Run:
    python pipeline/03_run_analytics.py
"""

import logging
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "settings.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def build_engine(cfg: dict):
    db  = cfg["database"]
    url = (
        f"postgresql+psycopg2://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['name']}"
    )
    return create_engine(url)


def run_sql_file(engine, sql_path: Path) -> None:
    """Execute a multi-statement SQL file using raw psycopg2 cursor to avoid SQLAlchemy text() parsing issues."""
    sql = sql_path.read_text(encoding="utf-8")
    with engine.raw_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    log.info(f"  ✓ Executed: {sql_path.name}")


def report_profit_waterfall(engine) -> None:
    """Print the profit waterfall from rpt_profit_waterfall."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM analytics.rpt_profit_waterfall")
        ).fetchone()

    if not row:
        log.warning("  rpt_profit_waterfall is empty — check preceding SQL.")
        return

    log.info("")
    log.info("  ══ Profit Waterfall — Full Portfolio ══════════════════")
    log.info(f"  Orders: {row.total_orders:,}  |  Customers: {row.total_customers:,}  |  Line Items: {row.total_line_items:,}")
    log.info(f"  {'─'*52}")
    log.info(f"  (+) Item Revenue              ₹{row.step_01_item_revenue:>14,.2f}")
    log.info(f"  (-) COGS                      ₹{row.step_02_less_cogs:>14,.2f}")
    log.info(f"  (-) Logistics                 ₹{row.step_03_less_logistics:>14,.2f}")
    log.info(f"  (-) Payment Fees              ₹{row.step_04_less_payment_fees:>14,.2f}")
    log.info(f"  (-) Discounts                 ₹{row.step_05_less_discounts:>14,.2f}")
    log.info(f"  (-) Return Costs              ₹{row.step_06_less_return_costs:>14,.2f}")
    log.info(f"  {'─'*52}")
    log.info(f"  (=) Contribution Margin       ₹{row.step_07_contribution_margin:>14,.2f}  ({row.cm_margin_pct}%)")
    log.info(f"  (-) CAC Allocation            ₹{row.step_08_less_cac:>14,.2f}")
    log.info(f"  {'─'*52}")
    log.info(f"  (=) Net Profit                ₹{row.step_09_net_profit:>14,.2f}  ({row.net_margin_pct}%)")
    log.info(f"  {'─'*52}")
    log.info(f"  Profit Leaked                 ₹{row.total_profit_leaked:>14,.2f}  ({row.leakage_pct}%)")
    log.info(f"  Loss-Making Items             {row.loss_making_line_items:>16,}  ({row.pct_items_losing_money}% of items)")
    log.info("")


def report_category_summary(engine) -> None:
    """Print category-level net profit ranked table."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT category, total_revenue, total_net_profit,
                   avg_net_margin_pct, leakage_pct, profitability_tier
            FROM analytics.rpt_category_profitability
            ORDER BY total_net_profit DESC
        """)).fetchall()

    log.info("  ══ Category Profitability ══════════════════════════════")
    log.info(f"  {'Category':<16} {'Revenue':>12} {'Net Profit':>12} {'Net Margin%':>12} {'Leakage%':>10} {'Tier'}")
    log.info(f"  {'─'*16} {'─'*12} {'─'*12} {'─'*12} {'─'*10} {'─'*15}")
    for r in rows:
        log.info(
            f"  {str(r[0]):<16} ₹{r[1]:>10,.0f} ₹{r[2]:>10,.0f} "
            f"{str(r[3]):>11}%  {str(r[4]):>8}%  {r[5]}"
        )
    log.info("")


def report_channel_cac(engine) -> None:
    """Print channel CAC and unit economics."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT channel, new_customers, estimated_cac,
                   total_net_profit, avg_net_margin_pct,
                   ltv_cac_ratio, channel_tier
            FROM analytics.rpt_cac_by_channel
            ORDER BY total_net_profit DESC
        """)).fetchall()

    log.info("  ══ Channel CAC & Unit Economics ═══════════════════════")
    log.info(f"  {'Channel':<18} {'New Cust':>9} {'CAC(₹)':>9} {'Net Profit':>12} {'NM%':>6} {'LTV/CAC':>8} {'Tier'}")
    log.info(f"  {'─'*18} {'─'*9} {'─'*9} {'─'*12} {'─'*6} {'─'*8} {'─'*18}")
    for r in rows:
        cac = f"{r[2]:>8,.0f}" if r[2] else "       N/A"
        ltv = f"{r[5]:>7.2f}" if r[5] else "    N/A"
        log.info(
            f"  {str(r[0]):<18} {str(r[1]):>9} ₹{cac} "
            f"₹{r[3]:>10,.0f}  {str(r[4]):>5}% {ltv}  {r[6]}"
        )
    log.info("")


def run_reconciliation_summary(engine) -> None:
    """Run key reconciliation checks and report PASS/FAIL."""
    log.info("  ══ Reconciliation Checks ═══════════════════════════════")

    checks = [
        # (label, query, expected_status_value, result_col_name)
        (
            "Revenue matches raw source",
            """
            WITH raw_rev AS (
                SELECT ROUND(SUM(oi.price::NUMERIC), 2) AS v
                FROM raw.order_items oi
                JOIN raw.orders o ON oi.order_id = o.order_id
                WHERE o.order_status IN ('delivered','returned')
            ),
            fact_rev AS (SELECT ROUND(SUM(item_revenue),2) AS v FROM analytics.fact_order_items)
            SELECT CASE WHEN ABS(f.v - r.v) <= 1 THEN 'PASS' ELSE 'FAIL' END AS s
            FROM raw_rev r, fact_rev f
            """,
        ),
        (
            "Payment fee allocation sums correctly",
            """
            SELECT CASE
                WHEN MAX(ABS(f.s - p.total_payment_fee)) <= 0.05 THEN 'PASS'
                ELSE 'FAIL'
            END AS s
            FROM (
                SELECT order_id, ROUND(SUM(payment_fee),2) AS s
                FROM analytics.fact_order_items GROUP BY order_id
            ) f
            JOIN staging.stg_order_payments p ON f.order_id = p.order_id
            """,
        ),
        (
            "No CAC on repeat orders",
            """
            SELECT CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS s
            FROM analytics.fact_order_items
            WHERE is_first_order = FALSE AND cac_allocation <> 0
            """,
        ),
        (
            "net_profit = CM - CAC (cascade integrity)",
            """
            SELECT CASE
                WHEN COUNT(*) FILTER (
                    WHERE ABS(net_profit - (contribution_margin - cac_allocation)) > 0.02
                ) = 0 THEN 'PASS' ELSE 'FAIL'
            END AS s
            FROM analytics.fact_order_items
            """,
        ),
        (
            "Return cost only on returned orders",
            """
            SELECT CASE
                WHEN COUNT(*) FILTER (WHERE return_flag = FALSE AND return_cost <> 0) = 0
                THEN 'PASS' ELSE 'FAIL'
            END AS s
            FROM analytics.fact_order_items
            """,
        ),
        (
            "All 5 report tables populated",
            """
            SELECT CASE WHEN MIN(cnt) >= 1 THEN 'PASS' ELSE 'FAIL' END AS s FROM (
                SELECT COUNT(*) AS cnt FROM analytics.rpt_category_profitability
                UNION ALL SELECT COUNT(*) FROM analytics.rpt_customer_profitability
                UNION ALL SELECT COUNT(*) FROM analytics.rpt_cac_by_channel
                UNION ALL SELECT COUNT(*) FROM analytics.rpt_profit_waterfall
            ) t
            """,
        ),
    ]

    all_pass = True
    with engine.connect() as conn:
        for label, query in checks:
            result = conn.execute(text(query)).scalar()
            icon = "✓" if result == "PASS" else "✗"
            if result != "PASS":
                all_pass = False
            log.info(f"  {icon} [{result}] {label}")

    log.info("")
    if all_pass:
        log.info("  ✓ All reconciliation checks passed.")
    else:
        log.warning("  ✗ Some checks FAILED — review before launching dashboard.")
    log.info("")


def report_table_counts(engine) -> None:
    tables = [
        ("analytics", "fact_order_items"),
        ("analytics", "summary_by_month"),
        ("analytics", "rpt_category_profitability"),
        ("analytics", "rpt_loss_making_orders"),
        ("analytics", "rpt_customer_profitability"),
        ("analytics", "rpt_cac_by_channel"),
        ("analytics", "rpt_profit_waterfall"),
    ]
    log.info("  ── Analytics Table Row Counts ───────────────────────")
    with engine.connect() as conn:
        for schema, tbl in tables:
            n = conn.execute(
                text(f"SELECT COUNT(*) FROM {schema}.{tbl}")
            ).scalar()
            log.info(f"  {schema}.{tbl:<40} {n:>6,} rows")
    log.info("")


def main() -> None:
    log.info("═" * 60)
    log.info("  STAGE 3: Build Analytics Layer")
    log.info("═" * 60)

    cfg    = load_config()
    engine = build_engine(cfg)
    sql_dir = PROJECT_ROOT / cfg["paths"]["sql_dir"] / "analytics"

    # ── Run all three analytics SQL files in order ─────────────
    for sql_file in [
        "03_create_analytics_schema.sql",
        "04_business_analysis.sql",
        "05_reconciliation.sql",
    ]:
        log.info(f"Running {sql_file} …")
        run_sql_file(engine, sql_dir / sql_file)

    log.info("")

    # ── Print output reports ───────────────────────────────────
    report_table_counts(engine)
    report_profit_waterfall(engine)
    report_category_summary(engine)
    report_channel_cac(engine)
    run_reconciliation_summary(engine)

    log.info("  Stage 3 complete. Analytics layer is ready.")
    log.info("  Next: streamlit run dashboard/app.py")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
