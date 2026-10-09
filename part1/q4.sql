-- Q4: Drill down from category to product - top 5 products by revenue
-- within each category.
WITH product_revenue AS (
    SELECT
        c.category_name,
        c.category_name_english,
        p.product_id,
        SUM(f.revenue) AS total_revenue,
        RANK() OVER (PARTITION BY c.category_name ORDER BY SUM(f.revenue) DESC) AS rnk
    FROM fact_order_items f
    JOIN dim_product p ON f.product_id = p.product_id
    JOIN dim_category c ON p.category_id = c.category_id
    GROUP BY c.category_name, c.category_name_english, p.product_id
)
SELECT
    category_name,
    COALESCE(category_name_english, category_name) AS category_name_english,
    product_id,
    ROUND(total_revenue, 2) AS total_revenue,
    rnk AS rank_within_category
FROM product_revenue
WHERE rnk <= 5
ORDER BY category_name, rnk;