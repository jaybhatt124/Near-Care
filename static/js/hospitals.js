/* ============================================================
   NearCares – Hospitals Page JS
   Map: "View All on Google Maps" button (reliable, no SDK needed)
   Click card / Directions → Google Maps navigation
   ============================================================ */

let userLat = null, userLng = null;
let selectedIllness = null, selectedBodyPart = null;
let allDiseases = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadDiseases();
  initSearchBar();
  initFromURL();
});

// ── Show "View All on Google Maps" button after results load ──
function showMap(hospitals) {
  const btn       = document.getElementById('viewOnMapBtn');
  const container = document.getElementById('mapBtnContainer');
  if (!btn || !container || !hospitals.length) return;

  // Build a Google Maps search URL with all hospital names near user location
  let url;
  if (hospitals.length === 1) {
    url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(hospitals[0].name)}&query_place_id=${hospitals[0].place_id || ''}`;
  } else {
    // Open Google Maps centered on user location searching for hospitals
    const query = encodeURIComponent('hospitals near me');
    url = userLat && userLng
      ? `https://www.google.com/maps/search/hospitals/@${userLat},${userLng},14z`
      : `https://www.google.com/maps/search/${query}`;
  }

  btn.href = url;
  container.style.display = 'block';
}

// ── Load disease list ─────────────────────────────────────────
async function loadDiseases() {
  try {
    const res = await fetch('/api/diseases');
    allDiseases = await res.json();
  } catch (e) { allDiseases = []; }
}

// ── Read URL params set by home page and auto-search ──────────
function initFromURL() {
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
    setLocation(lat, lng, null, true);
  } else {
    setLocationText('📡 Detecting location…', '');
    tryGPS(false);
  }

  if (illness) {
    selectedIllness = illness;
    selectedBodyPart = null;
    markPill(illness);
    waitForLocationThenSearch();
  } else if (bodyPart) {
    selectedBodyPart = bodyPart;
    selectedIllness = null;
    waitForLocationThenSearch();
  } else if (name) {
    const inp = document.getElementById('diseaseSearch');
    if (inp) inp.value = name;
    const match = allDiseases.find(d =>
      d.label.toLowerCase() === name.toLowerCase() || d.key === name);
    if (match) { selectedIllness = match.key; }
    waitForLocationThenSearch();
  }
}

function waitForLocationThenSearch() {
  const start = Date.now();
  const interval = setInterval(() => {
    if (userLat && userLng) {
      clearInterval(interval);
      searchHospitals();
    } else if (Date.now() - start > 5000) {
      // After 5s without location, stop waiting and prompt user
      clearInterval(interval);
      setLocationText('⚠️ Could not detect location', '');
      showResults(`<div style="padding:24px; background:#eff6ff; border-radius:14px; color:#1e40af; font-weight:500; text-align:center;">
        📍 Location could not be detected automatically.<br><br>
        <button onclick="refreshGPS()" style="background:#3b82f6;color:#fff;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">
          📍 Try GPS Again
        </button>
        <button onclick="showChangeLocationModal()" style="background:#f1f5f9;color:#374151;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">
          ✏️ Enter Location Manually
        </button>
      </div>`);
    }
  }, 300);
}

function setLocation(lat, lng, accuracy, resolveAddress) {
  userLat = lat;
  userLng = lng;
  if (resolveAddress) {
    setLocationText('📡 Resolving address…', '');
    fetch('/api/reverse-geocode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lng })
    }).then(r => r.json()).then(data => {
      const addr = data.formatted_address || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      const acc  = accuracy ? `±${Math.round(accuracy)}m` : '';
      setLocationText('📍 ' + addr, acc);
    }).catch(() => {
      setLocationText(`📍 ${lat.toFixed(4)}, ${lng.toFixed(4)}`, accuracy ? `±${Math.round(accuracy)}m` : '');
    });
  }
}

function setLocationText(text, accuracy) {
  const el = document.getElementById('locationText');
  const ac = document.getElementById('accuracyText');
  if (el) el.textContent = text;
  if (ac) ac.textContent = accuracy || '';
}

function refreshGPS() {
  if (!navigator.geolocation) { showChangeLocationModal(); return; }
  setLocationText('📡 Getting GPS location…', '');
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      setLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy, true);
      if (selectedIllness || selectedBodyPart) searchHospitals();
    },
    (err) => {
      console.warn('GPS error:', err.code, err.message);
      setLocationText('⚠️ GPS failed — enter location manually', '');
      showChangeLocationModal();
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
  );
}

