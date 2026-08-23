const state = {
  data: null,
  radius: 320,
  mode: 'all',
  result: null,
  map: null,
  layers: { aeds: null, demand: null, recommendation: null },
};

const fmt = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 0 });
const pct = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 1 });

function activeAeds() {
  const aeds = state.mode === '24h' ? state.data.aeds.filter(a => a.is24h) : state.data.aeds;
  return aeds.filter(a => a.networkSnapped);
}

function nearestKey() {
  return state.mode === '24h' ? 'nearest24hM' : 'nearestAllM';
}

function analyze() {
  const demand = state.data.demand;
  const radius = state.radius;
  const key = nearestKey();

  const demandStatus = demand.map((d, index) => {
    const nearest = d[key] == null ? Infinity : Number(d[key]);
    return { ...d, index, covered: nearest <= radius, nearestM: nearest };
  });
  const coveredFlags = demandStatus.map(d => d.covered);

  const totalPop = demandStatus.reduce((s, d) => s + d.population, 0);
  const coveredPop = demandStatus.reduce((s, d) => s + (d.covered ? d.population : 0), 0);
  const total75 = demandStatus.reduce((s, d) => s + d.senior75, 0);
  const covered75 = demandStatus.reduce((s, d) => s + (d.covered ? d.senior75 : 0), 0);

  let best = null;
  for (const c of state.data.candidates) {
    let gain = 0;
    let gain75 = 0;
    for (const [demandIndex, distance] of c.reach) {
      if (distance > radius || coveredFlags[demandIndex]) continue;
      const d = demand[demandIndex];
      gain += d.population;
      gain75 += d.senior75;
    }
    if (!best || gain > best.gain || (gain === best.gain && gain75 > best.gain75)) {
      best = { ...c, gain, gain75 };
    }
  }

  const ranking = demandStatus
    .filter(d => !d.covered)
    .sort((a, b) => b.population - a.population || String(a.meshcode).localeCompare(String(b.meshcode)))
    .slice(0, 10);

  state.result = { aeds: activeAeds(), demandStatus, totalPop, coveredPop, total75, covered75, best, ranking };
  renderAll();
}

function renderMetrics() {
  const r = state.result;
  const rate = r.totalPop ? r.coveredPop / r.totalPop * 100 : 0;
  document.querySelector('#coverageRate').textContent = `${pct.format(rate)}%`;
  document.querySelector('#coveragePopulation').textContent = `${fmt.format(r.coveredPop)} / ${fmt.format(r.totalPop)}人`;
  document.querySelector('#uncoveredPopulation').textContent = `${fmt.format(r.totalPop - r.coveredPop)}人`;
  document.querySelector('#uncoveredSenior').textContent = `${fmt.format(r.total75 - r.covered75)}人`;
  document.querySelector('#gainPopulation').textContent = `+${fmt.format(r.best?.gain || 0)}人`;
  const after = r.totalPop ? (r.coveredPop + (r.best?.gain || 0)) / r.totalPop * 100 : 0;
  document.querySelector('#gainDetail').textContent = `配置後 ${pct.format(after)}%（+${pct.format(after - rate)}pt）`;
}

function renderRecommendation() {
  const b = state.result.best;
  if (!b) return;
  document.querySelector('#recommendationEmpty').hidden = true;
  document.querySelector('#recommendation').hidden = false;
  document.querySelector('#recName').textContent = b.name;
  document.querySelector('#recAddress').textContent = b.address || '所在地情報なし';
  document.querySelector('#recRegion').textContent = b.candidateType || '公共施設';
  document.querySelector('#recGain').textContent = `+${fmt.format(b.gain)}人`;
  document.querySelector('#recGain75').textContent = `+${fmt.format(b.gain75)}人`;
  document.querySelector('#recNearest').textContent = b.nearestAedNetworkM == null
    ? `>${fmt.format(state.data.meta.maxRadiusM)}m`
    : `${fmt.format(b.nearestAedNetworkM)}m`;
  document.querySelector('#zoomButton').disabled = false;
}

function renderRanking() {
  const root = document.querySelector('#districtRanking');
  root.innerHTML = '';
  state.result.ranking.forEach((x, i) => {
    const li = document.createElement('li');
    li.innerHTML = `<span class="rank-no">${i + 1}</span><span>Mesh ${escapeHtml(x.meshcode)}</span><span class="rank-value">${fmt.format(x.population)}人</span>`;
    root.appendChild(li);
  });
}

