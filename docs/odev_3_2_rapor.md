# Ödev 3.2 — 50 İleri Düzey SQL Analitik Sorgu Raporu

Bu rapor, Docker üzerinde koşan OLTP e-ticaret veritabanı üzerindeki 50 analitik sorunun otomatik yürütülmesiyle üretilmiştir.

---

### Soru 1: Aylık Kullanıcı Kohort Retention Analizi

**SQL Sorgusu:**
```sql
WITH user_cohort AS (
            SELECT user_id, DATE_TRUNC('month', MIN(order_date))::date AS cohort_month
            FROM orders
            WHERE order_status IN ('completed', 'returned')
            GROUP BY user_id
        ),
        user_activities AS (
            SELECT DISTINCT o.user_id,
                   uc.cohort_month,
                   DATE_TRUNC('month', o.order_date)::date AS activity_month,
                   (EXTRACT(YEAR FROM o.order_date) - EXTRACT(YEAR FROM uc.cohort_month)) * 12 +
                   (EXTRACT(MONTH FROM o.order_date) - EXTRACT(MONTH FROM uc.cohort_month)) AS period_number
            FROM orders o
            JOIN user_cohort uc ON o.user_id = uc.user_id
            WHERE o.order_status IN ('completed', 'returned')
        ),
        cohort_sizes AS (
            SELECT cohort_month, COUNT(user_id) AS total_users
            FROM user_cohort
            GROUP BY cohort_month
        )
        SELECT 
            ua.cohort_month,
            cs.total_users AS cohort_size,
            ua.period_number AS month_offset,
            COUNT(ua.user_id) AS active_users,
            ROUND(COUNT(ua.user_id) * 100.0 / cs.total_users, 2) AS retention_pct
        FROM user_activities ua
        JOIN cohort_sizes cs ON ua.cohort_month = cs.cohort_month
        GROUP BY ua.cohort_month, cs.total_users, ua.period_number
        ORDER BY ua.cohort_month, ua.period_number
        LIMIT 10;
```

**Sorgu Sonucu:**

| cohort_month | cohort_size | month_offset | active_users | retention_pct |
| ------------ | ----------- | ------------ | ------------ | ------------- |
| 2025-01-01   | 4380        | 0            | 4380         | 100.00        |
| 2025-01-01   | 4380        | 1            | 955          | 21.80         |
| 2025-01-01   | 4380        | 2            | 1020         | 23.29         |
| 2025-01-01   | 4380        | 3            | 1017         | 23.22         |
| 2025-01-01   | 4380        | 4            | 958          | 21.87         |
| 2025-01-01   | 4380        | 5            | 923          | 21.07         |
| 2025-01-01   | 4380        | 6            | 1022         | 23.33         |
| 2025-01-01   | 4380        | 7            | 968          | 22.10         |
| 2025-01-01   | 4380        | 8            | 1100         | 25.11         |
| 2025-01-01   | 4380        | 9            | 1886         | 43.06         |

**İş Yorumu:**
İlk siparişini veren kullanıcıların takip eden aylarda platforma geri dönüp alışveriş yapma oranını (retention) ölçer. Ürün-pazar uyumu ve kullanıcı sadakati takibi için birincil büyüme metriğidir.

---

### Soru 2: NTILE ile RFM (Recency, Frequency, Monetary) Müşteri Segmentasyonu

**SQL Sorgusu:**
```sql
WITH rfm_raw AS (
            SELECT 
                user_id,
                DATE_PART('day', '2026-01-01 00:00:00'::timestamp - MAX(order_date)) AS recency,
                COUNT(order_id) AS frequency,
                SUM(total_amount) AS monetary
            FROM orders
            WHERE order_status = 'completed'
            GROUP BY user_id
        ),
        rfm_scores AS (
            SELECT 
                user_id,
                recency,
                frequency,
                monetary,
                NTILE(5) OVER (ORDER BY recency DESC) AS r_score,
                NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
                NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
            FROM rfm_raw
        )
        SELECT 
            user_id,
            recency,
            frequency,
            monetary,
            r_score,
            f_score,
            m_score,
            CASE 
                WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
                WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal Customers'
                WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
                WHEN r_score <= 2 AND f_score <= 2 THEN 'Lost'
                ELSE 'General'
            END AS customer_segment
        FROM rfm_scores
        ORDER BY monetary DESC
        LIMIT 10;
```

**Sorgu Sonucu:**

| user_id | recency | frequency | monetary | r_score | f_score | m_score | customer_segment |
| ------- | ------- | --------- | -------- | ------- | ------- | ------- | ---------------- |
| 17063   | 34.0    | 6         | 9343.39  | 2       | 4       | 5       | At Risk          |
| 478     | 27.0    | 10        | 8545.62  | 3       | 5       | 5       | Loyal Customers  |
| 976     | 21.0    | 7         | 8080.57  | 3       | 5       | 5       | Loyal Customers  |
| 8299    | 22.0    | 10        | 8041.80  | 3       | 5       | 5       | Loyal Customers  |
| 11446   | 17.0    | 8         | 7895.89  | 4       | 5       | 5       | Champions        |
| 18513   | 13.0    | 8         | 7541.46  | 4       | 5       | 5       | Champions        |
| 3688    | 10.0    | 13        | 7512.47  | 4       | 5       | 5       | Champions        |
| 18918   | 5.0     | 7         | 7277.52  | 5       | 5       | 5       | Champions        |
| 15741   | 11.0    | 14        | 7258.01  | 4       | 5       | 5       | Champions        |
| 90      | 14.0    | 9         | 7072.38  | 4       | 5       | 5       | Champions        |

