-- ============================================================================
-- Part 1: Snowflake Schema - Table Creation Script
-- Data Warehouse: DuckDB
-- Grain of fact table: ONE ROW PER ORDER ITEM
--   (i.e., one row per product line within an order - matches order_items_clean.csv,
--    since price/freight are recorded per item, not per order)
-- ============================================================================

-- ============================================================================
-- GEOGRAPHY HIERARCHY (snowflaked): zip_code -> city -> state -> region
-- Shared by BOTH customers and sellers (one hierarchy, referenced twice)
-- ============================================================================

CREATE TABLE dim_region (
    region_id     INTEGER PRIMARY KEY,
    region_name   VARCHAR NOT NULL UNIQUE      -- North, Northeast, Central-West, Southeast, South
);

CREATE TABLE dim_state (
    state_id      INTEGER PRIMARY KEY,
    state_code    VARCHAR NOT NULL UNIQUE,     -- e.g. 'SP', 'RJ'
    state_name    VARCHAR NOT NULL,
    region_id     INTEGER NOT NULL REFERENCES dim_region(region_id)
);

CREATE TABLE dim_city (
    city_id       INTEGER PRIMARY KEY,
    city_name     VARCHAR NOT NULL,            -- normalized (lowercase, accent-stripped)
    state_id      INTEGER NOT NULL REFERENCES dim_state(state_id),
    UNIQUE (city_name, state_id)
);

CREATE TABLE dim_zip_code (
    zip_code_prefix  INTEGER PRIMARY KEY,      -- from geolocation_clean.csv
    city_id          INTEGER NOT NULL REFERENCES dim_city(city_id),
    lat              DECIMAL(9,6),
    lng              DECIMAL(9,6)
);

-- ============================================================================
-- PRODUCT HIERARCHY (snowflaked): product -> category (+ English translation)
-- ============================================================================

CREATE TABLE dim_category (
    category_id            INTEGER PRIMARY KEY,
    category_name          VARCHAR NOT NULL UNIQUE,   -- from categories_clean.csv
    category_name_english  VARCHAR
);

CREATE TABLE dim_product (
    product_id                  VARCHAR PRIMARY KEY,   -- natural key, from products_clean.csv
    category_id                 INTEGER NOT NULL REFERENCES dim_category(category_id),
    product_name_length         INTEGER,
    product_description_length  INTEGER,
    product_photos_qty          INTEGER,
    product_weight_g            DECIMAL(10,2),
    product_length_cm           DECIMAL(10,2),
    product_height_cm           DECIMAL(10,2),
    product_width_cm            DECIMAL(10,2)
);

-- ============================================================================
-- SELLER HIERARCHY (snowflaked): seller -> acquisition details
-- ============================================================================

CREATE TABLE dim_seller (
    seller_id        VARCHAR PRIMARY KEY,       -- natural key, from sellers_clean.csv
    zip_code_prefix  INTEGER NOT NULL REFERENCES dim_zip_code(zip_code_prefix)
);

CREATE TABLE dim_seller_acquisition (
    seller_id                      VARCHAR PRIMARY KEY REFERENCES dim_seller(seller_id),
    mql_id                         VARCHAR,
    lead_origin                    VARCHAR,      -- marketing channel (Q10)
    first_contact_date             DATE,
    won_date                       TIMESTAMP,
    business_segment               VARCHAR,
    lead_type                      VARCHAR,
    business_type                  VARCHAR,
    declared_product_catalog_size  DOUBLE,
    declared_monthly_revenue       DOUBLE
    -- NOTE: not every seller has a matching acquisition record (only sellers
    -- recruited through the tracked marketing funnel do) - this table is
    -- intentionally sparse; sellers without a row here are just not part of
    -- that funnel, and should NOT be dropped from dim_seller.
);

-- ============================================================================
-- CUSTOMER DIMENSION (uses the shared geography hierarchy)
-- ============================================================================

CREATE TABLE dim_customer (
    customer_id         VARCHAR PRIMARY KEY,     -- from customers_clean.csv (order-level id)
    customer_unique_id   VARCHAR NOT NULL,        -- stable identity across multiple orders
    zip_code_prefix      INTEGER NOT NULL REFERENCES dim_zip_code(zip_code_prefix)
);

