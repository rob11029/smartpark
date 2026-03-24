function badgeFromLevel(level) {
  const { available, total_spots, status_text } = level;

  if (available === null && String(status_text).toLowerCase() === "open") {
    return "Open";
  }
  if (available === 0 || String(status_text).toLowerCase() === "full") {
    return "Full";
  }
  if (typeof available === "number" && typeof total_spots === "number" && total_spots > 0) {
    const ratio = available / total_spots;
    if (ratio >= 0.5) return "Available";
    if (ratio >= 0.2) return "Busy";
    return "Almost Full";
  }
  return status_text || "Unknown";
}

function levelBadgeClass(label) {
  switch (label) {
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

function levelRowHtml(level) {
  const badge = badgeFromLevel(level);

  return `
    <div class="level-info">
      <div class="level-name">${level.level_name || ""}</div>
      <div class="level-total">Total Spots ${level.total_spots ?? ""}</div>
      <div class="level-updated">${level.last_updated || ""}</div>
    </div>
    <div class="level-status-wrap">
      <div class="level-status">${level.status_text || ""}</div>
      <div class="level-badge status-pill ${levelBadgeClass(badge)}">${badge}</div>
    </div>
  `;
}

function sameLevels(oldLevels, newLevels) {
  if (!Array.isArray(oldLevels) || !Array.isArray(newLevels)) return false;
  if (oldLevels.length !== newLevels.length) return false;

  for (let i = 0; i < oldLevels.length; i++) {
    const a = oldLevels[i];
    const b = newLevels[i];

    if (
      (a.level_name || "") !== (b.level_name || "") ||
      (a.total_spots ?? null) !== (b.total_spots ?? null) ||
      (a.available ?? null) !== (b.available ?? null) ||
      (a.status_text || "") !== (b.status_text || "") ||
      (a.last_updated || "") !== (b.last_updated || "")
    ) {
      return false;
    }
  }

  return true;
}

async function renderLotLevels(lotName, container) {
  if (!container) return;

  const wrapper = container.closest(".detail-overlay") || container;
  const savedScrollTop = wrapper.scrollTop;

  try {
    const res = await fetch(`/api/parking/levels/${encodeURIComponent(lotName)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    const newLevels = Array.isArray(data.levels) ? data.levels : [];

    if (!data.has_levels || newLevels.length === 0) {
      if (container.dataset.empty !== "true") {
        container.innerHTML = `<div class="no-levels">No level data available.</div>`;
        container.dataset.empty = "true";
        container.dataset.levelsJson = "[]";
      }
      wrapper.scrollTop = savedScrollTop;
      return;
    }

    const oldLevels = container.dataset.levelsJson
      ? JSON.parse(container.dataset.levelsJson)
      : null;

    if (sameLevels(oldLevels, newLevels)) {
      wrapper.scrollTop = savedScrollTop;
      return;
    }

    const existingRows = Array.from(container.querySelectorAll(".level-row"));

    newLevels.forEach((level, index) => {
      const html = levelRowHtml(level);

      if (existingRows[index]) {
        existingRows[index].innerHTML = html;
      } else {
        const row = document.createElement("div");
        row.className = "level-row";
        row.innerHTML = html;
        container.appendChild(row);
      }
    });

    if (existingRows.length > newLevels.length) {
      for (let i = newLevels.length; i < existingRows.length; i++) {
        existingRows[i].remove();
      }
    }

    container.dataset.empty = "false";
    container.dataset.levelsJson = JSON.stringify(newLevels);

    requestAnimationFrame(() => {
      wrapper.scrollTop = savedScrollTop;
    });
  } catch (err) {
    console.error("Failed to load levels:", err);

    if (!container.dataset.errorShown) {
      container.innerHTML = `<div class="no-levels">Failed to load level data.</div>`;
      container.dataset.errorShown = "true";
    }

    requestAnimationFrame(() => {
      wrapper.scrollTop = savedScrollTop;
    });
  }
}