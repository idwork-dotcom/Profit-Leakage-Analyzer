-- =============================================================
-- FILE:    sql/analytics/03_create_analytics_schema.sql
-- LAYER:   Analytics — Core Fact Table & Dimension Views
-- PURPOSE: Computes the full profit leakage chain at order-item
--          grain using a staged CTE approach:
--
--          item_revenue
--            − item_cogs              → gross_profit
--            − logistics_cost
--            − payment_fee            (order-level, allocated by revenue share)
--            − discount_allocated     (order-level, allocated by revenue share)
--            − return_cost            → contribution_margin
--            − cac_allocation         (first order only, by revenue share)
--                                     → net_profit → net_margin_pct
--
-- COST ALLOCATION RULES:
--   Logistics   → item-level from source. No allocation needed.
--   Payment fee → order-level. Split to items by (item_rev / order_rev).
--   Discount    → order-level. Split to items by (item_rev / order_rev).
--   CAC         → channel-level per new customer. Charged only on
--                 customer's first order, split by (item_rev / order_rev).
--   Return cost → item-level. Only for returned orders:
--                 reverse_freight + 10% of COGS as restocking fee.
--
-- DEPENDS ON: staging schema fully populated (02_run_staging.py run first)
-- RUN VIA:    pipeline/03_run_analytics.py
-- =============================================================

CREATE SCHEMA IF NOT EXISTS analytics;


-- =============================================================
-- STEP 1: FACT TABLE  analytics.fact_order_items
-- GRAIN:  One row per order-item (order_id + order_item_id)
-- =============================================================
DROP TABLE IF EXISTS analytics.fact_order_items CASCADE;
CREATE TABLE analytics.fact_order_items AS

WITH

-- ── CTE 1: Order-level revenue total ──────────────────────────
-- Used as the denominator for proportional cost allocation.
-- Both payment_fee and discount are at order level; we split
-- them across items in proportion to each item's revenue share.
order_totals AS (
    SELECT
        order_id,
        SUM(selling_price)                      AS order_total_revenue,
        COUNT(*)                                AS item_count
    FROM staging.stg_order_items
    GROUP BY order_id
),

-- ── CTE 2: Return cost per item ───────────────────────────────
-- ASSUMPTION: return_cost = reverse freight + 10% COGS restocking.
-- Rationale: reverse logistics mirrors the forward shipping cost;
-- 10% restocking covers inspection, repackaging, and write-down risk.
-- For non-returned orders: return_cost = 0.
return_costs AS (
    SELECT
        oi.order_id,
        oi.order_item_id,
        CASE
            WHEN o.return_flag = TRUE
            THEN ROUND(
                oi.logistics_cost                    -- reverse freight
                + (oi.unit_cogs * 0.10),             -- restocking fee
                2
            )
            ELSE 0.00
        END                                     AS return_cost
    FROM staging.stg_order_items oi
    JOIN staging.stg_orders o ON oi.order_id = o.order_id
),

-- ── CTE 3: CAC per new customer by channel ────────────────────
-- ASSUMPTION: CAC = estimated monthly spend / new customers acquired
-- on that channel. Estimated spend is injected from config/settings.yaml
-- by pipeline/02_run_staging.py. Channels with zero spend have CAC = 0,
-- meaning their orders will still show contribution_margin = net_profit
-- (no acquisition cost deducted).
channel_cac AS (
    SELECT
        channel,
        COALESCE(estimated_cac, 0)              AS cac_per_new_customer
    FROM staging.stg_channel_summary
),