-- ============================================================================
-- DATE DIMENSION (generated, not from a raw file)
-- ============================================================================

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,           -- e.g. 20170925 (YYYYMMDD)
    full_date     DATE NOT NULL UNIQUE,
    day           INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    month_name    VARCHAR NOT NULL,
    quarter       INTEGER NOT NULL,
    year          INTEGER NOT NULL
);

-- ============================================================================
-- ORDER DIMENSION (order-level attributes not tied to a specific item)
-- Needed for Q9 (delivery timing) and to preserve order_status / missing dates
-- ============================================================================

CREATE TABLE dim_order (
    order_id                        VARCHAR PRIMARY KEY,
    order_status                    VARCHAR NOT NULL,
    order_purchase_date_key         INTEGER REFERENCES dim_date(date_key),
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,      -- NULL allowed: undelivered orders kept
    order_estimated_delivery_date   TIMESTAMP,
    delivery_status                 VARCHAR          -- 'early' | 'on_time' | 'late' | NULL (undelivered)
);

-- ============================================================================
-- REVIEW DIMENSION (kept separate; not every order has one)
-- ============================================================================

-- NOTE: review_id is NOT globally unique in the raw data (the same review_id
-- string is reused across multiple different orders in ~561 cases - a known
-- quirk of this dataset). order_id IS unique here (already deduped to one
-- review row per order in preprocessing), so we use a surrogate key and
-- enforce uniqueness on order_id instead.
CREATE TABLE dim_review (
    review_key                 BIGINT PRIMARY KEY,     -- surrogate key
    review_id                  VARCHAR,                -- natural id, NOT unique - reference only
    order_id                   VARCHAR NOT NULL UNIQUE REFERENCES dim_order(order_id),
    review_score                INTEGER,
    review_creation_date         TIMESTAMP,
    review_answer_timestamp      TIMESTAMP
);

-- ============================================================================
-- FACT TABLE
-- Grain: one row per order item (order_id + order_item_id)
-- ============================================================================

CREATE TABLE fact_order_items (
    order_item_key       BIGINT PRIMARY KEY,        -- surrogate key (auto-generated at load)
    order_id             VARCHAR NOT NULL REFERENCES dim_order(order_id),
    order_item_id        INTEGER NOT NULL,           -- item sequence number within the order
    product_id           VARCHAR NOT NULL REFERENCES dim_product(product_id),
    seller_id            VARCHAR NOT NULL REFERENCES dim_seller(seller_id),
    customer_id          VARCHAR NOT NULL REFERENCES dim_customer(customer_id),
    review_key           BIGINT REFERENCES dim_review(review_key),   -- NULL if order has no review
    shipping_limit_date  TIMESTAMP,

    -- measures
    price                DECIMAL(10,2) NOT NULL,
    freight_value        DECIMAL(10,2) NOT NULL,
    revenue              DECIMAL(10,2) NOT NULL,     -- = price + freight_value
    total_payment_value  DECIMAL(10,2),               -- from order_payments_clean (order-level, repeated per item)
    payment_installments INTEGER,
    payment_types        VARCHAR,

    UNIQUE (order_id, order_item_id)
);

-- ============================================================================
-- Indexes to speed up the analytical queries (rollups/cubes over these FKs)
-- ============================================================================

CREATE INDEX idx_fact_product   ON fact_order_items(product_id);
CREATE INDEX idx_fact_seller    ON fact_order_items(seller_id);
CREATE INDEX idx_fact_customer  ON fact_order_items(customer_id);
CREATE INDEX idx_fact_order     ON fact_order_items(order_id);

CREATE INDEX idx_product_category ON dim_product(category_id);
CREATE INDEX idx_seller_zip        ON dim_seller(zip_code_prefix);
CREATE INDEX idx_customer_zip      ON dim_customer(zip_code_prefix);
CREATE INDEX idx_zip_city          ON dim_zip_code(city_id);
CREATE INDEX idx_city_state        ON dim_city(state_id);
CREATE INDEX idx_state_region      ON dim_state(region_id);