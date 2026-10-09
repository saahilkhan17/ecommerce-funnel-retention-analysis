"""
run_analysis.py
----------------
Owner: saahilkhan

Loads the CSVs into an in-memory SQLite database, runs the queries in
sql/analysis.sql, prints the key findings, and saves charts to charts/.

This is the "analyst workflow" end to end:
    raw data  ->  SQL  ->  numbers  ->  charts  ->  written insight
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # render to file, no screen needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---- consistent, clean styling for every chart --------------------------
plt.rcParams.update({
    "figure.dpi": 120, "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
})
INK = "#1f2933"
ACCENT = "#4f46e5"
MUTED = "#94a3b8"


def load_db():
    """Read the three CSVs and load them into a SQLite database."""
    con = sqlite3.connect(":memory:")
    for name in ["users", "events", "orders"]:
        df = pd.read_csv(f"data/{name}.csv")
        df.to_sql(name, con, index=False, if_exists="replace")
    return con


def q(con, sql):
    return pd.read_sql_query(sql, con)


# =====================================================================
# 1. FUNNEL
# =====================================================================
def funnel(con):
    order = ["product_view", "add_to_cart", "begin_checkout", "purchase"]
    df = q(con, """
        SELECT event_name, COUNT(DISTINCT user_id) AS users_reached
        FROM events
        WHERE event_name IN
          ('product_view','add_to_cart','begin_checkout','purchase')
        GROUP BY event_name
    """)
    df = df.set_index("event_name").loc[order].reset_index()

    top = df["users_reached"].iloc[0]
    df["pct_of_top"] = (100 * df["users_reached"] / top).round(1)
    # step conversion = this stage / previous stage
    df["step_conv"] = (100 * df["users_reached"] /
                       df["users_reached"].shift(1)).round(1)
    df.loc[0, "step_conv"] = 100.0

    print("\n=== Q1. CONVERSION FUNNEL ===")
    print(df.to_string(index=False))

    # --- chart: horizontal funnel bars ---
    labels = ["Product View", "Add to Cart", "Begin Checkout", "Purchase"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ypos = np.arange(len(df))[::-1]
    ax.barh(ypos, df["users_reached"], color=ACCENT, alpha=0.85)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels)
    for i, (_, row) in enumerate(df.iterrows()):
        y = ypos[i]
        ax.text(row["users_reached"] + top * 0.01, y,
                f"{int(row['users_reached']):,}  ({row['pct_of_top']:.0f}%)",
                va="center", fontsize=10, color=INK)
        if i > 0:
            ax.text(row["users_reached"] + top * 0.16, y,
                    f"step: {row['step_conv']:.0f}%", va="center",
                    fontsize=9, color=MUTED)
    ax.set_title("Conversion Funnel — where users drop off",
                 fontweight="bold", color=INK)
    ax.set_xlabel("Distinct users")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_xlim(0, top * 1.35)
    fig.tight_layout()
    fig.savefig("charts/01_funnel.png", bbox_inches="tight")
    plt.close(fig)
    return df


# =====================================================================
# 2 & 3. CONVERSION BY CHANNEL / DEVICE
# =====================================================================
def conversion_segments(con):
    chan = q(con, """
        WITH buyers AS (SELECT DISTINCT user_id FROM events
                        WHERE event_name='purchase')
        SELECT u.acquisition_channel AS segment,
               COUNT(*) AS total_users, COUNT(b.user_id) AS buyers,
               ROUND(100.0*COUNT(b.user_id)/COUNT(*),1) AS conversion_pct
        FROM users u LEFT JOIN buyers b ON u.user_id=b.user_id
        GROUP BY u.acquisition_channel ORDER BY conversion_pct DESC
    """)
    dev = q(con, """
        WITH buyers AS (SELECT DISTINCT user_id FROM events
                        WHERE event_name='purchase')
        SELECT u.device AS segment,
               COUNT(*) AS total_users, COUNT(b.user_id) AS buyers,
               ROUND(100.0*COUNT(b.user_id)/COUNT(*),1) AS conversion_pct
        FROM users u LEFT JOIN buyers b ON u.user_id=b.user_id
        GROUP BY u.device ORDER BY conversion_pct DESC
    """)
    print("\n=== Q2. CONVERSION BY CHANNEL ===")
    print(chan.to_string(index=False))
    print("\n=== Q3. CONVERSION BY DEVICE ===")
    print(dev.to_string(index=False))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, df, title in [(axes[0], chan, "Conversion by Channel"),
                          (axes[1], dev, "Conversion by Device")]:
        bars = ax.bar(df["segment"], df["conversion_pct"],
                      color=ACCENT, alpha=0.85)
        ax.set_title(title, fontweight="bold", color=INK)
        ax.set_ylabel("Conversion %")
        ax.set_ylim(0, df["conversion_pct"].max() * 1.25)
        ax.tick_params(axis="x", rotation=20)
        for b, v in zip(bars, df["conversion_pct"]):
            ax.text(b.get_x() + b.get_width()/2, v + 0.3, f"{v:.1f}%",
                    ha="center", fontsize=9, color=INK)
    fig.tight_layout()
    fig.savefig("charts/02_conversion_by_segment.png", bbox_inches="tight")
    plt.close(fig)
    return chan, dev


# =====================================================================
# 4. COHORT RETENTION HEATMAP
# =====================================================================
def cohort(con):
    df = q(con, """
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
        ORDER BY fp.cohort_month, month_number
    """)
    pivot = df.pivot(index="cohort_month", columns="month_number",
                     values="active_users").fillna(0)
    cohort_size = pivot[0]
    retention = pivot.divide(cohort_size, axis=0) * 100  # % retained

    print("\n=== Q4. COHORT RETENTION (% of cohort still purchasing) ===")
    print(retention.round(1).to_string())

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    im = ax.imshow(retention.values, aspect="auto", cmap="Blues", vmin=0, vmax=100)
    ax.set_xticks(range(retention.shape[1]))
    ax.set_xticklabels(retention.columns)
    ax.set_yticks(range(retention.shape[0]))
    ax.set_yticklabels(retention.index)
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Cohort (first-purchase month)")
    ax.set_title("Monthly Cohort Retention  (%)", fontweight="bold", color=INK)
    for i in range(retention.shape[0]):
        for j in range(retention.shape[1]):
            v = retention.values[i, j]
            if not np.isnan(v) and v > 0:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                        fontsize=8, color="white" if v > 55 else INK)
    fig.colorbar(im, ax=ax, label="% retained")
    fig.tight_layout()
    fig.savefig("charts/03_cohort_retention.png", bbox_inches="tight")
    plt.close(fig)
    return retention


# =====================================================================
# 5. RFM SEGMENTS
# =====================================================================
def rfm(con):
    df = q(con, """
        WITH rfm_base AS (
            SELECT user_id,
              JULIANDAY('2025-06-30')-JULIANDAY(MAX(order_time)) AS recency_days,
              COUNT(*) AS frequency, SUM(revenue) AS monetary
            FROM orders GROUP BY user_id),
        scored AS (
            SELECT user_id, recency_days, frequency, monetary,
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
    """)
    summary = (df.groupby("segment")
                 .agg(customers=("user_id", "count"),
                      avg_orders=("frequency", "mean"),
                      total_revenue=("monetary", "sum"))
                 .sort_values("total_revenue", ascending=False)
                 .round(1))
    summary["revenue_share_%"] = (100 * summary["total_revenue"] /
                                  summary["total_revenue"].sum()).round(1)
    print("\n=== Q5. RFM SEGMENTS ===")
    print(summary.to_string())

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    s = summary.sort_values("total_revenue")
    bars = ax.barh(s.index, s["total_revenue"], color=ACCENT, alpha=0.85)
    for b, cust, rev in zip(bars, s["customers"], s["revenue_share_%"]):
        ax.text(b.get_width() * 1.01, b.get_y() + b.get_height()/2,
                f"{rev:.0f}% of rev · {int(cust)} cust",
                va="center", fontsize=9, color=INK)
    ax.set_title("Revenue by RFM Customer Segment",
                 fontweight="bold", color=INK)
    ax.set_xlabel("Total revenue")
    ax.set_xlim(0, s["total_revenue"].max() * 1.4)
    fig.tight_layout()
    fig.savefig("charts/04_rfm_segments.png", bbox_inches="tight")
    plt.close(fig)
    return summary


def main():
    con = load_db()
    f = funnel(con)
    chan, dev = conversion_segments(con)
    ret = cohort(con)
    seg = rfm(con)

    # ---- auto-generate the headline insights (used in the README) ----
    biggest_leak_idx = f["step_conv"].iloc[1:].idxmin()
    leak_from = ["Product View","Add to Cart","Begin Checkout","Purchase"][biggest_leak_idx-1]
    leak_to = ["Product View","Add to Cart","Begin Checkout","Purchase"][biggest_leak_idx]
    worst_dev = dev.sort_values("conversion_pct").iloc[0]
    best_chan = chan.iloc[0]
    print("\n" + "="*60)
    print("HEADLINE INSIGHTS (paste-ready for the README / interview)")
    print("="*60)
    print(f"1. Biggest funnel leak: {leak_from} -> {leak_to} "
          f"({f['step_conv'].iloc[biggest_leak_idx]:.0f}% step conversion).")
    print(f"2. {worst_dev['segment']} converts worst at "
          f"{worst_dev['conversion_pct']:.1f}% -> checkout UX friction.")
    print(f"3. Best channel: {best_chan['segment']} at "
          f"{best_chan['conversion_pct']:.1f}% conversion -> scale spend here.")
    print(f"4. Top RFM segment drives "
          f"{seg['revenue_share_%'].iloc[0]:.0f}% of revenue from "
          f"{int(seg['customers'].iloc[0])} customers -> protect & upsell them.")


if __name__ == "__main__":
    main()