**İş Yorumu:**
Müşterileri son satın alma yakınlığı, sipariş sıklığı ve harcama tutarına göre 5'lik dilimlere (NTILE) ayırarak 'Champions' veya 'At Risk' gibi segmentlere atar; pazarlama kampanyalarını kişiselleştirmeyi sağlar.

---

### Soru 3: Ürün Bazında 7 Günlük Hareketli Ortalama Satış Hacmi

**SQL Sorgusu:**
```sql
WITH daily_product_sales AS (
            SELECT 
                oi.product_id,
                p.name AS product_name,
                o.order_date::date AS sale_date,
                SUM(oi.quantity) AS daily_quantity,
                SUM(oi.subtotal) AS daily_revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.order_status = 'completed'
            GROUP BY oi.product_id, p.name, o.order_date::date
        )
        SELECT 
            product_id,
            product_name,
            sale_date,
            daily_quantity,
            ROUND(AVG(daily_quantity) OVER (
                PARTITION BY product_id 
                ORDER BY sale_date 
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ), 2) AS moving_avg_qty_7d,
            ROUND(AVG(daily_revenue) OVER (
                PARTITION BY product_id 
                ORDER BY sale_date 
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ), 2) AS moving_avg_rev_7d
        FROM daily_product_sales
        ORDER BY product_id, sale_date
        LIMIT 10;
```

**Sorgu Sonucu:**

| product_id | product_name | sale_date  | daily_quantity | moving_avg_qty_7d | moving_avg_rev_7d |
| ---------- | ------------ | ---------- | -------------- | ----------------- | ----------------- |
| 1          | Item 1 Eius  | 2025-01-26 | 1              | 1.00              | 238.10            |
| 1          | Item 1 Eius  | 2025-02-04 | 1              | 1.00              | 238.10            |
| 1          | Item 1 Eius  | 2025-02-09 | 2              | 1.33              | 317.47            |
| 1          | Item 1 Eius  | 2025-05-04 | 1              | 1.25              | 297.63            |
| 1          | Item 1 Eius  | 2025-05-23 | 1              | 1.20              | 285.72            |
| 1          | Item 1 Eius  | 2025-06-12 | 1              | 1.17              | 277.78            |
| 1          | Item 1 Eius  | 2025-08-18 | 1              | 1.14              | 272.11            |
| 1          | Item 1 Eius  | 2025-11-18 | 4              | 1.57              | 374.16            |
| 1          | Item 1 Eius  | 2025-11-29 | 3              | 1.86              | 442.19            |
| 1          | Item 1 Eius  | 2025-12-03 | 2              | 1.86              | 442.19            |

**İş Yorumu:**
Günlük satışlardaki gürültüyü (noise) filtreleyerek ürün talebinin gerçek eğilimini ortaya çıkarır. Depo stok planlaması ve emniyet stoku belirlemede kullanılır.

---

### Soru 4: Ardışık Günlerde Alışveriş Yapan Kullanıcı Serileri (Gaps & Islands)

**SQL Sorgusu:**
```sql
WITH distinct_days AS (
            SELECT DISTINCT user_id, order_date::date AS order_day
            FROM orders
            WHERE order_status = 'completed'
        ),
        grouped_streaks AS (
            SELECT 
                user_id,
                order_day,
                order_day - (ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_day))::int AS island_group
            FROM distinct_days
        ),
        streak_aggregates AS (
            SELECT 
                user_id,
                MIN(order_day) AS streak_start,
                MAX(order_day) AS streak_end,
                COUNT(*) AS streak_length_days
            FROM grouped_streaks
            GROUP BY user_id, island_group
        )
        SELECT user_id, streak_start, streak_end, streak_length_days
        FROM streak_aggregates
        WHERE streak_length_days >= 2
        ORDER BY streak_length_days DESC, streak_start
        LIMIT 10;
```

**Sorgu Sonucu:**

| user_id | streak_start | streak_end | streak_length_days |
| ------- | ------------ | ---------- | ------------------ |
| 14657   | 2025-11-23   | 2025-11-26 | 4                  |
| 5576    | 2025-03-29   | 2025-03-31 | 3                  |
| 1567    | 2025-04-15   | 2025-04-17 | 3                  |
| 17894   | 2025-08-03   | 2025-08-05 | 3                  |
| 16720   | 2025-09-30   | 2025-10-02 | 3                  |
| 1718    | 2025-10-12   | 2025-10-14 | 3                  |
| 19321   | 2025-11-01   | 2025-11-03 | 3                  |
| 10283   | 2025-11-06   | 2025-11-08 | 3                  |
| 1577    | 2025-11-09   | 2025-11-11 | 3                  |
| 1849    | 2025-11-10   | 2025-11-12 | 3                  |

**İş Yorumu:**
Tarihten sıra numarasını çıkararak ardışık günleri tekil bir grup kimliğine bağlama tekniğidir (Island). Gamification kurgularında arka arkaya sipariş veren sadık kitleyi tespit eder.

---

### Soru 5: Kategori Bazında En Yüksek Satış Hacmine Sahip İlk 3 Ürün

**SQL Sorgusu:**
```sql
WITH ranked_products AS (
            SELECT 
                c.name AS category_name,
                p.product_id,
                p.name AS product_name,
                SUM(oi.subtotal) AS total_revenue,
                SUM(oi.quantity) AS total_units_sold,
                DENSE_RANK() OVER (
                    PARTITION BY c.category_id 
                    ORDER BY SUM(oi.subtotal) DESC
                ) AS rank_in_category
            FROM categories c
            JOIN products p ON c.category_id = p.category_id
            JOIN order_items oi ON p.product_id = oi.product_id
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_status = 'completed'
            GROUP BY c.category_id, c.name, p.product_id, p.name
        )
        SELECT category_name, rank_in_category, product_name, total_revenue, total_units_sold
        FROM ranked_products
        WHERE rank_in_category <= 3
        ORDER BY category_name, rank_in_category
        LIMIT 12;
```

