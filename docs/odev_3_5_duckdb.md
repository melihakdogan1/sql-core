# Ödev 3.5 — DuckDB ile Dosya Analitiği ve Pandas Kıyaslama Raporu

Bu rapor, NYC Taxi Parquet veri seti (~3 milyon satır) üzerinde sunucu kurmadan doğrudan Parquet dosyasından okuyan **DuckDB** ile belleğe dataframe açan **Pandas** motorlarının performans ve bellek kıyaslamasını içerir.

---

## 1. Veri Seti Yükleme ve Başlangıç Bellek Maliyeti

- **Veri Seti:** `yellow_tripdata_2024-01.parquet` (2,964,624 satır)
- **DuckDB Yükleme Mantığı:** Zero-Copy streaming / Projection Pushdown (Dosyayı belleğe kopyalamaz, sorgu anında sadece ilgili kolonları akıtır).
- **Pandas Bellek Tüketimi:** Dosyayı açıp RAM'e yüklemek **944.82 MB** ekstra bellek tüketti ve **3502.34 ms** sürdü.

---

## 2. 10 Analitik Sorgu Performans ve Süre Karşılaştırması

| # | Analitik Soru | DuckDB Süre | Pandas Süre | Hızlanma (Speedup) |
|---|---|---|---|---|
| 1 | Sorgu 1: Toplam Yolculuk ve Ortalama Tutar | 137.90 ms | 147.89 ms | **1.07x** |
| 2 | Sorgu 2: Yolcu Sayısına Göre Dağılım ve Mesafe | 96.80 ms | 1352.95 ms | **13.98x** |
| 3 | Sorgu 3: Ödeme Türlerine Göre Gelir | 91.34 ms | 136.35 ms | **1.49x** |
| 4 | Sorgu 4: En Yüksek Bahşiş Oranlı Bölgeler | 233.05 ms | 19210.88 ms | **82.43x** |
| 5 | Sorgu 5: Saat Bazında Trafik Yoğunluğu | 143.79 ms | 112.45 ms | **0.78x** |
| 6 | Sorgu 6: Uzun Mesafe (>20 mil) Sefer Analizi | 35.88 ms | 60.87 ms | **1.7x** |
| 7 | Sorgu 7: Negatif/Sıfır Tutar Anomalileri | 23.15 ms | 11.69 ms | **0.5x** |
| 8 | Sorgu 8: Ortalama Hızı En Yüksek Bölge Çiftleri | 503.06 ms | 12714.86 ms | **25.28x** |
| 9 | Sorgu 9: Havalimanı Ücreti Geliri ve Sefer Sayısı | 16.78 ms | 219.22 ms | **13.06x** |
| 10 | Sorgu 10: Yolculuk Süre Segmentasyonu | 197.35 ms | 183.30 ms | **0.93x** |

---

## 3. Mimari ve Mühendislik Değerlendirmesi

1. **Vektörize Motor (Vectorized Engine):** DuckDB, SIMD komut setlerini kullanarak kolon bazlı veriyi CPU cache seviyesinde işler; Pandas ise Python nesne dönüşümleri ve satır/seri overhead'i nedeniyle CPU'yu daha yoğun tüketir.
2. **Projection & Filter Pushdown:** DuckDB, `SELECT passenger_count` dediğimizde 19 kolonlu Parquet dosyasının sadece 1 kolonunu diskten okur. Pandas ise `read_parquet` ile tüm tabloyu RAM'e doldurmak zorundadır.
3. **Out-of-Core Processing:** DuckDB RAM'e sığmayan yüzlerce GB'lık dosyaları dahi diskten stream ederek işleyebilirken, Pandas makinenin RAM'i aşıldığı anda `OutOfMemory (OOM)` hatasıyla çöker.
