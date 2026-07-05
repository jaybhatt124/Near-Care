/* ============================================================
   NearCares – Results Page JS
   Reads URL params, fetches hospitals, renders with Google Maps
   ============================================================ */

let userLat = null, userLng = null;
let selectedIllness = null, selectedBodyPart = null;
let allDiseases = [];
const MAPS_KEY = (typeof GOOGLE_MAPS_KEY !== 'undefined' && GOOGLE_MAPS_KEY) ? GOOGLE_MAPS_KEY : '';

document.addEventListener('DOMContentLoaded', async () => {
  await loadDiseases();
  initSearchBar();
  readParamsAndSearch();
});

async function loadDiseases() {
  try {
    const res = await fetch('/api/diseases');
    allDiseases = await res.json();
  } catch (e) { allDiseases = []; }
}

// ── Read URL params & auto-search ─────────────────────────────
function readParamsAndSearch() {
  const p = new URLSearchParams(location.search);
  const lat      = parseFloat(p.get('lat'));
  const lng      = parseFloat(p.get('lng'));
  const illness  = p.get('illness');
  const bodyPart = p.get('body_part') || p.get('part');
  const name     = p.get('name') || p.get('q');
  const radius   = p.get('radius');

  if (radius) {
    const sel = document.getElementById('radiusSelect');
    if (sel) sel.value = radius;
  }

  if (lat && lng) {
    userLat = lat; userLng = lng;
    reverseGeocode(lat, lng);
  }

  if (illness) {
    selectedIllness = illness; selectedBodyPart = null;
    markPill(illness);
    const subtitle = document.getElementById('resultsSubtitle');
    const label = allDiseases.find(d => d.key === illness)?.label || illness;
    if (subtitle) subtitle.textContent = `Results for: ${label}`;
    waitAndSearch();
  } else if (bodyPart) {
    selectedBodyPart = bodyPart; selectedIllness = null;
    const subtitle = document.getElementById('resultsSubtitle');
    if (subtitle) subtitle.textContent = `Results for: ${bodyPart}`;
    waitAndSearch();
  } else if (name) {
    const inp = document.getElementById('diseaseSearch');
    if (inp) inp.value = name;
    const match = allDiseases.find(d => d.label.toLowerCase() === name.toLowerCase() || d.key === name);
    if (match) { selectedIllness = match.key; }
    waitAndSearch();
  }
}

function waitAndSearch() {
  if (userLat && userLng) { searchHospitals(); return; }
  // Wait up to 8s for location
  const start = Date.now();
  const iv = setInterval(() => {
    if (userLat && userLng) { clearInterval(iv); searchHospitals(); }
    else if (Date.now() - start > 8000) {
      clearInterval(iv);
      showResults(`<div style="padding:24px; background:#eff6ff; border-radius:14px; color:#1e40af; text-align:center;">
        📍 Location needed to show hospitals.<br><br>
        <button onclick="refreshGPS()" style="background:#2563eb;color:#fff;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">📡 Use GPS</button>
        <button onclick="showChangeLocationModal()" style="background:#f1f5f9;color:#374151;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">✏️ Enter Location</button>
      </div>`);
    }
  }, 200);
}

