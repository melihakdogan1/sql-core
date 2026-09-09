import os
import psycopg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://dev_user:dev_password@localhost:5432/ecommerce_oltp",
)

OUTPUT_FILE = "docs/odev_3_3_performans.md"

SCENARIOS = [
    {
        "id": 1,
        "title": "Tarih Aralığı ve Statü Filtresi (B-Tree Composite Index)",
        "slow_sql": "SELECT order_id, user_id, total_amount, order_date FROM orders WHERE order_date >= '2025-11-01' AND order_date < '2025-12-01' AND order_status = 'completed';",
        "index_sql": "CREATE INDEX IF NOT EXISTS idx_orders_date_status ON orders(order_date, order_status);",
        "drop_sql": "DROP INDEX IF EXISTS idx_orders_date_status;",
        "fast_sql": "SELECT order_id, user_id, total_amount, order_date FROM orders WHERE order_date >= '2025-11-01' AND order_date < '2025-12-01' AND order_status = 'completed';",
        "problem": "100k satırlık orders tablosunda indeks olmadığı için Parallel Seq Scan ile tüm disk blokları taranıyor.",
        "solution": "order_date ve order_status için composite B-Tree indeks oluşturuldu, Bitmap Index Scan devreye girdi.",
    },
    {
        "id": 2,
        "title": "Büyük Foreign Key Filtrelemesi (Order Items Join/Filter)",
        "slow_sql": "SELECT product_id, SUM(subtotal) AS total_sales FROM order_items WHERE product_id = 42 GROUP BY product_id;",
        "index_sql": "CREATE INDEX IF NOT EXISTS idx_order_items_prod ON order_items(product_id);",
        "drop_sql": "DROP INDEX IF EXISTS idx_order_items_prod;",
        "fast_sql": "SELECT product_id, SUM(subtotal) AS total_sales FROM order_items WHERE product_id = 42 GROUP BY product_id;",
        "problem": "190k satırlık order_items tablosunda product_id indekssiz olduğu için her filtrelemede tablonun tamamı okunuyor.",
        "solution": "product_id kolonuna B-Tree indeks tanımlanarak maliyet O(N) yerine O(log N) seviyesine indirildi.",
    },
    {
        "id": 3,
        "title": "Non-Sargable Fonksiyon Çağrısı (Refactor)",
        "slow_sql": "SELECT count(*) FROM payments WHERE DATE_TRUNC('month', payment_date) = '2025-11-01'::timestamp;",
        "index_sql": "",
        "drop_sql": "",
        "fast_sql": "SELECT count(*) FROM payments WHERE payment_date >= '2025-11-01 00:00:00' AND payment_date < '2025-12-01 00:00:00';",
        "problem": "WHERE koşulunda kolona DATE_TRUNC uygulanması sorguyu non-sargable yapar; veritabanı tüm satırlarda fonksiyon çalıştırır.",
        "solution": "Sorgu açık tarih aralığı filtresine (>= ve <) dönüştürülerek sargable hale getirildi.",
    },
    {
        "id": 4,
        "title": "Partial Index ile Seyrek Statü Analizi (Returned Orders)",
        "slow_sql": "SELECT order_id, user_id, total_amount FROM orders WHERE order_status = 'returned';",
        "index_sql": "CREATE INDEX IF NOT EXISTS idx_orders_returned ON orders(order_id, total_amount) WHERE order_status = 'returned';",
        "drop_sql": "DROP INDEX IF EXISTS idx_orders_returned;",
        "fast_sql": "SELECT order_id, user_id, total_amount FROM orders WHERE order_status = 'returned';",
        "problem": "İadeler tablonun sadece %2'sini oluşturuyor; tüm tabloyu indekslemek belleği ve diski gereksiz tüketir.",
        "solution": "Sadece order_status = 'returned' satırlarını içeren hafif bir Partial Index oluşturuldu.",
    },
    {
        "id": 5,
        "title": "Covering Index ile Table Heap Lookup Önleme (Index Only Scan)",
        "slow_sql": "SELECT tracking_number, carrier, shipment_status FROM shipments WHERE carrier = 'Trendyol Express';",
        "index_sql": "CREATE INDEX IF NOT EXISTS idx_shipments_covering ON shipments(carrier) INCLUDE (tracking_number, shipment_status);",
        "drop_sql": "DROP INDEX IF EXISTS idx_shipments_covering;",
        "fast_sql": "SELECT tracking_number, carrier, shipment_status FROM shipments WHERE carrier = 'Trendyol Express';",
        "problem": "İndeks kullanılsa bile eksik kolonlar için ana tabloya (Heap) gidilip ekstra okuma yapılır.",
        "solution": "INCLUDE yan tümcesiyle covering index kuruldu; sorgu tamamen indeksten okundu (Index Only Scan).",
    },
]

