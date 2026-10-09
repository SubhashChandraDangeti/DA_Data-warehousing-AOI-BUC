"""
Part 1 - ETL Load Script
==========================
Loads the cleaned CSVs (produced by preprocessing.py) into the Snowflake
schema (produced by create_schema.sql), in strict top-down dependency order
so every foreign key resolves before it is referenced.

Run: python etl_load.py
Requires: duckdb
"""

import duckdb
import os

CLEAN_DIR = "cleaned"
DB_PATH = "warehouse.duckdb"
SCHEMA_SQL = "create_schema.sql"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

con = duckdb.connect(DB_PATH)

# ---------------------------------------------------------------------------
# 0. Create schema
# ---------------------------------------------------------------------------
with open(SCHEMA_SQL) as f:
    con.execute(f.read())
print("Schema created.")


# ---------------------------------------------------------------------------
# 1. dim_region
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_region (region_id, region_name)
    SELECT ROW_NUMBER() OVER (ORDER BY region) AS region_id, region
    FROM (SELECT DISTINCT region FROM read_csv_auto('{CLEAN_DIR}/state_region_mapping_clean.csv'))
""")
print("dim_region loaded:", con.execute("SELECT COUNT(*) FROM dim_region").fetchone()[0])


# ---------------------------------------------------------------------------
# 2. dim_state (FK -> region)
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_state (state_id, state_code, state_name, region_id)
    SELECT
        ROW_NUMBER() OVER (ORDER BY m.state_code) AS state_id,
        m.state_code,
        m.state_name,
        r.region_id
    FROM read_csv_auto('{CLEAN_DIR}/state_region_mapping_clean.csv') m
    JOIN dim_region r ON r.region_name = m.region
""")
print("dim_state loaded:", con.execute("SELECT COUNT(*) FROM dim_state").fetchone()[0])


# ---------------------------------------------------------------------------
# 3. dim_city (FK -> state)
#    Built from the union of distinct (city, state) pairs seen in
#    geolocation_clean, customers_clean, and sellers_clean, so every
#    customer/seller city has a home row even if geolocation didn't cover it.
# ---------------------------------------------------------------------------
con.execute(f"""
    CREATE OR REPLACE TEMP TABLE all_cities AS
    SELECT DISTINCT city AS city_name, state AS state_code
    FROM read_csv_auto('{CLEAN_DIR}/geolocation_clean.csv')
    UNION
    SELECT DISTINCT customer_city, customer_state FROM read_csv_auto('{CLEAN_DIR}/customers_clean.csv')
    UNION
    SELECT DISTINCT seller_city, seller_state FROM read_csv_auto('{CLEAN_DIR}/sellers_clean.csv')
""")

con.execute("""
    INSERT INTO dim_city (city_id, city_name, state_id)
    SELECT
        ROW_NUMBER() OVER (ORDER BY ac.city_name, ac.state_code) AS city_id,
        ac.city_name,
        s.state_id
    FROM all_cities ac
    JOIN dim_state s ON s.state_code = ac.state_code
""")
print("dim_city loaded:", con.execute("SELECT COUNT(*) FROM dim_city").fetchone()[0])


# ---------------------------------------------------------------------------
# 4. dim_zip_code (FK -> city)
#    Sourced entirely from geolocation_clean.csv - preprocessing.py already
#    patches this file to cover every zip prefix referenced by customers/
#    sellers (see step 11a in preprocessing.py), so no fallback is needed here.
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_zip_code (zip_code_prefix, city_id, lat, lng)
    SELECT g.zip_code_prefix, c.city_id, g.lat, g.lng
    FROM read_csv_auto('{CLEAN_DIR}/geolocation_clean.csv') g
    JOIN dim_city c ON c.city_name = g.city AND c.state_id = (
        SELECT state_id FROM dim_state WHERE state_code = g.state
    )
""")
print("dim_zip_code loaded:", con.execute("SELECT COUNT(*) FROM dim_zip_code").fetchone()[0])


# ---------------------------------------------------------------------------
# 5. dim_category
#    categories_clean.csv is already patched by preprocessing.py (step 11b)
#    to include every category name that appears in products_clean.csv.
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_category (category_id, category_name, category_name_english)
    SELECT ROW_NUMBER() OVER (ORDER BY product_category_name), product_category_name, product_category_name_english
    FROM read_csv_auto('{CLEAN_DIR}/categories_clean.csv')
""")
# Add the 'unknown_category' bucket (for products with NULL category, coalesced during cleaning)
con.execute("""
    INSERT INTO dim_category (category_id, category_name, category_name_english)
    SELECT (SELECT COALESCE(MAX(category_id),0)+1 FROM dim_category), 'unknown_category', 'unknown_category'
    WHERE NOT EXISTS (SELECT 1 FROM dim_category WHERE category_name = 'unknown_category')
""")
print("dim_category loaded:", con.execute("SELECT COUNT(*) FROM dim_category").fetchone()[0])


