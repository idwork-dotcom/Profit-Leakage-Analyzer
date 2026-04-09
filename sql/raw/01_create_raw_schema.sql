-- =============================================================
-- FILE:    sql/raw/01_create_raw_schema.sql
-- LAYER:   Raw
-- PURPOSE: Mirror layer — exact structural copies of source CSVs.
--          All columns stored as TEXT for safe, lossless ingestion.
--          No business logic. No transformations. No filters.
-- LOADED BY: pipeline/01_load_raw.py (via pandas + SQLAlchemy)
-- =============================================================

CREATE SCHEMA IF NOT EXISTS raw;


-- -------------------------------------------------------------
-- TABLE: raw.orders
-- SOURCE: orders.csv | ~420 rows
-- PURPOSE: Order header records. Contains order status,
--          timestamps, acquisition channel, and discount amount.
--          This is the anchor table for all profitability analysis.
-- KEY COLUMNS: order_id (PK), customer_id, order_status,
--              order_channel, order_discount_amount
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.orders CASCADE;
CREATE TABLE raw.orders (
    order_id                        TEXT,  -- Unique order identifier (e.g. ORD_00001)
    customer_id                     TEXT,  -- FK → raw.customers
    order_status                    TEXT,  -- delivered | returned | canceled | shipped
    order_purchase_timestamp        TEXT,  -- When the customer placed the order
    order_approved_at               TEXT,  -- When payment was approved
    order_delivered_carrier_date    TEXT,  -- Handed to carrier (shipped)
    order_delivered_customer_date   TEXT,  -- Received by customer (NULL if undelivered)
    order_estimated_delivery_date   TEXT,  -- SLA commitment date
    order_discount_amount           TEXT,  -- Total discount applied to the order (INR)
    order_channel                   TEXT   -- Channel: marketplace | paid_search | social_ads | etc.
);


-- -------------------------------------------------------------
-- TABLE: raw.order_items
-- SOURCE: order_items.csv | ~582 rows
-- PURPOSE: Line-item detail at the SKU level.
--          The grain is one row per product per order.
--          Contains the selling price and item-level freight cost.
-- KEY COLUMNS: order_id + order_item_id (composite PK),
--              product_id, price, freight_value
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.order_items CASCADE;
CREATE TABLE raw.order_items (
    order_id            TEXT,  -- FK → raw.orders
    order_item_id       TEXT,  -- Line number within the order (1, 2, 3 …)
    product_id          TEXT,  -- FK → raw.products
    seller_id           TEXT,  -- Fulfilling seller identifier
    shipping_limit_date TEXT,  -- Seller must dispatch by this date
    price               TEXT,  -- Selling price charged for this item (INR)
    freight_value       TEXT   -- Logistics/shipping cost for this item (INR)
);


-- -------------------------------------------------------------
-- TABLE: raw.order_payments
-- SOURCE: order_payments.csv | ~420 rows
-- PURPOSE: Payment records per order. An order can have
--          multiple rows when payments are split across methods
--          (e.g. part credit card, part voucher).
-- KEY COLUMNS: order_id, payment_type, payment_value
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.order_payments CASCADE;
CREATE TABLE raw.order_payments (
    order_id              TEXT,  -- FK → raw.orders
    payment_sequential    TEXT,  -- Row number for split payments (1, 2 …)
    payment_type          TEXT,  -- credit_card | debit_card | upi | voucher
    payment_installments  TEXT,  -- Number of installments chosen by customer
    payment_value         TEXT   -- Amount paid via this payment method (INR)
);


