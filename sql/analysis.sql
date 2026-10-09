-- =====================================================================
-- analysis.sql
-- E-commerce funnel, conversion, retention & RFM analysis
--
-- These queries run against a SQLite database built from the three CSVs
-- (users, events, orders). SQLite uses standard SQL, so 95% of this is
-- identical to what you'd write in PostgreSQL / BigQuery / Snowflake in production.
-- Dialect differences are noted in comments.
-- Author / Owner: saahilkhan
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. CONVERSION FUNNEL
-- "How many users reach each step, and where do we lose them?"
--
-- Idea: count DISTINCT users who fired each event. Because a user can
-- only reach 'purchase' if they passed the earlier stages, the counts
-- naturally decrease down the funnel. The drop between rows = leak.
-- ---------------------------------------------------------------------
SELECT
    event_name,
    COUNT(DISTINCT user_id) AS users_reached
FROM events
WHERE event_name IN ('product_view','add_to_cart','begin_checkout','purchase')
GROUP BY event_name
ORDER BY users_reached DESC;


-- ---------------------------------------------------------------------
-- Q2. CONVERSION RATE BY ACQUISITION CHANNEL
-- "Which marketing channel actually brings buyers, not just clicks?"
--
-- We join users -> their purchase events. A user 'converted' if they
-- have at least one purchase. Conversion rate = buyers / total users
-- in that channel. This is a classic "where should we spend?" insight.
-- ---------------------------------------------------------------------
WITH buyers AS (
    SELECT DISTINCT user_id
    FROM events
    WHERE event_name = 'purchase'
)
SELECT
    u.acquisition_channel,
    COUNT(*)                                   AS total_users,
    COUNT(b.user_id)                           AS buyers,
    ROUND(100.0 * COUNT(b.user_id) / COUNT(*), 1) AS conversion_pct
FROM users u
LEFT JOIN buyers b ON u.user_id = b.user_id
GROUP BY u.acquisition_channel
ORDER BY conversion_pct DESC;


-- ---------------------------------------------------------------------
-- Q3. CONVERSION RATE BY DEVICE
-- Same logic, split by device. Usually surfaces a mobile-checkout
-- friction point -> a concrete recommendation.
-- ---------------------------------------------------------------------
WITH buyers AS (
    SELECT DISTINCT user_id
    FROM events
    WHERE event_name = 'purchase'
)
SELECT
    u.device,
    COUNT(*)                                   AS total_users,
    COUNT(b.user_id)                           AS buyers,
    ROUND(100.0 * COUNT(b.user_id) / COUNT(*), 1) AS conversion_pct
FROM users u
LEFT JOIN buyers b ON u.user_id = b.user_id
GROUP BY u.device
ORDER BY conversion_pct DESC;


-- ---------------------------------------------------------------------
-- Q4. MONTHLY COHORT RETENTION (by purchase)
-- "Of the customers who first bought in month X, how many came back to
--  buy again in later months?"
--
-- Step 1 (first_purchase): each user's very first purchase month = their
--   cohort.
-- Step 2 (activity): every month a user made a purchase.
-- Step 3: join them and measure the gap (months since first purchase).
--   month_number = 0 is the acquisition month (always 100%).
--
-- NOTE: strftime('%Y-%m') is SQLite. In BigQuery you'd use
--   FORMAT_DATE('%Y-%m', ts); in Postgres to_char(ts,'YYYY-MM').
-- ---------------------------------------------------------------------
WITH first_purchase AS (
    SELECT user_id,
           MIN(strftime('%Y-%m', order_time)) AS cohort_month
    FROM orders
    GROUP BY user_id
),
activity AS (
    SELECT DISTINCT user_id,
           strftime('%Y-%m', order_time) AS active_month
    FROM orders
)
SELECT
    fp.cohort_month,
    -- months between cohort_month and active_month
    (CAST(strftime('%Y', a.active_month || '-01') AS INT) * 12
       + CAST(strftime('%m', a.active_month || '-01') AS INT))
    - (CAST(strftime('%Y', fp.cohort_month || '-01') AS INT) * 12
       + CAST(strftime('%m', fp.cohort_month || '-01') AS INT)) AS month_number,
    COUNT(DISTINCT a.user_id) AS active_users
FROM first_purchase fp
JOIN activity a ON fp.user_id = a.user_id
GROUP BY fp.cohort_month, month_number
ORDER BY fp.cohort_month, month_number;


-- ---------------------------------------------------------------------
-- Q5. RFM SEGMENTATION
-- Score every customer on Recency, Frequency, Monetary value, then
-- bucket them into actionable segments (Champions, Loyal, At-Risk...).
--
-- Recency  = days since their last order (smaller = better)
-- Frequency= number of orders
-- Monetary = total revenue
--
-- NTILE(5) splits customers into 5 equal groups (quintiles). We flip
-- recency so that "recent" gets the high score of 5.
-- ---------------------------------------------------------------------
WITH rfm_base AS (
    SELECT
        user_id,
        JULIANDAY('2025-06-30') - JULIANDAY(MAX(order_time)) AS recency_days,
        COUNT(*)         AS frequency,
        SUM(revenue)     AS monetary
    FROM orders
    GROUP BY user_id
),
scored AS (
    SELECT
        user_id, recency_days, frequency, monetary,
        6 - NTILE(5) OVER (ORDER BY recency_days)        AS r_score, -- recent = 5
        NTILE(5) OVER (ORDER BY frequency)               AS f_score,
        NTILE(5) OVER (ORDER BY monetary)                AS m_score
    FROM rfm_base
)
SELECT
    user_id, ROUND(recency_days) AS recency_days, frequency,
    ROUND(monetary,2) AS monetary,
    r_score, f_score, m_score,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
        WHEN r_score >= 4 AND f_score <= 2 THEN 'New / Promising'
        WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
        WHEN r_score <= 2 AND f_score <= 2 THEN 'Lost / Hibernating'
        ELSE 'Needs Attention'
    END AS segment
FROM scored
ORDER BY monetary DESC;