# ---------------------------------------------------------------------------
# 6. dim_product (FK -> category)
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_product (
        product_id, category_id, product_name_length, product_description_length,
        product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm
    )
    SELECT
        p.product_id, c.category_id, p.product_name_lenght, p.product_description_lenght,
        p.product_photos_qty, p.product_weight_g, p.product_length_cm, p.product_height_cm, p.product_width_cm
    FROM read_csv_auto('{CLEAN_DIR}/products_clean.csv') p
    JOIN dim_category c ON c.category_name = p.product_category_name
""")
print("dim_product loaded:", con.execute("SELECT COUNT(*) FROM dim_product").fetchone()[0])


# ---------------------------------------------------------------------------
# 7. dim_seller (FK -> zip_code) + dim_seller_acquisition (FK -> seller)
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_seller (seller_id, zip_code_prefix)
    SELECT seller_id, zip_code_prefix
    FROM read_csv_auto('{CLEAN_DIR}/sellers_clean.csv')
""")
print("dim_seller loaded:", con.execute("SELECT COUNT(*) FROM dim_seller").fetchone()[0])

con.execute(f"""
    INSERT INTO dim_seller_acquisition (
        seller_id, mql_id, lead_origin, first_contact_date, won_date,
        business_segment, lead_type, business_type,
        declared_product_catalog_size, declared_monthly_revenue
    )
    SELECT
        sa.seller_id, sa.mql_id, sa.lead_origin, sa.first_contact_date, sa.won_date,
        sa.business_segment, sa.lead_type, sa.business_type,
        sa.declared_product_catalog_size, sa.declared_monthly_revenue
    FROM read_csv_auto('{CLEAN_DIR}/seller_acquisition_clean.csv') sa
    JOIN dim_seller s ON s.seller_id = sa.seller_id
""")
print("dim_seller_acquisition loaded:", con.execute("SELECT COUNT(*) FROM dim_seller_acquisition").fetchone()[0])


# ---------------------------------------------------------------------------
# 8. dim_customer (FK -> zip_code)
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_customer (customer_id, customer_unique_id, zip_code_prefix)
    SELECT customer_id, customer_unique_id, zip_code_prefix
    FROM read_csv_auto('{CLEAN_DIR}/customers_clean.csv')
""")
print("dim_customer loaded:", con.execute("SELECT COUNT(*) FROM dim_customer").fetchone()[0])


# ---------------------------------------------------------------------------
# 9. dim_date - generated from the full range of dates across orders/reviews
# ---------------------------------------------------------------------------
con.execute(f"""
    CREATE OR REPLACE TEMP TABLE date_bounds AS
    SELECT
        MIN(order_purchase_timestamp)::DATE AS min_d,
        MAX(order_estimated_delivery_date)::DATE AS max_d
    FROM read_csv_auto('{CLEAN_DIR}/orders_clean.csv')
""")

con.execute("""
    INSERT INTO dim_date (date_key, full_date, day, month, month_name, quarter, year)
    SELECT
        CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
        d AS full_date,
        EXTRACT(day FROM d) AS day,
        EXTRACT(month FROM d) AS month,
        strftime(d, '%B') AS month_name,
        EXTRACT(quarter FROM d) AS quarter,
        EXTRACT(year FROM d) AS year
    FROM (
        SELECT UNNEST(generate_series(
            (SELECT min_d FROM date_bounds),
            (SELECT max_d FROM date_bounds),
            INTERVAL 1 DAY
        )) AS d
    )
""")
print("dim_date loaded:", con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0])


# ---------------------------------------------------------------------------
# 10. dim_order - derive delivery_status (early / on_time / late / NULL)
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_order (
        order_id, order_status, order_purchase_date_key, order_approved_at,
        order_delivered_carrier_date, order_delivered_customer_date,
        order_estimated_delivery_date, delivery_status
    )
    SELECT
        o.order_id,
        o.order_status,
        CAST(strftime(o.order_purchase_timestamp::DATE, '%Y%m%d') AS INTEGER),
        o.order_approved_at,
        o.order_delivered_carrier_date,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        CASE
            WHEN o.order_delivered_customer_date IS NULL THEN NULL
            WHEN o.order_delivered_customer_date::DATE < o.order_estimated_delivery_date::DATE THEN 'early'
            WHEN o.order_delivered_customer_date::DATE = o.order_estimated_delivery_date::DATE THEN 'on_time'
            ELSE 'late'
        END AS delivery_status
    FROM read_csv_auto('{CLEAN_DIR}/orders_clean.csv') o
""")
print("dim_order loaded:", con.execute("SELECT COUNT(*) FROM dim_order").fetchone()[0])


