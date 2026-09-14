/* Live standings HUD. #17 built the position/gap/interval table (fetches
 * from /api/session/<key>/standings, cache-backed — see
 * app/routes/replay.py) that updates as the 3D replay's playback clock
 * advances, with a per-row checkbox to show/hide that driver's car in
 * the 3D scene (setCarVisible, from replay-track.js — same
 * shared-module-instance trick used for `playback`). This (#18) adds
 * "last lap" / "best lap" columns to the same table rather than a
 * second panel — see app/services/standings.py's module docstring for
 * why. */
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

// Previous tick's sorted driver_number order — only touch the DOM
// (tbody.appendChild, which *moves* a node even when it's a no-op
// positionally) when this actually changes. Position updates ~666 times
// across a whole race, so almost every 200ms tick doesn't need to reorder
// anything; doing it unconditionally was moving all 20 rows 5x/second,
// and appendChild-ing a row mid-click can cancel that click's own
// checkbox toggle — reproduced: ~23% of clicks silently failed to toggle.
let lastOrder = null;

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

function formatLapTime(seconds) {
  if (seconds == null) return "–";
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds % 60).toFixed(3).padStart(6, "0");
  return `${minutes}:${rest}`;
}

// Unlike latestValueAtOrBefore (one current value), this returns every lap
// *completed* at or before t — "best lap so far" needs the whole prefix,
// not just the latest entry. cursorState.laps tracks how many are done.
function lapsCompletedAtOrBefore(lapsSeries, cursorState, t) {
  if (!lapsSeries.length) return [];

  if (cursorState.laps > 0 && t < lapsSeries[cursorState.laps - 1].t) {
    cursorState.laps = 0; // time moved backwards (scrub or loop)
  }
  while (cursorState.laps < lapsSeries.length && lapsSeries[cursorState.laps].t <= t) {
    cursorState.laps += 1;
  }

  return lapsSeries.slice(0, cursorState.laps);
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
    cursors.set(driver.driver_number, { position: 0, gap_to_leader: 0, interval: 0, laps: 0 });
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

  const lastLapCell = document.createElement("td");
  lastLapCell.className = "standings-last-lap";

  const bestLapCell = document.createElement("td");
  bestLapCell.className = "standings-best-lap";

  row.append(
    visibilityCell,
    positionCell,
    driverCell,
    gapCell,
    intervalCell,
    lastLapCell,
    bestLapCell
  );
  return row;
}

function updateTable(drivers) {
  const simTime = playback.simTime;

  const rows = drivers.map((driver) => {
    const cursorState = cursors.get(driver.driver_number);
    const completedLaps = lapsCompletedAtOrBefore(driver.laps, cursorState, simTime);
    const lastLap = completedLaps.length ? completedLaps[completedLaps.length - 1] : null;
    const bestLap = completedLaps.reduce(
      (best, lap) => (best == null || lap.lap_duration < best ? lap.lap_duration : best),
      null
    );
    return {
      driver,
      position: latestValueAtOrBefore(driver.position, "position", cursorState, simTime),
      gap: latestValueAtOrBefore(driver.gap_to_leader, "gap_to_leader", cursorState, simTime),
      interval: latestValueAtOrBefore(driver.interval, "interval", cursorState, simTime),
      lastLap: lastLap ? lastLap.lap_duration : null,
      bestLap,
    };
  });

  // Drivers without a position yet (replay hasn't reached their first
  // record) sort to the bottom rather than before P1.
  rows.sort((a, b) => (a.position ?? Infinity) - (b.position ?? Infinity));

  const newOrder = rows.map(({ driver }) => driver.driver_number);
  const orderChanged =
    !lastOrder ||
    newOrder.length !== lastOrder.length ||
    newOrder.some((number, i) => number !== lastOrder[i]);
  if (orderChanged) lastOrder = newOrder;

  for (const { driver, position, gap, interval, lastLap, bestLap } of rows) {
    const row = document.getElementById(`standings-row-${driver.driver_number}`);
    if (orderChanged) tbody.appendChild(row); // moves the node — only when order truly changed
    row.querySelector(".standings-position").textContent = position ?? "–";
    row.querySelector(".standings-gap").textContent = position === 1 ? "–" : formatGap(gap);
    row.querySelector(".standings-interval").textContent = position === 1 ? "–" : formatGap(interval);
    row.querySelector(".standings-last-lap").textContent = formatLapTime(lastLap);
    row.querySelector(".standings-best-lap").textContent = formatLapTime(bestLap);
  }
}

main();
