/* ============================================================
   NearCares – Home Page JS
   ============================================================ */

let allDiseases = [];
let _pendingSearch = null; // stores { searchType, searchValue, displayName }

document.addEventListener('DOMContentLoaded', () => {
  loadDiseases();
  initBodyMap();
  initIllnessCards();
  initSearchBar();
});

// ── Disease list ──────────────────────────────────────────────
async function loadDiseases() {
  try {
    const res = await fetch('/api/diseases');
    allDiseases = await res.json();
  } catch (e) { allDiseases = []; }
}

// ── Body Map ──────────────────────────────────────────────────
function initBodyMap() {
  const bodyParts = document.querySelectorAll('.body-part');
  const hoverChip = document.getElementById('hoverChip');

  bodyParts.forEach(part => {
    // Hover (desktop)
    part.addEventListener('mouseenter', () => {
      if (hoverChip) hoverChip.textContent = '👆 ' + part.dataset.name;
      highlightPart(part.dataset.part, true);
    });
    part.addEventListener('mouseleave', () => {
      if (hoverChip) hoverChip.textContent = '👆 Click any body part';
      highlightPart(part.dataset.part, false);
    });

    // Click / tap
    part.addEventListener('click', () => {
      if (hoverChip) hoverChip.textContent = '📍 ' + part.dataset.name + '…';
      _pendingSearch = { searchType: 'body_part', searchValue: part.dataset.part, displayName: part.dataset.name };
      showLocationChoiceModal();
    });
  });
}

function highlightPart(partName, on) {
  document.querySelectorAll(`[data-part="${partName}"]`).forEach(p => {
    p.style.fill        = on ? 'rgba(59,130,246,0.32)' : '';
    p.style.stroke      = on ? '#3b82f6' : '';
    p.style.strokeWidth = on ? '2' : '';
  });
}

// ── Illness Cards ─────────────────────────────────────────────
function initIllnessCards() {
  document.querySelectorAll('.illness-card').forEach(card => {
    card.addEventListener('click', () => {
      card.style.transform = 'scale(0.95)';
      setTimeout(() => card.style.transform = '', 180);
      const key   = card.dataset.key;
      const label = card.querySelector('.illness-label')?.textContent || key;
      _pendingSearch = { searchType: 'illness', searchValue: key, displayName: label };
      showLocationChoiceModal();
    });
  });
}

// ── Location Choice Modal (GPS OR Manual) ─────────────────────
function showLocationChoiceModal() {
  document.getElementById('locationChoiceModal')?.remove();

  const modal = document.createElement('div');
  modal.id = 'locationChoiceModal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-label', 'Choose location method');
  modal.style.cssText = `
    position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);
    display:flex;align-items:flex-end;justify-content:center;
    padding:0;
  `;

  modal.innerHTML = `
    <div style="
      background:#fff;border-radius:24px 24px 0 0;
      padding:28px 24px 36px;width:100%;max-width:480px;
      box-shadow:0 -8px 40px rgba(0,0,0,0.2);
      animation:slideUp 0.28s ease;
    ">
      <style>@keyframes slideUp{from{transform:translateY(100%)}to{transform:translateY(0)}}</style>

      <!-- Handle bar -->
      <div style="width:40px;height:4px;background:#e5e7eb;border-radius:4px;margin:0 auto 20px;"></div>

      <h3 style="font-size:1.1rem;font-weight:800;text-align:center;margin:0 0 6px;color:#111;">
        📍 How to find your location?
      </h3>
      <p style="font-size:0.83rem;color:#6b7280;text-align:center;margin:0 0 24px;">
        We need your location to show nearby hospitals
      </p>

      <!-- GPS Button -->
      <button id="useGpsBtn"
        style="width:100%;padding:16px;margin-bottom:12px;
               background:linear-gradient(135deg,#2563eb,#06b6d4);
               border:none;border-radius:14px;color:#fff;
               font-size:1rem;font-weight:700;cursor:pointer;
               display:flex;align-items:center;justify-content:center;gap:10px;"
        onclick="chooseGPS()">
        <span style="font-size:1.3rem;">📡</span>
        <span>Use My Current Location</span>
        <span style="font-size:0.75rem;background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:20px;margin-left:4px;">Recommended</span>
      </button>

      <!-- Manual Entry -->
      <button id="useManualBtn"
        style="width:100%;padding:15px;margin-bottom:20px;
               background:#f8fafc;border:2px solid #e5e7eb;
               border-radius:14px;color:#374151;
               font-size:0.95rem;font-weight:700;cursor:pointer;
               display:flex;align-items:center;justify-content:center;gap:10px;"
        onclick="chooseManual()">
        <span style="font-size:1.3rem;">✏️</span>
        Enter Location Manually
      </button>

      <!-- Cancel -->
      <button onclick="closeLocationChoiceModal()"
        style="width:100%;padding:12px;background:none;border:none;
               color:#9ca3af;font-size:0.9rem;cursor:pointer;font-weight:600;">
        Cancel
      </button>
    </div>`;

  document.body.appendChild(modal);

  // Close on backdrop tap
  modal.addEventListener('click', e => {
    if (e.target === modal) closeLocationChoiceModal();
  });
}