function reverseGeocode(lat, lng) {
  const txt = document.getElementById('locationText');
  if (txt) txt.textContent = '📡 Resolving…';
  fetch('/api/reverse-geocode', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({lat, lng})
  }).then(r => r.json()).then(data => {
    if (txt) txt.textContent = '📍 ' + (data.formatted_address || `${lat.toFixed(4)}, ${lng.toFixed(4)}`);
  }).catch(() => {
    if (txt) txt.textContent = `📍 ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
  });
}

// ── GPS ───────────────────────────────────────────────────────
function refreshGPS() {
  const txt = document.getElementById('locationText');
  if (txt) txt.textContent = '📡 Getting GPS…';
  if (!navigator.geolocation) { showChangeLocationModal(); return; }
  navigator.geolocation.getCurrentPosition(
    pos => {
      userLat = pos.coords.latitude; userLng = pos.coords.longitude;
      reverseGeocode(userLat, userLng);
      if (selectedIllness || selectedBodyPart) searchHospitals();
    },
    () => { if (txt) txt.textContent = '⚠️ GPS failed'; showChangeLocationModal(); },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
  );
}

// ── Change Location Modal ─────────────────────────────────────
function showChangeLocationModal() {
  const m = document.getElementById('changeLocModal');
  if (m) { m.style.display = 'flex'; setTimeout(() => document.getElementById('changeLocInput')?.focus(), 100); }
}
function hideChangeLocationModal() {
  const m = document.getElementById('changeLocModal');
  if (m) m.style.display = 'none';
  const e = document.getElementById('changeLocError');
  if (e) e.style.display = 'none';
}
document.addEventListener('click', e => {
  const m = document.getElementById('changeLocModal');
  if (m && e.target === m) hideChangeLocationModal();
});

async function submitChangeLocation() {
  const input = document.getElementById('changeLocInput');
  const errEl = document.getElementById('changeLocError');
  const btn   = document.getElementById('changeLocBtn');
  const addr  = (input?.value || '').trim();
  if (!addr) { if(input) input.style.borderColor='#ef4444'; return; }
  if (btn) { btn.textContent='🔄 Searching…'; btn.disabled=true; }
  if (errEl) errEl.style.display='none';
  try {
    const res  = await fetch('/api/geocode', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({address:addr}) });
    const data = await res.json();
    if (data.success) {
      userLat = data.lat; userLng = data.lng;
      const txt = document.getElementById('locationText');
      if (txt) txt.textContent = '📍 ' + (data.formatted_address || addr);
      hideChangeLocationModal();
      if (input) input.value = '';
      if (selectedIllness || selectedBodyPart) searchHospitals();
      else showResults(`<div style="padding:20px;background:#f0fdf4;border-radius:12px;color:#166534;text-align:center;">✅ Location set. Select a condition above to search.</div>`);
    } else { throw new Error(data.error || 'Not found'); }
  } catch(e) {
    if (errEl) { errEl.textContent='❌ '+e.message+'. Try a more specific address.'; errEl.style.display='block'; }
  } finally {
    if (btn) { btn.textContent='🔍 Search Here'; btn.disabled=false; }
  }
}

function onRadiusChange() {
  if (userLat && userLng && (selectedIllness || selectedBodyPart)) searchHospitals();
}

// ── Filter pills ──────────────────────────────────────────────
function selectIllness(key) {
  selectedIllness = key; selectedBodyPart = null;
  markPill(key); searchHospitals();
}
function selectBodyPart(part) {
  selectedBodyPart = part; selectedIllness = null;
  document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('btn-primary'));
  searchHospitals();
}
function markPill(key) {
  document.querySelectorAll('.filter-pill').forEach(b => b.classList.toggle('btn-primary', b.dataset.key === key));
}

// ── Search bar ────────────────────────────────────────────────
function initSearchBar() {
  const inp  = document.getElementById('diseaseSearch');
  const sugg = document.getElementById('searchSuggestions');
  if (!inp) return;
  inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    if (q.length < 2) { sugg.style.display='none'; return; }
    const matches = allDiseases.filter(d => d.label.toLowerCase().includes(q)).slice(0,8);
    if (!matches.length) { sugg.style.display='none'; return; }
    sugg.innerHTML = matches.map(d =>
      `<div class="suggestion-item" onclick="pickSuggestion('${d.key}','${d.label.replace(/'/g,"\\'")}')">
        <span>${d.icon}</span> ${d.label}</div>`).join('');
    sugg.style.display='block';
  });
  inp.addEventListener('keydown', e => { if (e.key==='Enter') { triggerSearch(); sugg.style.display='none'; } });
  document.addEventListener('click', e => { if (!e.target.closest('.search-input-wrapper')) sugg.style.display='none'; });
}
function pickSuggestion(key, label) {
  document.getElementById('diseaseSearch').value = label;
  document.getElementById('searchSuggestions').style.display = 'none';
  selectedIllness = key; selectedBodyPart = null; markPill(key); searchHospitals();
}
function triggerSearch() {
  const q = (document.getElementById('diseaseSearch')?.value || '').trim().toLowerCase();
  if (!q) return;
  const match = allDiseases.find(d => d.label.toLowerCase() === q || d.key === q)
             || allDiseases.find(d => d.label.toLowerCase().includes(q));
  if (match) { selectedIllness = match.key; selectedBodyPart = null; markPill(match.key); searchHospitals(); }
  else { selectedIllness = null; selectedBodyPart = null; doSearch({ custom_query: q }); }
}

// ── Core search ───────────────────────────────────────────────
async function searchHospitals() {
  if (!userLat || !userLng) {
    showResults(`<div style="padding:24px;background:#eff6ff;border-radius:14px;color:#1e40af;text-align:center;">
      📍 Location needed.<br><br>
      <button onclick="refreshGPS()" style="background:#2563eb;color:#fff;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">📡 Use GPS</button>
      <button onclick="showChangeLocationModal()" style="background:#f1f5f9;color:#374151;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">✏️ Enter Location</button>
    </div>`);
    return;
  }
  const radius = parseInt(document.getElementById('radiusSelect')?.value || 5000);
  await doSearch({ illness_type: selectedIllness, body_part: selectedBodyPart, radius });
}

async function doSearch({ illness_type, body_part, custom_query, radius }) {
  const r = radius || parseInt(document.getElementById('radiusSelect')?.value || 5000);
  showResults(`<div class="loading-overlay"><div class="spinner"></div><p style="color:var(--text-muted);font-weight:600;">Searching hospitals near you…</p></div>`);
  try {
    const res = await fetch('/api/search-hospitals', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ lat:userLat, lng:userLng, radius:r,
        illness_type:illness_type||'', body_part:body_part||'', custom_query:custom_query||'', limit:40 })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderResults(data);
  } catch(e) {
    showResults(`<div style="padding:20px;background:#fef2f2;border-radius:12px;color:#991b1b;">❌ ${e.message}</div>`);
  }
}

function renderResults(data) {
  const hdr = document.getElementById('resultsHeader');
  if (hdr) hdr.innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <h2 style="font-size:1.2rem;font-weight:800;">Results for <span style="color:var(--primary);">${data.search_label}</span></h2>
      <span class="badge badge-primary">${data.total} hospitals within ${data.radius_km} km</span>
    </div>`;
  if (!data.groups?.length) {
    showResults(`<div class="empty-state"><div class="empty-icon">🏥</div><h3>No hospitals found</h3>
      <p>Try a larger radius or <button onclick="showChangeLocationModal()" style="background:none;border:none;color:var(--primary);cursor:pointer;font-weight:700;padding:0;">change location</button></p>
    </div>`);
    return;
  }
  showResults(data.groups.map(g => `
    <div style="margin-bottom:32px;">
      <div class="group-header">
        <span class="group-icon">${g.icon}</span>
        <span class="group-label">${g.label}</span>
        <span class="group-count">${g.hospitals.length}</span>
      </div>
      ${g.hospitals.map(h => hospitalCard(h)).join('')}
    </div>`).join(''));
}

