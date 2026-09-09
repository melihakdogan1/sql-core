"""Synthetic data generation pipeline for E-Commerce OLTP schema.

Generates ~600k relational records featuring Power-Law (Pareto) sales distributions,
seasonal anomalies (Q4 spikes), and intentional data-quality edge cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import io
import logging
import os
import sys
import time
from typing import Final

from faker import Faker
import numpy as np
import psycopg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DATABASE_URL: Final[str] = os.getenv(
    "DATABASE_URL",
    "postgresql://dev_user:dev_password@localhost:5432/ecommerce_oltp",
)

# Volume Configuration
NUM_USERS: Final[int] = 20_000
NUM_CATEGORIES: Final[int] = 20
NUM_PRODUCTS: Final[int] = 1_000
NUM_COUPONS: Final[int] = 50
NUM_ORDERS: Final[int] = 100_000
CHUNK_BUFFER_SIZE: Final[int] = 50_000

fake = Faker("tr_TR")
np.random.seed(42)


def bulk_copy(
    cursor: psycopg.Cursor,
    table: str,
    columns: list[str],
    data_buffer: io.StringIO,
) -> None:
    """Streams CSV text data directly into PostgreSQL using binary COPY protocol."""
    data_buffer.seek(0)
    col_spec = ", ".join(columns)
    copy_query = f"COPY {table} ({col_spec}) FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '\\N')"
    with cursor.copy(copy_query) as copy_stream:
        copy_stream.write(data_buffer.read())
    data_buffer.seek(0)
    data_buffer.truncate(0)


def seed_database() -> None:
    """Executes truncation, schema reseeding, and relationship population."""
    start_time = time.perf_counter()
    logger.info("Initializing database connection to: %s", DATABASE_URL.split("@")[-1])

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            logger.info("Truncating existing relations...")
            cur.execute("""
                TRUNCATE TABLE 
                    inventory_movements, reviews, shipments, 
                    payments, order_items, orders, 
                    coupons, products, categories, users 
                RESTART IDENTITY CASCADE;
            """)
            conn.commit()

            # 1. Product Categories
            logger.info("Generating %d static categories...", NUM_CATEGORIES)
            categories = [
                ("Elektronik", "elektronik"), ("Giyim", "giyim"), ("Ev & Yaşam", "ev-yasam"),
                ("Kitap", "kitap"), ("Spor", "spor"), ("Kozmetik", "kozmetik"),
                ("Oyuncak", "oyuncak"), ("Otomotiv", "otomotiv"), ("Süpermarket", "supermarket"),
                ("Bahçe", "bahce"), ("Aksesuar", "aksesuar"), ("Bebek", "bebek"),
                ("Müzik", "muzik"), ("Hobi", "hobi"), ("Yazılım", "yazilim"),
                ("Kırtasiye", "kirtasiye"), ("Pet Shop", "pet-shop"), ("Ayakkabı", "ayakkabi"),
                ("Sağlık", "saglik"), ("Mücevher", "mucevher"),
            ]
            buf = io.StringIO()
            for name, slug in categories:
                buf.write(f'"{name}","{slug}"\n')
            bulk_copy(cur, "categories", ["name", "slug"], buf)

            # 2. Users (5% deliberate missing contact info)
            logger.info("Generating %d users (5%% simulated data incompleteness)...", NUM_USERS)
            base_registration_date = datetime(2024, 1, 1)
            for i in range(1, NUM_USERS + 1):
                email = f"usr_{i}_{fake.unique.user_name()}@example.com"
                full_name = fake.name().replace('"', '""')
                phone = f'"{fake.phone_number()}"' if np.random.rand() > 0.05 else r"\N"
                city = f'"{fake.city()}"' if np.random.rand() > 0.05 else r"\N"
                created_at = (base_registration_date + timedelta(days=int(np.random.uniform(0, 365)))).isoformat()
                buf.write(f'"{email}","{full_name}",{phone},{city},"{created_at}"\n')
            bulk_copy(cur, "users", ["email", "full_name", "phone", "city", "created_at"], buf)

            # 3. Products
            logger.info("Generating %d products with log-normal pricing...", NUM_PRODUCTS)
            product_prices = []
            base_catalog_date = datetime(2024, 1, 1).isoformat()
            for p_id in range(1, NUM_PRODUCTS + 1):
                cat_id = int(np.random.randint(1, NUM_CATEGORIES + 1))
                sku = f"SKU-{cat_id:02d}-{p_id:05d}"
                product_name = f"Item {p_id} {fake.word().capitalize()}"
                cost = round(float(np.random.exponential(scale=120.0) + 10.0), 2)
                margin = float(np.random.uniform(1.2, 2.5))
                price = round(cost * margin, 2)
                product_prices.append(price)
                buf.write(f'{cat_id},"{sku}","{product_name}",{price},{cost},"{base_catalog_date}"\n')
            bulk_copy(cur, "products", ["category_id", "sku", "name", "price", "cost", "created_at"], buf)
            product_prices_arr = np.array(product_prices, dtype=np.float64)

            # 4. Promotional Coupons
            logger.info("Generating %d promotional coupons...", NUM_COUPONS)
            for c_id in range(1, NUM_COUPONS + 1):
                code = f"PROMO{c_id:02d}"
                discount = float(np.random.choice([5.0, 10.0, 15.0, 20.0, 25.0]))
                max_disc = float(np.random.choice([100.0, 250.0, 500.0]))
                valid_from = datetime(2025, 1, 1).isoformat()
                valid_to = datetime(2026, 12, 31).isoformat()
                buf.write(f'"{code}",{discount},{max_disc},"{valid_from}","{valid_to}"\n')
            bulk_copy(cur, "coupons", ["code", "discount_pct", "max_discount_amount", "valid_from", "valid_to"], buf)

            # 5. Orders (Seasonal Gaussian distribution concentrated in Q4)
            logger.info("Generating %d orders with Q4 seasonal spike and 2%% return rate...", NUM_ORDERS)
            days_span = np.arange(365)
            # Gaussian distribution centered around Black Friday (day 330)
            q4_seasonal_weights = 1.0 + 3.0 * np.exp(-((days_span - 330) ** 2) / (2 * 30 ** 2))
            q4_seasonal_weights /= q4_seasonal_weights.sum()
            assigned_order_days = np.random.choice(days_span, size=NUM_ORDERS, p=q4_seasonal_weights)

            user_ids = np.random.randint(1, NUM_USERS + 1, size=NUM_ORDERS)
            coupon_ids = [
                np.random.randint(1, NUM_COUPONS + 1) if np.random.rand() < 0.20 else r"\N"
                for _ in range(NUM_ORDERS)
            ]
            statuses = np.random.choice(
                ["completed", "returned", "pending", "cancelled"],
                size=NUM_ORDERS,
                p=[0.90, 0.02, 0.05, 0.03],
            )

            order_timestamps: list[datetime] = []
            order_base_date = datetime(2025, 1, 1)
            for idx in range(NUM_ORDERS):
                ts = order_base_date + timedelta(
                    days=int(assigned_order_days[idx]),
                    seconds=int(np.random.randint(0, 86400)),
                )
                order_timestamps.append(ts)
                buf.write(f'{user_ids[idx]},{coupon_ids[idx]},"{statuses[idx]}",0.00,0.00,"{ts.isoformat()}"\n')
            bulk_copy(cur, "orders", ["user_id", "coupon_id", "order_status", "total_amount", "discount_amount", "order_date"], buf)

            # 6. Order Items (Power-law Zipfian distribution on product catalog)
            logger.info("Simulating %d orders into line-items via Zipfian distribution...", NUM_ORDERS)
            # a=1.4 enforces Pareto principle: top 20% products account for ~80% volume
            zipf_indices = np.random.zipf(a=1.4, size=NUM_ORDERS * 4) % NUM_PRODUCTS
            items_per_order = np.random.choice([1, 2, 3, 4], size=NUM_ORDERS, p=[0.45, 0.30, 0.15, 0.10])

            order_totals = np.zeros(NUM_ORDERS, dtype=np.float64)
            zipf_ptr = 0

            for o_idx in range(NUM_ORDERS):
                order_id = o_idx + 1
                item_count = items_per_order[o_idx]
                for _ in range(item_count):
                    p_idx = zipf_indices[zipf_ptr]
                    zipf_ptr = (zipf_ptr + 1) % len(zipf_indices)

                    product_id = p_idx + 1
                    qty = int(np.random.choice([1, 2, 3], p=[0.85, 0.12, 0.03]))
                    unit_price = product_prices_arr[p_idx]
                    subtotal = round(qty * unit_price, 2)
                    order_totals[o_idx] += subtotal

                    buf.write(f"{order_id},{product_id},{qty},{unit_price},{subtotal}\n")

                if o_idx % CHUNK_BUFFER_SIZE == 0 and o_idx > 0:
                    bulk_copy(cur, "order_items", ["order_id", "product_id", "quantity", "unit_price", "subtotal"], buf)

            if buf.tell() > 0:
                bulk_copy(cur, "order_items", ["order_id", "product_id", "quantity", "unit_price", "subtotal"], buf)

            logger.info("Synchronizing order total amounts via aggregate update...")
            cur.execute("""
                UPDATE orders o
                SET total_amount = sub.aggregated_amount
                FROM (
                    SELECT order_id, SUM(subtotal) AS aggregated_amount
                    FROM order_items
                    GROUP BY order_id
                ) sub
                WHERE o.order_id = sub.order_id;
            """)

            # 7. Payments
            logger.info("Emitting %d settlement transactions...", NUM_ORDERS)
            payment_methods = ["credit_card", "bank_transfer", "gift_card"]
            assigned_methods = np.random.choice(payment_methods, size=NUM_ORDERS, p=[0.85, 0.10, 0.05])

            for idx in range(NUM_ORDERS):
                order_id = idx + 1
                status = "successful" if statuses[idx] in ["completed", "returned"] else "failed"
                pay_date = (order_timestamps[idx] + timedelta(minutes=int(np.random.randint(1, 45)))).isoformat()
                amount = order_totals[idx]
                buf.write(f'{order_id},"{assigned_methods[idx]}","{status}",{amount:.2f},"{pay_date}"\n')
            bulk_copy(cur, "payments", ["order_id", "payment_method", "payment_status", "amount", "payment_date"], buf)

            # 8. Shipments (Deliberate quality anomalies: delivered_at < shipped_at)
            logger.info("Generating logistics dispatch records with intentional edge-case anomalies...")
            carriers = ["Yurtiçi Kargo", "Aras Kargo", "MNG Kargo", "Trendyol Express"]
            fulfilled_indices = np.where((statuses == "completed") | (statuses == "returned"))[0]

            for idx in fulfilled_indices:
                order_id = idx + 1
                tracking_no = f"TRK-{order_id:07d}-{np.random.randint(1000, 9999)}"
                carrier = np.random.choice(carriers)
                shipped_at = order_timestamps[idx] + timedelta(hours=int(np.random.randint(12, 48)))

                # 0.5% intentional data corruption: delivery precedes shipment
                if np.random.rand() < 0.005:
                    delivered_at = shipped_at - timedelta(days=1)
                else:
                    delivered_at = shipped_at + timedelta(days=int(np.random.randint(1, 4)))

                buf.write(f'{order_id},"{tracking_no}","{carrier}","delivered","{shipped_at.isoformat()}","{delivered_at.isoformat()}"\n')
            bulk_copy(cur, "shipments", ["order_id", "tracking_number", "carrier", "shipment_status", "shipped_at", "delivered_at"], buf)

            # 9. Product Reviews
            logger.info("Generating 30,000 product customer feedback reviews...")
            for _ in range(30_000):
                u_id = int(np.random.randint(1, NUM_USERS + 1))
                p_id = int(np.random.randint(1, NUM_PRODUCTS + 1))
                rating = int(np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.05, 0.10, 0.30, 0.50]))
                comment = f'"{fake.sentence().replace(chr(34), chr(39))}"' if np.random.rand() > 0.30 else r"\N"
                created_at = (order_base_date + timedelta(days=int(np.random.uniform(15, 360)))).isoformat()
                buf.write(f'{u_id},{p_id},{rating},{comment},"{created_at}"\n')
            bulk_copy(cur, "reviews", ["user_id", "product_id", "rating", "comment", "created_at"], buf)

            # 10. Inventory Adjustments
            logger.info("Generating 20,000 warehouse inventory adjustments...")
            reasons = ["PO_PURCHASE", "ORDER_FULFILLMENT", "RETURN_RESTOCK", "DAMAGED_SCRAP"]
            for _ in range(20_000):
                p_id = int(np.random.randint(1, NUM_PRODUCTS + 1))
                m_type = np.random.choice(["IN", "OUT"], p=[0.30, 0.70])
                qty = int(np.random.randint(1, 50))
                reason = np.random.choice(reasons)
                created_at = (order_base_date + timedelta(days=int(np.random.uniform(0, 365)))).isoformat()
                buf.write(f'{p_id},"{m_type}",{qty},"{reason}","{created_at}"\n')
            bulk_copy(cur, "inventory_movements", ["product_id", "movement_type", "quantity", "reference_reason", "created_at"], buf)

            conn.commit()

    elapsed = time.perf_counter() - start_time
    logger.info("Database ingestion pipeline finalized successfully in %.2f seconds.", elapsed)


if __name__ == "__main__":
    seed_database()