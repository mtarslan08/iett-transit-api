# İETT Transit Data API

Bu proje, İETT’nin canlı SOAP ve WMyBus kaynaklarını geliştiricilerin kolay tüketebileceği REST JSON endpoint’lerine dönüştüren topluluk yapımı bir adaptördür. Resmî İETT API’si değildir ve merkezi hosted API adresi sağlamaz; her geliştirici projeyi kendi ortamında çalıştırır.

## Hızlı başlangıç

```powershell
git clone https://github.com/mtarslan08/iett-transit-api.git
cd iett-transit-api
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn iett_tracker.app:app --reload --app-dir src
```

Ücretli Google API anahtarı gerekmez. API, doğrudan İETT kaynaklarına istek atar.

Uygulama çalışırken Swagger arayüzü: `http://localhost:8000/docs`

```bash
curl http://localhost:8000/api/v1/vehicles/KM34
curl "http://localhost:8000/api/v1/stops/225972/arrivals?line_code=KM34"
```

## Endpoint’ler

| Endpoint | Açıklama |
|---|---|
| `GET /api/v1/vehicles` | Tüm canlı araçlar |
| `GET /api/v1/vehicles/{line}` | Belirli hattın araçları |
| `GET /api/v1/lines/{line}` | Hat yönleri ve durakları |
| `GET /api/v1/stops` | Durak kataloğu |
| `GET /api/v1/stops/{code}` | Tek durak |
| `GET /api/v1/stops/{code}/arrivals?line_code=KM34` | Durak-hat varışları |
| `GET /health/detailed` | Kaynak sağlık ve son hata bilgisi |

## Cevap biçimi

```json
{
  "data": [],
  "meta": {
    "source": "iett-official-line-soap",
    "fetched_at": "2026-09-01T20:40:00Z",
    "stale": false
  }
}
```

`stale: true`, kaynağın boş veya son başarılı verinin kullanılamadığı anlamına gelir. Plaka eşleşmesi yoksa `plate` alanı `null` kalır; API veri uydurmaz.

Durak bulunamazsa sürümlü API `404` döndürür. `/api/eta` eski uyumluluk için tutulur ve deneysel bir tahmin üretir; yeni kullanıcılar `/api/v1` endpoint’lerini kullanmalıdır.

## Kullanım limiti

Public `/api/v1` endpoint’leri istemci başına dakikada 120 istekle sınırlıdır. Uygulamalar kendi tarafında da cache kullanmalı ve canlı endpoint’leri sürekli yenilememelidir. Limit aşılırsa `429` döner.

## Veri kaynakları

- Araç konumu ve hat: İETT `GetFiloAracKonum_json` / `GetHatOtoKonum_json`
- Durak kataloğu: İETT `GetDurak_json`
- Tahmini varış: İETT `WMyBus`

Kaynakların kullanım koşulları ve istek limitleri kontrol edilerek kullanılmalıdır. Üretim kullanımı için kendi cache katmanınızı ve makul istek aralığınızı uygulayın.