-- -------------------------------------------------------------
-- TABLE: raw.products
-- SOURCE: products.csv | 12 rows
-- PURPOSE: Product dimension. Contains category classification,
--          physical dimensions, price range, and the
--          estimated_cost_ratio used to derive unit COGS.
--          COGS derivation: unit_cogs = price × estimated_cost_ratio
-- KEY COLUMNS: product_id (PK), product_category_name,
--              estimated_cost_ratio
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.products CASCADE;
CREATE TABLE raw.products (
    product_id                   TEXT,  -- Unique product identifier (P001–P012)
    product_category_name        TEXT,  -- Category: Electronics | Fashion | Beauty | etc.
    product_name_lenght          TEXT,  -- Character length of product name
    product_description_lenght   TEXT,  -- Character length of product description
    product_photos_qty           TEXT,  -- Number of product listing photos
    product_weight_g             TEXT,  -- Gross weight in grams
    product_length_cm            TEXT,  -- Package length in cm
    product_height_cm            TEXT,  -- Package height in cm
    product_width_cm             TEXT,  -- Package width in cm
    list_price_min               TEXT,  -- Minimum listed price (INR)
    list_price_max               TEXT,  -- Maximum listed price (INR)
    estimated_cost_ratio         TEXT   -- COGS as fraction of price (e.g. 0.35 = 35% COGS)
);


-- -------------------------------------------------------------
-- TABLE: raw.customers
-- SOURCE: customers.csv | 180 rows
-- PURPOSE: Customer dimension with segment classification
--          and acquisition channel for CAC attribution.
-- KEY COLUMNS: customer_id (PK), customer_segment,
--              acquisition_channel
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.customers CASCADE;
CREATE TABLE raw.customers (
    customer_id         TEXT,  -- Unique identifier for this customer-order combination
    customer_unique_id  TEXT,  -- Deduplicated customer identity across multiple orders
    customer_city       TEXT,  -- City of delivery / registration
    customer_state      TEXT,  -- State of delivery / registration
    customer_segment    TEXT,  -- Mass | Mid Value | High Value
    acquisition_channel TEXT   -- Channel that acquired this customer
);


-- -------------------------------------------------------------
-- TABLE: raw.marketing_qualified_leads
-- SOURCE: marketing_qualified_leads.csv | ~4,417 rows
-- PURPOSE: Top-of-funnel lead records by channel and date.
--          Used to compute lead volume → conversion → CAC funnel.
-- KEY COLUMNS: mql_id (PK), first_contact_date, origin (channel)
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.marketing_qualified_leads CASCADE;
CREATE TABLE raw.marketing_qualified_leads (
    mql_id             TEXT,  -- Unique lead identifier
    first_contact_date TEXT,  -- Date of first marketing touchpoint
    landing_page_id    TEXT,  -- Landing page that captured the lead
    origin             TEXT   -- Acquisition channel (aligns with order_channel values)
);


-- -------------------------------------------------------------
-- TABLE: raw.closed_deals
-- SOURCE: closed_deals.csv | 668 rows
-- PURPOSE: Converted lead records. Joined with MQLs to compute
--          lead-to-customer conversion rates and CAC proxies
--          by channel and time period.
-- KEY COLUMNS: mql_id (FK → MQLs), won_date, business_segment
-- -------------------------------------------------------------
DROP TABLE IF EXISTS raw.closed_deals CASCADE;
CREATE TABLE raw.closed_deals (
    mql_id                        TEXT,  -- FK → raw.marketing_qualified_leads
    seller_id                     TEXT,  -- Seller identifier post-conversion
    sdr_id                        TEXT,  -- Sales Development Rep who worked the lead
    sr_id                         TEXT,  -- Sales Rep who closed the deal
    won_date                      TEXT,  -- Date the deal was closed/won
    business_segment              TEXT,  -- Segment: fashion | electronics | etc.
    lead_type                     TEXT,  -- online_medium | industry | other
    lead_behaviour_profile        TEXT,  -- Profile tag: cat | eagle | shark | wolf
    has_company                   TEXT,  -- Whether seller has a registered company (Yes/No)
    has_gtin                      TEXT,  -- Whether seller has GTIN barcodes (Yes/No)
    average_stock                 TEXT,  -- Declared average stock level
    business_type                 TEXT,  -- reseller | manufacturer | importer | etc.
    declared_product_catalog_size TEXT,  -- Number of products the seller lists
    declared_monthly_revenue      TEXT   -- Self-declared monthly revenue (INR)
);
