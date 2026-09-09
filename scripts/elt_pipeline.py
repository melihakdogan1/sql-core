"""Idempotent ELT pipeline with SCD Type 2 support and Star Schema ingestion."""

from __future__ import annotations
import os
import time
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dev_user:dev_password@localhost:5432/ecommerce_oltp")

def run_idempotent_elt() -> None:
    start_time = time.perf_counter()
    print("Idempotent ELT Pipeline Başlatılıyor...")

    with psycopg.connect(DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # 1. Dim Date (Idempotent)
            print("1/5: dim_date dolduruluyor...")
            cur.execute("""
                INSERT INTO dim_date (date_id, full_date, year, quarter, month, month_name, day, day_name, is_weekend)
                SELECT 
                    TO_CHAR(d, 'YYYYMMDD')::INT,
                    d::DATE,
                    EXTRACT(YEAR FROM d)::INT,
                    EXTRACT(QUARTER FROM d)::INT,
                    EXTRACT(MONTH FROM d)::INT,
                    TO_CHAR(d, 'TMMonth'),
                    EXTRACT(DAY FROM d)::INT,
                    TO_CHAR(d, 'TMDay'),
                    CASE WHEN EXTRACT(ISODOW FROM d) IN (6, 7) THEN TRUE ELSE FALSE END
                FROM GENERATE_SERIES('2024-01-01'::DATE, '2026-12-31'::DATE, '1 day'::INTERVAL) d
                ON CONFLICT (date_id) DO NOTHING;
            """)

            # 2. Dim Product (Idempotent)
            print("2/5: dim_product dolduruluyor...")
            cur.execute("""
                INSERT INTO dim_product (product_id, sku, product_name, category_name, unit_cost, unit_price)
                SELECT p.product_id, p.sku, p.name, c.name, p.cost, p.price
                FROM products p
                JOIN categories c ON p.category_id = c.category_id
                ON CONFLICT (product_id) DO UPDATE SET
                    product_name = EXCLUDED.product_name,
                    category_name = EXCLUDED.category_name,
                    unit_cost = EXCLUDED.unit_cost,
                    unit_price = EXCLUDED.unit_price;
            """)

            # 3. Dim Customer - Initial Load (SCD2 Idempotent)
            print("3/5: dim_customer (SCD2) ilk yükleme yapılıyor...")
            cur.execute("""
                INSERT INTO dim_customer (user_id, email, full_name, city, valid_from, valid_to, is_current)
                SELECT 
                    u.user_id, u.email, u.full_name, COALESCE(u.city, 'Bilinmiyor'),
                    u.created_at, NULL, TRUE
                FROM users u
                WHERE NOT EXISTS (
                    SELECT 1 FROM dim_customer dc WHERE dc.user_id = u.user_id
                );
            """)

            # SCD2 Test Simülasyonu: 100 kullanıcının şehri değiştiğinde tarihçe koruma testi
            print("   -> SCD2 güncelleme testi uygulanıyor (Örnek şehir değişiklikleri)...")
            cur.execute("""
                -- Eski kaydı pasife çek (valid_to güncelle, is_current = FALSE)
                UPDATE dim_customer dc
                SET valid_to = '2025-06-01 00:00:00', is_current = FALSE
                WHERE dc.user_id BETWEEN 1 AND 100 AND dc.is_current = TRUE;

                -- Yeni versiyonu ekle (is_current = TRUE)
                INSERT INTO dim_customer (user_id, email, full_name, city, valid_from, valid_to, is_current)
                SELECT 
                    u.user_id, u.email, u.full_name, 'İstanbul (Taşındı)',
                    '2025-06-01 00:00:00', NULL, TRUE
                FROM users u
                WHERE u.user_id BETWEEN 1 AND 100;
            """)

            # 4. Fact Orders (Grain: 1 sipariş)
            print("4/5: fct_orders dolduruluyor...")
            cur.execute("""
                INSERT INTO fct_orders (order_id, customer_key, order_date_id, order_status, total_amount, discount_amount, delivery_days)
                SELECT 
                    o.order_id,
                    dc.customer_key,
                    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
                    o.order_status,
                    o.total_amount,
                    o.discount_amount,
                    CASE WHEN s.delivered_at >= s.shipped_at THEN DATE_PART('day', s.delivered_at - s.shipped_at)::INT ELSE NULL END
                FROM orders o
                JOIN dim_customer dc ON o.user_id = dc.user_id 
                    AND o.order_date >= dc.valid_from 
                    AND (dc.valid_to IS NULL OR o.order_date < dc.valid_to)
                LEFT JOIN shipments s ON o.order_id = s.order_id
                ON CONFLICT (order_id) DO UPDATE SET
                    order_status = EXCLUDED.order_status,
                    total_amount = EXCLUDED.total_amount,
                    delivery_days = EXCLUDED.delivery_days;
            """)

            # 5. Fact Order Items (Grain: 1 sipariş kalemi - Tekilleştirilmiş Idempotent)
            print("5/5: fct_order_items tekilleştirilip dolduruluyor...")
            cur.execute("""
                WITH aggregated_items AS (
                    SELECT 
                        oi.order_id,
                        oi.product_id,
                        SUM(oi.quantity) AS quantity,
                        MAX(oi.unit_price) AS unit_price,
                        SUM(oi.subtotal) AS subtotal
                    FROM order_items oi
                    GROUP BY oi.order_id, oi.product_id
                )
                INSERT INTO fct_order_items (order_id, order_date_id, customer_key, product_key, quantity, unit_price, cost_amount, subtotal, gross_margin)
                SELECT 
                    ai.order_id,
                    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
                    dc.customer_key,
                    dp.product_key,
                    ai.quantity,
                    ai.unit_price,
                    ROUND(ai.quantity * dp.unit_cost, 2),
                    ai.subtotal,
                    ROUND(ai.subtotal - (ai.quantity * dp.unit_cost), 2)
                FROM aggregated_items ai
                JOIN orders o ON ai.order_id = o.order_id
                JOIN dim_customer dc ON o.user_id = dc.user_id 
                    AND o.order_date >= dc.valid_from 
                    AND (dc.valid_to IS NULL OR o.order_date < dc.valid_to)
                JOIN dim_product dp ON ai.product_id = dp.product_id
                ON CONFLICT (order_id, product_key) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    subtotal = EXCLUDED.subtotal,
                    gross_margin = EXCLUDED.gross_margin;
            """)

    elapsed = time.perf_counter() - start_time
    print(f"ELT başarıyla bitti! Süre: {elapsed:.2f} sn.")

if __name__ == "__main__":
    run_idempotent_elt()