"""
pipeline/run_pipeline.py
========================
Master pipeline runner — executes all three stages in sequence.

Usage:
    python pipeline/run_pipeline.py

Stages:
    Stage 1  →  01_load_raw.py       CSV → raw schema
    Stage 2  →  02_run_staging.py    raw → staging (clean + enrich)
    Stage 3  →  03_run_analytics.py  staging → analytics (fact + rollups)
"""

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).resolve().parent
STAGES = [
    ("Stage 1 — CSV Ingestion",       PIPELINE_DIR / "01_load_raw.py"),
    ("Stage 2 — Staging Transform",   PIPELINE_DIR / "02_run_staging.py"),
    ("Stage 3 — Analytics Build",     PIPELINE_DIR / "03_run_analytics.py"),
]


def run_stage(label: str, script: Path) -> bool:
    log.info("")
    log.info("▶" * 60)
    log.info(f"  {label}")
    log.info("▶" * 60)
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=False,
    )
    if result.returncode != 0:
        log.error(f"  ✗ {label} FAILED (exit code {result.returncode})")
        return False
    log.info(f"  ✓ {label} completed successfully.")
    return True


def main() -> None:
    log.info("=" * 60)
    log.info("  Profit Leakage Analyzer — Full Pipeline Run")
    log.info("=" * 60)

    for label, script in STAGES:
        success = run_stage(label, script)
        if not success:
            log.error("  Pipeline aborted. Fix the error above and re-run.")
            sys.exit(1)

    log.info("")
    log.info("=" * 60)
    log.info("  All stages complete. Database is ready.")
    log.info("  Launch dashboard: streamlit run dashboard/app.py")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
