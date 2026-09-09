# Ödev 3.4 — Veri Ambarı Modellemesi (Star Schema) Raporu

## 1. Mimari Tasarım (Grain & Şema)
- **Fact Tablosu:** `fact_sales` (Grain: Sipariş içerisindeki tekil ürün kalemi satırı).
- **Dimension Tabloları:** `dim_date`, `dim_users`, `dim_products`, `dim_coupons`.
- **Önceden Hesaplanmış Metrikler (Pre-aggregated Metrics):** `cost_amount`, `gross_margin`, `delivery_duration_days`.

---

## 2. OLTP vs. Star Schema Karşılaştırması

### Senaryo: Yıl/Çeyrek Bazında Kategori Kârlılık Analizi

#### A) OLTP Sorgusu (6 Tablo Join)
```sql
SELECT 
    c.name AS category_name,
    EXTRACT(YEAR FROM o.order_date) AS order_year,
    EXTRACT(QUARTER FROM o.order_date) AS order_quarter,
    ROUND(SUM(oi.subtotal), 2) AS total_revenue,
    ROUND(SUM(oi.subtotal - (oi.quantity * p.cost)), 2) AS total_profit
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories c ON p.category_id = c.category_id
WHERE o.order_status = 'completed'
GROUP BY c.name, EXTRACT(YEAR FROM o.order_date), EXTRACT(QUARTER FROM o.order_date)
ORDER BY total_profit DESC;
```

#### B) Star Schema Sorgusu (Sadece 2 Join + Basit Gruplama)
```sql
SELECT 
    dp.category_name,
    dd.year,
    dd.quarter,
    ROUND(SUM(fs.subtotal), 2) AS total_revenue,
    ROUND(SUM(fs.gross_margin), 2) AS total_profit
FROM fact_sales fs
JOIN dim_products dp ON fs.product_key = dp.product_key
JOIN dim_date dd ON fs.date_id = dd.date_id
WHERE fs.order_status = 'completed'
GROUP BY dp.category_name, dd.year, dd.quarter
ORDER BY total_profit DESC;
```

---

## 3. Elde Edilen Avantajlar
1. **Join Karmaşıklığının Azalması:** 6 tabloluk iç içe JOIN zinciri, olgu tablosundan boyutlara tek adımlı JOIN'lere indirgendi.
2. **Hesaplama Yükünün Önceden Alınması:** `gross_margin` ve teslimat süreleri ETL sırasında hesaplandığı için her BI/Dashboard sorgusunda satır başı çarpma/çıkarma maliyeti ortadan kalktı.
3. **Takvim Analitiği Kolaylığı:** `dim_date` sayesinde `EXTRACT` ve tarih fonksiyonları yerine doğrudan indeksli tamsayı (`date_id`) ve çeyrek/hafta sonu bayrakları üzerinden anlık filtreleme sağlandı.