# Power BI Build Guide — Funnel & Retention Dashboard

Build this dashboard yourself in **Power BI Desktop** (free, Windows) in about
30–45 minutes. Everything you need is in the `powerbi/` folder. By the end
you'll have a real `.pbix` you built and understand.

> New to Power BI? Three words to know:
> **Table** = a spreadsheet of data. **Measure** = a formula that recalculates
> when you filter (e.g. Conversion Rate). **Visual** = a chart on the canvas.

---

## Step 0 — Install
Download **Power BI Desktop** free from Microsoft (or install from the
Microsoft Store on Windows). Open it, close the splash screen.

---

## Step 1 — Load the data
1. **Home → Get data → Text/CSV.**
2. Import each of these from the `powerbi/` folder (repeat Get data per file):
   `dim_users.csv`, `dim_date.csv`, `fact_orders.csv`, `fact_events.csv`,
   `funnel.csv`, `cohort_retention.csv`, `rfm_customers.csv`.
3. For each, click **Load** (not Transform, unless you want to peek).

You'll see all 7 tables in the right-hand **Data** pane.

---

## Step 2 — Build the model (relationships)
Go to the **Model view** (left sidebar, third icon). Drag to connect:

| From (dimension) | To (fact) | on column |
|---|---|---|
| `dim_users[user_id]` | `fact_orders[user_id]` | user_id |
| `dim_users[user_id]` | `fact_events[user_id]` | user_id |
| `dim_date[date]` | `fact_orders[order_date]` | date |
| `dim_date[date]` | `fact_events[event_date]` | date |

Each should be **one-to-many** (1 user → many orders). `funnel`,
`cohort_retention`, and `rfm_customers` stay **standalone** (they're
pre-aggregated helper tables — no relationship needed).

*Why:* this "star schema" lets a single slicer (say, device) filter every
visual at once, correctly.

---

## Step 3 — Create the measures
Right-click `fact_orders` in the Data pane → **New measure**. Paste one
formula from `dax_measures.txt`, press Enter, repeat for each. Create at least:
`Total Users`, `Buyers`, `Conversion Rate`, `Total Revenue`, `Total Orders`,
`AOV`.

Format `Conversion Rate` as a percentage: select it, then **Measure tools →
Format → Percentage**.

---

## Step 4 — Build the visuals

Back in **Report view**. Add visuals from the **Visualizations** pane and drag
fields into them.

### A) KPI cards (top row)
Add four **Card** visuals. Drop one measure into each:
`Total Users`, `Conversion Rate`, `Total Revenue`, `AOV`.

### B) Funnel chart
Add the **Funnel** visual.
- **Category:** `funnel[stage_label]`
- **Values:** `Users Reached` (or `funnel[users_reached]`)
- Sort: the "1./2./3./4." prefixes keep the stages in order.

This is your "where do users drop off" centrepiece.

### C) Conversion by channel (bar chart)
Add a **Clustered bar chart**.
- **Y-axis:** `dim_users[acquisition_channel]`
- **X-axis:** `Conversion Rate`
- Sort descending by Conversion Rate (··· menu → Sort axis).

### D) Conversion by device (bar chart)
Same as C but **Y-axis:** `dim_users[device]`.

### E) Cohort retention (Matrix heatmap)
Add a **Matrix** visual.
- **Rows:** `cohort_retention[cohort_month]`
- **Columns:** `cohort_retention[month_number]`
- **Values:** `cohort_retention[retention_pct]` (set aggregation to
  **Average**, or use the `Retention %` measure)
- Turn it into a heatmap: select the visual → **Format → Cell elements →
  Background color → On → fx**, colour low = white, high = blue.

This gives you the same heatmap as the Python version, natively in Power BI.

### F) Revenue by RFM segment (bar chart)
Add a **Clustered bar chart**.
- **Y-axis:** `rfm_customers[segment]`
- **X-axis:** `Segment Revenue`
- Optional: add `Customers` as a tooltip.

### G) Slicer (interactivity)
Add a **Slicer** visual with `dim_users[device]` (or `acquisition_channel`).
Now clicking a device filters the whole page — the "aha" moment of BI.

---

## Step 5 — Polish
- Give the page a title text box: *"Commerce Intelligence — Funnel &
  Retention"*.
- Arrange: KPI cards across the top, funnel + cohort in the middle,
  channel/device/RFM along the bottom.
- **File → Save as** → `funnel_retention.pbix`.
- Optional: **Publish** to the free Power BI Service to get a shareable link
  for your resume/portfolio.

---

## Step 6 — Screenshot it for your portfolio
Power BI files don't preview in file listings, so:
1. Take a screenshot of your finished dashboard.
2. Save it as `powerbi/dashboard_screenshot.png` in the repo.
3. Add it to the top of the project README so recruiters see it instantly.

---

## What to say in the interview
> "I modelled the data as a star schema in Power BI, wrote DAX measures for
> conversion and revenue, and built an interactive dashboard — a funnel to
> show drop-off, a cohort matrix for retention, and RFM segments for customer
> value — with a device slicer so stakeholders can explore it themselves."

That sentence covers data modelling, DAX, and BI storytelling — exactly what
the role asks for.

---

### Data dictionary (quick reference)
- **dim_users** — user_id, signup_date, acquisition_channel, device
- **dim_date** — date, year, month_num, month_name, year_month
- **fact_orders** — order_id, user_id, order_date, revenue
- **fact_events** — event_id, user_id, event_name, stage_order, event_date, device
- **funnel** — stage_order, stage_label, stage, users_reached
- **cohort_retention** — cohort_month, month_number, active_users, cohort_size, retention_pct
- **rfm_customers** — user_id, recency_days, frequency, monetary, r/f/m scores, segment
