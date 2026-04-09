-- =============================================================
-- FILE:    sql/analytics/04_business_analysis.sql
-- LAYER:   Analytics — Final Business Reporting Views
-- PURPOSE: Five business-facing reporting tables built directly
--          from analytics.fact_order_items. These are the final
--          outputs that power the dashboard and answer:
--
--   1. rpt_category_profitability   → Where does profit leak by category?
--   2. rpt_loss_making_orders       → Which specific orders destroy value?
--   3. rpt_customer_profitability   → Who are the profitable customers?
--   4. rpt_cac_by_channel           → What is the true CAC per channel?
--   5. rpt_profit_waterfall         → Portfolio-level profit cascade
--
-- DEPENDS ON: analytics.fact_order_items must exist (03_create_analytics_schema.sql)
-- RUN VIA:    pipeline/03_run_analytics.py
-- =============================================================


-- =============================================================
-- REPORT 1: Category Profitability
-- Answers: "Which categories are profit drains vs. profit engines?"
-- Shows the full cost waterfall from gross revenue to net profit
-- for each product category, ranked by net profit.
-- =============================================================
DROP TABLE IF EXISTS analytics.rpt_category_profitability CASCADE;
CREATE TABLE analytics.rpt_category_profitability AS
SELECT
    category,

    -- Volume
    COUNT(*)                                    AS total_line_items,
    COUNT(DISTINCT order_id)                    AS total_orders,
    COUNT(DISTINCT customer_id)                 AS total_customers,

    -- Revenue
    ROUND(SUM(item_revenue), 2)                 AS total_revenue,

    -- Cost breakdown — absolute (INR)
    ROUND(SUM(item_cogs), 2)                    AS total_cogs,
    ROUND(SUM(logistics_cost), 2)               AS total_logistics_cost,
    ROUND(SUM(payment_fee), 2)                  AS total_payment_fees,
    ROUND(SUM(discount_allocated), 2)           AS total_discounts,
    ROUND(SUM(return_cost), 2)                  AS total_return_cost,
    ROUND(SUM(cac_allocation), 2)               AS total_cac_spend,

    -- Cost breakdown — as % of revenue (leak severity indicators)
    ROUND(SUM(item_cogs)        / NULLIF(SUM(item_revenue), 0) * 100, 2) AS cogs_pct,
    ROUND(SUM(logistics_cost)   / NULLIF(SUM(item_revenue), 0) * 100, 2) AS logistics_pct,
    ROUND(SUM(payment_fee)      / NULLIF(SUM(item_revenue), 0) * 100, 2) AS payment_fee_pct,
    ROUND(SUM(discount_allocated) / NULLIF(SUM(item_revenue), 0) * 100, 2) AS discount_pct,
    ROUND(SUM(return_cost)      / NULLIF(SUM(item_revenue), 0) * 100, 2) AS return_cost_pct,
    ROUND(SUM(cac_allocation)   / NULLIF(SUM(item_revenue), 0) * 100, 2) AS cac_pct,

    -- Profit milestones
    ROUND(SUM(gross_profit), 2)                 AS total_gross_profit,
    ROUND(SUM(gross_profit)    / NULLIF(SUM(item_revenue), 0) * 100, 2) AS gross_margin_pct,
    ROUND(SUM(contribution_margin), 2)          AS total_contribution_margin,
    ROUND(SUM(contribution_margin) / NULLIF(SUM(item_revenue), 0) * 100, 2) AS cm_pct,
    ROUND(SUM(net_profit), 2)                   AS total_net_profit,
    ROUND(AVG(net_margin_pct), 2)               AS avg_net_margin_pct,

    -- Return analysis
    COUNT(*) FILTER (WHERE return_flag)         AS returned_items,
    ROUND(
        (COUNT(*) FILTER (WHERE return_flag))::NUMERIC
        / NULLIF(COUNT(*), 0) * 100, 2
    )                                           AS return_rate_pct,

    -- Profit leakage
    ROUND(SUM(item_revenue) - GREATEST(SUM(net_profit), 0), 2) AS profit_leaked_abs,
    ROUND(
        (SUM(item_revenue) - GREATEST(SUM(net_profit), 0))
        / NULLIF(SUM(item_revenue), 0) * 100, 2
    )                                           AS leakage_pct,

    -- Primary cost driver (the biggest cost bucket for this category)
    CASE
        WHEN SUM(item_cogs)          = GREATEST(SUM(item_cogs), SUM(logistics_cost), SUM(cac_allocation), SUM(return_cost))
             THEN 'COGS'
        WHEN SUM(logistics_cost)     = GREATEST(SUM(item_cogs), SUM(logistics_cost), SUM(cac_allocation), SUM(return_cost))
             THEN 'Logistics'
        WHEN SUM(cac_allocation)     = GREATEST(SUM(item_cogs), SUM(logistics_cost), SUM(cac_allocation), SUM(return_cost))
             THEN 'CAC'
        ELSE 'Returns'
    END                                         AS primary_cost_driver,

    -- Profitability tier
    CASE
        WHEN ROUND(AVG(net_margin_pct), 2) >= 15 THEN 'High Margin'
        WHEN ROUND(AVG(net_margin_pct), 2) >= 5  THEN 'Moderate Margin'
        WHEN ROUND(AVG(net_margin_pct), 2) >= 0  THEN 'Low Margin'
        ELSE 'Loss-Making'
    END                                         AS profitability_tier

