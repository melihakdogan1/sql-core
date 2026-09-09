# 3.7 Kontrol Soruları

### 1. `LEFT JOIN` sonrası `WHERE b.col IS NOT NULL` yazmak ne yapar, `INNER JOIN`'den farkı nedir?

- **Ne yapar:** `LEFT JOIN` sağda eşleşmeyen satırlara NULL basar. Sen gidip arkasına `WHERE b.col IS NOT NULL` koyarsan o NULL gelen satırları elersin.
- **INNER JOIN'den farkı:** Sonuç kümesi olarak hiçbir farkı yok, ikisi de aynı satırları getirir. 
- **Olayı ne:** Temiz kod yazmamaktır. Postgres sorgu planlayıcısı çoğu zaman bunu anlayıp içeride sorguyu INNER JOIN'e çevirir (outer join elimination). Ama sorgu uzadığında veya subquery'ler devreye girdiğinde planlayıcı bunu atlayabilir; sol tabloyu gereksiz yere belleğe alıp sonra filtrelemeye çalışır, boş yere RAM ve I/O yakar.

---

### 2. `NOT IN` bir alt sorguda `NULL` varsa ne olur? Neden?

- **Ne olur:** Dış sorgu tek bir satır bile döndürmez, doğrudan boş küme gelir.
- **Neden:** SQL üç değerli mantık (three-valued logic) kullanır: TRUE, FALSE ve UNKNOWN (NULL).
  `x NOT IN (1, 2, NULL)` sorgusu arka planda şuna açılır:
  `x <> 1 AND x <> 2 AND x <> NULL`
  SQL standardında NULL ile yapılan herhangi bir eşitlik kontrolü (`x <> NULL`) FALSE değil UNKNOWN döner. Mantık zincirinde `AND UNKNOWN` olduğu sürece sonuç asla kesin TRUE olamaz. `WHERE` şartı da sadece TRUE olanları getirdiği için sorgu tamamen boş döner.
- **Çözüm:** Alt sorguda `NOT IN` yerine her zaman `NOT EXISTS` kullanmak ya da subquery içine `WHERE col IS NOT NULL` eklemektir.

---

### 3. `COUNT(*)` ile `COUNT(column)` farkı hangi durumda tehlikeli sonuç verir?

- **Fark:** `COUNT(*)` satırdaki veriye bakmadan dönen toplam fiziksel satırı sayar. `COUNT(column)` ise sadece o kolonu NULL olmayanları sayar.
- **Tehlikeli Durum:** 
  `LEFT JOIN` yapıp gruplama yaptığında patlar. Mesela kullanıcıların sipariş sayısını bulmak için `users u LEFT JOIN orders o ... GROUP BY u.user_id` yazdık. Kullanıcının hiç siparişi yoksa bile LEFT JOIN o kullanıcı için 1 satır üretir (orders kolonları NULL olarak gelir).
  Burada `COUNT(*)` dersen siparişi olmayan adama 1 sipariş yazarsın, rapor çöker. Doğrusu `COUNT(o.order_id)` yazmaktır; NULL olduğu için saymaz ve doğru şekilde 0 verir.

---

### 4. Bir join sonucunda satır sayım beklenenden 3 kat fazla çıktı; hangi 3 şeyi kontrol ederim?

1. **Join kolonunun tekilliği (1-to-N durumu):** Sağ tablodaki foreign key'in tekil olduğunu varsaymışımdır ama sağda aynı ID'den 3 tane vardır. Doğal olarak satırlar 3 katına çıkar (fan-out).
2. **Eksik composite key:** Tablo iki kolonla (mesela `tenant_id` + `order_id`) bağlıdır ama ben join atarken sadece `order_id` yazmışımdır. Başka kayıtlar da çakışıp satırları çoğaltır.
3. **SCD2 tarihçe tablosu:** Bağlandığım boyut tablosu tarihçelidir (SCD Type 2). Sorguya `is_current = TRUE` ya da tarih aralığı koymayı unuttuysam, işlem müşterinin geçmişteki her adres/durum kaydıyla ayrı ayrı eşleşip satır sayısını katlar.

---

### 5. Window function ile `GROUP BY` arasındaki temel fark nedir?

- **GROUP BY:** Satırları gruplayıp tek satıra indirir (collapse eder). Satır bazındaki tekil kolonları kaybedersin, sadece SUM, AVG gibi özet değerleri görürsün.
- **Window Function (`OVER`):** Satır sayısına dokunmaz. Tabloda 100k satır varsa çıktı yine 100k satırdır. Bireysel satır detaylarını korurken yanına ekstra kolon olarak sıra numarası (`ROW_NUMBER`), kümülatif toplam veya önceki ayın değeri (`LAG`) gibi hesaplamaları yapıştırır.

---

### 6. Bir tabloya index eklemenin maliyeti nedir? (Sadece faydasını sayma)

İndeks bedava hız değildir:
1. **Yazma performansı düşer:** Tabloya her `INSERT`, `UPDATE`, `DELETE` geldiğinde Postgres sadece tabloya yazmaz; o tablodaki tüm B-Tree indeks ağaçlarını da baştan düzenler (page split yapar). İndeks arttıkça yazma yavaşlar.
2. **Disk alanı ve bloat:** İndeksler diskte yer kaplar; bazen tablonun kendisinden büyük olur. Güncellemeler sıklaştıkça indeks parçalanır (bloat) ve `REINDEX` ister.
3. **Bellek (RAM) işgali:** İndeks sayfaları da belleğe (`shared_buffers`) yüklenir. Gereksiz indeksler sıcak veriyi bellekten dışarı atıp sistemi diske muhtaç eder.
4. **Planlama süresi (Planning Time) uzar:** Sorgu çalışmadan önce Cost-Based Optimizer tüm indeks kombinasyonlarını tek tek puanlar. Çok fazla indeks varsa sorgunun başlama süresi uzar.