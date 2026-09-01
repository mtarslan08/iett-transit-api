const $ = (id) => document.getElementById(id);
const lineInput = $('line');
const stopInput = $('stop');
const message = $('message');
let activeQuery = null;
let refreshTimer = null;
let map = null;

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function refreshConnectionStatus() {
  try {
    const data = await getJson('/api/live/status');
    $('connection-text').textContent = data.available ? `${data.fresh_vehicle_count.toLocaleString('tr-TR')} araç canlı` : 'Canlı kaynak bekleniyor';
  } catch (_) {
    $('connection-text').textContent = 'Kaynak bağlantısı yok';
  }
}

function showRoute(data) {
  const route = $('route');
  route.classList.remove('hidden');
  route.innerHTML = `<div class="route-head"><strong>${data.line}</strong><span class="muted">${data.count ? `${data.count} yön bulundu` : 'Güzergâh verisi yok'}</span></div>`;
  for (const direction of data.directions || []) {
    const block = document.createElement('div');
    block.className = 'direction';
    block.innerHTML = `<div class="muted">Yön ${direction.direction}</div><div class="stop-list"></div>`;
    const list = block.querySelector('.stop-list');
    for (const stop of direction.stops || []) {
      const item = document.createElement('span'); item.className = 'stop'; item.textContent = stop.name || stop.stop_id; list.appendChild(item);
    }
    route.appendChild(block);
  }
}

async function showMap(line) {
  if (!window.L) return;
  const data = await getJson(`/api/routes/${encodeURIComponent(line)}/map`);
  const places = (data.routes || []).flatMap(r => r.stationPlaces || []);
  if (!places.length) return;
  if (map) map.remove();
  map = L.map('map').setView([places[0].lat, places[0].lng], 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  const points = places.map(p => [p.lat, p.lng]);
  L.polyline(points, { color: '#238636', weight: 4 }).addTo(map);
  places.forEach(p => L.circleMarker([p.lat, p.lng], { radius: 4, color: '#58a6ff' }).bindTooltip(p.stationName || '').addTo(map));
  const live = await getJson(`/api/live/vehicles/near-route?line_code=${encodeURIComponent(line)}`);
  $('live-status').textContent = live.line_verified ? 'Hat eşleşmesi doğrulandı' : 'Güzergâha yakın araçlar · hat doğrulanmadı';
  for (const vehicle of live.vehicles || []) {
    L.marker([vehicle.latitude, vehicle.longitude]).bindPopup(`<b>${vehicle.plate || 'Plaka yok'}</b><br>Kapı: ${vehicle.door_number || '-'}<br>Hız: ${vehicle.speed_kmh ?? '-'} km/sa<br><small>Hat doğrulaması mevcut değil</small>`).addTo(map);
  }
  map.fitBounds(points, { padding: [20, 20] });
}

function showVehicles(data, line) {
  const target = $('vehicles');
  $('updated').textContent = data.fetched_at ? `Güncelleme: ${new Date(data.fetched_at).toLocaleTimeString('tr-TR')}` : '';
  const arrivals = data.arrivals || [];
  const stats = $('stats');
  if (arrivals.length) {
    stats.classList.remove('hidden');
    $('arrival-count').textContent = arrivals.length;
    $('nearest-eta').textContent = Math.min(...arrivals.map(v => v.eta_minutes).filter(Number.isFinite));
    $('source-age').textContent = data.fetched_at ? 'az önce' : '—';
  } else {
    stats.classList.add('hidden');
  }
  if (!data.available || !arrivals.length) { target.className = 'empty'; target.textContent = 'Bu durak için şu anda canlı varış verisi bulunamadı.'; return; }
  target.className = '';
  target.innerHTML = arrivals.map(v => `<article class="vehicle"><div><div class="line">${v.line}</div><div class="plate">${v.origin || 'Sefer'}</div><div class="meta">Tahmini kalkış: ${v.departure_time || '-'} · İETT canlı</div></div><div class="eta">${v.eta_minutes ?? '—'}<small>dakika</small></div></article>`).join('');
}

async function search() {
  const line = lineInput.value.trim().toUpperCase(); if (!line) return;
  $('search').disabled = true; $('search').querySelector('span').textContent = 'Yükleniyor'; message.textContent = `${line} aranıyor...`;
  const stop = stopInput.value.trim(); if (!stop) { message.textContent = 'Canlı ETA için durak kodu da girmen gerekiyor.'; $('search').disabled = false; return; }
  activeQuery = { line, stop };
  try { const [route, arrivals] = await Promise.all([getJson(`/api/routes/${encodeURIComponent(line)}`), getJson(`/api/live/arrivals?stop_code=${encodeURIComponent(stop)}&line_code=${encodeURIComponent(line)}`)]); showRoute(route); showVehicles(arrivals, line); await showMap(line); message.textContent = `${line} / ${stop} için canlı sonuçlar gösteriliyor.`; scheduleRefresh(); }
  catch (error) { message.textContent = 'Veri alınamadı. Birkaç saniye sonra tekrar dene.'; console.error(error); }
  finally { $('search').disabled = false; $('search').querySelector('span').textContent = 'Takibi başlat'; }
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    if (!activeQuery) return;
    try {
      const data = await getJson(`/api/live/arrivals?stop_code=${encodeURIComponent(activeQuery.stop)}&line_code=${encodeURIComponent(activeQuery.line)}`);
      showVehicles(data, activeQuery.line);
      await showMap(activeQuery.line);
      message.textContent = `${activeQuery.line} / ${activeQuery.stop} canlı olarak güncellendi.`;
    } catch (error) { message.textContent = 'Canlı yenileme başarısız; tekrar denenecek.'; }
    scheduleRefresh();
  }, 20000);
}
$('search').addEventListener('click', search); lineInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') search(); });
refreshConnectionStatus();