function popupAed(a) {
  const hours = a.is24h ? '24時間利用可（データ上）' : [a.days, a.start && a.end ? `${a.start}–${a.end}` : '', a.notes].filter(Boolean).join(' / ');
  const snap = a.snapM == null ? '歩行ネットワーク未接続' : `道路snap ${fmt.format(a.snapM)}m`;
  return `<strong>${escapeHtml(a.name)}</strong><br>${escapeHtml(a.address)}<br><small>${escapeHtml(hours || '利用可能時間の記載なし')} / ${escapeHtml(snap)}</small>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function distanceLabel(value) {
  return Number.isFinite(value) ? `${fmt.format(value)}m` : `>${fmt.format(state.data.meta.maxRadiusM)}m / 到達不能`;
}

function renderMap() {
  const r = state.result;
  if (!state.map) {
    state.map = L.map('map', { preferCanvas: true }).setView([33.84, 132.765], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(state.map);
  }
  Object.values(state.layers).forEach(layer => { if (layer) state.map.removeLayer(layer); });

  state.layers.aeds = L.layerGroup();
  for (const a of r.aeds) {
    L.circleMarker([a.lat, a.lon], {
      radius: 3.0, color: '#1878b6', weight: 1, fillColor: '#1878b6', fillOpacity: .72
    }).bindPopup(popupAed(a)).addTo(state.layers.aeds);
  }
  state.layers.aeds.addTo(state.map);

  const uncovered = r.demandStatus.filter(d => !d.covered);
  const renderedDemand = [...uncovered]
    .sort((a, b) => b.population - a.population)
    .slice(0, 5000);
  state.layers.demand = L.layerGroup();
  for (const d of renderedDemand) {
    const markerRadius = Math.max(2, Math.min(7, Math.sqrt(d.population) / 2.4));
    L.circleMarker([d.lat, d.lon], {
      radius: markerRadius, color: '#c33d3d', weight: .7, fillColor: '#c33d3d', fillOpacity: .33
    }).bindPopup(
      `<strong>未カバー100mメッシュ</strong><br>${escapeHtml(d.meshcode)}` +
      `<br>2020人口推計: 約${fmt.format(d.population)}人` +
      `<br>75歳以上: 約${fmt.format(d.senior75)}人` +
      `<br>最寄AED・歩行距離: ${escapeHtml(distanceLabel(d.nearestM))}` +
      `<br><small>道路snap: ${d.snapM == null ? '未接続' : `${fmt.format(d.snapM)}m`}</small>`
    ).addTo(state.layers.demand);
  }
  state.layers.demand.addTo(state.map);

  state.layers.recommendation = L.layerGroup();
  if (r.best) {
    L.circleMarker([r.best.lat, r.best.lon], {
      radius: 9, color: '#8a5700', weight: 2, fillColor: '#d58b14', fillOpacity: .95
    }).bindPopup(
      `<strong>次の1台 推薦候補</strong><br>${escapeHtml(r.best.name)}` +
      `<br>${escapeHtml(r.best.address)}<br>追加カバー: 約${fmt.format(r.best.gain)}人` +
      `<br><small>判定はOSM歩行最短距離</small>`
    ).addTo(state.layers.recommendation);
  }
  state.layers.recommendation.addTo(state.map);

  const note = uncovered.length > renderedDemand.length ? ` / 地図表示は人口上位${fmt.format(renderedDemand.length)}メッシュ` : '';
  document.querySelector('#mapStatus').textContent = `${r.aeds.length} AED / 未カバー ${fmt.format(uncovered.length)}メッシュ${note}`;
}

function renderAll() {
  renderMetrics();
  renderRecommendation();
  renderRanking();
  renderMap();
}

function bindControls() {
  const radius = document.querySelector('#radius');
  radius.addEventListener('input', () => {
    state.radius = Number(radius.value);
    document.querySelector('#radiusLabel').textContent = `${state.radius}m`;
    const minutes = state.radius / (state.data?.meta.walkSpeedKmh || 4.8) / 1000 * 60;
    document.querySelector('#walkMinutesHint').textContent = `歩行速度4.8km/hなら片道約${minutes.toFixed(1)}分。道路上の最短経路距離で判定します。`;
  });
  radius.addEventListener('change', analyze);

  document.querySelector('#modeAll').addEventListener('click', () => setMode('all'));
  document.querySelector('#mode24').addEventListener('click', () => setMode('24h'));
  document.querySelector('#optimizeButton').addEventListener('click', analyze);
  document.querySelector('#zoomButton').addEventListener('click', () => {
    const b = state.result?.best;
    if (!b) return;
    state.map.setView([b.lat, b.lon], 15);
    state.layers.recommendation.eachLayer(layer => { if (layer.getPopup) layer.openPopup(); });
  });
}

function setMode(mode) {
  state.mode = mode;
  document.querySelector('#modeAll').classList.toggle('active', mode === 'all');
  document.querySelector('#mode24').classList.toggle('active', mode === '24h');
  const s = state.data.summary;
  document.querySelector('#aedModeHint').textContent = mode === 'all'
    ? `全AED ${s.aedCount}件中、歩行ネットワーク接続 ${s.aedNetworkSnappedCount}件を分析`
    : `24時間判定 ${s.aed24hCount}件中、歩行ネットワーク接続 ${s.aed24hNetworkSnappedCount}件を分析`;
  analyze();
}

async function init() {
  bindControls();
  try {
    const res = await fetch('data/processed.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
    state.radius = state.data.meta.defaultRadiusM || 320;
    const slider = document.querySelector('#radius');
    slider.max = state.data.meta.maxRadiusM || 640;
    slider.value = state.radius;
    document.querySelector('#radiusLabel').textContent = `${state.radius}m`;
    document.querySelector('#walkMinutesHint').textContent = '320mは歩行速度4.8km/hで片道4分相当。道路上の最短経路距離で判定します。';
    document.querySelector('#aedModeHint').textContent = `全AED ${state.data.summary.aedCount}件中、歩行ネットワーク接続 ${state.data.summary.aedNetworkSnappedCount}件を分析`;
    analyze();
  } catch (err) {
    console.error(err);
    document.querySelector('#mapStatus').textContent = 'データ読込に失敗しました';
    document.querySelector('#recommendationEmpty').textContent = 'data/processed.json を読み込めません。データ生成処理を確認してください。';
  }
}

init();
