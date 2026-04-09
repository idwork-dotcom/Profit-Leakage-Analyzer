# Profit Leakage & True Unit Economics Analyzer
## Implementation Plan — Pre-Build Architecture Document

> This is a **planning document only**. No code should be written until this plan is reviewed and approved.
> All assumptions are explicitly flagged in Section 6.

---

## 1. Project Architecture

The project follows a **4-layer analytical pipeline** modeled after modern data warehouse conventions
(similar in spirit to dbt's staging / marts layer system). Each layer has one single responsibility.

```
[Raw Layer]  →  [Staging Layer]  →  [Analytics Layer]  →  [Dashboard Layer]
(CSV files)     (Python scripts)    (Fact & Dim tables)    (Streamlit + Plotly)
```

### Layer Responsibilities

| Layer     | Purpose                                      | Technology            |
|-----------|----------------------------------------------|-----------------------|
| Raw       | Store source data as-is, never modified      | CSV flat files        |
| Staging   | Clean, type-cast, rename, validate           | Python, pandas        |
| Analytics | Build fact table and compute all metrics     | Python, pandas        |
| Dashboard | Visualize KPIs, profit leakage, unit econ.  | Streamlit, Plotly     |

---

## 2. Folder Structure

```
profit-leakage/
|
|-- data/
|   |-- raw/                      # Source files — never modified
|   |   |-- orders.csv
|   |   |-- order_items.csv
|   |   |-- products.csv
|   |   |-- customers.csv
|   |   |-- logistics_costs.csv
|   |   +-- marketing_spend.csv
|   |
|   |-- staging/                  # Cleaned, typed intermediates (Parquet)
|   |   |-- stg_orders.parquet
|   |   |-- stg_order_items.parquet
|   |   |-- stg_products.parquet
|   |   |-- stg_customers.parquet
|   |   |-- stg_logistics.parquet
|   |   +-- stg_marketing.parquet
|   |
|   +-- analytics/                # Final fact & dimension tables
|       |-- fact_order_items.parquet
|       |-- dim_products.parquet
|       |-- dim_customers.parquet
|       +-- summary_metrics.parquet
|
|-- pipeline/
|   |-- 01_ingest.py              # Load raw CSVs, basic schema validation
|   |-- 02_stage.py               # Clean, cast, rename all staging tables
|   |-- 03_build_fact.py          # Join & compute all metrics into fact table
|   +-- 04_aggregate.py           # Roll up to category / customer summaries
|
|-- dashboard/
|   |-- app.py                    # Streamlit entry point
|   |-- components/
|   |   |-- kpi_cards.py
|   |   |-- leakage_waterfall.py
|   |   |-- category_breakdown.py
|   |   +-- customer_cohorts.py
|   +-- assets/
|       +-- style.css
|
|-- notebooks/
|   +-- exploration.ipynb         # EDA / ad-hoc scratch pad
|
|-- tests/
|   +-- test_metrics.py           # Unit tests for metric calculations
|
|-- config/
|   +-- settings.yaml             # Paths, constants, fee rates, thresholds
|
|-- README.md
|-- requirements.txt
+-- .gitignore
```

---

## 3. Data Flow: Raw → Dashboard

```
orders.csv          ──┐
order_items.csv     ──┤──► stg_orders / stg_items ──────────────────► fact_order_items ──► Waterfall Chart
products.csv        ──┤──► stg_products            ──► dim_products ──► fact_order_items ──► Category View
customers.csv       ──┤──► stg_customers           ──► dim_customers ─► fact_order_items ──► Explorer Table
logistics_costs.csv ──┤──► stg_logistics ──────────────────────────► fact_order_items
marketing_spend.csv ──┘──► stg_marketing ──────────────────────────► summary_metrics   ──► KPI Cards
                                                                                            Customer Econ
```

**Pipeline scripts run in order:**
1. `01_ingest.py` → validates raw files exist and have expected columns
2. `02_stage.py`  → outputs clean Parquet files to `data/staging/`
3. `03_build_fact.py` → outputs `fact_order_items.parquet` to `data/analytics/`
4. `04_aggregate.py`  → outputs `summary_metrics.parquet`

---

## 4. Fact Table Grain

> **The grain of `fact_order_items` is: one row per order-item line.**

Each row = a single SKU within a single order. This is the finest grain possible and enables
profitability slicing at every dimension: item, order, customer, category, channel, and time period.

### Column Manifest

| Column               | Type   | Source       | Description                                         |
|----------------------|--------|--------------|-----------------------------------------------------|
| order_item_id        | str    | order_items  | Primary key                                         |
| order_id             | str    | orders       | Parent order                                        |
| order_date           | date   | orders       | Date order was placed                               |
| customer_id          | str    | orders       | Customer who placed the order                       |
| product_id           | str    | order_items  | Product sold                                        |
| category             | str    | products     | Product category                                    |
| brand                | str    | products     | Product brand                                       |
| quantity             | int    | order_items  | Units ordered                                       |
| unit_selling_price   | float  | order_items  | Price charged to customer                           |
| unit_cogs            | float  | products     | Cost of goods per unit                              |
| item_revenue         | float  | computed     | unit_selling_price × quantity                       |
| item_cogs            | float  | computed     | unit_cogs × quantity                                |
| gross_profit         | float  | computed     | item_revenue − item_cogs                            |
| logistics_cost       | float  | logistics    | Allocated shipping + fulfillment cost               |
| payment_fee          | float  | computed     | item_revenue × payment_fee_rate                     |
| return_flag          | bool   | orders       | Was this order returned?                            |
| return_cost          | float  | computed     | Reverse logistics + restocking fee                  |
| contribution_margin  | float  | computed     | gross_profit − variable costs                       |
| cac_allocation       | float  | marketing    | CAC charged on first order only                     |
| net_profit           | float  | computed     | contribution_margin − cac_allocation                |
| net_margin_pct       | float  | computed     | net_profit / item_revenue × 100                     |
| channel              | str    | orders       | Acquisition channel                                 |
| is_first_order       | bool   | computed     | Is this the customer's first-ever order?            |

---

## 5. Core Business Metric Definitions

### 5.1 Item Revenue

```
item_revenue = unit_selling_price × quantity
```

Top-line revenue for a single order-item line.
Any discounts must be reflected in unit_selling_price before this calculation.

---

### 5.2 Logistics Cost

```
logistics_cost_per_item = order_shipping_cost × (item_revenue / order_total_revenue)
```

Order-level shipping and fulfillment cost, allocated proportionally to each line item
by its share of that order's total revenue.

⚠ **Assumption A2**: Costs are at order level and split by revenue share. Confirm if item-level data exists.

---

### 5.3 Payment Fee

```
payment_fee = item_revenue × payment_fee_rate   [default: 2%]
```

Gateway transaction fee (e.g., Razorpay, Stripe, UPI gateway).
Rate stored in `config/settings.yaml` as a configurable constant.

---

### 5.4 Contribution Margin

```
contribution_margin = item_revenue
                    − item_cogs
                    − logistics_cost
                    − payment_fee
                    − return_cost

cm_pct = contribution_margin / item_revenue × 100
```

The "true gross profit" after all variable per-unit costs.
This is the most important intermediate metric — it answers:
**"Is this product profitable at all, before we consider what it cost to get the customer?"**

---

### 5.5 CAC Allocation

```
# Channel-level CAC computed monthly
channel_cac = marketing_spend[channel, month] / new_customers_acquired[channel, month]

# Applied to first order only, split by item revenue share
if is_first_order:
    cac_allocation = channel_cac × (item_revenue / first_order_total_revenue)
else:
    cac_allocation = 0
```

CAC is charged exactly once — on the customer's first order.
Repeat orders carry zero CAC, making return-customer economics inherently better.

⚠ **Assumption A4**: CAC on first order only. Alternative: amortize across customer's LTV window. Confirm.

---

### 5.6 Net Profit (True Unit Economics)

```
net_profit     = contribution_margin − cac_allocation
net_margin_pct = net_profit / item_revenue × 100
```

The final "true unit economics" figure.
A **negative net_profit** flags a profit-leaking product, category, or channel —
one that looks profitable on the surface but destroys value after full cost accounting.

---

## 6. Assumptions & Unclear Areas (Explicit Log)

| #   | Area              | Assumption Made                                                    | Needs Confirmation?                        |
|-----|-------------------|--------------------------------------------------------------------|--------------------------------------------|
| A1  | Data source       | All source CSVs will be **synthetically generated** for demo       | Confirm if real data exists                |
| A2  | Logistics grain   | Costs at **order level**, split to items by revenue share          | Confirm if item-level data exists          |
| A3  | Payment fee       | Flat rate **2%**, uniform across all channels and methods          | Does rate vary by payment method?          |
| A4  | CAC allocation    | Charged to **first order only** per customer                       | Confirm; alt: amortize over LTV window     |
| A5  | Return cost       | Reverse logistics + **10% of item COGS** as restocking fee         | Confirm restocking rate                    |
| A6  | Marketing data    | Aggregated **monthly by channel** (Instagram, Google, Organic)     | Confirm available channels                 |
| A7  | COGS              | **Fixed per SKU** — no batch or seasonal variation                 | Confirm                                    |
| A8  | Currency          | Single currency — **INR (₹)**                                      | Confirm                                    |
| A9  | Time period       | **12 months** of synthetic transaction history                     | Confirm desired date range                 |
| A10 | Attribution       | **Single-touch** — one channel per order; no multi-touch in v1     | Confirm                                    |
| A11 | Discounts         | Treated as price reduction in unit_selling_price, not tracked sep. | Flag if promo code analysis is needed      |
| A12 | Taxes             | **Excluded** — all analysis on pre-tax basis                       | Confirm                                    |

---

## 7. Recommended Tech Stack

| Component          | Tool                          | Rationale                                                              |
|--------------------|-------------------------------|------------------------------------------------------------------------|
| Language           | Python 3.11+                  | Industry standard for data pipelines and analytics                     |
| Data processing    | pandas + numpy                | Efficient for analytical-scale CSV and Parquet data                    |
| Intermediate files | Parquet                       | Typed, compressed, fast I/O between pipeline steps                     |
| Configuration      | PyYAML (settings.yaml)        | Clean separation of constants (fee rates, paths) from code logic       |
| Dashboard          | **Streamlit**                 | Fastest path to recruiter-ready interactive app; Python-native         |
| Charts             | **Plotly** (via Streamlit)    | Interactive waterfall, treemap, bar/scatter charts out of the box      |
| Synthetic data     | Faker + custom Python script  | Generates realistic e-commerce data without needing a real dataset     |
| Testing            | pytest                        | Validates metric formula correctness                                   |
| Version control    | Git + GitHub                  | Portfolio visibility with clean, documented commit history             |

**Why Streamlit over custom HTML/JS?**
Streamlit delivers interactive filters, multi-page navigation, and polished Plotly charts in ~50 lines of Python.
For a portfolio project targeting business analytics and data roles, it is significantly more maintainable
and impressive than hand-rolled HTML. It also signals Python-first analytical thinking — what hiring managers value.

---

## 8. Planned Dashboard Pages

| Page                     | Key Visuals                                                              |
|--------------------------|--------------------------------------------------------------------------|
| Executive Summary        | KPI cards: Total Revenue, Gross Profit, CM%, Net Profit, Leakage %       |
| Profit Waterfall         | Revenue → COGS → Logistics → Payment Fee → Returns → CAC → Net Profit   |
| Category Deep-Dive       | Net Margin % by category; leakage heatmap by brand × category           |
| Customer Unit Economics  | CAC by channel, LTV vs CAC ratio, first-order profitability comparison   |
| Order-Level Explorer     | Filterable/sortable table of fact_order_items with all computed metrics  |

---

## 9. Build Sequence

```
Phase 1 — Data Foundation
  Step 1: Generate synthetic raw CSVs
          (orders, order_items, products, customers, logistics_costs, marketing_spend)
  Step 2: Build staging pipeline (01_ingest.py + 02_stage.py)

Phase 2 — Analytics Core
  Step 3: Build fact_order_items with all computed metrics (03_build_fact.py)
  Step 4: Build summary aggregations (04_aggregate.py)
  Step 5: Write metric unit tests (tests/test_metrics.py)

Phase 3 — Dashboard
  Step 6: Build Streamlit app shell with sidebar navigation
  Step 7: Build each of the 5 dashboard pages
  Step 8: Polish charts, filters, and visual theme

Phase 4 — Portfolio Packaging
  Step 9: Write README.md with business narrative and methodology
  Step 10: Push to GitHub with clean, logical commit history
```

---

**Next Step**: Confirm assumptions A1–A6. Once confirmed, Phase 1 begins immediately
with synthetic data generation (`generate_data.py`).
