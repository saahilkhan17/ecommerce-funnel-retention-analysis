# E-commerce Funnel, Retention & RFM Analysis

> Owner & maintainer: **saahilkhan**

An end-to-end **business-analytics** project on e-commerce clickstream and
transaction data: build a conversion funnel, find where users drop off,
measure retention with cohorts, and segment customers by value (RFM) — then
turn the numbers into business recommendations and a dashboard.

Built with **SQL + Python (pandas, matplotlib)**. No paid tools required.

> Why this exists: it mirrors a real data-intelligence workflow —
> *transactional data → user-journey events → funnel & drop-off → churn/retention
> → dashboards → recommendations.*

---

## What's in the box

```
ecommerce-funnel-retention/
├── data/                    generated CSVs (users, events, orders)
├── sql/analysis.sql         the SQL queries, heavily commented
├── src/
│   ├── generate_data.py     makes the synthetic dataset
│   ├── run_analysis.py      loads CSV→SQLite, runs SQL, makes charts + insights
│   ├── build_interactive_dashboard.py   builds interactive_dashboard.html
│   └── prepare_powerbi.py   reshapes data into Power BI-ready tables
├── charts/                  generated PNG charts
├── interactive_dashboard.html   open this in a browser
├── powerbi/                 Power BI-ready tables + DAX + build guide
├── requirements.txt
└── README.md
```

## Run it (3 commands)

```bash
cd ecommerce-funnel-retention
python3 src/generate_data.py                 # 1. create data/*.csv
python3 src/run_analysis.py                  # 2. run analysis -> charts/ + insights
python3 src/build_interactive_dashboard.py   # 3. build interactive_dashboard.html
```
Only needs `pandas`, `numpy`, `matplotlib` (`pip install pandas numpy matplotlib`).
SQLite is built into Python.

---

## The data model (what each table means)

| table | grain (1 row = ) | key columns |
|-------|------------------|-------------|
| `users`  | one user | `user_id`, `signup_date`, `acquisition_channel`, `device` |
| `events` | one action in a user's journey | `user_id`, `event_name`, `event_time` |
| `orders` | one completed purchase | `user_id`, `order_time`, `revenue` |

`event_name` moves through the funnel:
`product_view → add_to_cart → begin_checkout → purchase`.

This is exactly the shape of real product analytics data (think GA4 /
Mixpanel / Amplitude event streams + an orders table).

---

## The five analyses (and how each one works)

### 1. Conversion funnel — *where do we lose people?*
Count **distinct users** who reached each stage. Because you can't purchase
without checking out, counts shrink down the funnel; each drop is a leak.
- **Step conversion** = users at this stage ÷ users at the previous stage.
- The stage with the lowest step conversion is where to focus.

*Result here:* only **41%** of viewers add to cart → the top of the funnel is
the biggest leak, so product-page experiments move the most volume.

### 2. Conversion by channel & device — *who converts, not just who clicks?*
Join every user to whether they ever purchased, then compute
`buyers ÷ total_users` per channel and per device.

*Result:* **Email 23.7%** and **Paid Search 18.6%** beat **Social 5.9%**;
**Mobile converts at 9.8% vs Desktop 25.8%** → a mobile-checkout friction point.

### 3. Cohort retention — *do customers come back?*
- A customer's **cohort** = the month of their first purchase.
- For each later month, count how many of that cohort purchased again.
- `month_number = 0` is the acquisition month (always 100%); each column to
  the right shows the % still active N months later.

Reading the heatmap: rows are cohorts, columns are months-since-first-purchase,
darker = higher retention. The fall-off from column 0→1 is your repeat-purchase rate.

### 4. RFM segmentation — *which customers are worth the most?*
Score every customer on three axes, each split into quintiles (`NTILE(5)`):
- **R**ecency — days since last order (recent = good, so we flip it)
- **F**requency — number of orders
- **M**onetary — total spend

Then bucket into named segments (**Champions, Loyal, At Risk, Lost…**) with a
`CASE` statement. This converts raw scores into *actions*: reward Champions,
win back At-Risk, re-activate Lost.

*Result:* a few hundred **Champions/Loyal/At-Risk** customers hold ~**83%** of
revenue → win-back on **At-Risk** protects the biggest revenue pool.

### 5. Dashboard (interactive — just open it)
`interactive_dashboard.html` is a self-contained interactive dashboard — open
it in any browser, no install. **Toggle controls** let you filter by device and
channel (KPIs, funnel, and conversion charts recompute live, with cross-filtering),
switch the funnel between user counts and step-conversion %, flip RFM between
revenue and customer count, and view cohort retention as % or users. The
`powerbi/` folder (Power BI-ready tables + DAX + build guide) is there too if you
later want a Power BI version.

---

## SQL techniques used (say these in an interview)
- `COUNT(DISTINCT …)` for unique-user funnels
- `LEFT JOIN` + `CASE` to flag converters and build segments
- **CTEs** (`WITH …`) to keep multi-step logic readable
- **Window functions**: `NTILE(5) OVER (ORDER BY …)` for RFM quintiles
- Date bucketing for cohorts (`strftime` in SQLite; `FORMAT_DATE`/`to_char`
  in BigQuery/Postgres — noted inline in `analysis.sql`)

## Headline insights (the "so what")
1. **Top-of-funnel leak** (view→cart 41%) → prioritise product-page A/B tests.
2. **Mobile checkout friction** (9.8% vs 25.8%) → audit mobile checkout.
3. **Channel spend is mis-allocated** → shift budget to Email/Paid Search.
4. **Revenue is concentrated** in At-Risk/Champions → a retention/win-back
   program protects the most revenue per rupee spent.

## Notes & honesty
The dataset is **synthetic** (generated with controllable drop-off and a
decaying repeat-purchase process) so the repo runs with zero external
downloads. The *methods* — funnel, cohort, RFM, significance — are identical
to what you'd run on real warehouse data. To use real data, point
`generate_data.py`'s outputs at the [Olist e-commerce dataset](https://www.kaggle.com/olistbr/brazilian-ecommerce)
or the GA4 sample and the SQL/analysis works unchanged.

---

## Owner

Owned and maintained by **saahilkhan**.
