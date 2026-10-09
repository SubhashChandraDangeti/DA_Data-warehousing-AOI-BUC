-- Q9: Average review score by delivery timing - early vs on-time vs late.
SELECT
    o.delivery_status,
    ROUND(AVG(r.review_score), 2) AS avg_review_score,
    COUNT(DISTINCT o.order_id) AS num_orders
FROM dim_order o
JOIN dim_review r ON o.order_id = r.order_id
WHERE o.delivery_status IS NOT NULL   -- excludes undelivered orders (no delivery date to compare)
GROUP BY o.delivery_status
ORDER BY
    CASE o.delivery_status WHEN 'early' THEN 1 WHEN 'on_time' THEN 2 WHEN 'late' THEN 3 END;