INEFFECTIVE_CASES = [
    {
        "title": "Düşük Seçicilik (Low Cardinality) Nedeniyle İndeksin Kullanılmaması",
        "explanation": "Bir kolondaki tekil değer oranı çok düşükse ve aranan değer tablonun büyük kısmını oluşturuyorsa (ör. payment_status = 'successful' tablonun %92'si), Postgres indeks ağacını ve ardından heap bloklarını okumaktansa tek seferde ardışık taramayı (Seq Scan) daha az maliyetli hesaplar ve indeksi bilinçli olarak yok sayar.",
        "query": "EXPLAIN ANALYZE SELECT * FROM payments WHERE payment_status = 'successful';",
    },
    {
        "title": "Fonksiyon Uygulanmış Kolon / Tip Uyuşmazlığı (Non-Sargable)",
        "explanation": "İndeksli bir kolonun önüne fonksiyon konulduğunda (ör. LOWER(email) veya CAST) B-Tree ağacındaki sıralama geçersiz kalır. Fonksiyonel indeks (Expression Index) tanımlanmadığı sürece standart B-Tree indeksi tamamen devre dışı kalır.",
        "query": "EXPLAIN ANALYZE SELECT * FROM users WHERE LOWER(email) = 'test@example.com';",
    },
]


def run_explain(cur, sql):
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
    data = cur.fetchone()[0]
    exec_time = data[0]["Execution Time"]

    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")
    lines = [row[0] for row in cur.fetchall()]
    return exec_time, "\n".join(lines)


def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    summary_rows = []
    sections = []

    with psycopg.connect(DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for sc in SCENARIOS:
                if sc["drop_sql"]:
                    cur.execute(sc["drop_sql"])

                slow_time, slow_plan = run_explain(cur, sc["slow_sql"])

                if sc["index_sql"]:
                    cur.execute(sc["index_sql"])

                fast_time, fast_plan = run_explain(cur, sc["fast_sql"])
                speedup = round(slow_time / max(fast_time, 0.001), 2)

                summary_rows.append(
                    f"| {sc['id']} | {sc['title']} | {slow_time:.2f} ms | {fast_time:.2f} ms | **{speedup}x** |"
                )

                sec = (
                    f"### Senaryo {sc['id']}: {sc['title']}\n\n"
                    f"- **Teşhis:** {sc['problem']}\n"
                    f"- **Çözüm:** {sc['solution']}\n\n"
                    f"**Öncesi (Kötü Tasarım / İndekssiz):**\n"
                    f"```sql\n{sc['slow_sql']}\n```\n\n"
                    f"```text\nExecution Time: {slow_time:.3f} ms\n{slow_plan}\n```\n\n"
                    f"**Sonrası (İndeksli / Optimize):**\n"
                    f"```sql\n{sc['fast_sql']}\n```\n\n"
                    f"```text\nExecution Time: {fast_time:.3f} ms\n{fast_plan}\n```\n\n"
                    "---\n"
                )
                sections.append(sec)

            # Raporu yaz
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("# Ödev 3.3 — Performans Laboratuvarı Raporu\n\n")
                f.write("## 1. Öncesi / Sonrası Süre ve Hızlanma Tablosu\n\n")
                f.write("| # | Senaryo | Öncesi Süre | Sonrası Süre | Hızlanma (Speedup) |\n")
                f.write("|---|---|---|---|---|\n")
                f.write("\n".join(summary_rows) + "\n\n---\n\n")
                f.write("## 2. Senaryo Detayları ve Execution Plan İncelemeleri\n\n")
                f.write("\n".join(sections) + "\n\n")
                f.write("## 3. İndeksin İŞE YARAMADIĞI 2 Örnek ve Teknik Nedenleri\n\n")

                for i, case in enumerate(INEFFECTIVE_CASES, start=1):
                    f.write(f"### Örnek {i}: {case['title']}\n\n")
                    f.write(f"**Teknik Neden:** {case['explanation']}\n\n")
                    f.write(f"```sql\n{case['query']}\n```\n\n")

    print(f"Rapor hazır: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()