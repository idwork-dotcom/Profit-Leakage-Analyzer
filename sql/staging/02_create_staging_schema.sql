-- =============================================================
-- FILE:    sql/staging/02_create_staging_schema.sql
-- LAYER:   Staging
-- PURPOSE: Cleansed, typed, and business-filtered tables.
--          Only completed order cycles (delivered + returned)
--          are retained. All TEXT columns are cast to proper types.
--          Business logic begins here — COGS derivation, payment
--          fee computation, first-order flagging, and channel
--          funnel aggregation.
-- DEPENDS ON: raw schema must be populated first (01_load_raw.py)
-- RUN VIA:    pipeline/02_run_staging.py
-- =============================================================

CREATE SCHEMA IF NOT EXISTS staging;


-- -------------------------------------------------------------
-- TABLE: staging.stg_orders
-- SOURCE: raw.orders
-- FILTER: order_status IN ('delivered', 'returned')
--         Canceled and in-transit orders are excluded.
-- PURPOSE: Clean order header with parsed timestamps, derived
--          delivery performance metrics, order sequence rank
--          per customer, and return/discount flags.
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_orders CASCADE;
CREATE TABLE staging.stg_orders AS
SELECT
    order_id,
    customer_id,
    order_status,

    -- Parsed timestamps
    order_purchase_timestamp::TIMESTAMP                                AS order_purchase_at,
    order_approved_at::TIMESTAMP                                       AS order_approved_at,
    order_delivered_carrier_date::TIMESTAMP                            AS shipped_at,
    order_delivered_customer_date::TIMESTAMP                           AS delivered_at,
    order_estimated_delivery_date::TIMESTAMP                           AS estimated_delivery_at,
    DATE(order_purchase_timestamp::TIMESTAMP)                          AS order_date,
    DATE_TRUNC('month', order_purchase_timestamp::TIMESTAMP)::DATE     AS order_month,

    -- Financials
    COALESCE(order_discount_amount::NUMERIC, 0)                        AS discount_amount,
    order_channel,

    -- Return flag: order was delivered but later returned
    (order_status = 'returned')                                        AS return_flag,

    -- Delivery delay: positive = arrived late, negative = arrived early
    CASE
        WHEN order_delivered_customer_date IS NOT NULL
         AND order_estimated_delivery_date IS NOT NULL
        THEN EXTRACT(DAY FROM (
                order_delivered_customer_date::TIMESTAMP
                - order_estimated_delivery_date::TIMESTAMP
             ))::INT
        ELSE NULL
    END                                                                AS delivery_delay_days,

    -- Late delivery flag (meaningful for logistics cost analysis)
    CASE
        WHEN order_delivered_customer_date IS NOT NULL
         AND order_estimated_delivery_date IS NOT NULL
         AND order_delivered_customer_date::TIMESTAMP
             > order_estimated_delivery_date::TIMESTAMP
        THEN TRUE ELSE FALSE
    END                                                                AS is_late_delivery,

    -- Approval-to-ship lag in hours (operational efficiency metric)
    CASE
        WHEN order_approved_at IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM (
                order_approved_at::TIMESTAMP
                - order_purchase_timestamp::TIMESTAMP
             )) / 3600.0, 2)
        ELSE NULL
    END                                                                AS approval_lag_hours,

    -- Customer order sequence: 1 = this customer's first-ever order
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY order_purchase_timestamp::TIMESTAMP
    )                                                                  AS customer_order_seq

FROM raw.orders
WHERE order_status IN ('delivered', 'returned');

ALTER TABLE staging.stg_orders ADD PRIMARY KEY (order_id);


-- -------------------------------------------------------------
-- TABLE: staging.stg_order_items
-- SOURCE: raw.order_items joined with raw.products
-- FILTER: Only items whose order_id exists in stg_orders
-- PURPOSE: Line items enriched with product category and COGS.
--          COGS derivation: unit_cogs = price × estimated_cost_ratio
--          Freight is sourced directly at item level (no allocation).
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_order_items CASCADE;
CREATE TABLE staging.stg_order_items AS
SELECT
    oi.order_id,
    oi.order_item_id::INT                                              AS order_item_id,
    oi.product_id,
    oi.seller_id,

    -- Product attributes from dimension
    p.product_category_name                                            AS category,
    p.estimated_cost_ratio::NUMERIC                                    AS cost_ratio,

    -- Revenue
    ROUND(oi.price::NUMERIC, 2)                                        AS selling_price,

    -- COGS: derived from product-level cost ratio applied to actual transaction price
    ROUND(oi.price::NUMERIC * p.estimated_cost_ratio::NUMERIC, 2)     AS unit_cogs,

    -- Logistics: item-level freight from source (no order-level allocation needed)
    ROUND(oi.freight_value::NUMERIC, 2)                               AS logistics_cost,

    -- Gross profit = revenue - COGS (before logistics, fees, returns, CAC)
    ROUND(
        oi.price::NUMERIC
        - (oi.price::NUMERIC * p.estimated_cost_ratio::NUMERIC),
        2
    )                                                                  AS gross_profit,

    -- Gross margin % (product-level efficiency indicator)
    ROUND((1 - p.estimated_cost_ratio::NUMERIC) * 100, 2)            AS gross_margin_pct

