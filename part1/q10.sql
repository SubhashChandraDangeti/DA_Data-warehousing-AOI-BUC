-- Q10: Which lead origin (marketing channel) recruited the sellers that
-- generate the most revenue. Only covers sellers with an acquisition record
-- (the tracked marketing funnel), since the join is on dim_seller_acquisition.
SELECT
    sa.lead_origin,
    ROUND(SUM(f.revenue), 2) AS total_revenue,
    COUNT(DISTINCT sa.seller_id) AS num_sellers,
    ROUND(SUM(f.revenue) / COUNT(DISTINCT sa.seller_id), 2) AS avg_revenue_per_seller
FROM fact_order_items f
JOIN dim_seller_acquisition sa ON f.seller_id = sa.seller_id
GROUP BY sa.lead_origin
ORDER BY total_revenue DESC;