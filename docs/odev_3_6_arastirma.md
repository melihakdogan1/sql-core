# OLTP vs OLAP: Satır Bazlı vs Kolon Bazlı Depolama Mimarisi

## Bölüm 1: Mimari Temeller, Donanım Gerçekleri ve Blok Düzeni

Veri dünyasında "her işe tek çekiç" kafası gerçek hayatta doğrudan patlar. Operasyonel sistemler (OLTP) ile analitik ambarlar (OLAP) donanımı taban tabana zıt şekillerde sömürür. Bir kullanıcının sepete ürün atması, kayıt olması ya da siparişi güncellemesi gibi işler mikrosaniyeler mertebesinde düşük gecikme ve ACID garantileri ister. Öte yandan son 1 yılın çeyreklik kârını hesaplamak, cohort retention çıkarmak ya da milyonlarca satırdan sepet ortalaması çekmek gibi işler devasa veri taraması (throughput) ve saf CPU gücü gerektirir. Bu iki dünyanın temel ayrımı da verinin diskte ve RAM'de nasıl tutulduğuna dayanır: **Satır Bazlı Depolama (Row-Oriented / NSM)** ve **Kolon Bazlı Depolama (Columnar / DSM)**.

Bizim projede ayağa kaldırdığımız PostgreSQL gibi klasik RDBMS motorları satır bazlı mimarinin ders kitabı örneğidir. Postgres disk üzerinde veriyi 8 KB'lık sabit sayfalar (page/block) halinde tutar. Bir tabloya `INSERT` attığımızda o satırın `user_id`, `email`, `city`, `created_at` gibi tüm kolonları o 8 KB'lık bloğun içine yan yana, ardışık baytlar olarak yazılır. Operasyonel iş yükünde bu mükemmel çalışır. `user_id = 42` olan kullanıcıyı çekeceğimiz zaman B-Tree indeksten bloğun yerini buluruz, diskten tek bir 8 KB sayfa belleğe (`shared_buffers`) gelir ve satırın tüm kolonları tek bir I/O ile önümüze düşer. Sipariş statüsünü güncellemek istediğimizde de sadece o satırın olduğu sayfaya kilit atılır, atomik olarak iş biter.

Fakat analitik bir sorguya geçtiğimiz an bu satır odaklı yapı tam bir I/O işkencesine dönüşür. Diyelim ki 100k siparişlik tabloda sadece hafta sonu cirosunu toplayacağız. Bize gereken tek şey `order_date` ve `total_amount`. Ancak Postgres diskten veriyi kolon kolon cımbızlayamaz; 8 KB'lık sayfayı bir bütün olarak çekmek zorundadır. Bir satır diskte 200 bayt kaplıyorsa ve benim istediğim iki kolon sadece 16 bayt tutuyorsa, ben ihtiyacım olan her 16 bayt için veri yoluna (I/O bus) ve RAM'e 200 baytlık veri pompalarım. İhtiyaç duymadığım adresler, isimler, statüler boşu boşuna diskten okunur. Satır sayısı milyonlara dayandığında CPU hesap yapmaktan çok, diskten gelen gereksiz çöp veriyi beklemekle vakit öldürür (I/O Bus Saturation).

Kolon bazlı sistemlerde (DuckDB, Parquet, ClickHouse) ise tablo 90 derece döndürülür. Satırlar değil, her bir kolon kendi bloklarında ardışık saklanır. `total_amount` kolonunun tüm değerleri diskte arka arkaya dizilirken, `user_id` tamamen ayrı bloklarda durur. Bu durum analitikte iki devasa kapı açar: **Projection Pushdown** ve **Cache-Friendly Vektörize Yürütme**. Sorguda adı geçmeyen kolonun disk bloğuna motor elini bile sürmez. 20 kolonluk tabloda 2 kolon mu istedin? Diskten sadece o 2 kolon okunur, I/O trafiği doğrudan %90 oranında düşer.

## Bölüm 2: Sıkıştırma, CPU Cache, SIMD ve Canlı Laboratuvar Ölçümlerimiz

Kolon bazlı mimarinin asıl büyüsü sıkıştırma ve modern işlemci mimarisiyle birleştiğinde ortaya çıkar. Satır bazlı bir sayfada yan yana duran verilerin tipleri çorbadır: string, integer, timestamp, boolean peş peşe gelir. Birbirine benzemeyen veriyi verimli sıkıştıramazsınız. Kolon bazlı düzende ise bir blokta sadece aynı veri tipi vardır. Hatta çoğu zaman birbirini tekrar eden değerler peş peşe gelir (örneğin binlerce `completed` statüsü veya sıralı tarihler). Bu sayede Run-Length Encoding (RLE), Dictionary Encoding ve Bit-packing gibi algoritmalarla veriyi neredeyse kayıpsız şekilde ufacık boyutlara ezersiniz. Boyut küçülünce diskten okunacak bayt miktarı katbekat azalır.

