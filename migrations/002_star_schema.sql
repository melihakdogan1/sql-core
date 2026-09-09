-- Dim Date
CREATE TABLE IF NOT EXISTS dim_date (
    date_id INT PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    day INT NOT NULL,
    day_name VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- Dim Customer with SCD Type 2
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    city VARCHAR(100),
    valid_from TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    valid_to TIMESTAMP WITHOUT TIME ZONE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_dim_customer_lookup ON dim_customer(user_id, is_current);

-- Dim Product
CREATE TABLE IF NOT EXISTS dim_product (
    product_key SERIAL PRIMARY KEY,
    product_id INT NOT NULL UNIQUE,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    unit_cost NUMERIC(10, 2) NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

-- Fact Orders (Grain: 1 satır = 1 tamamlanan/işlenen sipariş)
CREATE TABLE IF NOT EXISTS fct_orders (
    order_key SERIAL PRIMARY KEY,
    order_id INT NOT NULL UNIQUE,
    customer_key INT NOT NULL REFERENCES dim_customer(customer_key),
    order_date_id INT NOT NULL REFERENCES dim_date(date_id),
    order_status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) NOT NULL,
    delivery_days INT
);

-- Fact Order Items (Grain: 1 satır = 1 sipariş içindeki tekil ürün kalemi)
CREATE TABLE IF NOT EXISTS fct_order_items (
    order_item_key SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    order_date_id INT NOT NULL REFERENCES dim_date(date_id),
    customer_key INT NOT NULL REFERENCES dim_customer(customer_key),
    product_key INT NOT NULL REFERENCES dim_product(product_key),
    quantity INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    cost_amount NUMERIC(12, 2) NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    gross_margin NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uq_order_product UNIQUE (order_id, product_key)
);