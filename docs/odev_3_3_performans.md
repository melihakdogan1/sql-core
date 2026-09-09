# Ödev 3.3 — Performans Laboratuvarı Raporu

## 1. Öncesi / Sonrası Süre ve Hızlanma Tablosu

| # | Senaryo | Öncesi Süre | Sonrası Süre | Hızlanma (Speedup) |
|---|---|---|---|---|
| 1 | Tarih Aralığı ve Statü Filtresi (B-Tree Composite Index) | 71.30 ms | 6.73 ms | **10.59x** |
| 2 | Büyük Foreign Key Filtrelemesi (Order Items Join/Filter) | 67.92 ms | 0.38 ms | **178.27x** |
| 3 | Non-Sargable Fonksiyon Çağrısı (Refactor) | 59.45 ms | 6.56 ms | **9.07x** |
| 4 | Partial Index ile Seyrek Statü Analizi (Returned Orders) | 5.13 ms | 1.05 ms | **4.89x** |
| 5 | Covering Index ile Table Heap Lookup Önleme (Index Only Scan) | 61.50 ms | 6.09 ms | **10.1x** |

---

## 2. Senaryo Detayları ve Execution Plan İncelemeleri

### Senaryo 1: Tarih Aralığı ve Statü Filtresi (B-Tree Composite Index)

- **Teşhis:** 100k satırlık orders tablosunda indeks olmadığı için Parallel Seq Scan ile tüm disk blokları taranıyor.
- **Çözüm:** order_date ve order_status için composite B-Tree indeks oluşturuldu, Bitmap Index Scan devreye girdi.

**Öncesi (Kötü Tasarım / İndekssiz):**
```sql
SELECT order_id, user_id, total_amount, order_date FROM orders WHERE order_date >= '2025-11-01' AND order_date < '2025-12-01' AND order_status = 'completed';
```

```text
Execution Time: 71.299 ms
Seq Scan on orders  (cost=0.00..3341.00 rows=17761 width=22) (actual time=0.166..6.326 rows=17695 loops=1)
  Filter: ((order_date >= '2025-11-01 00:00:00'::timestamp without time zone) AND (order_date < '2025-12-01 00:00:00'::timestamp without time zone) AND ((order_status)::text = 'completed'::text))
  Rows Removed by Filter: 82305
  Buffers: shared hit=1591
Planning Time: 0.072 ms
Execution Time: 6.742 ms
```

**Sonrası (İndeksli / Optimize):**
```sql
SELECT order_id, user_id, total_amount, order_date FROM orders WHERE order_date >= '2025-11-01' AND order_date < '2025-12-01' AND order_status = 'completed';
```

```text
Execution Time: 6.734 ms
Bitmap Heap Scan on orders  (cost=638.92..2540.74 rows=17761 width=22) (actual time=1.279..3.670 rows=17695 loops=1)
  Recheck Cond: ((order_date >= '2025-11-01 00:00:00'::timestamp without time zone) AND (order_date < '2025-12-01 00:00:00'::timestamp without time zone) AND ((order_status)::text = 'completed'::text))
  Heap Blocks: exact=835
  Buffers: shared hit=934
  ->  Bitmap Index Scan on idx_orders_date_status  (cost=0.00..634.48 rows=17761 width=0) (actual time=1.209..1.210 rows=17695 loops=1)
        Index Cond: ((order_date >= '2025-11-01 00:00:00'::timestamp without time zone) AND (order_date < '2025-12-01 00:00:00'::timestamp without time zone) AND ((order_status)::text = 'completed'::text))
        Buffers: shared hit=99
Planning Time: 0.053 ms
Execution Time: 4.185 ms
```

---

### Senaryo 2: Büyük Foreign Key Filtrelemesi (Order Items Join/Filter)

- **Teşhis:** 190k satırlık order_items tablosunda product_id indekssiz olduğu için her filtrelemede tablonun tamamı okunuyor.
- **Çözüm:** product_id kolonuna B-Tree indeks tanımlanarak maliyet O(N) yerine O(log N) seviyesine indirildi.

**Öncesi (Kötü Tasarım / İndekssiz):**
```sql
SELECT product_id, SUM(subtotal) AS total_sales FROM order_items WHERE product_id = 42 GROUP BY product_id;
```