function tryGPS(showModalOnFail = true) {
  if (!navigator.geolocation) {
    setLocationText('⚠️ GPS not supported', '');
    if (showModalOnFail) showChangeLocationModal();
    return;
  }

  // Try high accuracy first, fall back to low accuracy if it fails
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      setLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy, true);
    },
    (err) => {
      // High accuracy failed — retry with low accuracy (faster, works indoors)
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy, true);
        },
        () => {
          setLocationText('⚠️ Location unavailable', '');
          if (showModalOnFail) showChangeLocationModal();
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 }
      );
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
  );
}

function showChangeLocationModal() {
  const modal = document.getElementById('changeLocModal');
  if (modal) {
    modal.style.display = 'flex';
    setTimeout(() => document.getElementById('changeLocInput')?.focus(), 100);
  }
}

function hideChangeLocationModal() {
  const modal = document.getElementById('changeLocModal');
  if (modal) modal.style.display = 'none';
  const errEl = document.getElementById('changeLocError');
  if (errEl) errEl.style.display = 'none';
}

document.addEventListener('click', e => {
  const modal = document.getElementById('changeLocModal');
  if (modal && e.target === modal) hideChangeLocationModal();
});

async function submitChangeLocation() {
  const input   = document.getElementById('changeLocInput');
  const errEl   = document.getElementById('changeLocError');
  const btn     = document.getElementById('changeLocBtn');
  const address = (input?.value || '').trim();

  if (!address) { input.style.borderColor = '#ef4444'; return; }

  btn.textContent = '🔄 Searching…';
  btn.disabled    = true;
  if (errEl) errEl.style.display = 'none';
  input.style.borderColor = '';

  try {
    const res  = await fetch('/api/geocode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    const data = await res.json();

    if (data.success) {
      userLat = data.lat;
      userLng = data.lng;
      setLocationText('📍 ' + (data.formatted_address || address), '(manual)');
      hideChangeLocationModal();
      if (input) input.value = '';
      if (selectedIllness || selectedBodyPart) {
        searchHospitals();
      } else {
        showResults(`<div style="padding:20px; background:#f0fdf4; border-radius:12px; color:#166534; text-align:center;">
          ✅ Location set to <strong>${data.formatted_address || address}</strong><br>
          Now select a condition or body part above to search hospitals.
        </div>`);
      }
    } else {
      throw new Error(data.error || 'Address not found');
    }
  } catch (e) {
    if (errEl) {
      errEl.textContent = '❌ ' + e.message + '. Try a more specific address.';
      errEl.style.display = 'block';
    }
  } finally {
    btn.textContent = '🔍 Find Hospitals Here';
    btn.disabled    = false;
  }
}

function onRadiusChange() {
  if (userLat && userLng && (selectedIllness || selectedBodyPart)) searchHospitals();
}

function selectIllness(key) {
  selectedIllness  = key;
  selectedBodyPart = null;
  markPill(key);
  searchHospitals();
}

function selectBodyPart(part) {
  selectedBodyPart = part;
  selectedIllness  = null;
  document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('btn-primary'));
  searchHospitals();
}

function markPill(key) {
  document.querySelectorAll('.filter-pill').forEach(b => {
    b.classList.toggle('btn-primary', b.dataset.key === key);
  });
}

function initSearchBar() {
  const inp  = document.getElementById('diseaseSearch');
  const sugg = document.getElementById('searchSuggestions');
  if (!inp) return;

  inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    if (q.length < 2) { sugg.style.display = 'none'; return; }
    const matches = allDiseases.filter(d => d.label.toLowerCase().includes(q)).slice(0, 8);
    if (!matches.length) { sugg.style.display = 'none'; return; }
    sugg.innerHTML = matches.map(d =>
      `<div class="suggestion-item" onclick="pickSuggestion('${d.key}','${d.label.replace(/'/g,"\\'")}')">
        <span>${d.icon}</span> ${d.label}
      </div>`).join('');
    sugg.style.display = 'block';
  });
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { triggerSearch(); sugg.style.display = 'none'; }
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.search-input-wrapper')) sugg.style.display = 'none';
  });
}

function pickSuggestion(key, label) {
  document.getElementById('diseaseSearch').value = label;
  document.getElementById('searchSuggestions').style.display = 'none';
  selectedIllness = key;
  selectedBodyPart = null;
  markPill(key);
  searchHospitals();
}

