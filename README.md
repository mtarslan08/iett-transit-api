# İETT Transit API

İETT’nin canlı araç, hat, durak ve varış verilerini geliştiricilerin kullanabileceği REST API biçiminde sunan açık kaynak bir adaptör.

Resmî İETT API’si değildir. Merkezi bir API adresi sağlamaz; her geliştirici projeyi kendi ortamında çalıştırır.

## Kurulum

Gereksinimler: Python 3.11+ ve Git.

```powershell
git clone https://github.com/mtarslan08/otobusum_nerede_v2.git
cd otobusum_nerede_v2
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn iett_tracker.app:app --reload --app-dir src
```

API çalıştıktan sonra:

- Swagger: `http://127.0.0.1:8000/docs`
- Sağlık kontrolü: `http://127.0.0.1:8000/health`

Python PATH’te değilse `py` yerine kurulu Python yolunu kullanabilirsin.

## Endpoint’ler

| Endpoint | Açıklama |
|---|---|
| `GET /api/v1/vehicles` | Tüm canlı araçlar |
| `GET /api/v1/vehicles/{line_code}` | Bir hattın canlı araçları |
| `GET /api/v1/lines/{line_code}` | Hat yönleri ve durakları |
| `GET /api/v1/stops` | Durak kataloğu |
| `GET /api/v1/stops/{stop_code}` | Tek durak bilgisi |
| `GET /api/v1/stops/{stop_code}/arrivals?line_code=KM34` | Durak-hat varışları |

Örnek:

```bash
curl http://127.0.0.1:8000/api/v1/vehicles/KM34
curl "http://127.0.0.1:8000/api/v1/stops/225972/arrivals?line_code=KM34"
```

## Veri kaynakları

- `GetFiloAracKonum_json`: canlı filo konumları
- `GetHatOtoKonum_json`: hat bazlı canlı araçlar
- `GetDurak_json`: durak kataloğu
- `WMyBus`: tahmini durak varışları

Yanıtlar `data` ve `meta` alanlarıyla döner. `meta` içinde kaynak, alınma zamanı ve verinin güncel olup olmadığı bulunur. Plaka eşleşmesi yoksa `plate` alanı boş bırakılır.

Canlı kaynaklar geçici olarak yanıt vermezse cache ve retry mekanizmaları kullanılır. `/api/v1` endpoint’leri istemci başına dakikada 120 istekle sınırlıdır.

## Geliştirme

```powershell
pytest -q
```

Katkılar ve hata bildirimleri GitHub Issues üzerinden açılabilir.

## Lisans

MIT. İETT veri kaynaklarının kullanım koşulları ayrıca geçerlidir.
