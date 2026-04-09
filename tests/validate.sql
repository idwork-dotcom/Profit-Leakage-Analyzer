-- =============================================================
-- FILE:    tests/validate.sql
-- PURPOSE: Basic data quality checks across all three layers.
--          Run after the full pipeline to confirm data integrity.
--          All checks return a STATUS of PASS or FAIL.
-- RUN VIA: psql -d profit_leakage -f tests/validate.sql
-- =============================================================

-- ── Utility: suppress psql row output headers for clean printing
\pset tuples_only off
\pset border 2

-- =============================================================
-- SECTION 1: Raw Layer — Row Count Checks
-- Ensures every CSV was fully loaded with expected row counts.
-- =============================================================
SELECT '═══ RAW LAYER: Row Count Checks ════════════════════════' AS check_group;

SELECT
    'raw.orders'                    AS table_name,
    COUNT(*)                        AS actual_rows,
    420                             AS expected_min,
    CASE WHEN COUNT(*) >= 420 THEN 'PASS' ELSE 'FAIL' END AS status
FROM raw.orders

UNION ALL SELECT
    'raw.order_items',              COUNT(*), 582,
    CASE WHEN COUNT(*) >= 582 THEN 'PASS' ELSE 'FAIL' END
FROM raw.order_items

UNION ALL SELECT
    'raw.order_payments',           COUNT(*), 420,
    CASE WHEN COUNT(*) >= 420 THEN 'PASS' ELSE 'FAIL' END
FROM raw.order_payments

UNION ALL SELECT
    'raw.customers',                COUNT(*), 180,
    CASE WHEN COUNT(*) >= 180 THEN 'PASS' ELSE 'FAIL' END
FROM raw.customers

UNION ALL SELECT
    'raw.products',                 COUNT(*), 12,
    CASE WHEN COUNT(*) >= 12  THEN 'PASS' ELSE 'FAIL' END
FROM raw.products

UNION ALL SELECT
    'raw.marketing_qualified_leads', COUNT(*), 4000,
    CASE WHEN COUNT(*) >= 4000 THEN 'PASS' ELSE 'FAIL' END
FROM raw.marketing_qualified_leads

UNION ALL SELECT
    'raw.closed_deals',             COUNT(*), 600,
    CASE WHEN COUNT(*) >= 600  THEN 'PASS' ELSE 'FAIL' END
FROM raw.closed_deals;


-- =============================================================
-- SECTION 2: Raw Layer — NULL Checks on Key Columns
-- Ensures primary and join keys are never NULL after ingestion.
-- =============================================================
SELECT '═══ RAW LAYER: NULL Key Checks ════════════════════════' AS check_group;