-- ── CTE 4: Raw join base — all source columns in one place ────
-- This CTE assembles every column needed before any metric
-- calculations. Keeping joins here (not in the final SELECT)
-- makes the metric CTEs below readable and formula-only.
base AS (
    SELECT
        -- Keys
        oi.order_id,
        oi.order_item_id,
        o.customer_id,
        oi.product_id,
        oi.seller_id,

        -- Time
        o.order_date,
        o.order_month,
        EXTRACT(YEAR    FROM o.order_date)::INT AS order_year,
        EXTRACT(QUARTER FROM o.order_date)::INT AS order_quarter,
        TO_CHAR(o.order_date, 'Mon YYYY')       AS month_label,

        -- Dimensions
        oi.category,
        c.customer_segment,
        c.customer_state,
        o.order_channel,
        c.acquisition_channel,
        pay.primary_payment_type,

        -- Flags
        o.return_flag,
        o.is_late_delivery,
        o.customer_order_seq,
        (o.customer_order_seq = 1)              AS is_first_order,

        -- Revenue (Metric 1)
        oi.selling_price                        AS item_revenue,

        -- COGS (Metric 2)
        -- unit_cogs = selling_price × estimated_cost_ratio (from products)
        oi.unit_cogs                            AS item_cogs,
        oi.gross_profit,
        oi.gross_margin_pct,

        -- Logistics (Metric 3) — item-level, no allocation needed
        oi.logistics_cost,

        -- Return cost from CTE 2
        rc.return_cost,

        -- Order-level values used for allocation denominators
        pay.total_payment_fee                   AS order_payment_fee,
        o.discount_amount                       AS order_discount,
        ot.order_total_revenue,
        ot.item_count,

        -- CAC from CTE 3
        COALESCE(cac.cac_per_new_customer, 0)   AS channel_cac

    FROM staging.stg_order_items        oi
    JOIN staging.stg_orders             o    ON oi.order_id   = o.order_id
    JOIN staging.stg_customers          c    ON o.customer_id = c.customer_id
    JOIN staging.stg_order_payments     pay  ON oi.order_id   = pay.order_id
    JOIN order_totals                   ot   ON oi.order_id   = ot.order_id
    JOIN return_costs                   rc   ON oi.order_id   = rc.order_id
                                            AND oi.order_item_id = rc.order_item_id
    LEFT JOIN channel_cac               cac  ON o.order_channel = cac.channel
),

-- ── CTE 5: Allocate order-level costs to each item ────────────
-- ALLOCATION METHOD: Each item bears a share of order-level costs
-- equal to its fraction of the order's total revenue.
-- This is the fairest attribution when item-level breakdowns
-- are not available in the source system.
--
-- Formula: item_share = item_revenue / order_total_revenue
--
-- ⚠ DOUBLE-COUNT GUARD: We divide the total order fee once and
-- allocate it across items. The SUM of all item allocations for
-- an order will equal the original order total (within rounding).
allocated AS (
    SELECT
        b.*,

        -- Revenue share of this item within its order
        ROUND(
            b.item_revenue / NULLIF(b.order_total_revenue, 0),
            6
        )                                                AS item_revenue_share,

        -- Payment fee allocation (Metric 4)
        -- ASSUMPTION: payment fee is proportional to revenue, not item count,
        -- because gateways charge a % of transaction value.
        ROUND(
            b.order_payment_fee
            * (b.item_revenue / NULLIF(b.order_total_revenue, 0)),
            2
        )                                                AS payment_fee,

        -- Discount allocation
        -- ASSUMPTION: order-level discounts are spread proportionally.
        -- If a specific item received the discount (e.g. coupon on one SKU),
        -- this will over-spread it — accept this limitation for now.
        ROUND(
            b.order_discount
            * (b.item_revenue / NULLIF(b.order_total_revenue, 0)),
            2
        )                                                AS discount_allocated,

        -- CAC allocation (Metric 6 input)
        -- RULE: CAC only on first order. On repeat orders → 0.
        -- Rationale: the spend that acquired this customer is a sunk cost
        -- already incurred before repeat purchases. Including it in repeat
        -- orders would double-count and understate loyalty value.
        CASE
            WHEN b.customer_order_seq = 1
            THEN ROUND(
                b.channel_cac
                * (b.item_revenue / NULLIF(b.order_total_revenue, 0)),
                2
            )
            ELSE 0.00
        END                                              AS cac_allocation

    FROM base b
),

-- ── CTE 6: Build contribution margin ─────────────────────────
-- Contribution Margin = Revenue after all variable per-unit costs
-- but before customer acquisition cost.
-- This cleanly separates "is the product profitable?" from
-- "was this customer profitable to acquire?"
computed AS (
    SELECT
        a.*,
        ROUND(
            a.item_revenue
            - a.item_cogs
            - a.logistics_cost
            - a.payment_fee
            - a.discount_allocated
            - a.return_cost,
            2
        )                                                AS contribution_margin
    FROM allocated a
)