FROM analytics.fact_order_items
GROUP BY category
ORDER BY total_net_profit DESC;


-- =============================================================
-- REPORT 2: Loss-Making Orders
-- Answers: "Which specific orders are destroying profit and why?"
-- Shows every order where net_profit < 0, with the root cause.
-- Use this to identify systemic issues by category or channel.
-- =============================================================
DROP TABLE IF EXISTS analytics.rpt_loss_making_orders CASCADE;
CREATE TABLE analytics.rpt_loss_making_orders AS
WITH order_level AS (
    SELECT
        order_id,
        customer_id,
        order_date,
        order_month,
        order_channel,
        customer_segment,
        return_flag,
        is_first_order,
        MAX(category)                               AS primary_category,
        COUNT(*)                                    AS item_count,
        ROUND(SUM(item_revenue), 2)                 AS order_revenue,
        ROUND(SUM(item_cogs), 2)                    AS order_cogs,
        ROUND(SUM(logistics_cost), 2)               AS order_logistics,
        ROUND(SUM(payment_fee), 2)                  AS order_payment_fee,
        ROUND(SUM(discount_allocated), 2)           AS order_discount,
        ROUND(SUM(return_cost), 2)                  AS order_return_cost,
        ROUND(SUM(gross_profit), 2)                 AS order_gross_profit,
        ROUND(SUM(contribution_margin), 2)          AS order_contribution_margin,
        ROUND(SUM(cac_allocation), 2)               AS order_cac,
        ROUND(SUM(net_profit), 2)                   AS order_net_profit,
        ROUND(SUM(net_profit) / NULLIF(SUM(item_revenue), 0) * 100, 2) AS order_net_margin_pct
    FROM analytics.fact_order_items
    GROUP BY order_id, customer_id, order_date, order_month,
             order_channel, customer_segment, return_flag, is_first_order
)
SELECT
    order_id,
    customer_id,
    order_date,
    order_month,
    order_channel,
    customer_segment,
    primary_category,
    return_flag,
    is_first_order,
    item_count,

    -- Financials
    order_revenue,
    order_cogs,
    order_logistics,
    order_payment_fee,
    order_discount,
    order_return_cost,
    order_gross_profit,
    order_contribution_margin,
    order_cac,
    order_net_profit,
    order_net_margin_pct,

    -- Loss amount (absolute)
    ABS(order_net_profit)                           AS loss_amount,

    -- Root cause: the cost that converted a profitable CM into a loss
    -- Hierarchy: if removing any single cost would make it profitable → that's the cause
    CASE
        WHEN order_contribution_margin >= 0
         AND order_cac > order_contribution_margin THEN 'High CAC on First Order'
        WHEN return_flag = TRUE
         AND order_return_cost > (order_contribution_margin + order_cac) THEN 'Return Cost'
        WHEN order_gross_profit < 0 THEN 'Negative Gross Margin (COGS > Revenue)'
        WHEN order_discount > order_contribution_margin THEN 'Excess Discount'
        WHEN order_logistics > order_gross_profit * 0.5 THEN 'High Logistics Cost'
        ELSE 'Combined Cost Pressure'
    END                                             AS loss_root_cause,

    -- Loss severity tier
    CASE
        WHEN order_net_margin_pct < -50 THEN 'Severe   (>50% loss)'
        WHEN order_net_margin_pct < -20 THEN 'High     (20-50% loss)'
        WHEN order_net_margin_pct < -5  THEN 'Moderate (5-20% loss)'
        ELSE                                 'Marginal (<5% loss)'
    END                                             AS loss_severity

