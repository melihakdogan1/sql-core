"""NYC Taxi Analytics & Memory/Speed Benchmark: DuckDB vs Pandas.

Downloads yellow taxi trip records, executes 10 analytical queries on both
DuckDB and Pandas, measures latency and peak RAM usage, and outputs docs/odev_3_5_duckdb.md.
"""

from __future__ import annotations

import gc
import os
import time
import urllib.request
import duckdb
import pandas as pd
import psutil

DATA_DIR = "data"
PARQUET_FILE = os.path.join(DATA_DIR, "yellow_tripdata_2024-01.parquet")
DOWNLOAD_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet"
OUTPUT_REPORT = "docs/odev_3_5_duckdb.md"


def download_dataset() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PARQUET_FILE):
        print(f"Veri seti indiriliyor: {DOWNLOAD_URL} ...")
        urllib.request.urlretrieve(DOWNLOAD_URL, PARQUET_FILE)
        file_size_mb = os.path.getsize(PARQUET_FILE) / (1024 * 1024)
        print(f"İndirme tamamlandı: {PARQUET_FILE} ({file_size_mb:.2f} MB)")
    else:
        print(f"Veri seti zaten mevcut: {PARQUET_FILE}")


def get_process_memory_mb() -> float:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def measure_exec(func) -> tuple[float, float, any]:
    gc.collect()
    mem_before = get_process_memory_mb()
    t0 = time.perf_counter()
    result = func()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    mem_after = get_process_memory_mb()
    peak_mem_mb = max(mem_after - mem_before, 0.0)
    return elapsed_ms, peak_mem_mb, result