function hospitalCard(h) {
  const name   = h.name;
  const addr   = h.address || '';
  const srcChip = h.source === 'database' ? `<span class="meta-chip source-db">✅ Verified</span>` : '';
  const rating  = h.display_rating > 0 ? `<span class="meta-chip">⭐ ${h.display_rating}</span>` : '';

  // Google Maps links
  let mapsLink = '';
  if (MAPS_KEY && h.lat && h.lng) {
    // Embed directions using lat/lng
    mapsLink = `https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lng}&destination_place_id=`;
  } else {
    // Fallback: search by name
    mapsLink = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name + ' ' + addr)}`;
  }

  const mapsViewLink = (h.lat && h.lng)
    ? `https://www.google.com/maps?q=${h.lat},${h.lng}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name + ' ' + addr)}`;

  return `<div class="hospital-card">
    <div class="hospital-top">
      <div class="hospital-avatar" aria-hidden="true">🏥</div>
      <div class="hospital-info">
        <div class="hospital-name">${name}</div>
        <div class="hospital-address">${addr || 'Address not available'}</div>
      </div>
    </div>
    <div class="hospital-meta">
      <span class="meta-chip distance">📍 ${h.distance} km</span>
      <span class="meta-chip">${h.type || 'Hospital'}</span>
      ${rating}${srcChip}
      ${h.phone ? `<span class="meta-chip">📞 ${h.phone}</span>` : ''}
      <span class="meta-chip">${h.specialty_label || ''}</span>
    </div>
    <div class="hospital-actions">
      <a href="${mapsLink}" target="_blank" rel="noopener" class="btn btn-primary btn-sm" aria-label="Get directions to ${name}">🗺️ Directions</a>
      <a href="${mapsViewLink}" target="_blank" rel="noopener" class="btn btn-secondary btn-sm" aria-label="View ${name} on map">📌 Map</a>
      ${h.phone ? `<a href="tel:${h.phone}" class="btn btn-secondary btn-sm" aria-label="Call ${name}">📞 Call</a>` : ''}
    </div>
  </div>`;
}

function showResults(html) {
  const el = document.getElementById('resultsContent');
  if (el) el.innerHTML = html;
}