function triggerSearch() {
  const q = (document.getElementById('diseaseSearch')?.value || '').trim().toLowerCase();
  if (!q) return;
  const match = allDiseases.find(d => d.label.toLowerCase() === q || d.key === q)
             || allDiseases.find(d => d.label.toLowerCase().includes(q));
  if (match) {
    selectedIllness = match.key;
    selectedBodyPart = null;
    markPill(match.key);
    searchHospitals();
  } else {
    selectedIllness = null;
    selectedBodyPart = null;
    doSearch({ custom_query: q });
  }
}

async function searchHospitals() {
  if (!userLat || !userLng) {
    showResults(`<div style="padding:24px; background:#eff6ff; border-radius:14px; color:#1e40af; text-align:center;">
      📍 Location needed to show hospitals.<br><br>
      <button onclick="refreshGPS()" style="background:#3b82f6;color:#fff;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">
        📍 Use My GPS
      </button>
      <button onclick="showChangeLocationModal()" style="background:#f1f5f9;color:#374151;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">
        ✏️ Enter Location
      </button>
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
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lat: userLat, lng: userLng, radius: r,
        illness_type: illness_type || '',
        body_part:    body_part    || '',
        custom_query: custom_query || '',
        limit: 40
      })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderResults(data);
  } catch (e) {
    showResults(`<div style="padding:20px;background:#fef2f2;border-radius:12px;color:#991b1b;">❌ ${e.message}</div>`);
  }
}

function renderResults(data) {
  const hdr = document.getElementById('resultsHeader');
  if (hdr) hdr.innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <h2 style="font-size:1.3rem;font-weight:800;">
        Results for <span style="color:var(--primary);">${data.search_label}</span>
      </h2>
      <span class="badge badge-primary">${data.total} found within ${data.radius_km} km</span>
    </div>`;

  if (!data.groups?.length) {
    showResults(`<div class="empty-state"><div class="empty-icon">🏥</div>
      <h3>No hospitals found</h3>
      <p>Try increasing the radius or <button onclick="showChangeLocationModal()" style="background:none;border:none;color:var(--primary);cursor:pointer;font-weight:700;padding:0;">change location</button></p>
    </div>`);
    // hide map if no results
    const mc = document.getElementById('mapContainer');
    if (mc) mc.style.display = 'none';
    return;
  }

  // Show map with all hospitals placed as markers
  const allH = data.groups.flatMap(g => g.hospitals);
  showMap(allH);

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
  // clicking card opens directions in Google Maps
  const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lng}`;
  const mapsQ   = encodeURIComponent(h.name + ' ' + (h.address || ''));
  const srcChip = h.source === 'database' ? `<span class="meta-chip source-db">✅ Verified</span>` : '';
  const rating  = h.display_rating > 0 ? `<span class="meta-chip">⭐ ${h.display_rating}</span>` : '';

  return `<div class="hospital-card" onclick="focusOnMap(${h.lat},${h.lng},'${h.name.replace(/'/g,"\\'")}','${(h.address||'').replace(/'/g,"\\'")}',${h.distance||0},'${h.phone||''}')">
    <div class="hospital-top">
      <div class="hospital-avatar">🏥</div>
      <div class="hospital-info">
        <div class="hospital-name">${h.name}</div>
        <div class="hospital-address">${h.address || 'Address not available'}</div>
      </div>
    </div>
    <div class="hospital-meta">
      <span class="meta-chip distance">📍 ${h.distance} km</span>
      <span class="meta-chip">${h.type || 'Hospital'}</span>
      ${rating}${srcChip}
      ${h.phone ? `<span class="meta-chip">📞 ${h.phone}</span>` : ''}
      <span class="meta-chip">${h.specialty_label || ''}</span>
    </div>
    <div class="hospital-actions" onclick="event.stopPropagation()">
      <a href="${mapsUrl}" target="_blank" class="btn btn-primary btn-sm">🗺️ Directions</a>
      <a href="https://www.google.com/maps/search/?api=1&query=${mapsQ}" target="_blank" class="btn btn-secondary btn-sm">📌 Map</a>
      ${h.phone ? `<a href="tel:${h.phone}" class="btn btn-secondary btn-sm">📞 Call</a>` : ''}
    </div>
  </div>`;
}

// Click card → open Google Maps directions directly
function focusOnMap(lat, lng, name, address, distance, phone) {
  const url = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
  window.open(url, '_blank');
}

function showResults(html) {
  const el = document.getElementById('resultsContent');
  if (el) el.innerHTML = html;
}