FROM raw.order_items oi
-- Restrict to completed order cycles only
INNER JOIN staging.stg_orders so ON oi.order_id = so.order_id
-- Enrich with product dimension for COGS and category
LEFT JOIN raw.products p ON oi.product_id = p.product_id;


-- -------------------------------------------------------------
-- TABLE: staging.stg_order_payments
-- SOURCE: raw.order_payments
-- FILTER: Only orders in stg_orders
-- PURPOSE: Aggregate multi-row payment records to order level.
--          Compute total payment fee weighted by payment type rate.
-- Fee rates (set in config/settings.yaml):
--   credit_card: 2.5% | debit_card: 1.5% | upi: 0.5% | voucher: 0%
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_order_payments CASCADE;
CREATE TABLE staging.stg_order_payments AS
SELECT
    p.order_id,

    -- Number of payment rows (>1 indicates a split payment)
    COUNT(*)                                                           AS payment_count,

    -- Dominant payment method (highest single payment value)
    (ARRAY_AGG(p.payment_type ORDER BY p.payment_value::NUMERIC DESC))[1]
                                                                       AS primary_payment_type,

    -- Max installments chosen (proxy for customer affordability)
    MAX(p.payment_installments::INT)                                   AS max_installments,

    -- Total amount paid across all methods
    ROUND(SUM(p.payment_value::NUMERIC), 2)                           AS total_payment_value,

    -- Payment gateway fee: weighted sum across all payment method rows
    ROUND(SUM(
        p.payment_value::NUMERIC * CASE p.payment_type
            WHEN 'credit_card' THEN 0.025
            WHEN 'debit_card'  THEN 0.015
            WHEN 'upi'         THEN 0.005
            WHEN 'voucher'     THEN 0.000
            ELSE                    0.020  -- fallback for unmapped types
        END
    ), 2)                                                              AS total_payment_fee,

    -- Effective blended fee rate for the full order
    ROUND(
        SUM(p.payment_value::NUMERIC * CASE p.payment_type
                WHEN 'credit_card' THEN 0.025
                WHEN 'debit_card'  THEN 0.015
                WHEN 'upi'         THEN 0.005
                WHEN 'voucher'     THEN 0.000
                ELSE                    0.020
            END
        ) / NULLIF(SUM(p.payment_value::NUMERIC), 0) * 100,
        3
    )                                                                  AS effective_fee_rate_pct

FROM raw.order_payments p
INNER JOIN staging.stg_orders so ON p.order_id = so.order_id
GROUP BY p.order_id;

ALTER TABLE staging.stg_order_payments ADD PRIMARY KEY (order_id);


-- -------------------------------------------------------------
-- TABLE: staging.stg_products
-- SOURCE: raw.products
-- PURPOSE: Clean product dimension with physical attributes,
--          derived volumetric weight, and price range midpoint.
--          Reference table for COGS ratios used in stg_order_items.
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_products CASCADE;
CREATE TABLE staging.stg_products AS
SELECT
    product_id,
    product_category_name                                              AS category,
    product_weight_g::INT                                              AS weight_g,
    product_length_cm::INT                                             AS length_cm,
    product_height_cm::INT                                             AS height_cm,
    product_width_cm::INT                                              AS width_cm,
    product_photos_qty::INT                                            AS photos_qty,
    list_price_min::INT                                                AS list_price_min,
    list_price_max::INT                                                AS list_price_max,

    -- Midpoint of price range (useful for benchmarking actual sell price)
    ROUND((list_price_min::NUMERIC + list_price_max::NUMERIC) / 2, 2) AS avg_list_price,

    estimated_cost_ratio::NUMERIC                                      AS cost_ratio,

    -- Volumetric weight (courier standard: L × H × W ÷ 5000 cc)
    ROUND(
        (product_length_cm::NUMERIC
         * product_height_cm::NUMERIC
         * product_width_cm::NUMERIC) / 5000.0,
        3
    )                                                                  AS volumetric_weight_kg

FROM raw.products;

ALTER TABLE staging.stg_products ADD PRIMARY KEY (product_id);


