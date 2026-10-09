"""
prepare_powerbi.py
-------------------
Owner: saahilkhan

Reshapes the raw CSVs into clean, Power BI-friendly tables (a small star
schema + a couple of pre-aggregated helper tables for the harder visuals).

Why reshape at all?
  Power BI loves a STAR SCHEMA: skinny "fact" tables (events, orders) joined
  to "dimension" tables (users, date). Modelling it this way is what real BI
  analysts do, and it makes measures and slicers behave predictably.

  For two visuals that are painful to build from scratch in Power BI as a
  beginner (the funnel ordering and the cohort heatmap), we pre-aggregate
  here in the pipeline and hand Power BI a tidy table to display. This is a
  totally standard "ETL in Python, visualize in BI" pattern.

Outputs -> powerbi/ :
  dim_users.csv          one row per user
  dim_date.csv           a proper date dimension
  fact_orders.csv        one row per order (with date key)
  fact_events.csv        one row per journey event (with stage order + date key)
  funnel.csv             pre-aggregated distinct users per funnel stage
  cohort_retention.csv   pre-aggregated cohort retention (tidy/long format)
  rfm_customers.csv      per-customer RFM scores + segment label
"""
import os
import sqlite3
import numpy as np
import pandas as pd

os.makedirs("powerbi", exist_ok=True)

# ---- load raw data into SQLite so we can reuse the same SQL logic ----
con = sqlite3.connect(":memory:")
for n in ["users", "events", "orders"]:
    pd.read_csv(f"data/{n}.csv").to_sql(n, con, index=False, if_exists="replace")


# =====================================================================
# DIMENSIONS
# =====================================================================
users = pd.read_csv("data/users.csv")
users["signup_date"] = pd.to_datetime(users["signup_date"]).dt.date
users.to_csv("powerbi/dim_users.csv", index=False)

# Date dimension: one row per calendar day across the data range.
orders_raw = pd.read_csv("data/orders.csv", parse_dates=["order_time"])
events_raw = pd.read_csv("data/events.csv", parse_dates=["event_time"])
start = min(orders_raw.order_time.min(), events_raw.event_time.min()).normalize()
end = max(orders_raw.order_time.max(), events_raw.event_time.max()).normalize()
dates = pd.date_range(start, end, freq="D")
dim_date = pd.DataFrame({"date": dates.date})
dim_date["year"] = dates.year
dim_date["month_num"] = dates.month
dim_date["month_name"] = dates.strftime("%b")
dim_date["year_month"] = dates.strftime("%Y-%m")
dim_date.to_csv("powerbi/dim_date.csv", index=False)


# =====================================================================
# FACTS
# =====================================================================
fact_orders = orders_raw.copy()
fact_orders["order_date"] = fact_orders["order_time"].dt.date
fact_orders = fact_orders[["order_id", "user_id", "order_date", "revenue"]]
fact_orders.to_csv("powerbi/fact_orders.csv", index=False)

stage_order = {"product_view": 1, "add_to_cart": 2,
               "begin_checkout": 3, "purchase": 4}
fact_events = events_raw.copy()
fact_events["event_date"] = fact_events["event_time"].dt.date
fact_events["stage_order"] = fact_events["event_name"].map(stage_order)
fact_events = fact_events[["event_id", "user_id", "event_name",
                           "stage_order", "event_date", "device"]]
fact_events.to_csv("powerbi/fact_events.csv", index=False)


# =====================================================================
# HELPER 1: FUNNEL (pre-aggregated distinct users per stage)
# =====================================================================
funnel = pd.read_sql_query("""
    SELECT event_name AS stage, COUNT(DISTINCT user_id) AS users_reached
    FROM events
    WHERE event_name IN
      ('product_view','add_to_cart','begin_checkout','purchase')
    GROUP BY event_name
""", con)
funnel["stage_order"] = funnel["stage"].map(stage_order)
funnel = funnel.sort_values("stage_order")
# nice labels for the visual
label = {"product_view": "1. Product View", "add_to_cart": "2. Add to Cart",
         "begin_checkout": "3. Begin Checkout", "purchase": "4. Purchase"}
funnel["stage_label"] = funnel["stage"].map(label)
funnel = funnel[["stage_order", "stage_label", "stage", "users_reached"]]
funnel.to_csv("powerbi/funnel.csv", index=False)


# =====================================================================
# HELPER 2: COHORT RETENTION (tidy long format for a Matrix visual)
# =====================================================================
cohort = pd.read_sql_query("""
    WITH first_purchase AS (
        SELECT user_id, MIN(strftime('%Y-%m', order_time)) AS cohort_month
        FROM orders GROUP BY user_id),
    activity AS (
        SELECT DISTINCT user_id, strftime('%Y-%m', order_time) AS active_month
        FROM orders)
    SELECT fp.cohort_month,
      (CAST(strftime('%Y', a.active_month||'-01') AS INT)*12
         + CAST(strftime('%m', a.active_month||'-01') AS INT))
      -(CAST(strftime('%Y', fp.cohort_month||'-01') AS INT)*12
         + CAST(strftime('%m', fp.cohort_month||'-01') AS INT)) AS month_number,
      COUNT(DISTINCT a.user_id) AS active_users
    FROM first_purchase fp JOIN activity a ON fp.user_id=a.user_id
    GROUP BY fp.cohort_month, month_number
""", con)
size = (cohort[cohort.month_number == 0]
        .set_index("cohort_month")["active_users"].rename("cohort_size"))
cohort = cohort.merge(size, on="cohort_month")
cohort["retention_pct"] = (100 * cohort["active_users"]
                           / cohort["cohort_size"]).round(1)
cohort = cohort.sort_values(["cohort_month", "month_number"])
cohort.to_csv("powerbi/cohort_retention.csv", index=False)


# =====================================================================
# HELPER 3: RFM (per-customer scores + segment)
# =====================================================================
rfm = pd.read_sql_query("""
    WITH rfm_base AS (
        SELECT user_id,
          JULIANDAY('2025-06-30')-JULIANDAY(MAX(order_time)) AS recency_days,
          COUNT(*) AS frequency, SUM(revenue) AS monetary
        FROM orders GROUP BY user_id),
    scored AS (
        SELECT user_id,
          ROUND(recency_days) AS recency_days, frequency,
          ROUND(monetary,2) AS monetary,
          6-NTILE(5) OVER (ORDER BY recency_days) AS r_score,
          NTILE(5) OVER (ORDER BY frequency)      AS f_score,
          NTILE(5) OVER (ORDER BY monetary)       AS m_score
        FROM rfm_base)
    SELECT *,
      CASE
        WHEN r_score>=4 AND f_score>=4 THEN 'Champions'
        WHEN r_score>=3 AND f_score>=3 THEN 'Loyal'
        WHEN r_score>=4 AND f_score<=2 THEN 'New / Promising'
        WHEN r_score<=2 AND f_score>=3 THEN 'At Risk'
        WHEN r_score<=2 AND f_score<=2 THEN 'Lost / Hibernating'
        ELSE 'Needs Attention' END AS segment
    FROM scored
""", con)
rfm.to_csv("powerbi/rfm_customers.csv", index=False)


# ---- summary ----
for f in ["dim_users", "dim_date", "fact_orders", "fact_events",
          "funnel", "cohort_retention", "rfm_customers"]:
    n = len(pd.read_csv(f"powerbi/{f}.csv"))
    print(f"powerbi/{f}.csv  -> {n:,} rows")
