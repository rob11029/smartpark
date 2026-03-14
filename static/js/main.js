// MAP INIT
const map = L.map('map', { zoomControl: true }).setView([33.8816, -117.8855], 17);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);

let parkingLots = [];
let markers     = {};
let activeLotId = null;

// STATUS HELPERS
const STATUS_COLOR = { Available:'#00b84a', Busy:'#f59e0b', Full:'#ef4444', Closed:'#9099b0' };
const STATUS_PILL  = { Available:'pill-available', Busy:'pill-busy', Full:'pill-full', Closed:'pill-closed' };
const BAR_CLASS    = { Available:'fill-available', Busy:'fill-busy', Full:'fill-full', Closed:'fill-closed' };

function getColor(status) { return STATUS_COLOR[status] || '#9099b0'; }

function makeIcon(status, active=false) {
  const c = getColor(status);
  const size = active ? 26 : 18;
  return L.divIcon({
    className: '',
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:50%;
      background:${c};border:3px solid #fff;
      box-shadow:0 2px 12px ${c}cc;transition:all 0.2s;
    "></div>`,
    iconSize: [size, size], iconAnchor: [size/2, size/2]
  });
}

// LOAD LOTS
async function loadLots() {
  const res = await fetch('/api/lots');
  parkingLots = await res.json();
  Object.values(markers).forEach(m => map.removeLayer(m));
  markers = {};
  parkingLots.forEach(lot => {
    const m = L.marker([lot.lat, lot.lng], { icon: makeIcon(lot.status) })
      .addTo(map)
      .bindPopup(`<strong>${lot.name}</strong><br/>${lot.status} · ${lot.available} spots free`);
    m.on('click', () => selectLot(lot.id));
    markers[lot.id] = m;
  });
  renderSidebarLots();
  renderTopbarStats();
}

// SIDEBAR LOTS
function renderSidebarLots() {
  const el = document.getElementById('sidebar-lots');
  el.innerHTML = parkingLots.map((lot, i) => {
    const pct = Math.round((lot.available / lot.capacity) * 100);
    return `
      <div class="lot-card ${activeLotId === lot.id ? 'active' : ''}"
           style="animation-delay:${i*0.04}s"
           onclick="selectLot(${lot.id})">
        <div class="lot-card-top">
          <div class="lot-name">${lot.name}</div>
          <span class="status-pill ${STATUS_PILL[lot.status]}">${lot.status}</span>
        </div>
        <div class="occ-bar-wrap">
          <div class="occ-bar-bg">
            <div class="occ-bar-fill ${BAR_CLASS[lot.status]}" style="width:${pct}%"></div>
          </div>
          <span class="occ-text">${lot.available.toLocaleString()} free</span>
        </div>
      </div>`;
  }).join('');
}

// TOPBAR STATS
function renderTopbarStats() {
  const total = parkingLots.reduce((s,l) => s+l.capacity,  0);
  const avail = parkingLots.reduce((s,l) => s+l.available, 0);
  document.getElementById('stat-total').textContent = total.toLocaleString();
  document.getElementById('stat-avail').textContent = avail.toLocaleString();
}

// SELECT LOT
function selectLot(id) {
  activeLotId = id;
  const lot = parkingLots.find(l => l.id === id);
  if (!lot) return;

  // update marker sizes
  parkingLots.forEach(l => {
    if (markers[l.id]) markers[l.id].setIcon(makeIcon(l.status, l.id === id));
  });

  map.flyTo([lot.lat, lot.lng], 17, { duration: 0.8 });
  if (markers[id]) markers[id].openPopup();

  // populate detail overlay
  const pct    = Math.round((lot.available / lot.capacity) * 100);
  const occPct = 100 - pct;
  document.getElementById('detail-name').textContent      = lot.name;
  document.getElementById('d-available').textContent      = lot.available.toLocaleString();
  document.getElementById('d-capacity').textContent       = lot.capacity.toLocaleString();
  document.getElementById('d-pct').textContent            = pct + '%';
  document.getElementById('d-occ-label').textContent      = occPct + '% occupied';
  const pill = document.getElementById('detail-pill');
  pill.textContent = lot.status;
  pill.className   = `status-pill ${STATUS_PILL[lot.status]}`;
  const bar = document.getElementById('d-occ-bar');
  bar.style.width = occPct + '%';
  bar.className   = `detail-occ-bar-fill ${BAR_CLASS[lot.status]}`;
  document.getElementById('d-checkin-btn').onclick = () => checkIn(lot.id);
  document.getElementById('d-nav-btn').onclick     = () => navigateTo(lot.lat, lot.lng);
  document.getElementById('detail-overlay').classList.add('show');
  document.getElementById('analytics-overlay').classList.remove('show');

  renderSidebarLots();
}