FROM order_level
WHERE order_net_profit < 0
ORDER BY order_net_profit ASC;  -- Most negative first


-- =============================================================
-- REPORT 3: Customer Profitability (LTV & Unit Economics)
-- Answers: "Which customers are worth keeping, and who costs us?"
-- Rolls up all orders per customer to compute lifetime economics.
-- The LTV/CAC ratio is the key recruiter-facing metric here.
-- =============================================================
DROP TABLE IF EXISTS analytics.rpt_customer_profitability CASCADE;
CREATE TABLE analytics.rpt_customer_profitability AS
SELECT
    f.customer_id,
    f.customer_segment,
    f.acquisition_channel,
    f.customer_state,

    -- Order history
    COUNT(DISTINCT f.order_id)                  AS total_orders,
    MIN(f.order_date)                           AS first_order_date,
    MAX(f.order_date)                           AS last_order_date,
    (MAX(f.order_date) - MIN(f.order_date))     AS customer_lifespan_days,

    -- Revenue (LTV proxy)
    ROUND(SUM(f.item_revenue), 2)               AS total_revenue,
    ROUND(SUM(f.item_revenue)
        / NULLIF(COUNT(DISTINCT f.order_id), 0), 2) AS avg_order_value,

    -- Full cost breakdown
    ROUND(SUM(f.item_cogs), 2)                  AS total_cogs,
    ROUND(SUM(f.logistics_cost), 2)             AS total_logistics,
    ROUND(SUM(f.payment_fee), 2)                AS total_payment_fees,
    ROUND(SUM(f.discount_allocated), 2)         AS total_discounts,
    ROUND(SUM(f.return_cost), 2)                AS total_return_costs,

    -- Profitability milestones
    ROUND(SUM(f.gross_profit), 2)               AS total_gross_profit,
    ROUND(SUM(f.contribution_margin), 2)        AS total_contribution_margin,

    -- CAC (total paid to acquire this customer — only on first order)
    ROUND(SUM(f.cac_allocation), 2)             AS total_cac_paid,

    -- Net profit across all orders
    ROUND(SUM(f.net_profit), 2)                 AS total_net_profit,
    ROUND(SUM(f.net_profit)
        / NULLIF(SUM(f.item_revenue), 0) * 100, 2) AS net_margin_pct,

    -- LTV/CAC ratio: measures acquisition efficiency
    -- > 3.0 = healthy, 1-3 = marginal, < 1 = money-losing customer
    -- ASSUMPTION: LTV ≈ total net_profit (single-period, no churn discount)
    ROUND(
        SUM(f.net_profit) / NULLIF(SUM(f.cac_allocation), 0),
        2
    )                                           AS ltv_cac_ratio,

    -- CAC payback: how many orders to recover acquisition cost?
    ROUND(
        SUM(f.cac_allocation)
        / NULLIF(SUM(f.contribution_margin)
            / NULLIF(COUNT(DISTINCT f.order_id), 0), 0),
        1
    )                                           AS cac_payback_orders,

    -- Return behaviour
    COUNT(DISTINCT f.order_id) FILTER (
        WHERE f.return_flag = TRUE
    )                                           AS returned_orders,

    -- Customer value tier
    CASE
        WHEN ROUND(SUM(f.net_profit), 2) >= 5000 THEN 'Champion'
        WHEN ROUND(SUM(f.net_profit), 2) >= 1000 THEN 'Profitable'
        WHEN ROUND(SUM(f.net_profit), 2) >= 0    THEN 'Breakeven'
        ELSE                                          'Loss-Making'
    END                                         AS customer_value_tier

