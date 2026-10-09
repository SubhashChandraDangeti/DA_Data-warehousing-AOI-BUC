-- Q7: Top seller by revenue within each state.
WITH seller_state_revenue AS (
    SELECT
        s.state_code,
        f.seller_id,
        ROUND(SUM(f.revenue), 2) AS total_revenue
    FROM fact_order_items f
    JOIN dim_seller sel ON f.seller_id = sel.seller_id
    JOIN dim_zip_code z ON sel.zip_code_prefix = z.zip_code_prefix
    JOIN dim_city ci ON z.city_id = ci.city_id
    JOIN dim_state s ON ci.state_id = s.state_id
    GROUP BY s.state_code, f.seller_id
),
ranked AS (
    SELECT *,
        RANK() OVER (PARTITION BY state_code ORDER BY total_revenue DESC) AS rnk
    FROM seller_state_revenue
)
SELECT state_code, seller_id, total_revenue
FROM ranked
WHERE rnk = 1
ORDER BY total_revenue DESC;