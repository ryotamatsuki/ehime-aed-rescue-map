const state = {
  data: null,
  radius: 300,
  mode: 'all',
  result: null,
  map: null,
  layers: { aeds: null, demand: null, recommendation: null },
};

const fmt = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 0 });
const pct = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 1 });

function haversineM(a, b) {
  const R = 6371000;
  const p1 = a.lat * Math.PI / 180;
  const p2 = b.lat * Math.PI / 180;
  const dp = (b.lat - a.lat) * Math.PI / 180;
  const dl = (b.lon - a.lon) * Math.PI / 180;
  const x = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

function activeAeds() {
  if (state.mode === '24h') return state.data.aeds.filter(a => a.is24h);
  return state.data.aeds;
}

function analyze() {
  const aeds = activeAeds();
  const demand = state.data.demand;
  const radius = state.radius;

  const demandStatus = demand.map(d => {
    let nearest = Infinity;
    for (const a of aeds) {
      const dist = haversineM(d, a);
      if (dist < nearest) nearest = dist;
      if (nearest <= radius) break;
    }
    return { ...d, covered: nearest <= radius, nearestM: nearest };
  });

  const totalPop = demandStatus.reduce((s, d) => s + d.population, 0);
  const coveredPop = demandStatus.reduce((s, d) => s + (d.covered ? d.population : 0), 0);
  const total75 = demandStatus.reduce((s, d) => s + d.senior75, 0);
  const covered75 = demandStatus.reduce((s, d) => s + (d.covered ? d.senior75 : 0), 0);

  let best = null;
  for (const c of state.data.candidates) {
    let gain = 0;
    let gain75 = 0;
    for (const d of demandStatus) {
      if (d.covered) continue;
      if (haversineM(d, c) <= radius) {
        gain += d.population;
        gain75 += d.senior75;
      }
    }
    if (!best || gain > best.gain || (gain === best.gain && gain75 > best.gain75)) {
      best = { ...c, gain, gain75 };
    }
  }

  const districts = new Map();
  for (const d of demandStatus) {
    if (!districts.has(d.region)) districts.set(d.region, { region: d.region, uncovered: 0, uncovered75: 0 });
    if (!d.covered) {
      const x = districts.get(d.region);
      x.uncovered += d.population;
      x.uncovered75 += d.senior75;
    }
  }
  const ranking = [...districts.values()].sort((a, b) => b.uncovered - a.uncovered);

  state.result = { aeds, demandStatus, totalPop, coveredPop, total75, covered75, best, ranking };
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
  document.querySelector('#recRegion').textContent = b.region;
  document.querySelector('#recGain').textContent = `+${fmt.format(b.gain)}人`;
  document.querySelector('#recGain75').textContent = `+${fmt.format(b.gain75)}人`;
  document.querySelector('#recNearest').textContent = `${fmt.format(b.nearestAedM)}m`;
  document.querySelector('#zoomButton').disabled = false;
}

function renderRanking() {
  const root = document.querySelector('#districtRanking');
  root.innerHTML = '';
  state.result.ranking.slice(0, 10).forEach((x, i) => {
    const li = document.createElement('li');
    li.innerHTML = `<span class="rank-no">${i + 1}</span><span>${escapeHtml(x.region)}</span><span class="rank-value">${fmt.format(x.uncovered)}人</span>`;
    root.appendChild(li);
  });
}

function popupAed(a) {
  const hours = a.is24h ? '24時間利用可（データ上）' : [a.days, a.start && a.end ? `${a.start}–${a.end}` : '', a.notes].filter(Boolean).join(' / ');
  return `<strong>${escapeHtml(a.name)}</strong><br>${escapeHtml(a.address)}<br><small>${escapeHtml(hours || '利用可能時間の記載なし')}</small>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
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
      radius: 3.1, color: '#1878b6', weight: 1, fillColor: '#1878b6', fillOpacity: .72
    }).bindPopup(popupAed(a)).addTo(state.layers.aeds);
  }
  state.layers.aeds.addTo(state.map);

  state.layers.demand = L.layerGroup();
  for (const d of r.demandStatus) {
    if (d.covered) continue;
    const markerRadius = Math.max(3, Math.min(10, Math.sqrt(d.population) / 3));
    L.circleMarker([d.lat, d.lon], {
      radius: markerRadius, color: '#c33d3d', weight: 1, fillColor: '#c33d3d', fillOpacity: .38
    }).bindPopup(`<strong>未カバー需要点（推計）</strong><br>${escapeHtml(d.region)} / ${escapeHtml(d.name)}<br>人口配分: 約${fmt.format(d.population)}人<br>75歳以上: 約${fmt.format(d.senior75)}人<br>最寄AED: ${fmt.format(d.nearestM)}m`).addTo(state.layers.demand);
  }
  state.layers.demand.addTo(state.map);

  state.layers.recommendation = L.layerGroup();
  if (r.best) {
    L.circle([r.best.lat, r.best.lon], {
      radius: state.radius, color: '#d58b14', weight: 2, fillColor: '#d58b14', fillOpacity: .09
    }).addTo(state.layers.recommendation);
    L.circleMarker([r.best.lat, r.best.lon], {
      radius: 9, color: '#8a5700', weight: 2, fillColor: '#d58b14', fillOpacity: .95
    }).bindPopup(`<strong>次の1台 推薦候補</strong><br>${escapeHtml(r.best.name)}<br>${escapeHtml(r.best.address)}<br>追加カバー: 約${fmt.format(r.best.gain)}人`).addTo(state.layers.recommendation);
  }
  state.layers.recommendation.addTo(state.map);

  document.querySelector('#mapStatus').textContent = `${r.aeds.length} AED / 未カバー需要点 ${r.demandStatus.filter(d => !d.covered).length}`;
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
  document.querySelector('#aedModeHint').textContent = mode === 'all'
    ? `公開データ上の全AED ${state.data.summary.aedCount}件を対象`
    : `「いつでも使用可」等から保守的に判定した ${state.data.summary.aed24hCount}件を対象`;
  analyze();
}

async function init() {
  bindControls();
  try {
    const res = await fetch('data/processed.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
    state.radius = state.data.meta.defaultRadiusM || 300;
    document.querySelector('#radius').value = state.radius;
    document.querySelector('#radiusLabel').textContent = `${state.radius}m`;
    document.querySelector('#aedModeHint').textContent = `公開データ上の全AED ${state.data.summary.aedCount}件を対象`;
    analyze();
  } catch (err) {
    console.error(err);
    document.querySelector('#mapStatus').textContent = 'データ読込に失敗しました';
    document.querySelector('#recommendationEmpty').textContent = 'data/processed.json を読み込めません。データ生成処理を確認してください。';
  }
}

init();