FROM analytics.fact_order_items f
GROUP BY f.customer_id, f.customer_segment,
         f.acquisition_channel, f.customer_state
ORDER BY total_net_profit DESC;


-- =============================================================
-- REPORT 4: CAC by Channel
-- Answers: "Which channels acquire profitable customers?"
-- Links channel marketing spend → leads → conversions → customers
-- → revenue → net profit to give a channel-level unit economics view.
-- =============================================================
DROP TABLE IF EXISTS analytics.rpt_cac_by_channel CASCADE;
CREATE TABLE analytics.rpt_cac_by_channel AS
WITH

-- Channel-level order economics (from the fact table)
channel_orders AS (
    SELECT
        order_channel                           AS channel,
        COUNT(DISTINCT order_id)                AS total_orders,
        COUNT(DISTINCT customer_id)             AS total_customers,
        COUNT(DISTINCT customer_id) FILTER (
            WHERE is_first_order = TRUE
        )                                       AS new_customers,
        ROUND(SUM(item_revenue), 2)             AS total_revenue,
        ROUND(SUM(gross_profit), 2)             AS total_gross_profit,
        ROUND(SUM(logistics_cost), 2)           AS total_logistics,
        ROUND(SUM(contribution_margin), 2)      AS total_contribution_margin,
        ROUND(SUM(cac_allocation), 2)           AS total_cac_spend,
        ROUND(SUM(net_profit), 2)               AS total_net_profit,
        ROUND(AVG(net_margin_pct), 2)           AS avg_net_margin_pct,
        -- First-order economics in isolation
        ROUND(SUM(item_revenue) FILTER (
            WHERE is_first_order = TRUE
        ), 2)                                   AS first_order_revenue,
        ROUND(SUM(net_profit) FILTER (
            WHERE is_first_order = TRUE
        ), 2)                                   AS first_order_net_profit
    FROM analytics.fact_order_items
    GROUP BY order_channel
),

-- Marketing funnel data from staging
channel_funnel AS (
    SELECT
        channel,
        total_leads,
        total_deals,
        lead_conversion_rate_pct,
        estimated_monthly_spend,
        estimated_cac
    FROM staging.stg_channel_summary
)

SELECT
    co.channel,

    -- Funnel metrics
    COALESCE(cf.total_leads, 0)                 AS total_mql_leads,
    COALESCE(cf.total_deals, 0)                 AS total_deals_closed,
    COALESCE(cf.lead_conversion_rate_pct, 0)    AS lead_conversion_rate_pct,

    -- Acquisition outcomes
    co.new_customers,
    co.total_customers,
    -- Repeat customer rate (loyalty indicator)
    ROUND(
        (co.total_customers - co.new_customers)::NUMERIC
        / NULLIF(co.new_customers, 0) * 100, 2
    )                                           AS repeat_customer_rate_pct,

    -- CAC
    COALESCE(cf.estimated_monthly_spend, 0)     AS estimated_monthly_spend,
    COALESCE(cf.estimated_cac, 0)               AS estimated_cac,
    -- Actual CAC as recorded in fact table (cross-check)
    ROUND(
        co.total_cac_spend / NULLIF(co.new_customers, 0),
        2
    )                                           AS actual_cac_per_new_customer,

    -- Order economics
    co.total_orders,
    co.total_revenue,
    co.total_gross_profit,
    co.total_contribution_margin,
    co.total_cac_spend,
    co.total_net_profit,
    co.avg_net_margin_pct,

    -- Per-customer economics (LTV proxy)
    ROUND(co.total_revenue
        / NULLIF(co.new_customers, 0), 2)       AS revenue_per_new_customer,
    ROUND(co.total_net_profit
        / NULLIF(co.new_customers, 0), 2)       AS net_profit_per_new_customer,

    -- First-order profitability (hardest to achieve — inc. full CAC)
    co.first_order_revenue,
    co.first_order_net_profit,
    ROUND(
        co.first_order_net_profit
        / NULLIF(co.first_order_revenue, 0) * 100, 2
    )                                           AS first_order_net_margin_pct,

    -- LTV/CAC ratio
    ROUND(
        co.total_net_profit
        / NULLIF(COALESCE(cf.estimated_monthly_spend, co.total_cac_spend), 0),
        2
    )                                           AS ltv_cac_ratio,

    -- Channel efficiency tier
    CASE
        WHEN ROUND(co.total_net_profit / NULLIF(co.new_customers, 0), 2) >= 2000
             THEN 'High Value Channel'
        WHEN ROUND(co.total_net_profit / NULLIF(co.new_customers, 0), 2) >= 500
             THEN 'Moderate Value'
        WHEN ROUND(co.total_net_profit / NULLIF(co.new_customers, 0), 2) >= 0
             THEN 'Breakeven'
        ELSE 'Loss Channel'
    END                                         AS channel_tier