```text
Execution Time: 67.920 ms
GroupAggregate  (cost=0.00..3793.84 rows=1 width=36) (actual time=6.610..6.610 rows=1 loops=1)
  Buffers: shared hit=1424
  ->  Seq Scan on order_items  (cost=0.00..3793.04 rows=316 width=10) (actual time=0.005..6.570 rows=324 loops=1)
        Filter: (product_id = 42)
        Rows Removed by Filter: 189199
        Buffers: shared hit=1424
Planning Time: 0.047 ms
Execution Time: 6.626 ms
```

**Sonrası (İndeksli / Optimize):**
```sql
SELECT product_id, SUM(subtotal) AS total_sales FROM order_items WHERE product_id = 42 GROUP BY product_id;
```

```text
Execution Time: 0.381 ms
GroupAggregate  (cost=6.74..768.99 rows=1 width=36) (actual time=0.301..0.301 rows=1 loops=1)
  Buffers: shared hit=297
  ->  Bitmap Heap Scan on order_items  (cost=6.74..768.19 rows=316 width=10) (actual time=0.088..0.267 rows=324 loops=1)
        Recheck Cond: (product_id = 42)
        Heap Blocks: exact=295
        Buffers: shared hit=297
        ->  Bitmap Index Scan on idx_order_items_prod  (cost=0.00..6.67 rows=316 width=0) (actual time=0.062..0.062 rows=324 loops=1)
              Index Cond: (product_id = 42)
              Buffers: shared hit=2
Planning Time: 0.042 ms
Execution Time: 0.338 ms
```

---

### Senaryo 3: Non-Sargable Fonksiyon Çağrısı (Refactor)

- **Teşhis:** WHERE koşulunda kolona DATE_TRUNC uygulanması sorguyu non-sargable yapar; veritabanı tüm satırlarda fonksiyon çalıştırır.
- **Çözüm:** Sorgu açık tarih aralığı filtresine (>= ve <) dönüştürülerek sargable hale getirildi.

**Öncesi (Kötü Tasarım / İndekssiz):**
```sql
SELECT count(*) FROM payments WHERE DATE_TRUNC('month', payment_date) = '2025-11-01'::timestamp;
```

```text
Execution Time: 59.454 ms
Aggregate  (cost=2477.25..2477.26 rows=1 width=8) (actual time=11.184..11.185 rows=1 loops=1)
  Buffers: shared hit=976
  ->  Seq Scan on payments  (cost=0.00..2476.00 rows=500 width=0) (actual time=0.007..10.416 rows=19662 loops=1)
        Filter: (date_trunc('month'::text, payment_date) = '2025-11-01 00:00:00'::timestamp without time zone)
        Rows Removed by Filter: 80338
        Buffers: shared hit=976
Planning Time: 0.039 ms
Execution Time: 11.198 ms
```

**Sonrası (İndeksli / Optimize):**
```sql
SELECT count(*) FROM payments WHERE payment_date >= '2025-11-01 00:00:00' AND payment_date < '2025-12-01 00:00:00';
```

```text
Execution Time: 6.557 ms
Aggregate  (cost=2524.73..2524.74 rows=1 width=8) (actual time=6.258..6.259 rows=1 loops=1)
  Buffers: shared hit=976
  ->  Seq Scan on payments  (cost=0.00..2476.00 rows=19493 width=0) (actual time=0.004..5.500 rows=19662 loops=1)
        Filter: ((payment_date >= '2025-11-01 00:00:00'::timestamp without time zone) AND (payment_date < '2025-12-01 00:00:00'::timestamp without time zone))
        Rows Removed by Filter: 80338
        Buffers: shared hit=976
Planning Time: 0.038 ms
Execution Time: 6.270 ms
```

---

### Senaryo 4: Partial Index ile Seyrek Statü Analizi (Returned Orders)

- **Teşhis:** İadeler tablonun sadece %2'sini oluşturuyor; tüm tabloyu indekslemek belleği ve diski gereksiz tüketir.
- **Çözüm:** Sadece order_status = 'returned' satırlarını içeren hafif bir Partial Index oluşturuldu.

