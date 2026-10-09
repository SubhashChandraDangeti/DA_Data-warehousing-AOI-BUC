-- Q2: Highest-revenue month within each year, via RANK() over monthly totals.
WITH monthly_revenue AS (
    SELECT
        d.year,
        d.month,
        ROUND(SUM(f.revenue), 2) AS total_revenue
    FROM fact_order_items f
    JOIN dim_order o ON f.order_id = o.order_id
    JOIN dim_date d ON o.order_purchase_date_key = d.date_key
    GROUP BY d.year, d.month
),
ranked AS (
    SELECT *,
        RANK() OVER (PARTITION BY year ORDER BY total_revenue DESC) AS rnk
    FROM monthly_revenue
)
SELECT year, month, total_revenue
FROM ranked
WHERE rnk = 1
ORDER BY year;