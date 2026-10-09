-- Q5: Roll up seller geography city -> state -> region to find the
-- best-selling regions. region_rank/state_rank below aren't part of the
-- rollup itself - they're just used to sort the output so the biggest
-- region/state appears first, since ROLLUP doesn't order subtotals by value.
WITH geo_rollup AS (
    SELECT
        r.region_name,
        s.state_code,
        ci.city_name,
        SUM(f.revenue) AS rev,
        CASE
            WHEN GROUPING(r.region_name, s.state_code, ci.city_name) = 7 THEN 'Grand Total'
            WHEN GROUPING(s.state_code, ci.city_name) = 3 THEN 'Region Total'
            WHEN GROUPING(ci.city_name) = 1 THEN 'State Total'
            ELSE 'City Detail'
        END AS level
    FROM fact_order_items f
    JOIN dim_seller sel ON f.seller_id = sel.seller_id
    JOIN dim_zip_code z ON sel.zip_code_prefix = z.zip_code_prefix
    JOIN dim_city ci ON z.city_id = ci.city_id
    JOIN dim_state s ON ci.state_id = s.state_id
    JOIN dim_region r ON s.region_id = r.region_id
    GROUP BY ROLLUP (r.region_name, s.state_code, ci.city_name)
),
region_rank AS (
    SELECT r.region_name, SUM(f.revenue) AS region_total
    FROM fact_order_items f
    JOIN dim_seller sel ON f.seller_id = sel.seller_id
    JOIN dim_zip_code z ON sel.zip_code_prefix = z.zip_code_prefix
    JOIN dim_city ci ON z.city_id = ci.city_id
    JOIN dim_state s ON ci.state_id = s.state_id
    JOIN dim_region r ON s.region_id = r.region_id
    GROUP BY r.region_name
),
state_rank AS (
    SELECT r.region_name, s.state_code, SUM(f.revenue) AS state_total
    FROM fact_order_items f
    JOIN dim_seller sel ON f.seller_id = sel.seller_id
    JOIN dim_zip_code z ON sel.zip_code_prefix = z.zip_code_prefix
    JOIN dim_city ci ON z.city_id = ci.city_id
    JOIN dim_state s ON ci.state_id = s.state_id
    JOIN dim_region r ON s.region_id = r.region_id
    GROUP BY r.region_name, s.state_code
)
SELECT
    COALESCE(g.region_name, 'All Regions') AS region,
    COALESCE(g.state_code, 'All States') AS state,
    COALESCE(g.city_name, 'All Cities') AS city,
    ROUND(g.rev, 2) AS total_revenue,
    g.level
FROM geo_rollup g
LEFT JOIN region_rank rr ON rr.region_name IS NOT DISTINCT FROM g.region_name
LEFT JOIN state_rank sr ON sr.region_name IS NOT DISTINCT FROM g.region_name
                        AND sr.state_code IS NOT DISTINCT FROM g.state_code
ORDER BY
    rr.region_total DESC NULLS LAST,
    (g.state_code IS NULL) ASC,
    sr.state_total DESC NULLS LAST,
    (g.city_name IS NULL) ASC,
    g.rev DESC;