"""High-performance ELT pipeline using DuckDB and PostgreSQL.

Extracts operational data from OLTP tables, performs dimensional transformations,
and loads into Star Schema tables (dimensions + fact_sales).
"""

from __future__ import annotations

import os
import sys
import time
import duckdb
import psycopg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://dev_user:dev_password@localhost:5432/ecommerce_oltp",
)


def run_elt_pipeline() -> None:
    start_time = time.perf_counter()
    print("ELT Pipeline başlatılıyor...")

    # 1. PostgreSQL bağlantısı üzerinden doğrudan SQL tabanlı aktarım
    with psycopg.connect(DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Eski analitik tablolar temizleniyor...")
            cur.execute("""
                TRUNCATE TABLE fact_sales, dim_coupons, dim_products, dim_users, dim_date 
                RESTART IDENTITY CASCADE;
            """)

            # 1. Dim Date
            print("1/5: dim_date dolduruluyor...")
            cur.execute("""
                INSERT INTO dim_date (date_id, full_date, year, quarter, month, month_name, day, day_name, is_weekend)
                SELECT 
                    TO_CHAR(d, 'YYYYMMDD')::INT AS date_id,
                    d::DATE AS full_date,
                    EXTRACT(YEAR FROM d)::INT AS year,
                    EXTRACT(QUARTER FROM d)::INT AS quarter,
                    EXTRACT(MONTH FROM d)::INT AS month,
                    TO_CHAR(d, 'TMMonth') AS month_name,
                    EXTRACT(DAY FROM d)::INT AS day,
                    TO_CHAR(d, 'TMDay') AS day_name,
                    CASE WHEN EXTRACT(ISODOW FROM d) IN (6, 7) THEN TRUE ELSE FALSE END AS is_weekend
                FROM GENERATE_SERIES('2024-01-01'::DATE, '2026-12-31'::DATE, '1 day'::INTERVAL) d;
            """)

            # 2. Dim Users
            print("2/5: dim_users dolduruluyor...")
            cur.execute("""
                INSERT INTO dim_users (user_id, email, full_name, city, registration_date)
                SELECT user_id, email, full_name, city, created_at::DATE
                FROM users;
            """)

            # 3. Dim Products
            print("3/5: dim_products dolduruluyor...")
            cur.execute("""
                INSERT INTO dim_products (product_id, sku, product_name, category_name, unit_cost, unit_price)
                SELECT p.product_id, p.sku, p.name, c.name, p.cost, p.price
                FROM products p
                JOIN categories c ON p.category_id = c.category_id;
            """)

            # 4. Dim Coupons
            print("4/5: dim_coupons dolduruluyor...")
            cur.execute("""
                INSERT INTO dim_coupons (coupon_id, code, discount_pct, max_discount_amount)
                SELECT coupon_id, code, discount_pct, max_discount_amount
                FROM coupons;
            """)

            # 5. Fact Sales
            print("5/5: fact_sales hesaplanıp dolduruluyor...")
            cur.execute("""
                INSERT INTO fact_sales (
                    order_id, date_id, user_key, product_key, coupon_key,
                    quantity, unit_price, subtotal, cost_amount, gross_margin,
                    order_status, delivery_duration_days
                )
                SELECT 
                    o.order_id,
                    TO_CHAR(o.order_date, 'YYYYMMDD')::INT AS date_id,
                    du.user_key,
                    dp.product_key,
                    dc.coupon_key,
                    oi.quantity,
                    oi.unit_price,
                    oi.subtotal,
                    ROUND(oi.quantity * dp.unit_cost, 2) AS cost_amount,
                    ROUND(oi.subtotal - (oi.quantity * dp.unit_cost), 2) AS gross_margin,
                    o.order_status,
                    CASE 
                        WHEN s.delivered_at >= s.shipped_at THEN DATE_PART('day', s.delivered_at - s.shipped_at)::INT
                        ELSE NULL 
                    END AS delivery_duration_days
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                JOIN dim_users du ON o.user_id = du.user_id
                JOIN dim_products dp ON oi.product_id = dp.product_id
                LEFT JOIN dim_coupons dc ON o.coupon_id = dc.coupon_id
                LEFT JOIN shipments s ON o.order_id = s.order_id;
            """)

    elapsed = time.perf_counter() - start_time
    print(f"ELT Tamamlandı! Süre: {elapsed:.2f} saniye.")


if __name__ == "__main__":
    run_elt_pipeline()