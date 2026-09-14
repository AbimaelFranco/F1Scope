/* Comparative telemetry charts. #15 built the charts: reads the up-to-two
 * `drivers` selected on the session-selection page (#9) from the URL,
 * fetches each one's telemetry from /api/session/<key>/telemetry (#14),
 * and renders speed/throttle/brake/RPM/gear line charts with Chart.js.
 * #16 added a time cursor synced to the 3D replay's session-wide
 * playback clock (`playback.simTime`, shared via import from
 * replay-track.js — both script tags load the same module instance, so
 * they read/write the same object).
 *
 * #47 (live-validation feedback) switched the default from one lap to
 * the whole session, with `t` already relative to the same session-wide
 * origin `playback.simTime` uses — which simplified the cursor down to a
 * single shared vertical line (no more per-driver lap_start_offset
 * conversion, since both drivers' charts now live in the same time
 * domain as the replay clock). */
import { Chart } from "chart.js";
import { playback } from "./replay-track.js";

const CHART_DEFS = [
  { key: "speed", canvasId: "chart-speed", label: "Velocidad (km/h)" },
  { key: "throttle", canvasId: "chart-throttle", label: "Acelerador (%)" },
  { key: "brake", canvasId: "chart-brake", label: "Freno (%)" },
  { key: "rpm", canvasId: "chart-rpm", label: "RPM" },
  { key: "n_gear", canvasId: "chart-gear", label: "Marcha" },
];

const AXIS_COLOR = "#8ea0bf";
const GRID_COLOR = "#1c2433";
const TEXT_COLOR = "#e6f1ff";

const scriptEl = document.getElementById("replay-telemetry-script");
const sessionKey = scriptEl.dataset.sessionKey;
const panel = document.getElementById("telemetry-panel");
const status = document.getElementById("telemetry-status");

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

async function main() {
  const params = new URLSearchParams(window.location.search);
  const driverNumbers = (params.get("drivers") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 2);

  if (driverNumbers.length < 2) {
    return; // nothing to compare — panel stays hidden
  }

  panel.hidden = false;
  setStatus("Cargando telemetría...");

  let driversInfo;
  let telemetryByDriver;
  try {
    const allDrivers = await fetchJSON(
      `/api/drivers?session_key=${encodeURIComponent(sessionKey)}`
    );
    driversInfo = new Map(allDrivers.map((driver) => [String(driver.driver_number), driver]));

    telemetryByDriver = await Promise.all(
      driverNumbers.map((number) =>
        fetchJSON(
          `/api/session/${encodeURIComponent(sessionKey)}/telemetry?driver_number=${encodeURIComponent(number)}`
        )
      )
    );
  } catch (err) {
    setStatus(`Error al cargar telemetría: ${err.message}`, { isError: true });
    console.error("F1Scope: failed to load telemetry", err);
    return;
  }

  const series = driverNumbers.map((number, index) => {
    const info = driversInfo.get(number) || {};
    return {
      label: info.name_acronym || `#${number}`,
      color: `#${info.team_colour || "888888"}`,
      telemetry: telemetryByDriver[index],
    };
  });

  const anyLapScoped = series.some((s) => s.telemetry.lap_number != null);
  const names = series
    .map((s) =>
      s.telemetry.lap_number != null ? `${s.label} (vuelta ${s.telemetry.lap_number})` : s.label
    )
    .join(" vs. ");
  setStatus(anyLapScoped ? names : `${names} — carrera completa`);

  const charts = CHART_DEFS.map((def, index) => renderChart(def, series, index === 0));
  startCursorLoop(charts);
}

// One shared vertical line at the 3D replay's current session-wide time.
// Both drivers' points already live in that same time domain (#47), so —
// unlike before #47, when each lap had its own local origin — this no
// longer needs to know anything about which series it's drawing over.
const SYNC_CURSOR_PLUGIN = {
  id: "syncCursor",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    const t = playback.simTime;
    if (t < scales.x.min || t > scales.x.max) return;

    const pixelX = scales.x.getPixelForValue(t);
    ctx.save();
    ctx.strokeStyle = "#ffb020";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(pixelX, chartArea.top);
    ctx.lineTo(pixelX, chartArea.bottom);
    ctx.stroke();
    ctx.restore();
  },
};

function renderChart(def, series, showLegend) {
  const canvas = document.getElementById(def.canvasId);
  return new Chart(canvas, {
    type: "line",
    data: {
      datasets: series.map((s) => ({
        label: s.label,
        borderColor: s.color,
        backgroundColor: s.color,
        data: s.telemetry.points.map((p) => ({ x: p.t, y: p[def.key] })),
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.15,
      })),
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      scales: {
        x: {
          type: "linear",
          ticks: { color: AXIS_COLOR, maxTicksLimit: 6 },
          grid: { color: GRID_COLOR },
        },
        y: {
          ticks: { color: AXIS_COLOR },
          grid: { color: GRID_COLOR },
        },
      },
      plugins: {
        title: { display: true, text: def.label, color: TEXT_COLOR, font: { size: 12 } },
        legend: { display: showLegend, labels: { color: TEXT_COLOR, boxWidth: 12 } },
      },
    },
    plugins: [SYNC_CURSOR_PLUGIN],
  });
}

// Redraws (no animation, no data re-parse) at a modest cadence so the sync
// cursor visibly tracks the replay clock without competing with the WebGL
// scene's own 60fps render loop for CPU.
function startCursorLoop(charts) {
  setInterval(() => {
    for (const chart of charts) chart.update("none");
  }, 100);
}

main();