# ---------------------------------------------------------------------------
# 11. dim_review
#     review_id is NOT globally unique in the raw data (reused across
#     different orders in ~561 cases), so we generate a surrogate review_key
#     and enforce uniqueness on order_id instead (already deduped upstream).
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO dim_review (review_key, review_id, order_id, review_score, review_creation_date, review_answer_timestamp)
    SELECT
        ROW_NUMBER() OVER (ORDER BY order_id) AS review_key,
        review_id, order_id, review_score, review_creation_date, review_answer_timestamp
    FROM read_csv_auto('{CLEAN_DIR}/order_reviews_clean.csv')
""")
print("dim_review loaded:", con.execute("SELECT COUNT(*) FROM dim_review").fetchone()[0])


# ---------------------------------------------------------------------------
# 12. fact_order_items - grain: one row per order item
#     LEFT JOIN payments and reviews so orders missing either are NOT dropped
# ---------------------------------------------------------------------------
con.execute(f"""
    INSERT INTO fact_order_items (
        order_item_key, order_id, order_item_id, product_id, seller_id, customer_id,
        review_key, shipping_limit_date, price, freight_value, revenue,
        total_payment_value, payment_installments, payment_types
    )
    SELECT
        ROW_NUMBER() OVER (ORDER BY oi.order_id, oi.order_item_id) AS order_item_key,
        oi.order_id,
        oi.order_item_id,
        oi.product_id,
        oi.seller_id,
        o.customer_id,
        r.review_key,
        oi.shipping_limit_date,
        oi.price,
        oi.freight_value,
        oi.price + oi.freight_value AS revenue,
        p.total_payment_value,
        p.max_installments,
        p.payment_types
    FROM read_csv_auto('{CLEAN_DIR}/order_items_clean.csv') oi
    JOIN read_csv_auto('{CLEAN_DIR}/orders_clean.csv') o ON o.order_id = oi.order_id
    LEFT JOIN read_csv_auto('{CLEAN_DIR}/order_payments_clean.csv') p ON p.order_id = oi.order_id
    LEFT JOIN dim_review r ON r.order_id = oi.order_id
""")
print("fact_order_items loaded:", con.execute("SELECT COUNT(*) FROM fact_order_items").fetchone()[0])


# ---------------------------------------------------------------------------
# Sanity checks - row counts + orphan FK checks
# ---------------------------------------------------------------------------
print("\n--- Sanity checks ---")

raw_items = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{CLEAN_DIR}/order_items_clean.csv')").fetchone()[0]
fact_items = con.execute("SELECT COUNT(*) FROM fact_order_items").fetchone()[0]
print(f"order_items_clean rows: {raw_items} | fact_order_items rows: {fact_items} "
      f"({'OK - no items dropped' if raw_items == fact_items else 'MISMATCH'})")

orphan_product = con.execute("""
    SELECT COUNT(*) FROM fact_order_items f LEFT JOIN dim_product p ON f.product_id = p.product_id
    WHERE p.product_id IS NULL
""").fetchone()[0]
orphan_seller = con.execute("""
    SELECT COUNT(*) FROM fact_order_items f LEFT JOIN dim_seller s ON f.seller_id = s.seller_id
    WHERE s.seller_id IS NULL
""").fetchone()[0]
orphan_customer = con.execute("""
    SELECT COUNT(*) FROM fact_order_items f LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
    WHERE c.customer_id IS NULL
""").fetchone()[0]
print(f"Orphan product FKs: {orphan_product} | Orphan seller FKs: {orphan_seller} | Orphan customer FKs: {orphan_customer}")

no_review = con.execute("SELECT COUNT(*) FROM fact_order_items WHERE review_key IS NULL").fetchone()[0]
no_payment = con.execute("SELECT COUNT(*) FROM fact_order_items WHERE total_payment_value IS NULL").fetchone()[0]
no_delivery = con.execute("""
    SELECT COUNT(*) FROM fact_order_items f JOIN dim_order o ON f.order_id = o.order_id
    WHERE o.order_delivered_customer_date IS NULL
""").fetchone()[0]
print(f"Fact rows with no review: {no_review} | no payment: {no_payment} | undelivered order: {no_delivery}")
print("(These being > 0 is CORRECT - it confirms such rows were preserved, not dropped.)")

con.close()
print("\nETL load complete. Warehouse saved to:", DB_PATH)