# İETT Canlı Otobüs Takibi

İETT canlı araç konumlarını ve durak bilgilerini tek bir backend üzerinden birleştiren açık kaynak proje.

## Hedef mimari

İETT canlı veri sağlayıcısı → normalize edilmiş araç modeli → durak/hat eşleştirme → ETA ve bekleme hesabı → web/mobile arayüz.

Arayüzde birincil araç kartı sırası: hat numarası, tahmini süre, plaka ve kapı numarasıdır. Plaka araç ayrımı için görünen kimlik; kapı numarası ise İETT’nin operasyonel araç kimliğidir.

Canlı veri kaynağı değişebildiği için sağlayıcı katmanı ayrı tutulur. API anahtarları koda yazılmaz; `.env` üzerinden verilir.

## Başlangıç

> Önemli: `static/index.html` dosyasını çift tıklayarak açma. Uygulama FastAPI üzerinden çalışır; aksi halde CSS ve JavaScript yüklenmez.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn iett_tracker.app:app --reload
```

Python PATH'te değilse Windows'ta şu komutu kullanabilirsin:

```powershell
& "C:\Users\harslan\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn iett_tracker.app:app --reload --app-dir src
```

Ardından tarayıcıda `http://127.0.0.1:8000` adresini aç.

Geliştiriciler için sürümlü REST API endpoint’leri `/api/v1` altında bulunur. Swagger: `http://127.0.0.1:8000/docs`. Ayrıntılı kullanım için [API.md](API.md) dosyasına bakabilirsin.

`GET http://127.0.0.1:8000/health` ile kontrol edilebilir.

ETA denemesi için `POST /api/eta` endpoint’ine aşağıdaki gövde gönderilebilir:

```json
{"id":"DURAK_ID","name":"Durak adı","latitude":41.0082,"longitude":28.9784}
```

ETA tarafında Google Maps API kullanılmaz; uygulama resmi İETT canlı akışlarıyla çalışır ve plaka eşleşmesi olmayan kayıtlarda tahmin uydurmaz.

Canlı araç cevapları varsayılan olarak 20 saniye cache’lenir. `LIVE_CACHE_SECONDS` ile değiştirilebilir. Aynı anda gelen isteklerde yalnızca tek bir veri yenilemesi yapılır.

İETT servisi geçici olarak cevap vermezse son başarılı cache kullanılır. Cache yoksa endpoint hata fırlatmak yerine `available: false` ve boş veri döndürür.

Canlı durak varışları için İETT’nin `WMyBus` HTML kaynağı kullanılır. `GET /api/live/arrivals?stop_code=225972&line_code=KM12` endpoint’i `origin`, `departure_time` ve `eta_minutes` alanlarını döndürür.

Hat bazlı canlı araçlar için resmi İETT `GetHatOtoKonum_json` SOAP metodu kullanılır. Güncel WSDL’de parametre adı `HatKodu` ve `AuthHeader` alanları `Username`/`Password` olarak tanımlıdır; bu değerler `.env` üzerinden verilebilir. Metot çalışmazsa haritada yalnızca güzergâha yakınlık fallback’i kullanılır.

Hat-durak ETA sonuçları 15 saniye cache’lenir; İETT servisi geçici olarak yanıt vermezse son başarılı cevap korunur.

Canlı filo gözlemleri `data/vehicles.sqlite3` içinde zaman damgasıyla tutulur. Araç kimliği (plaka/kapı no) sabit, hat ataması ise ayrı ve zamanla değişen bir ilişki olarak ele alınır.

Bir aracın geçmişi `GET /api/live/vehicles/{vehicle_id}/history` ile incelenebilir. Hat ataması, tek bir GPS noktasından değil, ardışık gözlemlerden üretilecektir.

## Durum

Resmi İETT hat bazlı SOAP, filo SOAP ve WMyBus kaynakları; retry, sağlık izleme, ETA-plaka eşleştirmesi ve temel favori/konum/bildirim arayüzü hazırdır.

## Lisans

Lisans kararı ilk yayın öncesi verilecektir.