def run_benchmark() -> None:
    download_dataset()

    print("\nDuckDB ve Pandas üzerinde 10 analitik sorgu başlatılıyor...\n")
    con = duckdb.connect()

    # Pandas için veriyi yükleyelim (bu adımın bile RAM maliyetini göreceğiz)
    print("Pandas ile Parquet DataFrame belleğe okunuyor...")
    t_load_0 = time.perf_counter()
    mem_load_0 = get_process_memory_mb()
    df = pd.read_parquet(PARQUET_FILE)
    pandas_load_time = (time.perf_counter() - t_load_0) * 1000
    pandas_load_mem = get_process_memory_mb() - mem_load_0
    print(f"Pandas okuma bitti: {pandas_load_time:.2f} ms, Bellek artışı: {pandas_load_mem:.2f} MB, Satır sayısı: {len(df):,}\n")

    benchmarks = []

    # 1. Toplam yolculuk sayısı ve ortalama tutar
    def q1_duck():
        return con.execute(f"SELECT COUNT(*), AVG(total_amount) FROM '{PARQUET_FILE}'").fetchall()
    def q1_pd():
        return len(df), df["total_amount"].mean()

    # 2. Yolcu sayısına göre dağılım ve ortalama mesafe
    def q2_duck():
        return con.execute(f"SELECT passenger_count, COUNT(*), AVG(trip_distance) FROM '{PARQUET_FILE}' GROUP BY 1 ORDER BY 2 DESC").fetchall()
    def q2_pd():
        return df.groupby("passenger_count").agg(cnt=("trip_distance", "count"), avg_dist=("trip_distance", "mean")).sort_values("cnt", ascending=False)

    # 3. Ödeme türlerine göre toplam gelir
    def q3_duck():
        return con.execute(f"SELECT payment_type, SUM(total_amount) FROM '{PARQUET_FILE}' GROUP BY 1 ORDER BY 2 DESC").fetchall()
    def q3_pd():
        return df.groupby("payment_type")["total_amount"].sum().sort_values(ascending=False)

    # 4. En yüksek ortalama bahşiş oranına sahip alma bölgeleri (PULocationID) (Min 1000 yolculuk)
    def q4_duck():
        return con.execute(f"SELECT PULocationID, AVG(tip_amount / NULLIF(total_amount, 0)) AS tip_rate FROM '{PARQUET_FILE}' GROUP BY 1 HAVING COUNT(*) > 1000 ORDER BY 2 DESC LIMIT 5").fetchall()
    def q4_pd():
        sub = df[df["total_amount"] > 0]
        g = sub.groupby("PULocationID").filter(lambda x: len(x) > 1000)
        return (g["tip_amount"] / g["total_amount"]).groupby(g["PULocationID"]).mean().nlargest(5)

    # 5. Günün saatlerine göre yolculuk yoğunluğu
    def q5_duck():
        return con.execute(f"SELECT EXTRACT(HOUR FROM tpep_pickup_datetime) AS hr, COUNT(*) FROM '{PARQUET_FILE}' GROUP BY 1 ORDER BY 1").fetchall()
    def q5_pd():
        return df["tpep_pickup_datetime"].dt.hour.value_counts().sort_index()

    # 6. Uzun mesafe yolculuklar (Mesafe > 20 mil) oranı ve ortalama ücret
    def q6_duck():
        return con.execute(f"SELECT COUNT(*), AVG(total_amount) FROM '{PARQUET_FILE}' WHERE trip_distance > 20").fetchall()
    def q6_pd():
        f = df[df["trip_distance"] > 20]
        return len(f), f["total_amount"].mean()

    # 7. Ücret tutarı 0 veya negatif olan anomalili kayıtlar
    def q7_duck():
        return con.execute(f"SELECT COUNT(*) FROM '{PARQUET_FILE}' WHERE total_amount <= 0").fetchall()
    def q7_pd():
        return (df["total_amount"] <= 0).sum()

    # 8. Ortalama hız hesabı (Mesafe / Dakika) en yüksek 5 bölge çifti
    def q8_duck():
        return con.execute(f"""
            SELECT PULocationID, DOLocationID, 
                   AVG(trip_distance / NULLIF(date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime), 0)) * 60 AS avg_mph
            FROM '{PARQUET_FILE}'
            WHERE date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) BETWEEN 5 AND 120
            GROUP BY 1, 2
            HAVING COUNT(*) > 100
            ORDER BY 3 DESC LIMIT 5
        """).fetchall()
    def q8_pd():
        mins = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 60.0
        mask = (mins >= 5) & (mins <= 120)
        sub = df[mask].copy()
        sub["mph"] = (sub["trip_distance"] / (mins[mask])) * 60.0
        g = sub.groupby(["PULocationID", "DOLocationID"]).filter(lambda x: len(x) > 100)
        return g.groupby(["PULocationID", "DOLocationID"])["mph"].mean().nlargest(5)

    # 9. Havalimanı ek ücreti (Airport_fee) ödenen toplam sefer ve gelir
    def q9_duck():
        return con.execute(f"SELECT COUNT(*), SUM(Airport_fee) FROM '{PARQUET_FILE}' WHERE Airport_fee > 0").fetchall()
    def q9_pd():
        f = df[df["Airport_fee"] > 0]
        return len(f), f["Airport_fee"].sum()

    # 10. Yolculuk süresi dağılımı (Kısa, Orta, Uzun segmentler)
    def q10_duck():
        return con.execute(f"""
            SELECT 
                CASE 
                    WHEN date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) < 10 THEN 'Kısa (<10 dk)'
                    WHEN date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) BETWEEN 10 AND 30 THEN 'Orta (10-30 dk)'
                    ELSE 'Uzun (>30 dk)'
                END AS trip_type,
                COUNT(*),
                AVG(total_amount)
            FROM '{PARQUET_FILE}'
            GROUP BY 1
        """).fetchall()
    def q10_pd():
        mins = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 60.0
        cat = pd.cut(mins, bins=[-float("inf"), 10, 30, float("inf")], labels=["Kısa (<10 dk)", "Orta (10-30 dk)", "Uzun (>30 dk)"])
        return df.groupby(cat, observed=False).agg(cnt=("total_amount", "count"), avg_fare=("total_amount", "mean"))

    queries = [
        ("Sorgu 1: Toplam Yolculuk ve Ortalama Tutar", q1_duck, q1_pd),
        ("Sorgu 2: Yolcu Sayısına Göre Dağılım ve Mesafe", q2_duck, q2_pd),
        ("Sorgu 3: Ödeme Türlerine Göre Gelir", q3_duck, q3_pd),
        ("Sorgu 4: En Yüksek Bahşiş Oranlı Bölgeler", q4_duck, q4_pd),
        ("Sorgu 5: Saat Bazında Trafik Yoğunluğu", q5_duck, q5_pd),
        ("Sorgu 6: Uzun Mesafe (>20 mil) Sefer Analizi", q6_duck, q6_pd),
        ("Sorgu 7: Negatif/Sıfır Tutar Anomalileri", q7_duck, q7_pd),
        ("Sorgu 8: Ortalama Hızı En Yüksek Bölge Çiftleri", q8_duck, q8_pd),
        ("Sorgu 9: Havalimanı Ücreti Geliri ve Sefer Sayısı", q9_duck, q9_pd),
        ("Sorgu 10: Yolculuk Süre Segmentasyonu", q10_duck, q10_pd),
    ]

    for idx, (title, f_duck, f_pd) in enumerate(queries, start=1):
        print(f"Çalıştırılıyor [{idx}/10]: {title}...")
        t_duck, m_duck, _ = measure_exec(f_duck)
        t_pd, m_pd, _ = measure_exec(f_pd)
        speedup = round(t_pd / max(t_duck, 0.001), 2)
        benchmarks.append({
            "id": idx,
            "title": title,
            "duck_time": t_duck,
            "pd_time": t_pd,
            "speedup": speedup,
            "duck_mem": m_duck,
            "pd_mem": m_pd,
        })

    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# Ödev 3.5 — DuckDB ile Dosya Analitiği ve Pandas Kıyaslama Raporu\n\n")
        f.write("Bu rapor, NYC Taxi Parquet veri seti (~3 milyon satır) üzerinde sunucu kurmadan doğrudan Parquet dosyasından okuyan **DuckDB** ile belleğe dataframe açan **Pandas** motorlarının performans ve bellek kıyaslamasını içerir.\n\n---\n\n")
        
        f.write("## 1. Veri Seti Yükleme ve Başlangıç Bellek Maliyeti\n\n")
        f.write(f"- **Veri Seti:** `yellow_tripdata_2024-01.parquet` ({len(df):,} satır)\n")
        f.write("- **DuckDB Yükleme Mantığı:** Zero-Copy streaming / Projection Pushdown (Dosyayı belleğe kopyalamaz, sorgu anında sadece ilgili kolonları akıtır).\n")
        f.write(f"- **Pandas Bellek Tüketimi:** Dosyayı açıp RAM'e yüklemek **{pandas_load_mem:.2f} MB** ekstra bellek tüketti ve **{pandas_load_time:.2f} ms** sürdü.\n\n---\n\n")

        f.write("## 2. 10 Analitik Sorgu Performans ve Süre Karşılaştırması\n\n")
        f.write("| # | Analitik Soru | DuckDB Süre | Pandas Süre | Hızlanma (Speedup) |\n")
        f.write("|---|---|---|---|---|\n")
        for b in benchmarks:
            f.write(f"| {b['id']} | {b['title']} | {b['duck_time']:.2f} ms | {b['pd_time']:.2f} ms | **{b['speedup']}x** |\n")

        f.write("\n---\n\n")
        f.write("## 3. Mimari ve Mühendislik Değerlendirmesi\n\n")
        f.write("1. **Vektörize Motor (Vectorized Engine):** DuckDB, SIMD komut setlerini kullanarak kolon bazlı veriyi CPU cache seviyesinde işler; Pandas ise Python nesne dönüşümleri ve satır/seri overhead'i nedeniyle CPU'yu daha yoğun tüketir.\n")
        f.write("2. **Projection & Filter Pushdown:** DuckDB, `SELECT passenger_count` dediğimizde 19 kolonlu Parquet dosyasının sadece 1 kolonunu diskten okur. Pandas ise `read_parquet` ile tüm tabloyu RAM'e doldurmak zorundadır.\n")
        f.write("3. **Out-of-Core Processing:** DuckDB RAM'e sığmayan yüzlerce GB'lık dosyaları dahi diskten stream ederek işleyebilirken, Pandas makinenin RAM'i aşıldığı anda `OutOfMemory (OOM)` hatasıyla çöker.\n")

    print(f"\nBenchmark tamamlandı! Rapor oluşturuldu: {OUTPUT_REPORT}")


if __name__ == "__main__":
    run_benchmark()