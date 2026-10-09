-- Q3: Which product categories generate the most revenue.
-- Falls back to the Portuguese name when no English translation exists.
SELECT
    COALESCE(c.category_name_english, c.category_name) AS category_name_english,
    ROUND(SUM(f.revenue), 2) AS total_revenue
FROM fact_order_items f
JOIN dim_product p ON f.product_id = p.product_id
JOIN dim_category c ON p.category_id = c.category_id
GROUP BY c.category_name_english, c.category_name
ORDER BY total_revenue DESC;