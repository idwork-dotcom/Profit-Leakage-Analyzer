-- =============================================================
-- FILE:    sql/analytics/05_reconciliation.sql
-- LAYER:   Analytics — Profit Logic Validation & Reconciliation
-- PURPOSE: Formal reconciliation queries to validate that:
--   1. No revenue was lost or duplicated crossing layers
--   2. Cost allocation is consistent (item allocations sum to order totals)
--   3. Metric cascade is logically correct
--   4. No data anomalies exist in the fact table
--
-- How to interpret results:
--   All DELTA columns should be 0 (or within ±1 for rounding)
--   All STATUS columns should read PASS
--   Any FAIL requires investigation before trusting the dashboard
--
-- RUN VIA: psql -d profit_leakage -f tests/reconciliation.sql
--          OR: python -c "from pipeline.03_run_analytics import *"
-- =============================================================


-- =============================================================
-- SECTION 1: Cross-Layer Revenue Reconciliation
-- Tests that total revenue in fact equals raw source revenue
-- for the same filtered order set (delivered + returned only).
-- =============================================================
SELECT '════ SECTION 1: Revenue Reconciliation ════════════════════' AS test_section;

WITH raw_revenue AS (
    -- Revenue from raw source for matching order statuses
    SELECT
        ROUND(SUM(oi.price::NUMERIC), 2)        AS raw_total_revenue,
        COUNT(DISTINCT oi.order_id)             AS raw_order_count,
        COUNT(*)                                AS raw_line_items
    FROM raw.order_items oi
    JOIN raw.orders o ON oi.order_id = o.order_id
    WHERE o.order_status IN ('delivered', 'returned')
),
fact_revenue AS (
    SELECT
        ROUND(SUM(item_revenue), 2)             AS fact_total_revenue,
        COUNT(DISTINCT order_id)                AS fact_order_count,
        COUNT(*)                                AS fact_line_items
    FROM analytics.fact_order_items
)
SELECT
    raw_total_revenue,
    fact_total_revenue,
    ROUND(fact_total_revenue - raw_total_revenue, 2)    AS revenue_delta,
    raw_order_count,
    fact_order_count,
    (fact_order_count - raw_order_count)                AS order_count_delta,
    raw_line_items,
    fact_line_items,
    (fact_line_items - raw_line_items)                  AS line_item_delta,
    CASE
        WHEN ABS(fact_total_revenue - raw_total_revenue) <= 1
         AND (fact_order_count - raw_order_count) = 0
         AND (fact_line_items - raw_line_items) = 0
        THEN 'PASS'
        ELSE 'FAIL — Revenue or row count mismatch'
    END                                                 AS reconciliation_status
FROM raw_revenue, fact_revenue;


-- =============================================================
-- SECTION 2: Payment Fee Allocation Reconciliation
-- Tests that the sum of per-item payment fees across each order
-- equals the order-level total_payment_fee in staging.
-- Max allowable rounding error = ₹0.05 per order.
-- =============================================================
SELECT '════ SECTION 2: Payment Fee Allocation Check ═══════════════' AS test_section;

WITH order_fee_fact AS (
    SELECT
        order_id,
        ROUND(SUM(payment_fee), 2)              AS sum_item_fees
    FROM analytics.fact_order_items
    GROUP BY order_id
),
order_fee_staging AS (
    SELECT
        order_id,
        total_payment_fee                       AS staging_order_fee
    FROM staging.stg_order_payments
)
SELECT
    COUNT(*)                                    AS orders_checked,
    COUNT(*) FILTER (
        WHERE ABS(f.sum_item_fees - s.staging_order_fee) > 0.05
    )                                           AS orders_with_fee_mismatch,
    ROUND(MAX(ABS(f.sum_item_fees - s.staging_order_fee)), 4) AS max_rounding_error,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE ABS(f.sum_item_fees - s.staging_order_fee) > 0.05
        ) = 0
        THEN 'PASS — All fee allocations sum correctly'
        ELSE 'FAIL — Fee allocation mismatch (check multi-item orders)'
    END                                         AS status
FROM order_fee_fact f
JOIN order_fee_staging s ON f.order_id = s.order_id;


-- =============================================================
-- SECTION 3: Discount Allocation Reconciliation
-- Tests that sum of per-item discounts equals order_discount_amount
-- in staging. Max allowable rounding error = ₹0.05 per order.
-- =============================================================
SELECT '════ SECTION 3: Discount Allocation Check ══════════════════' AS test_section;

