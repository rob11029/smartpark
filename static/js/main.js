const map = L.map("map", { zoomControl: true }).setView([33.8816, -117.8855], 17);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

const LIVE_REFRESH_MS = 5000;

let parkingLots = [];
let markers = {};
let activeLotId = null;
let levelsVisible = false;
let loadLotsInFlight = false;

const STATUS_COLOR = {
  Available: "#00b84a",
  Busy: "#f59e0b",
  "Almost Full": "#fb923c",
  Full: "#ef4444",
  Closed: "#9099b0",
  Open: "#22c55e",
};

const LOT_COORDS = {
  "Nutwood Structure": { lat: 33.8795, lng: -117.8867 },
  "State College Structure": { lat: 33.8810, lng: -117.8883 },
  "Eastside North": { lat: 33.8787, lng: -117.8828 },
  "Eastside South": { lat: 33.8769, lng: -117.8827 },
  "S8 and S10": { lat: 33.8838, lng: -117.8910 },
  "Fullerton Free Church": { lat: 33.8819, lng: -117.8922 },
};

function getColor(status) {
  return STATUS_COLOR[status] || "#9099b0";
}

function makeIcon(status, active = false) {
  const c = getColor(status);
  const size = active ? 26 : 18;

  return L.divIcon({
    className: "",
    html: `<div style="
      width:${size}px;
      height:${size}px;
      border-radius:50%;
      background:${c};
      border:3px solid #fff;
      box-shadow:0 2px 12px ${c}cc;
      transition:all 0.2s;
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function normalizeStatus(available, capacity, statusText) {
  const text = String(statusText || "").trim().toLowerCase();

  if (text === "closed") return "Closed";
  if (text === "full" || available === 0) return "Full";
  if (text === "open" && available == null) return "Open";

  if (typeof available === "number" && typeof capacity === "number" && capacity > 0) {
    const ratio = available / capacity;
    if (ratio >= 0.5) return "Available";
    if (ratio >= 0.2) return "Busy";
    return "Almost Full";
  }

  return "Closed";
}

function pillClassForStatus(status) {
  switch (status) {
    case "Available":
    case "Open":
      return "pill-available";
    case "Busy":
      return "pill-busy";
    case "Almost Full":
    case "Full":
      return "pill-full";
    default:
      return "pill-closed";
  }
}

function barClassForStatus(status) {
  switch (status) {
    case "Available":
    case "Open":
      return "bar-available";
    case "Busy":
      return "bar-busy";
    case "Almost Full":
    case "Full":
      return "bar-full";
    default:
      return "bar-closed";
  }
}

function formatFreeLine(lot) {
  if (typeof lot.available === "number" && typeof lot.capacity === "number") {
    return `${lot.available} / ${lot.capacity} free`;
  }

  if (lot.status === "Open") return "Open";
  if (lot.status === "Full") return "0 spots free";
  if (lot.status_text) return lot.status_text;

  return "Unknown";
}

function mergeParkingFromApi(dbLots, parkingPayload) {
  const liveLots = Array.isArray(parkingPayload?.lots) ? parkingPayload.lots : [];

  return dbLots.map((dbLot) => {
    const live = liveLots.find(
      (x) => String(x.name || "").trim().toLowerCase() === String(dbLot.name || "").trim().toLowerCase()
    );

    const lat = dbLot.lat ?? LOT_COORDS[dbLot.name]?.lat ?? 33.8816;
    const lng = dbLot.lng ?? LOT_COORDS[dbLot.name]?.lng ?? -117.8855;

    if (!live) {
      const status = normalizeStatus(dbLot.available, dbLot.capacity, null);
      const freePercent =
        typeof dbLot.available === "number" && typeof dbLot.capacity === "number" && dbLot.capacity > 0
          ? Math.round((dbLot.available / dbLot.capacity) * 100)
          : 0;

      return {
        ...dbLot,
        lat,
        lng,
        status,
        status_text: status,
        has_levels: false,
        levels: [],
        freePercent,
      };
    }

    const capacity =
      typeof live.total_spots === "number"
        ? live.total_spots
        : typeof dbLot.capacity === "number"
        ? dbLot.capacity
        : 0;

    const available = typeof live.available === "number" ? live.available : null;
    const status = normalizeStatus(available, capacity, live.status_text);
    const freePercent =
      typeof available === "number" && typeof capacity === "number" && capacity > 0
        ? Math.round((available / capacity) * 100)
        : status === "Open"
        ? 100
        : 0;

    return {
      ...dbLot,
      lat,
      lng,
      capacity,
      available,
      total_spots: capacity,
      status,
      status_text: live.status_text || status,
      last_updated: live.last_updated || dbLot.last_updated || "",
      has_levels: !!live.has_levels,
      levels: Array.isArray(live.levels) ? live.levels : [],
      freePercent,
      lot_id: live.lot_id || null,
    };
  });
}

function applyParkingSummaryToDom(summary) {
  const statTotal = document.getElementById("stat-total");
  const statAvail = document.getElementById("stat-avail");
  const statLots = document.getElementById("stat-lots");
  const statLastUpdated = document.getElementById("stat-last-updated");

  if (statTotal) statTotal.textContent = (summary.total_spots_sum ?? 0).toLocaleString();
  if (statAvail) statAvail.textContent = (summary.total_available_sum ?? 0).toLocaleString();
  if (statLots) statLots.textContent = String(summary.lot_count ?? 0);
  if (statLastUpdated) statLastUpdated.textContent = summary.last_updated_max || "—";
}

function renderTopbarStats() {
  const total = parkingLots.reduce((s, l) => s + (l.capacity || 0), 0);
  const avail = parkingLots.reduce((s, l) => s + (typeof l.available === "number" ? l.available : 0), 0);

  const statTotal = document.getElementById("stat-total");
  const statAvail = document.getElementById("stat-avail");
  const statLots = document.getElementById("stat-lots");
  const statLastUpdated = document.getElementById("stat-last-updated");

  if (statTotal) statTotal.textContent = total.toLocaleString();
  if (statAvail) statAvail.textContent = avail.toLocaleString();
  if (statLots) statLots.textContent = String(parkingLots.length);
  if (statLastUpdated) {
    const latest = parkingLots.map((x) => x.last_updated).filter(Boolean).sort().pop();
    statLastUpdated.textContent = latest || "—";
  }
}

async function loadLots() {
  if (loadLotsInFlight) return;
  loadLotsInFlight = true;

  try {
    let parkingPayload = null;
    let liveAvailable = false;

    try {
      const pr = await fetch("/api/parking");
      if (pr.ok) {
        parkingPayload = await pr.json();
        liveAvailable = Array.isArray(parkingPayload?.lots);
      } else {
        console.warn("Live parking API returned non-OK:", pr.status);
      }
    } catch (e) {
      console.warn("Live parking unavailable", e);
    }

    const lotsRes = await fetch("/api/lots");
    if (!lotsRes.ok) throw new Error(`Failed /api/lots: ${lotsRes.status}`);
    const dbLots = await lotsRes.json();

    if (liveAvailable) {
      parkingLots = mergeParkingFromApi(dbLots, parkingPayload);
      if (parkingPayload?.summary) {
        applyParkingSummaryToDom(parkingPayload.summary);
      } else {
        renderTopbarStats();
      }
    } else {
      parkingLots = dbLots.map((lot) => ({
        ...lot,
        lat: lot.lat ?? LOT_COORDS[lot.name]?.lat ?? 33.8816,
        lng: lot.lng ?? LOT_COORDS[lot.name]?.lng ?? -117.8855,
        has_levels: false,
        levels: [],
        status_text: lot.status,
        freePercent:
          typeof lot.available === "number" && typeof lot.capacity === "number" && lot.capacity > 0
            ? Math.round((lot.available / lot.capacity) * 100)
            : 0,
      }));
      renderTopbarStats();
    }

    Object.values(markers).forEach((m) => map.removeLayer(m));
    markers = {};

    parkingLots.forEach((lot) => {
      if (typeof lot.lat !== "number" || typeof lot.lng !== "number") return;

      const marker = L.marker([lot.lat, lot.lng], { icon: makeIcon(lot.status) })
        .addTo(map)
        .bindPopup(`<strong>${lot.name}</strong><br/>${lot.status} · ${formatFreeLine(lot)}`);

      marker.on("click", () => selectLot(lot.id));
      markers[lot.id] = marker;
    });

    if (activeLotId) {
      const active = parkingLots.find((l) => l.id === activeLotId);
      if (active && markers[activeLotId]) {
        markers[activeLotId].setIcon(makeIcon(active.status, true));
      }
    }

    renderSidebarLots();

    const detail = document.getElementById("detail-overlay");
    if (activeLotId && detail && detail.classList.contains("show")) {
      const lot = parkingLots.find((l) => l.id === activeLotId);
      if (lot) fillDetailPanelContent(lot);
    }
  } catch (err) {
    console.error("loadLots failed:", err);
  } finally {
    loadLotsInFlight = false;
  }
}

function renderSidebarLots() {
  const el = document.getElementById("sidebar-lots");
  if (!el) return;

  el.innerHTML = parkingLots
    .map((lot, i) => {
      const availablePct = lot.freePercent != null
        ? lot.freePercent
        : lot.capacity
        ? Math.round(((lot.available || 0) / lot.capacity) * 100)
        : 0;

const fullPct = Math.max(0, 100 - availablePct);

return `
  <div class="lot-card ${activeLotId === lot.id ? "active" : ""}"
       data-lot-id="${lot.id}"
       style="animation-delay:${i * 0.04}s"
       onclick="selectLot(${lot.id})">
    <div class="lot-card-top">
      <div class="lot-name">${lot.name}</div>
      <span class="status-pill ${pillClassForStatus(lot.status)}">${lot.status}</span>
    </div>
    <div class="occ-bar-wrap">
      <div class="occ-bar-bg">
        <div class="occ-bar-fill ${barClassForStatus(lot.status)}" style="width:${fullPct}%"></div>
      </div>
      <span class="occ-text">
        ${typeof lot.available === "number" ? `${lot.available} spots available` : (lot.status_text || lot.status)}
      </span>
    </div>
  </div>
`;
    })
    .join("");
}

function fillDetailPanelContent(lot) {
  const pct = lot.freePercent != null
    ? lot.freePercent
    : lot.capacity
    ? Math.round(((lot.available || 0) / lot.capacity) * 100)
    : 0;

  const occPct = Math.max(0, 100 - pct);

  const detailName = document.getElementById("detail-name");
  const dAvailable = document.getElementById("d-available");
  const dCapacity = document.getElementById("d-capacity");
  const dPct = document.getElementById("d-pct");
  const dOccLabel = document.getElementById("d-occ-label");
  const dLastUpdated = document.getElementById("d-last-updated");
  const pill = document.getElementById("detail-pill");
  const bar = document.getElementById("d-occ-bar");

  if (detailName) detailName.textContent = lot.name;
  if (dAvailable) dAvailable.textContent = formatFreeLine(lot);
  if (dCapacity) dCapacity.textContent = (lot.capacity || 0).toLocaleString();
  if (dPct) dPct.textContent = `${pct}%`;
  if (dOccLabel) dOccLabel.textContent = `${occPct}% occupied`;
  if (dLastUpdated) dLastUpdated.textContent = lot.last_updated || "—";

  if (pill) {
    pill.textContent = lot.status;
    pill.className = `status-pill ${pillClassForStatus(lot.status)}`;
  }

  if (bar) {
    bar.style.width = `${occPct}%`;
    bar.className = `detail-occ-bar-fill ${barClassForStatus(lot.status)}`;
  }

  const checkBtn = document.getElementById("d-checkin-btn");
  const navBtn = document.getElementById("d-nav-btn");
  const levelsBtn = document.getElementById("d-levels-btn");

  if (checkBtn) checkBtn.onclick = () => checkIn(lot.id);
  if (navBtn) navBtn.onclick = () => navigateTo(lot.lat, lot.lng);

  if (levelsBtn) {
    levelsBtn.style.display = lot.has_levels ? "inline-flex" : "none";
  }

  if (levelsVisible) {
    const levelsBody = document.getElementById("d-levels-body");
    renderLotLevels(lot.name, levelsBody);
  }
}

function selectLot(id) {
  activeLotId = id;
  const lot = parkingLots.find((l) => l.id === id);
  if (!lot) return;

  parkingLots.forEach((l) => {
    if (markers[l.id]) markers[l.id].setIcon(makeIcon(l.status, l.id === id));
  });

  if (typeof lot.lat === "number" && typeof lot.lng === "number") {
    map.flyTo([lot.lat, lot.lng], 17, { duration: 0.8 });
    if (markers[id]) markers[id].openPopup();
  }

  fillDetailPanelContent(lot);

  const detailOverlay = document.getElementById("detail-overlay");
  const analyticsOverlay = document.getElementById("analytics-overlay");

  if (detailOverlay) detailOverlay.classList.add("show");
  if (analyticsOverlay) analyticsOverlay.classList.remove("show");

  renderSidebarLots();
}

function closeDetail() {
  const detailOverlay = document.getElementById("detail-overlay");
  if (detailOverlay) detailOverlay.classList.remove("show");

  closeLevels();
  activeLotId = null;

  parkingLots.forEach((l) => {
    if (markers[l.id]) markers[l.id].setIcon(makeIcon(l.status, false));
  });

  renderSidebarLots();
}

function toggleLevels() {
  if (levelsVisible) closeLevels();
  else openLevels();
}

function openLevels() {
  const lot = activeLotId ? parkingLots.find((l) => l.id === activeLotId) : null;
  if (!lot || !lot.has_levels) return;

  const section = document.getElementById("d-levels-section");
  const body = document.getElementById("d-levels-body");
  const btn = document.getElementById("d-levels-btn");

  if (section) section.style.display = "block";
  if (btn) btn.textContent = "✕ Hide Levels";
  levelsVisible = true;

  renderLotLevels(lot.name, body);
}

function closeLevels() {
  const section = document.getElementById("d-levels-section");
  const body = document.getElementById("d-levels-body");
  const btn = document.getElementById("d-levels-btn");

  if (section) section.style.display = "none";
  if (body) body.innerHTML = "";
  if (btn) btn.textContent = "≡ Levels";
  levelsVisible = false;
}

async function checkIn(lotId) {
  const lot = parkingLots.find((l) => l.id === lotId);
  if (lot && lot.status === "Full") {
    alert("This lot is full.");
    return;
  }

  const res = await fetch("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lot_id: lotId }),
  });

  const data = await res.json();

  if (res.ok && data.status === "success") {
    alert(`✓ ${data.message}\n${data.available} spots remaining.`);
    await loadLots();
    selectLot(lotId);
  } else {
    alert(`Error: ${data.message || data.error || "Check-in failed"}`);
  }
}

function navigateTo(lat, lng) {
  window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`, "_blank");
}

function setActiveNav(btn) {
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
}

async function loadAnalyticsPanel() {
  const overlay = document.getElementById("analytics-overlay");
  const body = document.getElementById("analytics-body");
  const detailOverlay = document.getElementById("detail-overlay");

  if (detailOverlay) detailOverlay.classList.remove("show");
  if (overlay) overlay.classList.add("show");
  if (body) body.innerHTML = '<p class="muted">Loading...</p>';

  const res = await fetch("/api/analytics");

  if (res.status === 401) {
    if (body) body.innerHTML = '<p class="muted">Please <a href="/login">sign in</a> to view analytics.</p>';
    return;
  }

  const data = await res.json();

  if (!body) return;

  body.innerHTML = `
    <div class="analytics-grid" style="grid-template-columns:repeat(2,1fr);gap:0.5rem;margin-bottom:0.9rem">
      <div class="analytics-card"><label>Total Check-ins</label><span>${data.total_checkins ?? 0}</span></div>
      <div class="analytics-card"><label>Favorite Lot</label><span style="font-size:0.82rem">${data.favorite_lot ? data.favorite_lot.name : "—"}</span></div>
    </div>
    <div style="font-size:0.72rem;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5rem">Recent Check-ins</div>
    ${
      Array.isArray(data.recent_checkins) && data.recent_checkins.length
        ? data.recent_checkins
            .map(
              (c) => `
                <div class="history-item">
                  <div>
                    <div class="history-lot">${c.lot_name}</div>
                    <div class="history-time">${new Date(c.timestamp).toLocaleString()}</div>
                  </div>
                </div>
              `
            )
            .join("")
        : '<p class="muted">No check-ins yet.</p>'
    }
  `;
}

function openCheckinModal() {
  const modal = document.getElementById("modal");
  const modalLots = document.getElementById("modal-lots");

  if (!modal || !modalLots) return;

  modal.classList.add("show");
  modalLots.innerHTML = parkingLots
    .map(
      (lot) => `
        <div class="modal-lot ${lot.status === "Full" ? "disabled" : ""}">
          <div>
            <div class="modal-lot-name">${lot.name}</div>
            <div class="modal-lot-meta">${lot.status} · ${formatFreeLine(lot)}</div>
          </div>
          <button class="btn-sm btn-primary-sm"
                  ${lot.status === "Full" ? "disabled" : ""}
                  onclick="checkIn(${lot.id}); closeCheckinModal();">
            Check In
          </button>
        </div>
      `
    )
    .join("");
}

function closeCheckinModal() {
  const modal = document.getElementById("modal");
  if (modal) modal.classList.remove("show");
}

function maybeClose(e) {
  if (e.target.id === "modal") closeCheckinModal();
}

window.addEventListener("DOMContentLoaded", async () => {
  await loadLots();
  setInterval(loadLots, LIVE_REFRESH_MS);
});