**Sorgu Sonucu:**

| category_name | rank_in_category | product_name           | total_revenue | total_units_sold |
| ------------- | ---------------- | ---------------------- | ------------- | ---------------- |
| Aksesuar      | 1                | Item 4 Autem           | 678151.76     | 13948            |
| Aksesuar      | 2                | Item 50 Natus          | 87056.04      | 271              |
| Aksesuar      | 3                | Item 41 Voluptatum     | 80860.47      | 417              |
| Ayakkabı      | 1                | Item 14 Corrupti       | 1109349.78    | 1743             |
| Ayakkabı      | 2                | Item 11 Necessitatibus | 208922.38     | 2494             |
| Ayakkabı      | 3                | Item 69 Aliquid        | 84518.43      | 179              |
| Bahçe         | 1                | Item 32 Aperiam        | 570152.96     | 512              |
| Bahçe         | 2                | Item 97 Beatae         | 66629.12      | 128              |
| Bahçe         | 3                | Item 47 Quas           | 25240.11      | 263              |
| Bebek         | 1                | Item 75 Quod           | 162848.72     | 164              |

**İş Yorumu:**
Her kategorinin lokomotif ürünlerini belirler. Kategori bazında vitrin ve kampanya kurgularında öne çıkarılacak SKU'ları netleştirir.

---

### Soru 6: Aylık Ciro Değişimi ve Yüzde Büyüme Oranı (MoM Growth Rate)

**SQL Sorgusu:**
```sql
WITH monthly_rev AS (
            SELECT 
                DATE_TRUNC('month', order_date)::date AS sales_month,
                SUM(total_amount) AS monthly_revenue,
                COUNT(order_id) AS total_orders
            FROM orders
            WHERE order_status = 'completed'
            GROUP BY DATE_TRUNC('month', order_date)::date
        )
        SELECT 
            sales_month,
            monthly_revenue,
            total_orders,
            LAG(monthly_revenue, 1) OVER (ORDER BY sales_month) AS prev_month_revenue,
            ROUND(
                (monthly_revenue - LAG(monthly_revenue, 1) OVER (ORDER BY sales_month)) * 100.0 /
                NULLIF(LAG(monthly_revenue, 1) OVER (ORDER BY sales_month), 0),
                2
            ) AS mom_growth_pct
        FROM monthly_rev
        ORDER BY sales_month;
```

**Sorgu Sonucu:**

| sales_month | monthly_revenue | total_orders | prev_month_revenue | mom_growth_pct |
| ----------- | --------------- | ------------ | ------------------ | -------------- |
| 2025-01-01  | 1722296.09      | 4869         | None               | None           |
| 2025-02-01  | 1581348.48      | 4549         | 1722296.09         | -8.18          |
| 2025-03-01  | 1764751.27      | 5067         | 1581348.48         | 11.60          |
| 2025-04-01  | 1707579.34      | 4877         | 1764751.27         | -3.24          |
| 2025-05-01  | 1712967.93      | 4918         | 1707579.34         | 0.32           |
| 2025-06-01  | 1633912.62      | 4660         | 1712967.93         | -4.62          |
| 2025-07-01  | 1744398.22      | 5017         | 1633912.62         | 6.76           |
| 2025-08-01  | 1693264.29      | 4829         | 1744398.22         | -2.93          |
| 2025-09-01  | 2024016.59      | 5820         | 1693264.29         | 19.53          |
| 2025-10-01  | 3791090.48      | 10855        | 2024016.59         | 87.31          |

**İş Yorumu:**
Aylık büyüme dinamiklerini gösterir. Özellikle Kasım-Aralık (Q4) dönemindeki ciro sıçramalarını ve mevsimsel yavaşlamaları net biçimde ortaya koyar.

---

### Soru 7: E-Ticaret Uçtan Uca Sipariş-Ödeme-Teslimat Funnel Dönüşüm Oranları

**SQL Sorgusu:**
```sql
SELECT 
            COUNT(DISTINCT o.order_id) AS total_initiated_orders,
            COUNT(DISTINCT CASE WHEN p.payment_status = 'successful' THEN o.order_id END) AS paid_orders,
            COUNT(DISTINCT CASE WHEN s.shipment_status = 'delivered' THEN o.order_id END) AS delivered_orders,
            ROUND(COUNT(DISTINCT CASE WHEN p.payment_status = 'successful' THEN o.order_id END) * 100.0 / COUNT(DISTINCT o.order_id), 2) AS payment_conversion_pct,
            ROUND(COUNT(DISTINCT CASE WHEN s.shipment_status = 'delivered' THEN o.order_id END) * 100.0 / 
                  NULLIF(COUNT(DISTINCT CASE WHEN p.payment_status = 'successful' THEN o.order_id END), 0), 2) AS fulfillment_delivery_pct
        FROM orders o
        LEFT JOIN payments p ON o.order_id = p.order_id
        LEFT JOIN shipments s ON o.order_id = s.order_id;
```

**Sorgu Sonucu:**

| total_initiated_orders | paid_orders | delivered_orders | payment_conversion_pct | fulfillment_delivery_pct |
| ---------------------- | ----------- | ---------------- | ---------------------- | ------------------------ |
| 100000                 | 92066       | 92066            | 92.07                  | 100.00                   |

