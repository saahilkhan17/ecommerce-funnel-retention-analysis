"""
generate_data.py
------------------
Owner: saahilkhan

Creates a realistic synthetic e-commerce dataset so the whole project runs
end-to-end with NO external download required.

It produces three CSVs that mimic what you'd get from a real product's
data warehouse:

  users.csv   -> one row per user (who they are, when/how they joined)
  events.csv  -> one row per user action (the "user journey" / clickstream)
  orders.csv  -> one row per completed purchase (transactions + revenue)

WHY synthetic data?
  Real datasets (Google Analytics sample, Olist) need a BigQuery/Kaggle
  account. Generating our own means anyone can `git clone` and run it.
  In interviews you say: "I modelled a realistic funnel with configurable
  drop-off and a decaying repeat-purchase process, then analysed it" —
  which actually shows you understand the *shape* of e-commerce data.
"""

import numpy as np
import pandas as pd

# A fixed seed makes the data identical every run -> reproducible results.
rng = np.random.default_rng(42)

# ----------------------------------------------------------------------
# Config knobs. Change these and the whole analysis updates.
# ----------------------------------------------------------------------
N_USERS = 6000
START = pd.Timestamp("2025-01-01")
END = pd.Timestamp("2025-06-30")
CHANNELS = ["Organic", "Paid Search", "Social", "Email", "Referral"]
CHANNEL_WEIGHTS = [0.34, 0.24, 0.20, 0.12, 0.10]
DEVICES = ["Mobile", "Desktop", "Tablet"]
DEVICE_WEIGHTS = [0.62, 0.33, 0.05]

# Funnel stages in order. The number is the probability a user who reached
# the PREVIOUS stage continues to THIS stage. This is what creates drop-off.
FUNNEL = [
    ("product_view", 1.00),   # everyone who lands views a product
    ("add_to_cart", 0.42),    # 42% of viewers add to cart
    ("begin_checkout", 0.55), # 55% of cart-adders start checkout
    ("purchase", 0.64),       # 64% of checkout-starters actually buy
]

# Paid/Email traffic converts a bit better; Social a bit worse. This makes
# the "conversion by channel" analysis produce a real, defensible insight.
CHANNEL_CONV_MULT = {
    "Organic": 1.00, "Paid Search": 1.10, "Social": 0.80,
    "Email": 1.20, "Referral": 1.05,
}
# Mobile converts worse than desktop -> a classic real-world friction point.
DEVICE_CONV_MULT = {"Mobile": 0.85, "Desktop": 1.20, "Tablet": 0.95}


def random_dates(n, start, end):
    """n random timestamps uniformly between start and end."""
    span = (end - start).total_seconds()
    secs = rng.uniform(0, span, n)
    return start + pd.to_timedelta(secs, unit="s")


def build_users():
    ids = np.arange(1, N_USERS + 1)
    signup = random_dates(N_USERS, START, END).sort_values().values
    channel = rng.choice(CHANNELS, N_USERS, p=CHANNEL_WEIGHTS)
    device = rng.choice(DEVICES, N_USERS, p=DEVICE_WEIGHTS)
    return pd.DataFrame({
        "user_id": ids,
        "signup_date": pd.to_datetime(signup),
        "acquisition_channel": channel,
        "device": device,
    })


def build_events_and_orders(users):
    """
    For each user we walk them down the funnel. Their per-stage continue
    probability is scaled by their channel and device multipliers, so
    'good' channels/devices lose fewer people. Every time a user reaches
    'purchase', we also record an order with revenue.
    """
    events = []
    orders = []
    order_id = 1

    for row in users.itertuples(index=False):
        uid = row.user_id
        base_t = pd.Timestamp(row.signup_date)
        cmult = CHANNEL_CONV_MULT[row.acquisition_channel]
        dmult = DEVICE_CONV_MULT[row.device]

        # session id for this first visit
        session = f"s{uid}_1"
        t = base_t
        reached = True
        for stage, p in FUNNEL:
            if stage == "product_view":
                # everyone views at least one product on landing
                pass
            else:
                # scale continue-probability, cap at 0.98
                p_eff = min(p * cmult * dmult, 0.98)
                if rng.random() > p_eff:
                    reached = False
            if not reached:
                break
            # each stage happens a little later in the session
            t = t + pd.to_timedelta(rng.uniform(20, 400), unit="s")
            events.append((uid, session, stage, t, row.device))

            if stage == "purchase":
                revenue = round(float(rng.lognormal(mean=3.4, sigma=0.6)), 2)
                orders.append((order_id, uid, t, revenue))
                order_id += 1

        # ---- repeat purchases: a decaying process over the next months ----
        # Users who bought once may come back. Probability decays each time,
        # so we get a realistic long-tail of loyal repeat buyers. This is
        # what makes cohort-retention and RFM interesting.
        if reached:  # they made at least one purchase
            repeat_p = 0.35
            last_t = t
            k = 2
            while rng.random() < repeat_p and last_t < END:
                gap = rng.uniform(5, 45)  # days until next visit
                last_t = last_t + pd.to_timedelta(gap, unit="D")
                if last_t > END:
                    break
                session = f"s{uid}_{k}"
                # a return visit still goes through view -> cart -> etc.,
                # but we keep it simple: they view then purchase again
                events.append((uid, session, "product_view", last_t, row.device))
                buy_t = last_t + pd.to_timedelta(rng.uniform(60, 600), unit="s")
                events.append((uid, session, "purchase", buy_t, row.device))
                revenue = round(float(rng.lognormal(mean=3.4, sigma=0.6)), 2)
                orders.append((order_id, uid, buy_t, revenue))
                order_id += 1
                repeat_p *= 0.55  # decay -> fewer and fewer come back
                k += 1

    events_df = pd.DataFrame(
        events, columns=["user_id", "session_id", "event_name",
                         "event_time", "device"]
    ).sort_values("event_time").reset_index(drop=True)
    events_df.insert(0, "event_id", np.arange(1, len(events_df) + 1))

    orders_df = pd.DataFrame(
        orders, columns=["order_id", "user_id", "order_time", "revenue"]
    ).sort_values("order_time").reset_index(drop=True)

    return events_df, orders_df


def main():
    users = build_users()
    events, orders = build_events_and_orders(users)

    users.to_csv("data/users.csv", index=False)
    events.to_csv("data/events.csv", index=False)
    orders.to_csv("data/orders.csv", index=False)

    print(f"users : {len(users):>7,} rows -> data/users.csv")
    print(f"events: {len(events):>7,} rows -> data/events.csv")
    print(f"orders: {len(orders):>7,} rows -> data/orders.csv")
    print(f"total revenue: {orders['revenue'].sum():,.0f}")


if __name__ == "__main__":
    main()