function closeLocationChoiceModal() {
  document.getElementById('locationChoiceModal')?.remove();
  // Reset chip text
  const hoverChip = document.getElementById('hoverChip');
  if (hoverChip) hoverChip.textContent = '👆 Click any body part';
}

// ── GPS option chosen ─────────────────────────────────────────
function chooseGPS() {
  // Replace modal content with spinner
  const modal = document.getElementById('locationChoiceModal');
  if (modal) {
    const inner = modal.querySelector('div');
    if (inner) inner.innerHTML = `
      <div style="text-align:center;padding:20px 0 12px;">
        <div style="width:48px;height:48px;border:3px solid #dbeafe;border-top-color:#2563eb;
                    border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px;"></div>
        <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
        <p style="font-weight:700;color:#111;margin:0 0 6px;">Getting your location…</p>
        <p style="font-size:0.82rem;color:#6b7280;margin:0 0 20px;">Please allow location access when prompted</p>
        <button onclick="chooseManual()"
          style="padding:10px 24px;background:#f1f5f9;border:none;border-radius:10px;
                 color:#374151;cursor:pointer;font-weight:600;font-size:0.85rem;">
          Enter manually instead
        </button>
      </div>`;
  }

  if (!navigator.geolocation) {
    closeLocationChoiceModal();
    showManualEntryModal('GPS is not supported on this device.');
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      closeLocationChoiceModal();
      if (_pendingSearch) {
        navigateTo(
          _pendingSearch.searchType,
          _pendingSearch.searchValue,
          _pendingSearch.displayName,
          pos.coords.latitude,
          pos.coords.longitude
        );
      }
    },
    (err) => {
      closeLocationChoiceModal();
      const msg = {
        1: 'Location permission was denied. Please allow it in your browser settings, or enter manually.',
        2: 'Could not detect your location. Please try entering it manually.',
        3: 'Location request timed out. Please try again or enter manually.'
      }[err.code] || 'Could not get location.';
      showManualEntryModal(msg);
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );
}

// ── Manual entry option chosen ────────────────────────────────
function chooseManual() {
  closeLocationChoiceModal();
  showManualEntryModal('');
}