Daha da önemlisi modern işlemcilerin L1/L2/L3 cache mekanizmaları ve SIMD (Single Instruction, Multiple Data) komut setleridir. Klasik Postgres gibi satır bazlı motorlar "Volcano Iterator Model" kullanır; her operatör bir sonraki satırı almak için `next()` metodunu çağırır. 1 milyon satır için 1 milyon fonksiyon çağrısı, pointer takibi ve sürekli CPU cache miss demektir. DuckDB gibi modern kolonel OLAP motorları ise veriyi örneğin 2048'lik vektörler (vektörize yürütme) halinde çeker. Bellekte yan yana duran bu integer veya float dizileri doğrudan CPU L1 cache'e oturur ve tek bir CPU çevriminde 4, 8 veya 16 işlem birden paralel koşturulur (AVX-512 / NEON).

Bu teorik farkları yaptığımız testlerde bizzat gözlemledik:

1. **PostgreSQL Tarafındaki I/O Boğulması:**
   Ödev 3.3'te 190k satırlık `order_items` tablosunda `product_id = 42` için ciro toplamaya kalktığımızda, indekssiz durumda motor **Sequential Scan**'e düştü. İlgisiz tüm kolonları da diskten belleğe çekmek zorunda kaldığı için tam **1.424 disk bloğunu (shared hit buffer)** taradı ve işlem **67.92 ms** sürdü.
2. **DuckDB ve Parquet'nin Vektörize Üstünlüğü:**
   Ödev 3.5'te 3 milyon satırlık (2.964.624 satır) resmi NYC Taxi Parquet dosyasını test ettik. Pandas klasiği satır ve seri nesnelerine dönüştürüp RAM'e açtığında tek başına **944.82 MB bellek artışı** yarattı. DuckDB ise dosyayı belleğe kopyalamadan (Zero-Copy), sadece ilgili kolonları akıtarak ve vektörize motoruyla çalıştı:
   - Yolcu sayısına göre mesafe analizi sorgusunda Pandas **1.352,95 ms** harcarken, DuckDB aynı işi **96,80 ms** içinde bitirdi (**13.98x hızlanma**).
   - Bahşiş oranı ve eşik filtrelemesinde Pandas Python döngüleri ve satır kontrolleri yüzünden **19.210,88 ms (19 saniye)** boyunca kilitlenirken, DuckDB SIMD ve filtre itme (filter pushdown) sayesinde sorguyu **233,05 ms** içinde tamamladı (**82.43x hızlanma**).

## Bölüm 3: Mimari Çıkarım ve Production Kararı

Bu ölçümler bize neden tek bir veritabanı ile tüm mimariyi çözemeyeceğimizi açıkça kanıtlıyor. 

Operasyonel dünyada; satır güncellemeleri, kilit mekanizmaları, yüksek yazma hacmi ve tekil kayıt sorguları için PostgreSQL gibi satır bazlı bir motor vazgeçilmezdir. Kolon bazlı bir motora tek satırlık `INSERT` veya `UPDATE` atmaya kalkarsanız, motor her kolonun ayrı bloğunu açıp yazmak zorunda kalacağı için yazma performansı tabana vurur (Write Amplification). 

Ancak iş raporlamaya, agregasyonlara, panolara ve analitiğe geldiğinde satır bazlı mimariyi zorlamak donanıma eziyettir. Yapılması gereken; operasyonel yükü satır bazlı PostgreSQL üzerinde tutup, veriyi idempotent ELT hatlarıyla Star Schema formatında DuckDB, ClickHouse veya Snowflake gibi kolonel ambarlara akıtmaktır. Analitiğin gerçek performansı, sorgulanmayacak kolonları hiç okumayan disk mimarisinden ve vektörize CPU yürütmesinden gelir.

---

# SCD Type 2 Nedir ve Neden ML Özelliği (Feature) Üretirken Kritiktir?

## 1. Yavaş Değişen Boyutlar (SCD) ve Tip 2 Mekanizması

Veri ambarı dünyasında gerçek hayat hiçbir zaman sabit kalmaz. Kullanıcılar adres değiştirir, medeni durumları güncellenir, gelir seviyeleri artar ya da platformdaki müşteri segmentleri değişir. Boyut tablolarındaki (dimension tables) bu tür zamana bağlı değişimleri yönetme stratejilerine **Slowly Changing Dimensions (SCD)** denir.

En ilkel yaklaşım olan **SCD Type 1**, eski verinin üzerine doğrudan `UPDATE` çeker. Örneğin kullanıcı Kadıköy'den Bodrum'a taşındığında veya segmenti "Standart"tan "VIP"ye yükseldiğinde eski kayıt ezilir, geçmiş tamamen yok edilir. Bu durum operasyonel olarak basit görünse de analitik ve makine öğrenmesi süreçleri için felakettir.