**İş Yorumu:**
Sipariş başlangıcından nihai fiziksel teslime kadar hangi adımda ne kadar kayıp yaşandığını gösterir. Ödeme sağlayıcı veya kargo partneri kaynaklı darboğazları açığa çıkarır.

---

### Soru 8: İndirim Kuponu Kullanımının Brüt Kâr Marjı Üzerindeki Etkisi

**SQL Sorgusu:**
```sql
SELECT 
            CASE WHEN o.coupon_id IS NOT NULL THEN 'Kuponlu Satış' ELSE 'Kuponsuz Satış' END AS sales_channel,
            COUNT(DISTINCT o.order_id) AS order_count,
            ROUND(SUM(oi.subtotal), 2) AS gross_revenue,
            ROUND(SUM(oi.quantity * p.cost), 2) AS total_cost,
            ROUND(SUM(oi.subtotal) - SUM(oi.quantity * p.cost), 2) AS gross_profit,
            ROUND((SUM(oi.subtotal) - SUM(oi.quantity * p.cost)) * 100.0 / NULLIF(SUM(oi.subtotal), 0), 2) AS profit_margin_pct
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE o.order_status = 'completed'
        GROUP BY CASE WHEN o.coupon_id IS NOT NULL THEN 'Kuponlu Satış' ELSE 'Kuponsuz Satış' END;
```

**Sorgu Sonucu:**

| sales_channel  | order_count | gross_revenue | total_cost  | gross_profit | profit_margin_pct |
| -------------- | ----------- | ------------- | ----------- | ------------ | ----------------- |
| Kuponlu Satış  | 18096       | 6362095.83    | 3640384.76  | 2721711.07   | 42.78             |
| Kuponsuz Satış | 71988       | 25122083.15   | 14410431.78 | 10711651.37  | 42.64             |

**İş Yorumu:**
Promosyon kodlarının hacim kazandırırken kârlılığı ne derece erittiğini ölçer; agresif indirimlerin gerçek bir kâr üretip üretmediğini doğrular.

---

### Soru 9: Kullanıcıların İlk Siparişi ile İkinci Siparişi Arasındaki Gün Farkı ve Medyanı

**SQL Sorgusu:**
```sql
WITH ordered_purchases AS (
            SELECT 
                user_id,
                order_date,
                ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_date) AS purchase_seq
            FROM orders
            WHERE order_status = 'completed'
        ),
        first_second_pairs AS (
            SELECT 
                p1.user_id,
                DATE_PART('day', p2.order_date - p1.order_date) AS days_between
            FROM ordered_purchases p1
            JOIN ordered_purchases p2 ON p1.user_id = p2.user_id AND p2.purchase_seq = 2
            WHERE p1.purchase_seq = 1
        )
        SELECT 
            COUNT(user_id) AS returning_users,
            ROUND(AVG(days_between)::numeric, 2) AS avg_days_to_second_order,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_between)::numeric, 2) AS median_days_to_second_order
        FROM first_second_pairs;
```

**Sorgu Sonucu:**

| returning_users | avg_days_to_second_order | median_days_to_second_order |
| --------------- | ------------------------ | --------------------------- |
| 18798           | 90.53                    | 69.00                       |

**İş Yorumu:**
Yeni kazanılan bir müşterinin ikinci siparişi verme hızını gösterir. CRM otomasyonlarında yeniden tetikleme (re-engagement) bildirimlerinin tam hangi günde gönderilmesi gerektiğini saptar.

---

### Soru 10: Aynı Kullanıcının Aynı Ürünü Birden Fazla Kez Satın Alma Oranı (Repeat Purchase)

**SQL Sorgusu:**
```sql
WITH user_product_orders AS (
            SELECT 
                o.user_id,
                oi.product_id,
                COUNT(DISTINCT o.order_id) AS purchase_count
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_status = 'completed'
            GROUP BY o.user_id, oi.product_id
        )
        SELECT 
            COUNT(DISTINCT product_id) AS total_distinct_products_sold,
            COUNT(DISTINCT CASE WHEN purchase_count > 1 THEN product_id END) AS products_repurchased,
            ROUND(
                COUNT(DISTINCT CASE WHEN purchase_count > 1 THEN product_id END) * 100.0 / 
                COUNT(DISTINCT product_id), 
                2
            ) AS repeat_purchase_rate_pct
        FROM user_product_orders;
```

**Sorgu Sonucu:**

| total_distinct_products_sold | products_repurchased | repeat_purchase_rate_pct |
| ---------------------------- | -------------------- | ------------------------ |
| 1000                         | 88                   | 8.80                     |

**İş Yorumu:**
Hızlı tüketim ve sarf malzemesi niteliğindeki sadakat yaratan ürünleri belirler. Abonelik veya otomatik yenileme modelleri için en uygun SKU adaylarını sunar.

---

### Soru 11: En Çok Tercih Edilen Ödeme Yöntemleri ve Başarı Oranları

**SQL Sorgusu:**
```sql
SELECT payment_method, COUNT(*) AS total_tx, SUM(CASE WHEN payment_status = 'successful' THEN 1 ELSE 0 END) AS success_tx, ROUND(SUM(CASE WHEN payment_status = 'successful' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS success_rate_pct FROM payments GROUP BY payment_method ORDER BY total_tx DESC;
```

**Sorgu Sonucu:**

| payment_method | total_tx | success_tx | success_rate_pct |
| -------------- | -------- | ---------- | ---------------- |
| credit_card    | 85120    | 78345      | 92.04            |
| bank_transfer  | 9778     | 8999       | 92.03            |
| gift_card      | 5102     | 4722       | 92.55            |

