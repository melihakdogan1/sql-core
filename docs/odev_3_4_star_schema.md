# Ödev 3.4 — Star Schema Analitik Katman ve Performans Raporu

## 1. Grain Tanımları

- **`fct_orders` Grain:** 1 satır = 1 tekil siparişi temsil eder (Sipariş toplam tutarı, statüsü, indirim ve kargo süresi).
- **`fct_order_items` Grain:** 1 satır = 1 sipariş içindeki tekil ürün kalemini temsil eder (Adet, birim fiyat, satır kâr marjı).
- **`dim_customer` (SCD Type 2):** `valid_from`, `valid_to`, `is_current` bayraklarıyla müşterinin siparişi verdiği andaki özniteliklerini (ör. o tarihteki şehri) tarihsel olarak korur.

---

## 2. OLTP vs. Star Schema 10 Soru Süre Kıyaslama Tablosu

| # | Soru / Analiz | OLTP Süre | Star Schema Süre | Hızlanma |
|---|---|---|---|---|
| 1 | Aylık Ciro ve Büyüme (MoM) | 50.53 ms | 28.06 ms | **1.8x** |
| 2 | Kategori Bazında Toplam Kâr (Gross Margin) | 135.33 ms | 126.01 ms | **1.07x** |
| 3 | Hafta Sonu vs Hafta İçi Satış Analizi | 55.21 ms | 22.25 ms | **2.48x** |
| 4 | Şehirlere Göre Müşteri Ciro Dağılımı (SCD2 Duyarlı) | 61.48 ms | 55.45 ms | **1.11x** |
| 5 | En Çok Satan İlk 5 Ürün (Adet Bazında) | 53.74 ms | 84.67 ms | **0.63x** |
| 6 | Ortalama Teslimat Süresi | 21.23 ms | 11.53 ms | **1.84x** |
| 7 | Çeyrek (Quarter) Bazında Satış Hacmi | 97.50 ms | 24.96 ms | **3.91x** |
| 8 | Ortalama Sepet Tutarı (AOV) | 19.78 ms | 13.52 ms | **1.46x** |
| 9 | Kullanıcı Başına Toplam Harcama Dağılımı | 52.30 ms | 41.86 ms | **1.25x** |
| 10 | Kategori Bazında Satılan Toplam Kalem Sayısı | 47.91 ms | 44.90 ms | **1.07x** |

---

## 3. SCD2 Mantığı ve Idempotent Testi

- **Idempotency:** Pipeline `ON CONFLICT DO UPDATE / NOTHING` mekanizmasıyla inşa edildi. Betik 10 kez arka arkaya çalıştırılsa dahi yinelenen satır üretmez.
- **SCD2 Geçerlilik:** 1-100 ID'li kullanıcıların şehirleri simülasyonla güncellendiğinde, eski siparişlerin eski şehre (`valid_to` dolmuş pasif kayıt), yeni siparişlerin güncel şehre (`is_current = TRUE`) bağlandığı doğrulandı.
