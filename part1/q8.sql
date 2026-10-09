-- Q8: CUBE over (region, category, year) - total revenue at every
-- combination of these three dimensions, including all their subtotals.
SELECT
    COALESCE(r.region_name, 'All Regions') AS region,
    COALESCE(c.category_name, 'All Categories') AS category,
    COALESCE(CAST(d.year AS VARCHAR), 'All Years') AS year,
    ROUND(SUM(f.revenue), 2) AS total_revenue
FROM fact_order_items f
JOIN dim_seller sel ON f.seller_id = sel.seller_id
JOIN dim_zip_code z ON sel.zip_code_prefix = z.zip_code_prefix
JOIN dim_city ci ON z.city_id = ci.city_id
JOIN dim_state s ON ci.state_id = s.state_id
JOIN dim_region r ON s.region_id = r.region_id
JOIN dim_product p ON f.product_id = p.product_id
JOIN dim_category c ON p.category_id = c.category_id
JOIN dim_order o ON f.order_id = o.order_id
JOIN dim_date d ON o.order_purchase_date_key = d.date_key
GROUP BY CUBE (r.region_name, c.category_name, d.year)
ORDER BY r.region_name NULLS LAST, c.category_name NULLS LAST, d.year NULLS LAST;