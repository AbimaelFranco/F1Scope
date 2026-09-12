/* Comparative telemetry charts for issue #15: reads the up-to-two
 * `drivers` selected on the session-selection page (#9) from the URL,
 * fetches each one's lap telemetry from /api/session/<key>/telemetry
 * (#14), and renders speed/throttle/brake/RPM/gear line charts with
 * Chart.js. Charts stay static for now — syncing a time cursor with the
 * 3D replay's playback clock is #16. */
import { Chart } from "chart.js";

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

  setStatus(
    series.map((s) => `${s.label} (vuelta ${s.telemetry.lap_number ?? "?"})`).join(" vs. ")
  );

  CHART_DEFS.forEach((def, index) => renderChart(def, series, index === 0));
}

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
  });
}

main();
