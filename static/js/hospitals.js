/* ============================================================
   Smart Health Navigator – Hospitals Page JS
   - Reads lat/lng from URL params (passed by home page)
   - "My Location" button re-fetches GPS
   - "Change Location" modal lets user type address manually
   - Auto-searches when params present
   ============================================================ */

let userLat = null, userLng = null;
let selectedIllness = null, selectedBodyPart = null;
let allDiseases = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadDiseases();
  initSearchBar();
  initFromURL();
});

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

  // Set radius selector
  if (radius) {
    const sel = document.getElementById('radiusSelect');
    if (sel) sel.value = radius;
  }

  // Set location
  if (lat && lng) {
    setLocation(lat, lng, null, true); // true = resolve address display
  } else {
    // No location passed — try GPS silently
    setLocationText('📡 Detecting location…', '');
    tryGPS(false); // silent — don't show modal on failure
  }

  // Trigger search based on params
  if (illness) {
    selectedIllness = illness;
    selectedBodyPart = null;
    markPill(illness);
    // Search after location is ready
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

// Wait up to 8s for location then search
function waitForLocationThenSearch() {
  const start = Date.now();
  const interval = setInterval(() => {
    if (userLat && userLng) {
      clearInterval(interval);
      searchHospitals();
    } else if (Date.now() - start > 8000) {
      clearInterval(interval);
      // Location still not available — show prompt in results
      showResults(`<div style="padding:24px; background:#eff6ff; border-radius:14px; color:#1e40af; font-weight:500; text-align:center;">
        📍 Location needed to show hospitals.<br><br>
        <button onclick="refreshGPS()" style="background:#3b82f6;color:#fff;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">
          📍 Use My GPS
        </button>
        <button onclick="showChangeLocationModal()" style="background:#f1f5f9;color:#374151;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;margin:4px;">
          ✏️ Enter Location
        </button>
      </div>`);
    }
  }, 200);
}

// ── Set location and update display ──────────────────────────
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

// ── GPS ───────────────────────────────────────────────────────
function refreshGPS() {
  if (!navigator.geolocation) {
    showChangeLocationModal();
    return;
  }
  setLocationText('📡 Getting GPS location…', '');
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      setLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy, true);
      if (selectedIllness || selectedBodyPart) searchHospitals();
    },
    (err) => {
      setLocationText('⚠️ GPS failed', '');
      showChangeLocationModal();
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
  );
}

function tryGPS(showModalOnFail = true) {
  if (!navigator.geolocation) {
    if (showModalOnFail) showChangeLocationModal();
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      setLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy, true);
    },
    () => {
      setLocationText('⚠️ Location unavailable', '');
      if (showModalOnFail) showChangeLocationModal();
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
  );
}

// ── Change Location Modal ─────────────────────────────────────
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

// Close modal on backdrop click
document.addEventListener('click', e => {
  const modal = document.getElementById('changeLocModal');
  if (modal && e.target === modal) hideChangeLocationModal();
});

async function submitChangeLocation() {
  const input  = document.getElementById('changeLocInput');
  const errEl  = document.getElementById('changeLocError');
  const btn    = document.getElementById('changeLocBtn');
  const address = (input?.value || '').trim();

  if (!address) {
    input.style.borderColor = '#ef4444';
    return;
  }

  btn.textContent = '🔄 Searching…';
  btn.disabled = true;
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
      // Re-search with new location
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
    btn.disabled = false;
  }
}

function onRadiusChange() {
  if (userLat && userLng && (selectedIllness || selectedBodyPart)) searchHospitals();
}

// ── Filter pills ──────────────────────────────────────────────
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

// ── Search bar ────────────────────────────────────────────────
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

// ── Core hospital search ──────────────────────────────────────
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
      <span class="badge badge-primary">${data.total} hospitals within ${data.radius_km} km</span>
    </div>`;

  if (!data.groups?.length) {
    showResults(`<div class="empty-state"><div class="empty-icon">🏥</div>
      <h3>No hospitals found</h3>
      <p>Try increasing the radius or <button onclick="showChangeLocationModal()" style="background:none;border:none;color:var(--primary);cursor:pointer;font-weight:700;padding:0;">change location</button></p>
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
  const mapsQ   = encodeURIComponent(h.name + ' ' + (h.address || ''));
  const srcChip = h.source === 'database' ? `<span class="meta-chip source-db">✅ Verified</span>` : '';
  const rating  = h.display_rating > 0 ? `<span class="meta-chip">⭐ ${h.display_rating}</span>` : '';
  return `<div class="hospital-card">
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
    <div class="hospital-actions">
      <a href="https://www.google.com/maps/search/?api=1&query=${mapsQ}" target="_blank" class="btn btn-primary btn-sm">🗺️ Directions</a>
      <a href="https://www.google.com/maps/search/?api=1&query=${mapsQ}" target="_blank" class="btn btn-secondary btn-sm">📌 Map</a>
      ${h.phone ? `<a href="tel:${h.phone}" class="btn btn-secondary btn-sm">📞 Call</a>` : ''}
    </div>
  </div>`;
}

function showResults(html) {
  const el = document.getElementById('resultsContent');
  if (el) el.innerHTML = html;
}