-- ── Final SELECT: Net Profit and derived margin percentages ───
SELECT
    -- Surrogate key
    (c.order_id || '-' || c.order_item_id::TEXT)        AS order_item_key,

    -- Natural keys
    c.order_id,
    c.order_item_id,
    c.customer_id,
    c.product_id,
    c.seller_id,

    -- Time dimensions
    c.order_date,
    c.order_month,
    c.order_year,
    c.order_quarter,
    c.month_label,

    -- Business dimensions
    c.category,
    c.customer_segment,
    c.customer_state,
    c.order_channel,
    c.acquisition_channel,
    c.primary_payment_type,

    -- Flags
    c.return_flag,
    c.is_late_delivery,
    c.is_first_order,
    c.customer_order_seq,
    c.item_revenue_share,

    -- ── Metric 1: Item Revenue ────────────────────────────────
    c.item_revenue,

    -- ── Metric 2: COGS ────────────────────────────────────────
    c.item_cogs,

    -- Intermediate: Gross Profit (Revenue − COGS)
    c.gross_profit,
    c.gross_margin_pct,

    -- ── Metric 3: Logistics Cost (item-level, no allocation) ─
    c.logistics_cost,

    -- ── Metric 4: Payment Fee (allocated) ────────────────────
    c.payment_fee,

    -- Discount (allocated)
    c.discount_allocated,

    -- Return Cost (zero for delivered orders)
    c.return_cost,

    -- ── Metric 5: Contribution Margin ────────────────────────
    c.contribution_margin,
    ROUND(
        c.contribution_margin / NULLIF(c.item_revenue, 0) * 100,
        2
    )                                                    AS contribution_margin_pct,

    -- ── Metric 6: CAC Allocation (first order only) ───────────
    c.cac_allocation,

    -- ── Metric 7: Net Profit (True Unit Economics) ────────────
    ROUND(c.contribution_margin - c.cac_allocation, 2)  AS net_profit,
    ROUND(
        (c.contribution_margin - c.cac_allocation)
        / NULLIF(c.item_revenue, 0) * 100,
        2
    )                                                    AS net_margin_pct,

    -- Leakage flag: TRUE if this item destroys value
    (c.contribution_margin - c.cac_allocation) < 0      AS is_profit_leak

FROM computed c;

ALTER TABLE analytics.fact_order_items ADD PRIMARY KEY (order_item_key);

CREATE INDEX idx_fact_order_id       ON analytics.fact_order_items (order_id);
CREATE INDEX idx_fact_customer_id    ON analytics.fact_order_items (customer_id);
CREATE INDEX idx_fact_category       ON analytics.fact_order_items (category);
CREATE INDEX idx_fact_order_channel  ON analytics.fact_order_items (order_channel);
CREATE INDEX idx_fact_order_month    ON analytics.fact_order_items (order_month);


-- =============================================================
-- STEP 2: DIMENSION VIEWS
-- =============================================================

-- Product dimension
DROP VIEW IF EXISTS analytics.dim_products;
CREATE VIEW analytics.dim_products AS
SELECT
    product_id,
    category,
    cost_ratio,
    list_price_min,
    list_price_max,
    avg_list_price,
    weight_g,
    volumetric_weight_kg
FROM staging.stg_products;

-- Customer dimension with order history
DROP VIEW IF EXISTS analytics.dim_customers;
CREATE VIEW analytics.dim_customers AS
SELECT
    c.customer_id,
    c.customer_unique_id,
    c.customer_city,
    c.customer_state,
    c.customer_segment,
    c.acquisition_channel,
    COUNT(o.order_id)                               AS total_orders,
    MIN(o.order_date)                               AS first_order_date,
    MAX(o.order_date)                               AS last_order_date,
    (MAX(o.order_date) - MIN(o.order_date))         AS customer_lifespan_days
FROM staging.stg_customers c
LEFT JOIN staging.stg_orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.customer_unique_id, c.customer_city,
         c.customer_state, c.customer_segment, c.acquisition_channel;


-- =============================================================
-- STEP 3: MONTHLY TREND SUMMARY (for dashboard time-series)
-- =============================================================
DROP TABLE IF EXISTS analytics.summary_by_month CASCADE;
CREATE TABLE analytics.summary_by_month AS
SELECT
    order_month,
    order_year,
    month_label,
    COUNT(DISTINCT order_id)                AS total_orders,
    COUNT(*)                                AS total_line_items,
    ROUND(SUM(item_revenue), 2)             AS total_revenue,
    ROUND(SUM(item_cogs), 2)                AS total_cogs,
    ROUND(SUM(logistics_cost), 2)           AS total_logistics,
    ROUND(SUM(payment_fee), 2)              AS total_payment_fees,
    ROUND(SUM(discount_allocated), 2)       AS total_discounts,
    ROUND(SUM(return_cost), 2)              AS total_return_costs,
    ROUND(SUM(contribution_margin), 2)      AS total_contribution_margin,
    ROUND(AVG(contribution_margin_pct), 2)  AS avg_cm_pct,
    ROUND(SUM(cac_allocation), 2)           AS total_cac,
    ROUND(SUM(net_profit), 2)               AS total_net_profit,
    ROUND(AVG(net_margin_pct), 2)           AS avg_net_margin_pct,
    COUNT(*) FILTER (WHERE is_profit_leak)  AS profit_leak_items
FROM analytics.fact_order_items
GROUP BY order_month, order_year, month_label
ORDER BY order_month;
