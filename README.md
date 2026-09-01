# İETT Canlı Otobüs Takibi

İETT canlı araç konumlarını, durak bilgilerini ve ileride Google Routes trafik sürelerini tek bir backend üzerinden birleştiren açık kaynak proje.

## Hedef mimari

İETT canlı veri sağlayıcısı → normalize edilmiş araç modeli → durak/hat eşleştirme → ETA ve bekleme hesabı → web/mobile arayüz.

Arayüzde birincil araç kartı sırası: hat numarası, tahmini süre, plaka ve kapı numarasıdır. Plaka araç ayrımı için görünen kimlik; kapı numarası ise İETT’nin operasyonel araç kimliğidir.

Canlı veri kaynağı değişebildiği için sağlayıcı katmanı ayrı tutulur. API anahtarları koda yazılmaz; `.env` üzerinden verilir.

## Başlangıç

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn iett_tracker.app:app --reload
```

`GET http://127.0.0.1:8000/health` ile kontrol edilebilir.

ETA denemesi için `POST /api/eta` endpoint’ine aşağıdaki gövde gönderilebilir:

```json
{"id":"DURAK_ID","name":"Durak adı","latitude":41.0082,"longitude":28.9784}
```

Bu MVP kuş uçuşu mesafe ve ortalama hız kullanır. Gerçek yol ağı, yön ve trafik hesabı Google Routes katmanında eklenecektir.

Google Routes toplu taşıma çağrısı için `.env` dosyasına `GOOGLE_MAPS_API_KEY` eklenebilir. Anahtar yoksa sistem çalışmaya devam eder. Google transit süresi, İETT’nin canlı araç konumunun yerine geçmez; rota süresi için yardımcı veridir.

Canlı araç cevapları varsayılan olarak 20 saniye cache’lenir. `LIVE_CACHE_SECONDS` ile değiştirilebilir. Aynı anda gelen isteklerde yalnızca tek bir veri yenilemesi yapılır.

İETT servisi geçici olarak cevap vermezse son başarılı cache kullanılır. Cache yoksa endpoint hata fırlatmak yerine `available: false` ve boş veri döndürür.

Canlı durak varışları için çalışan web kaynağı `GET /api/live/arrivals?stop_code=225972&line_code=KM12` endpoint’i üzerinden kullanılır. Backend, İETT’nin `WMyBus` HTML yanıtını parse eder ve `origin`, `departure_time` ve `eta_minutes` alanlarını döndürür.

Hat-durak ETA sonuçları 15 saniye cache’lenir; İETT servisi geçici olarak yanıt vermezse son başarılı cevap korunur.

Canlı filo gözlemleri `data/vehicles.sqlite3` içinde zaman damgasıyla tutulur. Araç kimliği (plaka/kapı no) sabit, hat ataması ise ayrı ve zamanla değişen bir ilişki olarak ele alınır.

Bir aracın geçmişi `GET /api/live/vehicles/{vehicle_id}/history` ile incelenebilir. Hat ataması, tek bir GPS noktasından değil, ardışık gözlemlerden üretilecektir.

## Durum

İlk sürümde canlı sağlayıcı sözleşmesi ve normalize edilmiş veri modeli hazırlanıyor. İETT endpoint’inin güncel cevap formatı doğrulandıktan sonra gerçek adapter eklenecek. Google Routes entegrasyonu opsiyonel olacak ve yalnızca trafik etkili rota süresi için kullanılacak.

## Lisans

Lisans kararı ilk yayın öncesi verilecektir.
