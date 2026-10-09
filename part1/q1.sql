-- Q1: Total revenue per year, drilled down to quarter and month via ROLLUP.
-- The level column labels which grouping each row belongs to, since ROLLUP
-- just returns NULLs for the columns it's aggregated over.
SELECT
    d.year,
    COALESCE(CAST(d.quarter AS VARCHAR), 'All Quarters') AS quarter,
    COALESCE(CAST(d.month AS VARCHAR), 'All Months') AS month,
    ROUND(SUM(f.revenue), 2) AS total_revenue,
    CASE
        WHEN GROUPING(d.year, d.quarter, d.month) = 7 THEN 'Grand Total'
        WHEN GROUPING(d.quarter, d.month) = 3 THEN 'Year Total'
        WHEN GROUPING(d.month) = 1 THEN 'Quarter Total'
        ELSE 'Month Detail'
    END AS level
FROM fact_order_items f
JOIN dim_order o ON f.order_id = o.order_id
JOIN dim_date d ON o.order_purchase_date_key = d.date_key
GROUP BY ROLLUP (d.year, d.quarter, d.month)
ORDER BY d.year NULLS LAST, d.quarter NULLS LAST, d.month NULLS LAST;