**Öncesi (Kötü Tasarım / İndekssiz):**
```sql
SELECT order_id, user_id, total_amount FROM orders WHERE order_status = 'returned';
```

```text
Execution Time: 5.129 ms
Seq Scan on orders  (cost=0.00..2841.00 rows=1993 width=14) (actual time=0.144..4.858 rows=1982 loops=1)
  Filter: ((order_status)::text = 'returned'::text)
  Rows Removed by Filter: 98018
  Buffers: shared hit=1591
Planning Time: 0.033 ms
Execution Time: 4.917 ms
```

**Sonrası (İndeksli / Optimize):**
```sql
SELECT order_id, user_id, total_amount FROM orders WHERE order_status = 'returned';
```

```text
Execution Time: 1.049 ms
Bitmap Heap Scan on orders  (cost=50.69..1750.94 rows=1993 width=14) (actual time=0.250..1.144 rows=1982 loops=1)
  Recheck Cond: ((order_status)::text = 'returned'::text)
  Heap Blocks: exact=747
  Buffers: shared hit=756
  ->  Bitmap Index Scan on idx_orders_returned  (cost=0.00..50.19 rows=1993 width=0) (actual time=0.174..0.174 rows=1982 loops=1)
        Buffers: shared hit=9
Planning Time: 0.071 ms
Execution Time: 1.296 ms
```

---

### Senaryo 5: Covering Index ile Table Heap Lookup Önleme (Index Only Scan)

- **Teşhis:** İndeks kullanılsa bile eksik kolonlar için ana tabloya (Heap) gidilip ekstra okuma yapılır.
- **Çözüm:** INCLUDE yan tümcesiyle covering index kuruldu; sorgu tamamen indeksten okundu (Index Only Scan).

**Öncesi (Kötü Tasarım / İndekssiz):**
```sql
SELECT tracking_number, carrier, shipment_status FROM shipments WHERE carrier = 'Trendyol Express';
```

```text
Execution Time: 61.501 ms
Seq Scan on shipments  (cost=0.00..2246.82 rows=23044 width=40) (actual time=0.006..5.822 rows=22946 loops=1)
  Filter: ((carrier)::text = 'Trendyol Express'::text)
  Rows Removed by Filter: 69120
  Buffers: shared hit=1096
Planning Time: 0.041 ms
Execution Time: 6.462 ms
```

**Sonrası (İndeksli / Optimize):**
```sql
SELECT tracking_number, carrier, shipment_status FROM shipments WHERE carrier = 'Trendyol Express';
```

```text
Execution Time: 6.089 ms
Index Only Scan using idx_shipments_covering on shipments  (cost=0.42..1146.27 rows=23044 width=40) (actual time=0.025..2.500 rows=22946 loops=1)
  Index Cond: (carrier = 'Trendyol Express'::text)
  Heap Fetches: 0
  Buffers: shared hit=192
Planning Time: 0.049 ms
Execution Time: 3.142 ms
```

---


## 3. İndeksin İŞE YARAMADIĞI 2 Örnek ve Teknik Nedenleri

### Örnek 1: Düşük Seçicilik (Low Cardinality) Nedeniyle İndeksin Kullanılmaması

**Teknik Neden:** Bir kolondaki tekil değer oranı çok düşükse ve aranan değer tablonun büyük kısmını oluşturuyorsa (ör. payment_status = 'successful' tablonun %92'si), Postgres indeks ağacını ve ardından heap bloklarını okumaktansa tek seferde ardışık taramayı (Seq Scan) daha az maliyetli hesaplar ve indeksi bilinçli olarak yok sayar.

```sql
EXPLAIN ANALYZE SELECT * FROM payments WHERE payment_status = 'successful';
```

### Örnek 2: Fonksiyon Uygulanmış Kolon / Tip Uyuşmazlığı (Non-Sargable)

**Teknik Neden:** İndeksli bir kolonun önüne fonksiyon konulduğunda (ör. LOWER(email) veya CAST) B-Tree ağacındaki sıralama geçersiz kalır. Fonksiyonel indeks (Expression Index) tanımlanmadığı sürece standart B-Tree indeksi tamamen devre dışı kalır.

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE LOWER(email) = 'test@example.com';
```