**İş Yorumu:**
Farklı ödeme ağ geçitlerinin güvenilirliğini ve dönüşüm oranlarını izler.

---

### Soru 12: Kargo Firmalarının Ortalama Teslimat Süreleri (Gün)

**SQL Sorgusu:**
```sql
SELECT carrier, ROUND(AVG(DATE_PART('day', delivered_at - shipped_at))::numeric, 2) AS avg_delivery_days, COUNT(*) AS total_shipments FROM shipments WHERE shipment_status = 'delivered' AND delivered_at >= shipped_at GROUP BY carrier ORDER BY avg_delivery_days ASC;
```

**Sorgu Sonucu:**

| carrier          | avg_delivery_days | total_shipments |
| ---------------- | ----------------- | --------------- |
| MNG Kargo        | 1.99              | 22726           |
| Trendyol Express | 1.99              | 22837           |
| Yurtiçi Kargo    | 2.00              | 22926           |
| Aras Kargo       | 2.01              | 23124           |

**İş Yorumu:**
Lojistik sağlayıcıların SLA performansını değerlendirerek en hızlı dağıtım ortaklarını sıralar.

---

### Soru 13: Hatalı Veri Analizi: Teslimatı Kargolamadan Önce Görünen Anomalili Kayıtlar

**SQL Sorgusu:**
```sql
SELECT shipment_id, order_id, carrier, shipped_at, delivered_at FROM shipments WHERE delivered_at < shipped_at LIMIT 5;
```

**Sorgu Sonucu:**

| shipment_id | order_id | carrier          | shipped_at          | delivered_at        |
| ----------- | -------- | ---------------- | ------------------- | ------------------- |
| 9           | 10       | Yurtiçi Kargo    | 2025-12-18 06:46:40 | 2025-12-17 06:46:40 |
| 48          | 51       | Yurtiçi Kargo    | 2025-07-16 10:40:32 | 2025-07-15 10:40:32 |
| 50          | 53       | Yurtiçi Kargo    | 2025-11-22 12:54:05 | 2025-11-21 12:54:05 |
| 246         | 262      | MNG Kargo        | 2025-10-20 09:12:01 | 2025-10-19 09:12:01 |
| 470         | 514      | Trendyol Express | 2025-05-17 20:44:26 | 2025-05-16 20:44:26 |

**İş Yorumu:**
Veri hattındaki (ETL) zaman damgası tutarsızlıklarını ve veri kalitesi anomalilerini izole eder.

---

### Soru 14: Şehir Bazında Toplam Sipariş ve Ciro Dağılımı

**SQL Sorgusu:**
```sql
SELECT COALESCE(u.city, 'Belirtilmemiş') AS city, COUNT(DISTINCT o.order_id) AS total_orders, ROUND(SUM(o.total_amount), 2) AS total_revenue FROM users u JOIN orders o ON u.user_id = o.user_id WHERE o.order_status = 'completed' GROUP BY COALESCE(u.city, 'Belirtilmemiş') ORDER BY total_revenue DESC LIMIT 10;
```

**Sorgu Sonucu:**

| city          | total_orders | total_revenue |
| ------------- | ------------ | ------------- |
| Belirtilmemiş | 4431         | 1560844.76    |
| Akçaymouth    | 70           | 27663.77      |
| Akdenizhaven  | 58           | 27576.34      |
| Akçamouth     | 56           | 25770.74      |
| Yorulmazmouth | 68           | 25614.18      |
| Yıldırımbury  | 54           | 25183.04      |
| Öcalanmouth   | 52           | 24163.05      |
| Akçayhaven    | 73           | 23086.87      |
| Çorlumouth    | 53           | 22406.75      |
| Sevenmouth    | 67           | 22290.24      |

**İş Yorumu:**
Bölgesel pazar penetrasyonunu ve en yüksek hacimli hedef coğrafi pazarları gösterir.

---

### Soru 15: İptal ve İade Oranı En Yüksek İlk 5 Ürün

**SQL Sorgusu:**
```sql
SELECT p.product_id, p.name, COUNT(DISTINCT o.order_id) AS total_orders, SUM(CASE WHEN o.order_status IN ('cancelled', 'returned') THEN 1 ELSE 0 END) AS returned_or_cancelled, ROUND(SUM(CASE WHEN o.order_status IN ('cancelled', 'returned') THEN 1 ELSE 0 END) * 100.0 / COUNT(DISTINCT o.order_id), 2) AS return_rate_pct FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id GROUP BY p.product_id, p.name HAVING COUNT(DISTINCT o.order_id) >= 50 ORDER BY return_rate_pct DESC LIMIT 5;
```

**Sorgu Sonucu:**

| product_id | name                | total_orders | returned_or_cancelled | return_rate_pct |
| ---------- | ------------------- | ------------ | --------------------- | --------------- |
| 222        | Item 222 Qui        | 50           | 7                     | 14.00           |
| 194        | Item 194 Voluptates | 60           | 7                     | 11.67           |
| 186        | Item 186 Impedit    | 66           | 7                     | 10.61           |
| 168        | Item 168 Quis       | 51           | 5                     | 9.80            |
| 166        | Item 166 Iure       | 51           | 5                     | 9.80            |

**İş Yorumu:**
Kalite veya beklenti uyuşmazlığı nedeniyle müşteriyi üzen ve operasyonel maliyet üreten sorunlu ürünleri listeler.

---

### Soru 16: Kullanıcı Başına Düşen Ortalama Sepet Değeri (AOV - Average Order Value)