SELECT
    'raw.orders.order_id'           AS column_check,
    COUNT(*) FILTER (WHERE order_id IS NULL)    AS null_count,
    CASE WHEN COUNT(*) FILTER (WHERE order_id IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END            AS status
FROM raw.orders

UNION ALL SELECT
    'raw.orders.customer_id',
    COUNT(*) FILTER (WHERE customer_id IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE customer_id IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM raw.orders

UNION ALL SELECT
    'raw.order_items.order_id',
    COUNT(*) FILTER (WHERE order_id IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE order_id IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM raw.order_items

UNION ALL SELECT
    'raw.order_items.product_id',
    COUNT(*) FILTER (WHERE product_id IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE product_id IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM raw.order_items

UNION ALL SELECT
    'raw.order_items.price',
    COUNT(*) FILTER (WHERE price IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE price IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM raw.order_items

UNION ALL SELECT
    'raw.products.estimated_cost_ratio',
    COUNT(*) FILTER (WHERE estimated_cost_ratio IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE estimated_cost_ratio IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM raw.products

UNION ALL SELECT
    'raw.customers.acquisition_channel',
    COUNT(*) FILTER (WHERE acquisition_channel IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE acquisition_channel IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM raw.customers;


-- =============================================================
-- SECTION 3: Staging Layer — Filter Validation
-- Confirms only valid order statuses passed through.
-- =============================================================
SELECT '═══ STAGING LAYER: Filter Checks ═══════════════════════' AS check_group;

SELECT
    'No canceled orders in stg_orders'     AS check_name,
    COUNT(*) FILTER (WHERE order_status = 'canceled') AS violations,
    CASE WHEN COUNT(*) FILTER (WHERE order_status = 'canceled') = 0
         THEN 'PASS' ELSE 'FAIL' END       AS status
FROM staging.stg_orders

UNION ALL SELECT
    'No in-transit orders in stg_orders',
    COUNT(*) FILTER (WHERE order_status = 'shipped'),
    CASE WHEN COUNT(*) FILTER (WHERE order_status = 'shipped') = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM staging.stg_orders

UNION ALL SELECT
    'All stg_orders have an order_date',
    COUNT(*) FILTER (WHERE order_date IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE order_date IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM staging.stg_orders

UNION ALL SELECT
    'stg_orders customer_order_seq starts at 1',
    COUNT(*) FILTER (
        WHERE customer_order_seq < 1 OR customer_order_seq IS NULL
    ),
    CASE WHEN COUNT(*) FILTER (
        WHERE customer_order_seq < 1 OR customer_order_seq IS NULL
    ) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM staging.stg_orders;


-- =============================================================
-- SECTION 4: Staging Layer — COGS Derivation Check
-- unit_cogs must always be > 0 (cost_ratio is non-zero for all products).
-- =============================================================
SELECT '═══ STAGING LAYER: COGS Derivation Checks ══════════════' AS check_group;

SELECT
    'stg_order_items: no NULL unit_cogs'   AS check_name,
    COUNT(*) FILTER (WHERE unit_cogs IS NULL) AS violations,
    CASE WHEN COUNT(*) FILTER (WHERE unit_cogs IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END       AS status
FROM staging.stg_order_items

UNION ALL SELECT
    'stg_order_items: unit_cogs < selling_price',
    COUNT(*) FILTER (WHERE unit_cogs >= selling_price),
    CASE WHEN COUNT(*) FILTER (WHERE unit_cogs >= selling_price) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM staging.stg_order_items

UNION ALL SELECT
    'stg_order_items: gross_profit > 0 for all products',
    COUNT(*) FILTER (WHERE gross_profit <= 0),
    CASE WHEN COUNT(*) FILTER (WHERE gross_profit <= 0) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM staging.stg_order_items

UNION ALL SELECT
    'stg_order_payments: total_payment_fee >= 0',
    COUNT(*) FILTER (WHERE total_payment_fee < 0),
    CASE WHEN COUNT(*) FILTER (WHERE total_payment_fee < 0) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM staging.stg_order_payments;


-- =============================================================
-- SECTION 5: Analytics Layer — Fact Table Integrity
-- Ensures all metric columns are populated and logically correct.
-- =============================================================
SELECT '═══ ANALYTICS LAYER: Fact Table Checks ══════════════════' AS check_group;

SELECT
    'fact: no NULL item_revenue'           AS check_name,
    COUNT(*) FILTER (WHERE item_revenue IS NULL) AS violations,
    CASE WHEN COUNT(*) FILTER (WHERE item_revenue IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END       AS status
FROM analytics.fact_order_items

UNION ALL SELECT
    'fact: no NULL contribution_margin',
    COUNT(*) FILTER (WHERE contribution_margin IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE contribution_margin IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM analytics.fact_order_items

UNION ALL SELECT
    'fact: no NULL net_profit',
    COUNT(*) FILTER (WHERE net_profit IS NULL),
    CASE WHEN COUNT(*) FILTER (WHERE net_profit IS NULL) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM analytics.fact_order_items

UNION ALL SELECT
    'fact: net_profit <= contribution_margin (CAC is non-negative)',
    COUNT(*) FILTER (WHERE net_profit > contribution_margin),
    CASE WHEN COUNT(*) FILTER (WHERE net_profit > contribution_margin) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM analytics.fact_order_items

UNION ALL SELECT
    'fact: CAC = 0 for non-first orders',
    COUNT(*) FILTER (WHERE is_first_order = FALSE AND cac_allocation <> 0),
    CASE WHEN COUNT(*) FILTER (WHERE is_first_order = FALSE AND cac_allocation <> 0) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM analytics.fact_order_items

UNION ALL SELECT
    'fact: return_cost = 0 for delivered orders',
    COUNT(*) FILTER (WHERE return_flag = FALSE AND return_cost <> 0),
    CASE WHEN COUNT(*) FILTER (WHERE return_flag = FALSE AND return_cost <> 0) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM analytics.fact_order_items

UNION ALL SELECT
    'fact: order_item_key is unique (no duplicates)',
    COUNT(*) - COUNT(DISTINCT order_item_key),
    CASE WHEN COUNT(*) - COUNT(DISTINCT order_item_key) = 0
         THEN 'PASS' ELSE 'FAIL' END
FROM analytics.fact_order_items;


-- =============================================================
-- SECTION 6: Business Sanity Metrics
-- Quick health-check numbers for human review.
-- =============================================================
SELECT '═══ BUSINESS SANITY METRICS ═════════════════════════════' AS check_group;

SELECT
    COUNT(DISTINCT order_id)                               AS total_orders,
    COUNT(DISTINCT customer_id)                            AS total_customers,
    ROUND(SUM(item_revenue), 2)                            AS total_revenue,
    ROUND(SUM(net_profit), 2)                              AS total_net_profit,
    ROUND(AVG(net_margin_pct), 2)                          AS avg_net_margin_pct,
    COUNT(*) FILTER (WHERE return_flag)                    AS returned_items,
    ROUND(
        (COUNT(*) FILTER (WHERE net_profit < 0))::NUMERIC
        / NULLIF(COUNT(*), 0) * 100, 2
    )                                                      AS pct_items_losing_money
FROM analytics.fact_order_items;
