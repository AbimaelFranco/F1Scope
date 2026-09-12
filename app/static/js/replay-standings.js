/* Live standings HUD for issue #17: fetches per-driver position/gap/
 * interval timeseries from /api/session/<key>/standings (cache-backed —
 * see app/routes/replay.py) and renders a table that updates as the 3D
 * replay's playback clock advances. Each row has a checkbox to show/hide
 * that driver's car in the 3D scene (setCarVisible, from replay-track.js
 * — same shared-module-instance trick used for `playback`). */
import { playback, setCarVisible } from "./replay-track.js";

const scriptEl = document.getElementById("replay-standings-script");
const sessionKey = scriptEl.dataset.sessionKey;
const panel = document.getElementById("standings-panel");
const status = document.getElementById("standings-status");
const tbody = document.getElementById("standings-body");

// One cursor per driver per field, advanced forward as simTime increases
// so a 60-row-ish table update doesn't rescan every series from scratch
// every tick. Reset to 0 whenever simTime moves backwards (scrub/loop).
const cursors = new Map(); // driver_number -> { position: 0, gap_to_leader: 0, interval: 0 }

function setStatus(text, { isError = false } = {}) {
  status.textContent = text;
  status.classList.toggle("error", isError);
}

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `HTTP ${response.status}`);
  }
  return response.json();
}

function latestValueAtOrBefore(series, cursorKey, cursorState, t) {
  if (!series.length) return null;

  if (t < series[cursorState[cursorKey]].t) {
    cursorState[cursorKey] = 0; // time moved backwards (scrub or loop)
  }
  while (
    cursorState[cursorKey] < series.length - 1 &&
    series[cursorState[cursorKey] + 1].t <= t
  ) {
    cursorState[cursorKey] += 1;
  }

  const point = series[cursorState[cursorKey]];
  return point.t <= t ? point.value : null; // nothing recorded yet at this time
}

function formatGap(value) {
  if (value == null) return "–";
  if (typeof value === "number") return `+${value.toFixed(3)}`;
  return String(value); // OpenF1 sometimes reports lapped cars as a string
}

async function main() {
  panel.hidden = false;
  setStatus("Cargando posiciones...");

  let payload;
  try {
    payload = await fetchJSON(`/api/session/${encodeURIComponent(sessionKey)}/standings`);
  } catch (err) {
    setStatus(`Error al cargar posiciones: ${err.message}`, { isError: true });
    console.error("F1Scope: failed to load standings", err);
    return;
  }

  const drivers = payload.drivers || [];
  if (!drivers.length) {
    setStatus("Sin datos de posiciones para esta sesión.", { isError: true });
    return;
  }

  setStatus(`${drivers.length} pilotos`);
  for (const driver of drivers) {
    cursors.set(driver.driver_number, { position: 0, gap_to_leader: 0, interval: 0 });
    tbody.appendChild(renderRow(driver));
  }

  setInterval(() => updateTable(drivers), 200);
}

function renderRow(driver) {
  const row = document.createElement("tr");
  row.id = `standings-row-${driver.driver_number}`;

  const visibilityCell = document.createElement("td");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = true;
  checkbox.setAttribute("aria-label", `Mostrar #${driver.driver_number} en el trazado 3D`);
  checkbox.addEventListener("change", () => {
    setCarVisible(driver.driver_number, checkbox.checked);
  });
  visibilityCell.appendChild(checkbox);

  const positionCell = document.createElement("td");
  positionCell.className = "standings-position";
  positionCell.textContent = "–";

  const driverCell = document.createElement("td");
  const swatch = document.createElement("span");
  swatch.className = "driver-swatch";
  swatch.style.backgroundColor = `#${driver.team_colour}`;
  driverCell.append(swatch, document.createTextNode(driver.name_acronym));

  const gapCell = document.createElement("td");
  gapCell.className = "standings-gap";

  const intervalCell = document.createElement("td");
  intervalCell.className = "standings-interval";

  row.append(visibilityCell, positionCell, driverCell, gapCell, intervalCell);
  return row;
}

function updateTable(drivers) {
  const simTime = playback.simTime;

  const rows = drivers.map((driver) => {
    const cursorState = cursors.get(driver.driver_number);
    return {
      driver,
      position: latestValueAtOrBefore(driver.position, "position", cursorState, simTime),
      gap: latestValueAtOrBefore(driver.gap_to_leader, "gap_to_leader", cursorState, simTime),
      interval: latestValueAtOrBefore(driver.interval, "interval", cursorState, simTime),
    };
  });

  // Drivers without a position yet (replay hasn't reached their first
  // record) sort to the bottom rather than before P1.
  rows.sort((a, b) => (a.position ?? Infinity) - (b.position ?? Infinity));

  for (const { driver, position, gap, interval } of rows) {
    const row = document.getElementById(`standings-row-${driver.driver_number}`);
    tbody.appendChild(row); // re-append in sorted order; no-op if already there
    row.querySelector(".standings-position").textContent = position ?? "–";
    row.querySelector(".standings-gap").textContent = position === 1 ? "–" : formatGap(gap);
    row.querySelector(".standings-interval").textContent = position === 1 ? "–" : formatGap(interval);
  }
}

main();