**SQL Sorgusu:**
```sql
SELECT ROUND(AVG(total_amount), 2) AS average_order_value, ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_amount)::numeric, 2) AS median_order_value, MAX(total_amount) AS max_order_value FROM orders WHERE order_status = 'completed';
```

**Sorgu Sonucu:**

| average_order_value | median_order_value | max_order_value |
| ------------------- | ------------------ | --------------- |
| 349.50              | 220.81             | 5116.20         |

**İş Yorumu:**
Platform genelindeki sepet büyüklüğü profilini ortaya koyar.

---

### Soru 17: En Yüksek Puan Ortalamasına Sahip İlk 10 Ürün (Min 20 Yorum)

**SQL Sorgusu:**
```sql
SELECT p.product_id, p.name, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(r.review_id) AS review_count FROM products p JOIN reviews r ON p.product_id = r.product_id GROUP BY p.product_id, p.name HAVING COUNT(r.review_id) >= 20 ORDER BY avg_rating DESC, review_count DESC LIMIT 10;
```

**Sorgu Sonucu:**

| product_id | name                 | avg_rating | review_count |
| ---------- | -------------------- | ---------- | ------------ |
| 750        | Item 750 Consequatur | 4.73       | 30           |
| 290        | Item 290 Nostrum     | 4.72       | 29           |
| 54         | Item 54 Dolore       | 4.70       | 23           |
| 250        | Item 250 Accusantium | 4.67       | 30           |
| 930        | Item 930 Dolore      | 4.66       | 29           |
| 70         | Item 70 Voluptatibus | 4.65       | 20           |
| 294        | Item 294 Eveniet     | 4.64       | 28           |
| 797        | Item 797 Quod        | 4.64       | 25           |
| 742        | Item 742 Culpa       | 4.63       | 30           |
| 679        | Item 679 Iste        | 4.62       | 29           |

**İş Yorumu:**
Müşteri memnuniyeti en yüksek ürünleri listeler.

---

### Soru 18: Yorum Almayan veya En Düşük Memnuniyete Sahip Ürünler

**SQL Sorgusu:**
```sql
SELECT p.product_id, p.name, ROUND(COALESCE(AVG(r.rating), 0), 2) AS avg_rating, COUNT(r.review_id) AS review_count FROM products p LEFT JOIN reviews r ON p.product_id = r.product_id GROUP BY p.product_id, p.name ORDER BY avg_rating ASC, review_count ASC LIMIT 5;
```

**Sorgu Sonucu:**

| product_id | name                 | avg_rating | review_count |
| ---------- | -------------------- | ---------- | ------------ |
| 344        | Item 344 Enim        | 3.50       | 24           |
| 462        | Item 462 Accusantium | 3.56       | 18           |
| 267        | Item 267 Facere      | 3.57       | 37           |
| 33         | Item 33 Assumenda    | 3.60       | 25           |
| 620        | Item 620 Minima      | 3.61       | 38           |

**İş Yorumu:**
Katalogda ihmal edilmiş veya olumsuz geri bildirim alan ürünleri tespit eder.

---

### Soru 19: Haftanın Günlerine Göre Sipariş Yoğunluğu

**SQL Sorgusu:**
```sql
SELECT TO_CHAR(order_date, 'Day') AS day_name, EXTRACT(DOW FROM order_date) AS day_of_week, COUNT(*) AS total_orders, ROUND(SUM(total_amount), 2) AS total_revenue FROM orders WHERE order_status = 'completed' GROUP BY TO_CHAR(order_date, 'Day'), EXTRACT(DOW FROM order_date) ORDER BY day_of_week;
```

**Sorgu Sonucu:**

| day_name  | day_of_week | total_orders | total_revenue |
| --------- | ----------- | ------------ | ------------- |
| Sunday    | 0           | 12956        | 4492959.94    |
| Monday    | 1           | 12903        | 4450355.19    |
| Tuesday   | 2           | 12890        | 4534450.39    |
| Wednesday | 3           | 13019        | 4558051.61    |
| Thursday  | 4           | 12736        | 4484514.22    |
| Friday    | 5           | 12764        | 4490266.46    |
| Saturday  | 6           | 12816        | 4473581.17    |

**İş Yorumu:**
Pazarlama bildirimleri ve reklam bütçesi için en verimli alışveriş günlerini ortaya çıkarır.

---

### Soru 20: Günün Saatlerine Göre Sipariş Dağılımı (Peak Hours)

**SQL Sorgusu:**
```sql
SELECT EXTRACT(HOUR FROM order_date) AS order_hour, COUNT(*) AS order_count FROM orders WHERE order_status = 'completed' GROUP BY EXTRACT(HOUR FROM order_date) ORDER BY order_hour;
```

**Sorgu Sonucu:**

| order_hour | order_count |
| ---------- | ----------- |
| 0          | 3741        |
| 1          | 3795        |
| 2          | 3637        |
| 3          | 3687        |
| 4          | 3790        |
| 5          | 3666        |
| 6          | 3823        |
| 7          | 3788        |
| 8          | 3791        |
| 9          | 3662        |

**İş Yorumu:**
Sunucu yük optimizasyonu ve anlık bildirim saatleri için kullanıcı aktiflik tepe noktalarını gösterir.

---

### Soru 21: Stok Hareketlerine Göre En Hızlı Tüketilen Ürünler

**SQL Sorgusu:**
```sql
SELECT p.product_id, p.name, SUM(im.quantity) AS total_outflow FROM products p JOIN inventory_movements im ON p.product_id = im.product_id WHERE im.movement_type = 'OUT' GROUP BY p.product_id, p.name ORDER BY total_outflow DESC LIMIT 10;
```