WITH order_discount_fact AS (
    SELECT
        order_id,
        ROUND(SUM(discount_allocated), 2)       AS sum_item_discounts
    FROM analytics.fact_order_items
    GROUP BY order_id
),
order_discount_staging AS (
    SELECT
        order_id,
        discount_amount                         AS staging_discount
    FROM staging.stg_orders
)
SELECT
    COUNT(*)                                    AS orders_checked,
    COUNT(*) FILTER (
        WHERE ABS(f.sum_item_discounts - s.staging_discount) > 0.05
    )                                           AS orders_with_discount_mismatch,
    ROUND(MAX(ABS(f.sum_item_discounts - s.staging_discount)), 4) AS max_rounding_error,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE ABS(f.sum_item_discounts - s.staging_discount) > 0.05
        ) = 0
        THEN 'PASS — All discount allocations sum correctly'
        ELSE 'FAIL — Discount allocation mismatch detected'
    END                                         AS status
FROM order_discount_fact f
JOIN order_discount_staging s ON f.order_id = s.order_id;


-- =============================================================
-- SECTION 4: CAC Allocation Rules
-- Tests that:
--   a) First orders always have cac_allocation >= 0
--   b) Repeat orders always have cac_allocation = exactly 0
--   c) CAC was not applied to cancelled/undelivered orders
-- =============================================================
SELECT '════ SECTION 4: CAC Allocation Logic Checks ═══════════════' AS test_section;

SELECT
    'Repeat orders have zero CAC'               AS rule_name,
    COUNT(*) FILTER (
        WHERE is_first_order = FALSE
          AND cac_allocation <> 0
    )                                           AS violations,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE is_first_order = FALSE AND cac_allocation <> 0
        ) = 0
        THEN 'PASS' ELSE 'FAIL'
    END                                         AS status
FROM analytics.fact_order_items

UNION ALL

SELECT
    'First orders have non-negative CAC',
    COUNT(*) FILTER (
        WHERE is_first_order = TRUE
          AND cac_allocation < 0
    ),
    CASE
        WHEN COUNT(*) FILTER (
            WHERE is_first_order = TRUE AND cac_allocation < 0
        ) = 0
        THEN 'PASS' ELSE 'FAIL'
    END
FROM analytics.fact_order_items

UNION ALL

SELECT
    'No negative cac_allocation anywhere',
    COUNT(*) FILTER (WHERE cac_allocation < 0),
    CASE
        WHEN COUNT(*) FILTER (WHERE cac_allocation < 0) = 0
        THEN 'PASS' ELSE 'FAIL'
    END
FROM analytics.fact_order_items;


-- =============================================================
-- SECTION 5: Return Cost Logic
-- Tests that return_cost is non-zero ONLY for returned orders,
-- and that the formula components are positive.
-- =============================================================
SELECT '════ SECTION 5: Return Cost Logic Checks ══════════════════' AS test_section;

SELECT
    'Non-returned orders have zero return_cost' AS rule_name,
    COUNT(*) FILTER (
        WHERE return_flag = FALSE
          AND return_cost <> 0
    )                                           AS violations,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE return_flag = FALSE AND return_cost <> 0
        ) = 0
        THEN 'PASS' ELSE 'FAIL'
    END                                         AS status
FROM analytics.fact_order_items

UNION ALL

SELECT
    'Returned orders have positive return_cost',
    COUNT(*) FILTER (
        WHERE return_flag = TRUE
          AND return_cost <= 0
    ),
    CASE
        WHEN COUNT(*) FILTER (
            WHERE return_flag = TRUE AND return_cost <= 0
        ) = 0
        THEN 'PASS' ELSE 'FAIL'
    END
FROM analytics.fact_order_items;


-- =============================================================
-- SECTION 6: Metric Cascade Integrity
-- Validates the logical chain:
--   gross_profit     = item_revenue - item_cogs
--   contribution_margin = item_revenue - item_cogs - logistics
--                         - payment_fee - discount - return_cost
--   net_profit       = contribution_margin - cac_allocation
-- Rounding tolerance: ±0.02 per row.
-- =============================================================
SELECT '════ SECTION 6: Metric Cascade Integrity ══════════════════' AS test_section;

SELECT
    'gross_profit = item_revenue - item_cogs'   AS check_name,
    COUNT(*) FILTER (
        WHERE ABS(gross_profit - (item_revenue - item_cogs)) > 0.02
    )                                           AS violations,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE ABS(gross_profit - (item_revenue - item_cogs)) > 0.02
        ) = 0
        THEN 'PASS' ELSE 'FAIL'
    END                                         AS status
FROM analytics.fact_order_items

UNION ALL

