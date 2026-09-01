# İETT Transit Data API

Bu proje, İETT’nin canlı SOAP ve WMyBus kaynaklarını geliştiricilerin kolay tüketebileceği REST JSON endpoint’lerine dönüştüren topluluk yapımı bir adaptördür. Resmî İETT API’si değildir.

## Hızlı başlangıç

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

## Veri kaynakları

- Araç konumu ve hat: İETT `GetFiloAracKonum_json` / `GetHatOtoKonum_json`
- Durak kataloğu: İETT `GetDurak_json`
- Tahmini varış: İETT `WMyBus`

Kaynakların kullanım koşulları ve istek limitleri kontrol edilerek kullanılmalıdır. Üretim kullanımı için kendi cache katmanınızı ve makul istek aralığınızı uygulayın.
