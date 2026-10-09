-- Q6: Top 5 customers by total purchase amount. Grouped by
-- customer_unique_id, not customer_id, since the same person can get a new
-- customer_id per order in this dataset.
SELECT
    cu.customer_unique_id,
    ROUND(SUM(f.revenue), 2) AS total_purchase_amount
FROM fact_order_items f
JOIN dim_customer cu ON f.customer_id = cu.customer_id
GROUP BY cu.customer_unique_id
ORDER BY total_purchase_amount DESC
LIMIT 5;