FROM channel_orders co
LEFT JOIN channel_funnel cf ON co.channel = cf.channel
ORDER BY total_net_profit DESC;


-- =============================================================
-- REPORT 5: Profit Waterfall (Portfolio Level)
-- Answers: "Where does every rupee of revenue go?"
-- A single-row table with each profit waterfall step as a column.
-- Used to populate the waterfall chart in the dashboard.
-- =============================================================
DROP TABLE IF EXISTS analytics.rpt_profit_waterfall CASCADE;
CREATE TABLE analytics.rpt_profit_waterfall AS
SELECT
    -- Revenue
    ROUND(SUM(item_revenue), 2)                 AS step_01_item_revenue,

    -- Deductions (all positive = cost to subtract)
    ROUND(SUM(item_cogs), 2)                    AS step_02_less_cogs,
    ROUND(SUM(logistics_cost), 2)               AS step_03_less_logistics,
    ROUND(SUM(payment_fee), 2)                  AS step_04_less_payment_fees,
    ROUND(SUM(discount_allocated), 2)           AS step_05_less_discounts,
    ROUND(SUM(return_cost), 2)                  AS step_06_less_return_costs,

    -- Contribution Margin milestone
    ROUND(SUM(contribution_margin), 2)          AS step_07_contribution_margin,
    ROUND(SUM(contribution_margin)
        / NULLIF(SUM(item_revenue), 0) * 100, 2) AS cm_margin_pct,

    -- CAC deduction
    ROUND(SUM(cac_allocation), 2)               AS step_08_less_cac,

    -- Final Net Profit
    ROUND(SUM(net_profit), 2)                   AS step_09_net_profit,
    ROUND(SUM(net_profit)
        / NULLIF(SUM(item_revenue), 0) * 100, 2) AS net_margin_pct,

    -- Profit leakage = every rupee that didn't become net profit
    ROUND(SUM(item_revenue) - GREATEST(SUM(net_profit), 0), 2) AS total_profit_leaked,
    ROUND(
        (SUM(item_revenue) - GREATEST(SUM(net_profit), 0))
        / NULLIF(SUM(item_revenue), 0) * 100, 2
    )                                           AS leakage_pct,

    -- Counts for reference
    COUNT(DISTINCT order_id)                    AS total_orders,
    COUNT(*)                                    AS total_line_items,
    COUNT(DISTINCT customer_id)                 AS total_customers,
    COUNT(*) FILTER (WHERE is_profit_leak)      AS loss_making_line_items,
    ROUND(
        (COUNT(*) FILTER (WHERE is_profit_leak))::NUMERIC
        / NULLIF(COUNT(*), 0) * 100, 2
    )                                           AS pct_items_losing_money

FROM analytics.fact_order_items;