function showManualEntryModal(reason) {
  document.getElementById('shnManualModal')?.remove();

  const modal = document.createElement('div');
  modal.id = 'shnManualModal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-label', 'Enter location manually');
  modal.style.cssText = `
    position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);
    display:flex;align-items:flex-end;justify-content:center;
  `;

  const sv = _pendingSearch ? encodeURIComponent(_pendingSearch.searchValue) : '';
  const dn = _pendingSearch ? encodeURIComponent(_pendingSearch.displayName) : '';
  const st = _pendingSearch ? _pendingSearch.searchType : '';

  modal.innerHTML = `
    <div style="
      background:#fff;border-radius:24px 24px 0 0;
      padding:28px 24px 36px;width:100%;max-width:480px;
      box-shadow:0 -8px 40px rgba(0,0,0,0.2);
      animation:slideUp 0.28s ease;
    ">
      <style>@keyframes slideUp{from{transform:translateY(100%)}to{transform:translateY(0)}}</style>
      <div style="width:40px;height:4px;background:#e5e7eb;border-radius:4px;margin:0 auto 20px;"></div>

      <h3 style="font-size:1.1rem;font-weight:800;margin:0 0 6px;color:#111;">✏️ Enter Your Location</h3>
      ${reason ? `<p style="font-size:0.82rem;color:#ef4444;margin:0 0 12px;">${reason}</p>` : ''}
      <p style="font-size:0.83rem;color:#6b7280;margin:0 0 16px;">
        Type your city, area, or pincode
      </p>

      <input id="manualLocInput"
        type="text"
        placeholder="e.g. Ahmedabad, Gujarat or 380001"
        autocomplete="off"
        aria-label="Enter your city or area"
        style="width:100%;padding:14px 16px;border:2px solid #e5e7eb;
               border-radius:12px;font-size:1rem;outline:none;
               box-sizing:border-box;margin-bottom:8px;"
        onkeydown="if(event.key==='Enter') shnGeocode('${st}','${sv}','${dn}')"/>

      <div id="manualLocError" style="display:none;color:#ef4444;font-size:0.82rem;margin-bottom:10px;" role="alert"></div>

      <button id="manualLocBtn"
        onclick="shnGeocode('${st}','${sv}','${dn}')"
        style="width:100%;padding:15px;margin-bottom:10px;
               background:linear-gradient(135deg,#2563eb,#06b6d4);
               border:none;border-radius:14px;color:#fff;
               font-size:1rem;font-weight:700;cursor:pointer;">
        🔍 Find Hospitals
      </button>

      <button onclick="document.getElementById('shnManualModal').remove();showLocationChoiceModal()"
        style="width:100%;padding:12px;background:#f8fafc;border:2px solid #e5e7eb;
               border-radius:12px;color:#374151;font-size:0.9rem;cursor:pointer;font-weight:600;">
        ← Back
      </button>
    </div>`;

  document.body.appendChild(modal);
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
  setTimeout(() => document.getElementById('manualLocInput')?.focus(), 100);
}

async function shnGeocode(searchType, svEncoded, dnEncoded) {
  const input   = document.getElementById('manualLocInput');
  const errEl   = document.getElementById('manualLocError');
  const btn     = document.getElementById('manualLocBtn');
  const address = (input?.value || '').trim();

  if (!address) {
    if (input) input.style.borderColor = '#ef4444';
    return;
  }

  if (btn) { btn.textContent = '🔄 Searching…'; btn.disabled = true; }
  if (errEl) errEl.style.display = 'none';

  try {
    const res  = await fetch('/api/geocode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    const data = await res.json();

    if (data.success) {
      document.getElementById('shnManualModal')?.remove();
      navigateTo(
        decodeURIComponent(searchType),
        decodeURIComponent(svEncoded),
        decodeURIComponent(dnEncoded),
        data.lat, data.lng
      );
    } else {
      throw new Error(data.error || 'Address not found');
    }
  } catch (e) {
    if (errEl) { errEl.textContent = '❌ ' + e.message + '. Try a more specific address.'; errEl.style.display = 'block'; }
    if (input) input.style.borderColor = '#ef4444';
    if (btn) { btn.textContent = '🔍 Find Hospitals'; btn.disabled = false; }
  }
}

function navigateTo(searchType, searchValue, displayName, lat, lng) {
  const radius = document.getElementById('radiusSelect')?.value || 5000;
  let url = `/hospitals?lat=${lat}&lng=${lng}&name=${encodeURIComponent(displayName)}&radius=${radius}`;
  if (searchType === 'illness') {
    url += `&illness=${encodeURIComponent(searchValue)}`;
  } else {
    url += `&body_part=${encodeURIComponent(searchValue)}`;
  }
  window.location.href = url;
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
      </div>`
    ).join('');
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
  _pendingSearch = { searchType: 'illness', searchValue: key, displayName: label };
  showLocationChoiceModal();
}

function triggerSearch() {
  const q = (document.getElementById('diseaseSearch')?.value || '').trim().toLowerCase();
  if (!q) return;
  const match = allDiseases.find(d => d.label.toLowerCase() === q || d.key === q)
             || allDiseases.find(d => d.label.toLowerCase().includes(q));
  const key   = match?.key   || q;
  const label = match?.label || q;
  _pendingSearch = { searchType: 'illness', searchValue: key, displayName: label };
  showLocationChoiceModal();
}

function onRadiusChange() {}