function closeDetail() {
  document.getElementById('detail-overlay').classList.remove('show');
  activeLotId = null;
  parkingLots.forEach(l => { if (markers[l.id]) markers[l.id].setIcon(makeIcon(l.status, false)); });
  renderSidebarLots();
}

// CHECK IN
async function checkIn(lotId) {
  const res  = await fetch('/api/checkin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lot_id: lotId })
  });
  const data = await res.json();
  if (data.status === 'success') {
    alert(`✓ ${data.message}\n${data.available} spots remaining.`);
    await loadLots();
    selectLot(lotId);
  } else {
    alert(`Error: ${data.message}`);
  }
}

// NAVIGATE
function navigateTo(lat, lng) {
  window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`, '_blank');
}

// NAV
function setActiveNav(btn) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// ANALYTICS PANEL
async function loadAnalyticsPanel() {
  const overlay = document.getElementById('analytics-overlay');
  const body    = document.getElementById('analytics-body');
  document.getElementById('detail-overlay').classList.remove('show');
  overlay.classList.add('show');
  body.innerHTML = '<p class="muted">Loading...</p>';

  const res = await fetch('/api/analytics');
  if (res.status === 401) {
    body.innerHTML = '<p class="muted">Please <a href="/login">sign in</a> to view analytics.</p>';
    return;
  }
  const data = await res.json();
  body.innerHTML = `
    <div class="analytics-grid" style="grid-template-columns:repeat(2,1fr);gap:0.5rem;margin-bottom:0.9rem">
      <div class="analytics-card"><label>Total Check-ins</label><span>${data.total_checkins}</span></div>
      <div class="analytics-card"><label>Favorite Lot</label><span style="font-size:0.82rem">${data.favorite_lot ? data.favorite_lot.name : '—'}</span></div>
    </div>
    <div style="font-size:0.72rem;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5rem">Recent Check-ins</div>
    ${data.recent_checkins.length ? data.recent_checkins.map(c => `
      <div style="padding:0.5rem 0;border-bottom:1px solid var(--gray-100);font-size:0.82rem">
        <strong>${c.name}</strong>
        <div style="font-size:0.72rem;color:var(--gray-400)">${c.timestamp}</div>
      </div>`).join('') : '<p class="muted">No check-ins yet.</p>'}
  `;
}

// CHECK-IN MODAL
function openCheckinModal() {
  document.getElementById('modal-lots').innerHTML = parkingLots.map(lot => `
    <div class="modal-lot">
      <div>
        <strong>${lot.name}</strong>
        <p>${lot.available.toLocaleString()} of ${lot.capacity.toLocaleString()} available &nbsp;·&nbsp;
          <span style="color:${getColor(lot.status)}">${lot.status}</span>
        </p>
      </div>
      <div class="modal-lot-actions">
        <button class="btn-sm btn-outline-sm" onclick="navigateTo(${lot.lat},${lot.lng})">↗ Go</button>
        <button class="btn-sm btn-orange-sm"  onclick="checkIn(${lot.id});closeCheckinModal()">✓ In</button>
      </div>
    </div>`).join('');
  document.getElementById('modal').classList.add('open');
}
function closeCheckinModal() { document.getElementById('modal').classList.remove('open'); }
function maybeClose(e) { if (e.target.id === 'modal') closeCheckinModal(); }

// INIT
loadLots();