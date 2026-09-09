-- Dimensional Model (Star Schema)

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

CREATE TABLE IF NOT EXISTS dim_users (
    user_key SERIAL PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    city VARCHAR(100),
    registration_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_key SERIAL PRIMARY KEY,
    product_id INT NOT NULL UNIQUE,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    unit_cost NUMERIC(10, 2) NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_coupons (
    coupon_key SERIAL PRIMARY KEY,
    coupon_id INT NOT NULL UNIQUE,
    code VARCHAR(50) NOT NULL,
    discount_pct NUMERIC(5, 2) NOT NULL,
    max_discount_amount NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_sales (
    sale_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    date_id INT NOT NULL REFERENCES dim_date(date_id),
    user_key INT NOT NULL REFERENCES dim_users(user_key),
    product_key INT NOT NULL REFERENCES dim_products(product_key),
    coupon_key INT REFERENCES dim_coupons(coupon_key),
    quantity INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    cost_amount NUMERIC(12, 2) NOT NULL,
    gross_margin NUMERIC(12, 2) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    delivery_duration_days INT
);