**SCD Type 2** ise verinin üzerine asla yazmaz; geçmişi satır bazında versiyonlayarak saklar. Her değişiklikte tabloya yeni bir satır eklenir ve her satırın hangi zaman aralığında geçerli olduğunu gösteren metaveriler tutulur:
- `valid_from`: Bu kaydın ve özniteliklerin geçerli olmaya başladığı an.
- `valid_to`: Kaydın geçerliliğini yitirdiği an (güncel kayıtlarda `NULL` bırakılır).
- `is_current`: Kaydın şu anki en güncel durumu temsil edip etmediğini belirten mantıksal (`BOOLEAN`) bayrak.

Ödev 3.4 kapsamında kurduğumuz `dim_customer` tablosu bu mantığın tam bir yansımasıdır. Bir müşteri taşındığında eski kaydının `valid_to` alanı güncellenip `is_current = FALSE` yapılır; yeni adresi ise yeni bir birincil anahtarla (`customer_key`) ve `is_current = TRUE` olarak tabloya girer. Böylece müşterinin hayat döngüsü kesintisiz bir zaman çizgisi olarak modellenir.

## 2. ML Dünyasının Sessiz Katili: Zamansal Veri Sızıntısı (Data Leakage)

Bir makine öğrenmesi modelinin eğitim setinde kusursuz metrikler (yüksek AUC, sıfır kayıp) verip prodüksiyona çıktığı gün tamamen çökmesinin bir numaralı sebebi **Data Leakage (Hedef/Veri Sızıntısı)** ve daha spesifik olarak **Lookahead Bias (Geleceği Görme Hatası)** problemidir.

Bir e-ticaret platformunda kullanıcıların churn (terk) etme olasılığını veya bir sonraki sepet tutarını tahmin eden bir model geliştirdiğimizi düşünelim. Modelimizi eğitmek için 2025 yılı boyunca gerçekleşen siparişleri feature pipeline'ından geçiriyoruz. Eğitim kümesindeki bir satır **Mart 2025** tarihindeki bir siparişe ait olsun.

Eğer boyut tablolarımızda **SCD Type 1** kullanılıyorsa:
Kullanıcı Haziran 2025'te adresini değiştirmiş veya Kasım 2025'teki Black Friday indirimlerinde çılgınca alışveriş yaparak sistemde "VIP / Champion" segmentine yükselmiş olsun. Biz bugün geçmişe dönük Mart 2025 tarihi için feature üretmeye kalktığımızda, sorgumuz kullanıcının bugünkü güncel durumunu ("VIP" ve "Bodrum") çekecektir.

Bu durum iki kritik modelleme faciasına yol açar:
1. **Gelecekten Bilgi Çalma:** Mart ayında sıradan bir kullanıcı olan ve terk etme riski taşıyan birine, aylar sonra yapacağı harcamaların ödülü olan "VIP" etiketini yapıştırmış oluruz. Model, aslında o tarihte var olmayan bir geleceği öğrenir.
2. **Prodüksiyon Çöküşü:** Model canlıya alındığında yeni bir kullanıcı gelir. Bu kullanıcının elinde henüz gelecekteki "VIP" etiketi yoktur. Model eğitimde geleceği görmeye alıştığı için canlı ortamdaki gerçek veriyi tanıyamaz ve tahminleri tamamen saçmalar.

## 3. SCD Type 2 ile "Point-in-Time Correctness" (Geçmişe Doğru Zamansal Doğruluk)

Bu sızıntıyı engellemenin tek yolu, model özniteliklerini üretirken **Point-in-Time Correctness** ilkesine sadık kalmaktır. Yani bir model geçmişteki belirli bir $T$ anı için eğitiliyorsa, feature pipeline o $T$ anında dünyanın tam olarak nasıl göründüğünü yeniden inşa edebilmelidir.

SCD Type 2 tabloları, SQL'de **As-Of Join (Zamansal Eşleştirme)** yapmamıza olanak tanır:

```sql
SELECT 
    fo.order_id,
    fo.order_date_id,
    dc.city AS historical_city,
    dc.customer_key
FROM fct_orders fo
JOIN dim_date dd ON fo.order_date_id = dd.date_id
JOIN dim_customer dc 
  ON fo.customer_key = dc.customer_key
 AND dd.full_date >= dc.valid_from 
 AND (dc.valid_to IS NULL OR dd.full_date < dc.valid_to);
```

Bu kurgu sayesinde Mart 2025 tarihindeki bir sipariş için özellik üretilirken, kullanıcının tam o tarihte geçerli olan kaydı eşleşir; aylar sonraki şehir değişikliği veya segment artışı geçmişe sızamaz.

Feature Store (Feast, Hopsworks) mimarilerinin ve veri ambarlarının temelinde SCD Type 2 mantığının bulunmasının sebebi budur. SCD Type 2 olmadan üretilen geçmiş tarihli her ML özelliği, geleceği bugüne sızdıran saatli bir bombadır.
 