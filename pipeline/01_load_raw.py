"""
pipeline/01_load_raw.py
=======================
Stage 1: CSV Ingestion into raw schema.

Reads each source CSV from the configured data directory and
loads it into the corresponding raw.* PostgreSQL table.
Uses pandas + SQLAlchemy for portable, server-side-path-free loading.

Run:
    python pipeline/01_load_raw.py
"""

import sys
import logging
from pathlib import Path

import pandas as pd
import yaml
from sqlalchemy import create_engine, text

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Resolve project root and config ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "settings.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def build_engine(cfg: dict):
    db = cfg["database"]
    url = (
        f"postgresql+psycopg2://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['name']}"
    )
    return create_engine(url)


def run_sql_file(engine, sql_path: Path) -> None:
    """Execute a multi-statement SQL file against the database."""
    sql = sql_path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    log.info(f"Executed: {sql_path.name}")


def load_csv_to_raw(engine, csv_path: Path, table_name: str) -> int:
    """
    Load a CSV file into a raw schema table.
    All values are loaded as strings to match the TEXT column definitions.
    Existing rows are replaced on each run (if_exists='replace' is NOT used
    here — table structure is preserved, only data is refreshed via TRUNCATE).
    """
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    # Replace empty strings with None (→ NULL in PostgreSQL)
    df = df.replace("", None)

    row_count = len(df)
    log.info(f"  Loading {csv_path.name} → raw.{table_name}  ({row_count:,} rows)")

    with engine.begin() as conn:
        # Truncate first so raw tables are idempotent (safe to re-run)
        conn.execute(text(f"TRUNCATE TABLE raw.{table_name}"))

    df.to_sql(
        name=table_name,
        schema="raw",
        con=engine,
        if_exists="append",   # table DDL already created by SQL file
        index=False,
        method="multi",
        chunksize=500,
    )
    return row_count


def main() -> None:
    log.info("═" * 60)
    log.info("  STAGE 1: CSV → raw schema ingestion")
    log.info("═" * 60)

    cfg = load_config()
    engine = build_engine(cfg)

    # ── Step 1: Create raw schema and tables ──────────────────────
    sql_dir = PROJECT_ROOT / cfg["paths"]["sql_dir"]
    raw_sql  = sql_dir / "raw" / "01_create_raw_schema.sql"
    log.info("Creating raw schema tables …")
    run_sql_file(engine, raw_sql)

    # ── Step 2: Load each CSV ─────────────────────────────────────
    data_dir = PROJECT_ROOT / cfg["paths"]["raw_data_dir"]
    csv_map  = cfg["csv_files"]          # table_name → filename

    if not data_dir.exists():
        log.error(f"Data directory not found: {data_dir}")
        sys.exit(1)

    total_rows = 0
    results    = []

    for table_name, filename in csv_map.items():
        csv_path = data_dir / filename
        if not csv_path.exists():
            log.warning(f"  MISSING: {csv_path} — skipping {table_name}")
            results.append((table_name, filename, "MISSING", 0))
            continue
        try:
            rows = load_csv_to_raw(engine, csv_path, table_name)
            total_rows += rows
            results.append((table_name, filename, "OK", rows))
        except Exception as exc:
            log.error(f"  FAILED loading {filename}: {exc}")
            results.append((table_name, filename, "ERROR", 0))

    # ── Summary report ────────────────────────────────────────────
    log.info("")
    log.info("── Ingestion Summary ──────────────────────────────────")
    log.info(f"  {'Table':<35} {'File':<40} {'Status':<8} {'Rows':>8}")
    log.info(f"  {'─'*35} {'─'*40} {'─'*8} {'─'*8}")
    for table, filename, status, rows in results:
        log.info(f"  {('raw.' + table):<35} {filename:<40} {status:<8} {rows:>8,}")
    log.info(f"  {'─'*93}")
    log.info(f"  {'TOTAL':>84} {total_rows:>8,}")
    log.info("")
    log.info("  Stage 1 complete. Run pipeline/02_run_staging.py next.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