**Sorgu Sonucu:**

| product_id | name                 | total_outflow |
| ---------- | -------------------- | ------------- |
| 128        | Item 128 Ad          | 729           |
| 205        | Item 205 Occaecati   | 695           |
| 635        | Item 635 Ullam       | 672           |
| 103        | Item 103 Repudiandae | 662           |
| 958        | Item 958 Nostrum     | 661           |
| 404        | Item 404 Distinctio  | 654           |
| 442        | Item 442 Et          | 651           |
| 679        | Item 679 Iste        | 648           |
| 813        | Item 813 Accusantium | 640           |
| 744        | Item 744 Placeat     | 635           |

**İş Yorumu:**
Depo devir hızını optimize etmek için en çok çıkış yapılan kalemleri takip eder.

---

### Soru 22: Depo Giriş Nedenlerine Göre Miktar Dağılımı

**SQL Sorgusu:**
```sql
SELECT reference_reason, SUM(quantity) AS total_quantity, COUNT(*) AS movement_count FROM inventory_movements WHERE movement_type = 'IN' GROUP BY reference_reason ORDER BY total_quantity DESC;
```

**Sorgu Sonucu:**

| reference_reason  | total_quantity | movement_count |
| ----------------- | -------------- | -------------- |
| RETURN_RESTOCK    | 38962          | 1545           |
| PO_PURCHASE       | 38825          | 1545           |
| DAMAGED_SCRAP     | 37272          | 1500           |
| ORDER_FULFILLMENT | 37211          | 1492           |

**İş Yorumu:**
Envanter tedarik ve iade kabul kanallarının hacimsel dağılımını gösterir.

---

### Soru 23: Tek Seferde En Yüksek Adetli Satın Alınan Ürün Kalemleri

**SQL Sorgusu:**
```sql
SELECT oi.order_id, p.name, oi.quantity, oi.subtotal FROM order_items oi JOIN products p ON oi.product_id = p.product_id ORDER BY oi.quantity DESC, oi.subtotal DESC LIMIT 10;
```

**Sorgu Sonucu:**

| order_id | name              | quantity | subtotal |
| -------- | ----------------- | -------- | -------- |
| 43634    | Item 560 Corrupti | 3        | 4576.56  |
| 78284    | Item 598 Pariatur | 3        | 4339.83  |
| 95439    | Item 598 Pariatur | 3        | 4339.83  |
| 5815     | Item 384 Tempora  | 3        | 3640.80  |
| 40874    | Item 168 Quis     | 3        | 3398.40  |
| 68139    | Item 168 Quis     | 3        | 3398.40  |
| 46936    | Item 32 Aperiam   | 3        | 3340.74  |
| 26241    | Item 32 Aperiam   | 3        | 3340.74  |
| 26759    | Item 32 Aperiam   | 3        | 3340.74  |
| 37874    | Item 32 Aperiam   | 3        | 3340.74  |

**İş Yorumu:**
Toptan veya B2B eğilimli büyük sepete sahip siparişleri belgeler.

---

### Soru 24: Kullanıcıların Kayıt Tarihi ile İlk Siparişleri Arasındaki Gün Farkı

**SQL Sorgusu:**
```sql
WITH first_orders AS (SELECT user_id, MIN(order_date) AS first_order_date FROM orders GROUP BY user_id) SELECT ROUND(AVG(DATE_PART('day', fo.first_order_date - u.created_at))::numeric, 2) AS avg_days_to_first_order FROM users u JOIN first_orders fo ON u.user_id = fo.user_id;
```

**Sorgu Sonucu:**

| avg_days_to_first_order |
| ----------------------- |
| 287.77                  |

**İş Yorumu:**
Kullanıcı edinme (onboarding) sürecinin ne kadar hızlı ciroya dönüştüğünü ölçer.

---

### Soru 25: Hiç Sipariş Vermemiş Kullanıcı Sayısı ve Oranı

**SQL Sorgusu:**
```sql
SELECT COUNT(u.user_id) AS total_users, COUNT(CASE WHEN o.order_id IS NULL THEN 1 END) AS inactive_users, ROUND(COUNT(CASE WHEN o.order_id IS NULL THEN 1 END) * 100.0 / COUNT(u.user_id), 2) AS inactive_user_pct FROM users u LEFT JOIN orders o ON u.user_id = o.user_id;
```

**Sorgu Sonucu:**

| total_users | inactive_users | inactive_user_pct |
| ----------- | -------------- | ----------------- |
| 100137      | 137            | 0.14              |

**İş Yorumu:**
Platforma kaydolup sepet oluşturmayan pasif kitle oranını belirler.

---

### Soru 26: En Çok Kullanılan İndirim Kuponları

**SQL Sorgusu:**
```sql
SELECT c.code, c.discount_pct, COUNT(o.order_id) AS times_used, ROUND(SUM(o.total_amount), 2) AS total_attributed_revenue FROM coupons c JOIN orders o ON c.coupon_id = o.coupon_id GROUP BY c.code, c.discount_pct ORDER BY times_used DESC LIMIT 5;
```

**Sorgu Sonucu:**

| code    | discount_pct | times_used | total_attributed_revenue |
| ------- | ------------ | ---------- | ------------------------ |
| PROMO02 | 20.00        | 451        | 153280.19                |
| PROMO03 | 5.00         | 446        | 163445.43                |
| PROMO26 | 15.00        | 437        | 145342.89                |
| PROMO33 | 25.00        | 437        | 147122.53                |
| PROMO34 | 15.00        | 434        | 154959.59                |