-- -------------------------------------------------------------
-- TABLE: staging.stg_customers
-- SOURCE: raw.customers
-- PURPOSE: Clean customer dimension with segment and acquisition
--          channel. Used for cohort analysis and CAC attribution.
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_customers CASCADE;
CREATE TABLE staging.stg_customers AS
SELECT
    customer_id,
    customer_unique_id,
    customer_city,
    customer_state,
    customer_segment,      -- Mass | Mid Value | High Value
    acquisition_channel    -- Channel that originally acquired this customer
FROM raw.customers;

ALTER TABLE staging.stg_customers ADD PRIMARY KEY (customer_id);


-- -------------------------------------------------------------
-- TABLE: staging.stg_marketing_leads
-- SOURCE: raw.marketing_qualified_leads
-- PURPOSE: Lead-level records by channel and contact date.
--          The detailed base for channel funnel aggregation.
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_marketing_leads CASCADE;
CREATE TABLE staging.stg_marketing_leads AS
SELECT
    mql_id,
    origin                                                             AS channel,
    first_contact_date::DATE                                           AS first_contact_date,
    DATE_TRUNC('month', first_contact_date::DATE)::DATE               AS lead_month
FROM raw.marketing_qualified_leads;


-- -------------------------------------------------------------
-- TABLE: staging.stg_closed_deals
-- SOURCE: raw.closed_deals + raw.marketing_qualified_leads
-- PURPOSE: Converted deals enriched with originating channel
--          and days-to-close velocity metrics.
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_closed_deals CASCADE;
CREATE TABLE staging.stg_closed_deals AS
SELECT
    cd.mql_id,
    cd.seller_id,
    cd.won_date::DATE                                                  AS won_date,
    DATE_TRUNC('month', cd.won_date::DATE)::DATE                      AS won_month,
    cd.business_segment,
    cd.lead_type,
    cd.business_type,
    cd.declared_monthly_revenue::NUMERIC                              AS declared_monthly_revenue,
    mql.origin                                                         AS channel,
    mql.first_contact_date::DATE                                       AS first_contact_date,
    -- Sales velocity: days from first contact to deal close
    (cd.won_date::DATE - mql.first_contact_date::DATE)               AS days_to_close
FROM raw.closed_deals cd
LEFT JOIN raw.marketing_qualified_leads mql ON cd.mql_id = mql.mql_id;


-- -------------------------------------------------------------
-- TABLE: staging.stg_channel_summary
-- SOURCE: stg_marketing_leads + stg_closed_deals + stg_customers
-- PURPOSE: Channel-level marketing funnel summary.
--          Aggregates lead volume, conversions, and new customers
--          per channel. CAC is computed by the pipeline after
--          injecting estimated_monthly_spend from settings.yaml.
-- NOTE:    estimated_monthly_spend and estimated_cac columns are
--          populated by pipeline/02_run_staging.py via UPDATE.
-- -------------------------------------------------------------
DROP TABLE IF EXISTS staging.stg_channel_summary CASCADE;
CREATE TABLE staging.stg_channel_summary AS
WITH leads_by_channel AS (
    SELECT channel, COUNT(*) AS total_leads
    FROM staging.stg_marketing_leads
    GROUP BY channel
),
deals_by_channel AS (
    SELECT channel, COUNT(*) AS total_deals
    FROM staging.stg_closed_deals
    GROUP BY channel
),
-- New customers: distinct customers who placed at least one order
new_customers_by_channel AS (
    SELECT
        c.acquisition_channel           AS channel,
        COUNT(DISTINCT c.customer_id)   AS new_customers
    FROM staging.stg_customers c
    WHERE EXISTS (
        SELECT 1 FROM staging.stg_orders o
        WHERE o.customer_id = c.customer_id
    )
    GROUP BY c.acquisition_channel
)
SELECT
    COALESCE(l.channel, d.channel, n.channel)     AS channel,
    COALESCE(l.total_leads, 0)                    AS total_leads,
    COALESCE(d.total_deals, 0)                    AS total_deals,
    COALESCE(n.new_customers, 0)                  AS new_customers,

    -- Lead-to-deal conversion rate (funnel health indicator)
    ROUND(
        COALESCE(d.total_deals, 0)::NUMERIC
        / NULLIF(COALESCE(l.total_leads, 0), 0) * 100,
        2
    )                                             AS lead_conversion_rate_pct,

    -- Populated by pipeline/02_run_staging.py from config/settings.yaml
    NULL::NUMERIC                                 AS estimated_monthly_spend,
    NULL::NUMERIC                                 AS estimated_cac

FROM leads_by_channel l
FULL OUTER JOIN deals_by_channel d   ON l.channel = d.channel
FULL OUTER JOIN new_customers_by_channel n
    ON COALESCE(l.channel, d.channel) = n.channel;

ALTER TABLE staging.stg_channel_summary ADD PRIMARY KEY (channel);
