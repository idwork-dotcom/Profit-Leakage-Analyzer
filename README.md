# Profit Leakage & True Unit Economics Analyzer


## 📌 Project Overview
This project is an end-to-end analytics platform designed to solve a critical business problem for e-commerce and retail operations: **Profit Leakage**. 

Many businesses accurately track gross Top-Line Revenue and Cost of Goods Sold (COGS). However, operational friction—such as payment gateway fees, hidden freight costs, aggressive discounting, return and restocking costs, and Customer Acquisition Cost (CAC)—silently degrades profitability before it reaches the bottom line. 

This repository implements a production-grade data pipeline and interactive dashboard that maps exactly where revenue is leaking, calculating the **True Unit Economics** at the order-item and customer level.

---

## 🎯 Business Problem & Objectives
**The Problem:** The business is profitable on a gross margin basis, but net profits are significantly trailing expectations. Leadership needs to understand *why*, *where*, and *who* is driving this leakage.

**The Solution:**
1. Ingest raw, fragmented e-commerce files (orders, items, payments, marketing leads).
2. Clean and standardize the data into a Medallion architecture (Raw → Staging → Analytics).
3. Systematically allocate unpegged order-level costs down to the item level.
4. Deliver a diagnostic dashboard that provides answers on Category Profitability, Customer LTV/CAC, and Root Cause Diagnostics for loss-making orders.

---

## 🏗️ Architecture & Data Flow
The project mirrors an enterprise ELT (Extract, Load, Transform) pipeline.

* **Layer 1: Raw** (`raw.*`) — Lossless schema mirroring source CSVs. String types only.
* **Layer 2: Staging** (`staging.stg_*`) — Typed, cleaned, and enriched data. Validates order states (ignoring fully canceled orders without shipment footprints) and handles basic derivations (like COGS estimation).
* **Layer 3: Analytics** (`analytics.fact_*`, `analytics.rpt_*`) — The core business logic layer. Implements strict cost allocations, computes the profit waterfall, and aggregates into dimensional reporting tables for fast UI querying.
* **Layer 4: Presentation** (`dashboard/app.py`) — A Streamlit-powered BI application.

---

## 📊 Core Metric Cascade (The Profit Waterfall)
The foundation of this analyzer is the strict hierarchy of the profit waterfall computed for every single line item:

| Step | Metric | Derivation |
|---|---|---|
| (+) | **Item Revenue** | Selling price of the item. |
| (-) | **COGS** | Estimated based on `cost_ratio` mapped to the product category. |
| (-) | **Logistics Cost** | Realized forward freight cost tied directly to the item. |
| (-) | **Payment Fees** | Apportioned based on the payment gateway rate. |
| (-) | **Discounts** | Allocated from order headers based on revenue share per item. |
| (-) | **Return Costs** | Derived cost (reverse freight + restocking) applied *only* if the order was returned. |
| **(=)** | **Contribution Margin** | *The true operational profit of the actual sale.* |
| (-) | **CAC Allocation** | Injected based on marketing channel spend. Applied **ONLY** to the customer's first order. |
| **(=)** | **Net Profit** | *The final bottom-line value generated for the portfolio.* |

---

## ⚠️ Assumptions & Cost Allocation Rules
To achieve True Unit Economics without perfect accounting mapping, the following defensible business assumptions were implemented:

1. **Order-to-Item Allocation:** Order-level values (Payment Flags, Discounts) are structurally apportioned to the items within that order using a **Revenue Share Ratio** (`item_revenue / order_total_revenue`).
2. **First-Order CAC Imputation:** Customer Acquisition Cost is a sunk cost used to acquire a user. Therefore, 100% of the channel-driven CAC is applied to the customer's **First Order**. Repeat orders carry a $0 CAC allocation, cleanly surfacing Customer Lifetime Value (LTV).
3. **Return Cost Estimation:** Return logistics are not provided heavily in the source. Therefore, a returned order assumes a reverse-logistics cost equal to 1x the forward shipping cost, plus a 10% COGS deduction representing restocking and processing labor constraints. 
4. **Organic Search CAC:** Organic search has a $0 direct marketing spend imputed.

---

## 🚀 How to Run the Project

### Prerequisites
* Python 3.10+
* PostgreSQL 15+ (Running locally or hosted)

### 1. Setup Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Create the PostgreSQL database
createdb profit_leakage
```

### 2. Configuration
Update your database credentials in `config/settings.yaml`. You can also manipulate marketing spend or fee rates dynamically here without altering the code.

### 3. Run Data Pipeline
```bash
# Executes 01_load_raw.py -> 02_run_staging.py -> 03_run_analytics.py
python pipeline/run_pipeline.py
```
*Note: The pipeline automatically prints a command-line reconciliation and unit economics summary report to standard-out for CI/CD tracing.*

### 4. Launch Dashboard
```bash
streamlit run dashboard/app.py
```

---

## 💡 Key Findings & Insights (Sample Case Study Highlights)
* **Categories to Target:** *Beauty* products generate high return rates which, when paired with average shipping profiles, flip the category into net loss-making status despite healthy initial gross margins. 
* **Acquisition Efficiency:** *Organic* and *Email* channels drive the highest LTV/CAC ratios. *Paid Search* has generated a severe CAC overage causing an overall LTV/CAC ratio of `< 1.0`, meaning the company is currently burning cash to acquire users on that channel.
* **Loss Order Root Causes:** While discounting drives top-line metrics, "Excessive Discounting" was identified as the secondary root-cause of profit destruction, eclipsed only by High First-Order CACs.

> **Author / Contact**: Designed as a portfolio business case outlining robust data modeling and commercial acumen.
