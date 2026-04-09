"""
pipeline/02_run_staging.py
==========================
Stage 2: Build staging schema from raw tables.

Executes 02_create_staging_schema.sql which cleans, casts, filters,
and enriches raw data. After the SQL runs, this script injects the
estimated monthly marketing spend (from settings.yaml) into
staging.stg_channel_summary to enable CAC calculation.

Run:
    python pipeline/02_run_staging.py
"""

import logging
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text

# ── Logging setup ──────────────────────────────────────────────────────────
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
    sql = sql_path.read_text(encoding="utf-8")
    with engine.raw_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    log.info(f"Executed: {sql_path.name}")


def inject_marketing_spend(engine, cfg: dict) -> None:
    """
    Injects estimated monthly marketing spend per channel into
    staging.stg_channel_summary and then computes estimated_cac.

    CAC formula:
        estimated_cac = estimated_monthly_spend / new_customers
    """
    spend_map = cfg.get("marketing_spend", {})

    if not spend_map:
        log.warning("  No marketing_spend config found — CAC will be NULL.")
        return

    log.info("  Injecting marketing spend and computing CAC …")

    with engine.begin() as conn:
        for channel, monthly_spend in spend_map.items():
            conn.execute(
                text("""
                    UPDATE staging.stg_channel_summary
                    SET
                        estimated_monthly_spend = :spend,
                        estimated_cac = CASE
                            WHEN new_customers > 0
                            THEN ROUND(:spend_num / new_customers::NUMERIC, 2)
                            ELSE NULL
                        END
                    WHERE channel = :channel
                """), {"spend": monthly_spend, "spend_num": monthly_spend, "channel": channel}
            )
            log.info(f"    {channel:<20} spend = ₹{monthly_spend:>10,}")

    # Report resulting CAC values
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT channel, new_customers, estimated_monthly_spend, estimated_cac
            FROM staging.stg_channel_summary
            ORDER BY estimated_cac DESC NULLS LAST
        """)).fetchall()

    log.info("")
    log.info("  ── Channel CAC Summary ─────────────────────────────")
    log.info(f"  {'Channel':<20} {'New Customers':>14} {'Spend (₹)':>12} {'CAC (₹)':>10}")
    log.info(f"  {'─'*20} {'─'*14} {'─'*12} {'─'*10}")
    for row in rows:
        cac_display = f"₹{row[3]:>9,.2f}" if row[3] else "     N/A"
        log.info(
            f"  {row[0]:<20} {row[1]:>14} "
            f"  ₹{int(row[2] or 0):>9,} {cac_display}"
        )
    log.info("")


def report_staging_counts(engine) -> None:
    """Print row counts for all staging tables."""
    tables = [
        "stg_orders", "stg_order_items", "stg_order_payments",
        "stg_products", "stg_customers",
        "stg_marketing_leads", "stg_closed_deals", "stg_channel_summary",
    ]
    log.info("  ── Staging Table Row Counts ────────────────────────")
    with engine.connect() as conn:
        for tbl in tables:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM staging.{tbl}")
            ).scalar()
            log.info(f"  staging.{tbl:<30} {result:>8,} rows")
    log.info("")


def main() -> None:
    log.info("═" * 60)
    log.info("  STAGE 2: raw → staging transformation")
    log.info("═" * 60)

    cfg    = load_config()
    engine = build_engine(cfg)

    sql_path = PROJECT_ROOT / cfg["paths"]["sql_dir"] / "staging" / "02_create_staging_schema.sql"
    log.info("Running staging SQL …")
    run_sql_file(engine, sql_path)

    inject_marketing_spend(engine, cfg)
    report_staging_counts(engine)

    log.info("  Stage 2 complete. Run pipeline/03_run_analytics.py next.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