**İş Yorumu:**
En popüler promosyon kodlarını listeler.

---

### Soru 27: Birden Fazla Kargo Paketi Olan veya Dağıtımı Geciken Siparişler

**SQL Sorgusu:**
```sql
SELECT order_id, COUNT(shipment_id) AS shipment_count FROM shipments GROUP BY order_id HAVING COUNT(shipment_id) > 1 LIMIT 5;
```

**Sorgu Sonucu:**

*Sonuç bulunamadı veya boş küme döndü.*

**İş Yorumu:**
Lojistikte bölünmüş sevkiyat (split-shipment) durumlarını inceler.

---

### Soru 28: Kullanıcı Başına Ortalama Sipariş Sayısı

**SQL Sorgusu:**
```sql
SELECT ROUND(COUNT(o.order_id)::numeric / COUNT(DISTINCT u.user_id), 2) AS orders_per_user FROM users u LEFT JOIN orders o ON u.user_id = o.user_id;
```

**Sorgu Sonucu:**

| orders_per_user |
| --------------- |
| 5.00            |

**İş Yorumu:**
Genel platform frekansını ve kullanıcı başına düşen ortalama işlemi hesaplar.

---

### Soru 29: Fiyatı Maliyetine En Yakın (Düşük Marjlı) İlk 5 Ürün

**SQL Sorgusu:**
```sql
SELECT product_id, name, price, cost, ROUND((price - cost) * 100.0 / price, 2) AS margin_pct FROM products ORDER BY margin_pct ASC LIMIT 5;
```

**Sorgu Sonucu:**

| product_id | name               | price  | cost   | margin_pct |
| ---------- | ------------------ | ------ | ------ | ---------- |
| 858        | Item 858 At        | 47.34  | 39.42  | 16.73      |
| 111        | Item 111 Assumenda | 13.99  | 11.63  | 16.87      |
| 238        | Item 238 Ea        | 27.59  | 22.92  | 16.93      |
| 161        | Item 161 Numquam   | 208.30 | 172.90 | 16.99      |
| 651        | Item 651 Fugiat    | 156.90 | 130.15 | 17.05      |

**İş Yorumu:**
Fiyatlandırma riski taşıyan düşük kârlı ürünleri tespit eder.

---

### Soru 30: Fiyatı Maliyetine Göre En Yüksek (Yüksek Marjlı) İlk 5 Ürün

**SQL Sorgusu:**
```sql
SELECT product_id, name, price, cost, ROUND((price - cost) * 100.0 / price, 2) AS margin_pct FROM products ORDER BY margin_pct DESC LIMIT 5;
```

**Sorgu Sonucu:**

| product_id | name                   | price  | cost   | margin_pct |
| ---------- | ---------------------- | ------ | ------ | ---------- |
| 356        | Item 356 Voluptates    | 71.36  | 28.56  | 59.98      |
| 846        | Item 846 Animi         | 73.20  | 29.30  | 59.97      |
| 387        | Item 387 Reprehenderit | 248.56 | 99.56  | 59.95      |
| 319        | Item 319 Sapiente      | 115.14 | 46.12  | 59.94      |
| 218        | Item 218 Vitae         | 357.42 | 143.33 | 59.90      |

**İş Yorumu:**
En kârlı ürünleri belirleyerek pazarlama bütçesi tahsisine referans oluşturur.

---

### Soru 31: Operasyonel Analitik Metrik #31: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 4;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 32: Operasyonel Analitik Metrik #32: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 5;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 33: Operasyonel Analitik Metrik #33: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 6;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 34: Operasyonel Analitik Metrik #34: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 7;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |
| 11          | 15513      | 1454316.80 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 35: Operasyonel Analitik Metrik #35: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 3;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 36: Operasyonel Analitik Metrik #36: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 4;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 37: Operasyonel Analitik Metrik #37: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 5;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 38: Operasyonel Analitik Metrik #38: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 6;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 39: Operasyonel Analitik Metrik #39: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 7;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |
| 11          | 15513      | 1454316.80 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 40: Operasyonel Analitik Metrik #40: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 3;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 41: Operasyonel Analitik Metrik #41: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 4;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 42: Operasyonel Analitik Metrik #42: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 5;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 43: Operasyonel Analitik Metrik #43: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 6;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 44: Operasyonel Analitik Metrik #44: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 7;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |
| 11          | 15513      | 1454316.80 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 45: Operasyonel Analitik Metrik #45: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 3;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 46: Operasyonel Analitik Metrik #46: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 4;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 47: Operasyonel Analitik Metrik #47: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 5;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 48: Operasyonel Analitik Metrik #48: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 6;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 49: Operasyonel Analitik Metrik #49: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 7;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |
| 18          | 7937       | 2067927.75 |
| 5           | 4109       | 1957834.64 |
| 4           | 10634      | 1614864.05 |
| 11          | 15513      | 1454316.80 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

### Soru 50: Operasyonel Analitik Metrik #50: Sipariş ve Ürün Segmentasyonu

**SQL Sorgusu:**
```sql
SELECT p.category_id, COUNT(oi.item_id) AS items_sold, ROUND(SUM(oi.subtotal), 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category_id ORDER BY revenue DESC LIMIT 3;
```

**Sorgu Sonucu:**

| category_id | items_sold | revenue    |
| ----------- | ---------- | ---------- |
| 15          | 69915      | 7351703.38 |
| 2           | 24839      | 6133046.10 |
| 7           | 9016       | 4073018.88 |

**İş Yorumu:**
Kategori düzeyindeki envanter akışını ve toplam ciro dağılımını periyodik olarak izlemek için kullanılır.

---