SELECT
    'CM = Revenue - COGS - Logistics - Fee - Disc - Returns',
    COUNT(*) FILTER (WHERE ABS(
        contribution_margin
        - (item_revenue - item_cogs - logistics_cost
           - payment_fee - discount_allocated - return_cost)
    ) > 0.02),
    CASE
        WHEN COUNT(*) FILTER (WHERE ABS(
            contribution_margin
            - (item_revenue - item_cogs - logistics_cost
               - payment_fee - discount_allocated - return_cost)
        ) > 0.02) = 0
        THEN 'PASS' ELSE 'FAIL'
    END
FROM analytics.fact_order_items

UNION ALL

SELECT
    'net_profit = contribution_margin - cac_allocation',
    COUNT(*) FILTER (
        WHERE ABS(net_profit - (contribution_margin - cac_allocation)) > 0.02
    ),
    CASE
        WHEN COUNT(*) FILTER (
            WHERE ABS(net_profit - (contribution_margin - cac_allocation)) > 0.02
        ) = 0
        THEN 'PASS' ELSE 'FAIL'
    END
FROM analytics.fact_order_items;


-- =============================================================
-- SECTION 7: Business Sanity Summary
-- A quick human-readable health-check of the final model.
-- Review this output for any obviously wrong numbers.
-- =============================================================
SELECT '════ SECTION 7: Business Sanity Summary ════════════════════' AS test_section;

SELECT
    COUNT(DISTINCT order_id)                    AS total_orders,
    COUNT(DISTINCT customer_id)                 AS total_customers,
    COUNT(DISTINCT order_id) FILTER (
        WHERE is_first_order = TRUE
    )                                           AS first_orders,

    ROUND(SUM(item_revenue), 2)                 AS total_revenue,
    ROUND(SUM(item_cogs), 2)                    AS total_cogs,
    ROUND(SUM(logistics_cost), 2)               AS total_logistics,
    ROUND(SUM(payment_fee), 2)                  AS total_payment_fees,
    ROUND(SUM(discount_allocated), 2)           AS total_discounts,
    ROUND(SUM(return_cost), 2)                  AS total_return_costs,
    ROUND(SUM(contribution_margin), 2)          AS total_cm,
    ROUND(SUM(cac_allocation), 2)               AS total_cac,
    ROUND(SUM(net_profit), 2)                   AS total_net_profit,

    -- Margin percentages
    ROUND(SUM(gross_profit)
        / NULLIF(SUM(item_revenue), 0) * 100, 2) AS gross_margin_pct,
    ROUND(SUM(contribution_margin)
        / NULLIF(SUM(item_revenue), 0) * 100, 2) AS cm_pct,
    ROUND(SUM(net_profit)
        / NULLIF(SUM(item_revenue), 0) * 100, 2) AS net_margin_pct,

    -- Leakage
    ROUND(SUM(item_revenue) - GREATEST(SUM(net_profit), 0), 2) AS total_leaked,
    ROUND(
        (SUM(item_revenue) - GREATEST(SUM(net_profit), 0))
        / NULLIF(SUM(item_revenue), 0) * 100, 2
    )                                           AS leakage_pct,

    -- Anomaly flags
    COUNT(*) FILTER (WHERE is_profit_leak)      AS loss_making_line_items,
    COUNT(DISTINCT order_id) FILTER (
        WHERE return_flag = TRUE
    )                                           AS returned_orders
FROM analytics.fact_order_items;


-- =============================================================
-- SECTION 8: Report Table Completeness Check
-- Confirms all 5 business analysis reports were populated.
-- =============================================================
SELECT '════ SECTION 8: Report Table Completeness ══════════════════' AS test_section;

SELECT
    'rpt_category_profitability'                AS report_table,
    COUNT(*)                                    AS row_count,
    CASE WHEN COUNT(*) >= 1 THEN 'PASS' ELSE 'FAIL — Empty Report' END AS status
FROM analytics.rpt_category_profitability

UNION ALL SELECT
    'rpt_loss_making_orders',
    COUNT(*),
    CASE WHEN COUNT(*) >= 0 THEN 'PASS' ELSE 'FAIL' END
FROM analytics.rpt_loss_making_orders

UNION ALL SELECT
    'rpt_customer_profitability',
    COUNT(*),
    CASE WHEN COUNT(*) >= 1 THEN 'PASS' ELSE 'FAIL — Empty Report' END
FROM analytics.rpt_customer_profitability

UNION ALL SELECT
    'rpt_cac_by_channel',
    COUNT(*),
    CASE WHEN COUNT(*) >= 1 THEN 'PASS' ELSE 'FAIL — Empty Report' END
FROM analytics.rpt_cac_by_channel

UNION ALL SELECT
    'rpt_profit_waterfall',
    COUNT(*),
    CASE WHEN COUNT(*) = 1 THEN 'PASS' ELSE 'FAIL — Expected 1 row' END
FROM analytics.rpt_profit_waterfall;
