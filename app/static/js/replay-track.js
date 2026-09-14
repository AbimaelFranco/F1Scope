/* 3D track + car replay. #11 built the static track shape, #12 animated
 * the cars along it (fetched from /api/session/<key>/cars, cache-backed
 * — see app/routes/replay.py). This (#13) adds play/pause, a speed
 * control, and a time scrub bar on top of that same animation clock. */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const DEFAULT_PLAYBACK_SPEED = 20; // sim-seconds per real second

// OpenF1's elevation (z) is tiny next to the track's horizontal extent —
// on a real circuit like Bahrain, x/y span ~8,000-12,000 units while z
// only spans ~170, a ~1:50-70 ratio that renders as a visually flat line
// at 1:1 scale. Exaggerating just the vertical component is standard
// practice for terrain/track visualization at this kind of scale
// disparity.
//
// Caveat found via live validation: the per-sample z *noise* between
// different cars/laps is roughly the same order of magnitude as the
// elevation range itself — so exaggerating it doesn't just make the
// track's own elevation profile read better, it also amplifies small,
// ordinary z discrepancies between a car's raw telemetry and the "one
// lap" trace the track tube is built from, making cars visibly hover off
// the track surface at high values. There's no single "correct" value —
// it's a tradeoff between visible elevation and car/track alignment
// noise, so this is user-adjustable (see settings-panel) instead of a
// fixed constant. Default kept conservative for that reason.
const DEFAULT_VERTICAL_EXAGGERATION = 5;
const EXAGGERATION_STORAGE_KEY = "f1scope.verticalExaggeration";

let verticalExaggeration = readStoredExaggeration() ?? DEFAULT_VERTICAL_EXAGGERATION;

function readStoredExaggeration() {
  const raw = localStorage.getItem(EXAGGERATION_STORAGE_KEY);
  const value = raw != null ? Number(raw) : NaN;
  return Number.isFinite(value) && value > 0 ? value : null;
}

// OpenF1's (x, y) is the ground plane and z is elevation; Three.js is
// Y-up, so z maps to Y — scaled up by verticalExaggeration so real
// elevation changes read visually instead of the track looking flat.
// Shared by the track (initScene/rebuildGeometry) and the cars (loadCars)
// so both stay aligned to the same geometry.
function toSceneVector(p) {
  return new THREE.Vector3(p.x, p.z * verticalExaggeration, p.y);
}

const canvas = document.getElementById("replay-canvas");
const status = document.getElementById("replay-status");
const sessionKey = document.getElementById("replay-track-script").dataset.sessionKey;

// Shared playback state: the animate() loop and the control panel both
// read/write this, so a scrub-bar drag and the auto-advancing clock never
// fight each other (advancement pauses while playback.scrubbing is true).
export const playback = {
  simTime: 0,
  speed: DEFAULT_PLAYBACK_SPEED,
  playing: true,
  scrubbing: false,
};
let controlEls = null;

function setStatus(text, { isError = false } = {}) {
  status.textContent = text;
  status.classList.toggle("error", isError);
}

async function main() {
  setStatus("Cargando trazado...");

  let track;
  try {
    const response = await fetch(`/api/session/${encodeURIComponent(sessionKey)}/track`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.message || `HTTP ${response.status}`);
    }
    track = await response.json();
  } catch (err) {
    setStatus(`Error al cargar el trazado: ${err.message}`, { isError: true });
    console.error("F1Scope: failed to load track", err);
    return;
  }

  if (!track.points || track.points.length < 2) {
    setStatus("No hay suficientes datos de posición para este trazado.", { isError: true });
    return;
  }

  setStatus(`Trazado: ${track.points.length} puntos (piloto #${track.driver_number})`);
  const { scene, center, spacing } = initScene(track.points);
  loadCars(scene, center, spacing);
}

function averageSpacing(vectors) {
  let total = 0;
  for (let i = 1; i < vectors.length; i++) {
    total += vectors[i].distanceTo(vectors[i - 1]);
  }
  return total / (vectors.length - 1);
}

function initScene(points) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05070c);

  const camera = new THREE.PerspectiveCamera(
    60,
    window.innerWidth / window.innerHeight,
    1,
    1000000
  );

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(window.devicePixelRatio);

  const { center, spacing, geometry } = buildTrackGeometry(points);
  const material = new THREE.MeshStandardMaterial({
    color: 0x18e0ff,
    emissive: 0x083744,
    roughness: 0.4,
    metalness: 0.1,
  });
  const trackMesh = new THREE.Mesh(geometry, material);
  scene.add(trackMesh);

  sceneState.scene = scene;
  sceneState.trackMesh = trackMesh;
  sceneState.rawTrackPoints = points;
  sceneState.center.copy(center);

  const box = new THREE.Box3().setFromObject(trackMesh);
  const size = box.getSize(new THREE.Vector3()).length();

  const grid = new THREE.GridHelper(size * 1.5, 40, 0x1c2433, 0x12161f);
  scene.add(grid);

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(size, size, size);
  scene.add(dirLight);

  camera.position.set(0, size * 0.5, size * 0.5);
  camera.lookAt(0, 0, 0);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  const clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);
    controls.update();

    if (carState.maxT > 0) {
      const delta = clock.getDelta();
      if (playback.playing && !playback.scrubbing) {
        playback.simTime = (playback.simTime + delta * playback.speed) % carState.maxT;
      }
      updateCars(playback.simTime);
      updateControlsUI();
    }

    renderer.render(scene, camera);
  }
  animate();

  return { scene, center, spacing };
}

// Populated once /cars loads; the animate loop above reads carState.maxT
// every frame to know whether (and how) to advance the cars.
const carState = { cars: [], maxT: 0 };

// Populated in initScene; rebuildGeometry() (settings panel) reads these
// to redo the track/car transforms from the original raw data whenever
// verticalExaggeration changes, instead of needing a full page reload.
const sceneState = {
  scene: null,
  trackMesh: null,
  rawTrackPoints: null,
  center: new THREE.Vector3(),
};

// Shared by initScene (first build) and rebuildGeometry (settings panel):
// turns raw track points into re-centered scene vectors plus the tube
// geometry built from them, using the *current* verticalExaggeration.
function buildTrackGeometry(points) {
  const vectors = points.map(toSceneVector);

  const center = new THREE.Vector3();
  for (const v of vectors) center.add(v);
  center.divideScalar(vectors.length);
  for (const v of vectors) v.sub(center);

  const spacing = averageSpacing(vectors);
  const tubeRadius = Math.max(spacing * 0.4, 1);
  const curve = new THREE.CatmullRomCurve3(vectors, true);
  const geometry = new THREE.TubeGeometry(
    curve,
    Math.max(200, vectors.length),
    tubeRadius,
    8,
    true
  );

  return { center, spacing, geometry };
}

// Re-derives the track tube and every car's position series from their
// original raw API data, using whatever verticalExaggeration is current.
// Lets the settings panel's slider update the scene live instead of
// requiring a page reload.
function rebuildGeometry() {
  if (!sceneState.trackMesh || !sceneState.rawTrackPoints) return;

  const { center, geometry } = buildTrackGeometry(sceneState.rawTrackPoints);
  sceneState.trackMesh.geometry.dispose();
  sceneState.trackMesh.geometry = geometry;
  sceneState.center.copy(center);

  for (const car of carState.cars) {
    car.points = car.rawPoints.map((p) => ({
      t: p.t,
      pos: toSceneVector(p).sub(center),
    }));
    car.cursor = 0;
  }
  updateCars(playback.simTime);
}

// Lets the standings HUD (#17) show/hide a driver's car without knowing
// anything about carState's internals.
export function setCarVisible(driverNumber, visible) {
  const car = carState.cars.find((c) => String(c.driverNumber) === String(driverNumber));
  if (car) car.mesh.visible = visible;
}

async function loadCars(scene, center, spacing) {
  let payload;
  try {
    const response = await fetch(`/api/session/${encodeURIComponent(sessionKey)}/cars`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    payload = await response.json();
  } catch (err) {
    console.error("F1Scope: failed to load car positions", err);
    return;
  }

  const drivers = payload.drivers || [];
  if (!drivers.length) {
    console.warn("F1Scope: no car position data for this session");
    return;
  }

  const carRadius = Math.max(spacing * 1.5, 3);
  const geometry = new THREE.SphereGeometry(carRadius, 12, 12);

  let maxT = 0;
  for (const driver of drivers) {
    if (!driver.points.length) continue;

    const material = new THREE.MeshStandardMaterial({
      color: new THREE.Color(`#${driver.team_colour}`),
      emissive: new THREE.Color(`#${driver.team_colour}`),
      emissiveIntensity: 0.5,
    });
    const mesh = new THREE.Mesh(geometry, material);

    // Same toSceneVector mapping (+ exaggeration) and re-centering used
    // for the track itself, so cars line up with it. sceneState.center
    // (not the `center` argument) so this stays correct even if
    // rebuildGeometry() has already run once by the time cars load.
    const points = driver.points.map((p) => ({
      t: p.t,
      pos: toSceneVector(p).sub(sceneState.center),
    }));
    mesh.position.copy(points[0].pos);
    scene.add(mesh);

    carState.cars.push({
      driverNumber: driver.driver_number,
      points,
      mesh,
      cursor: 0,
      rawPoints: driver.points, // kept for rebuildGeometry() to redo the transform
    });
    maxT = Math.max(maxT, points[points.length - 1].t);
  }
  carState.maxT = maxT;

  const carCount = carState.cars.length;
  status.textContent += ` · ${carCount} auto${carCount === 1 ? "" : "s"} animándose`;

  setupControls();
  setupSettingsUI();
}

function setupControls() {
  const panel = document.getElementById("replay-controls");
  controlEls = {
    panel,
    playPauseBtn: document.getElementById("play-pause-btn"),
    scrub: document.getElementById("scrub"),
    timeDisplay: document.getElementById("time-display"),
    speedSelect: document.getElementById("speed-select"),
  };

  controlEls.scrub.max = String(carState.maxT);
  playback.speed = Number(controlEls.speedSelect.value);

  controlEls.playPauseBtn.addEventListener("click", () => {
    playback.playing = !playback.playing;
    controlEls.playPauseBtn.textContent = playback.playing ? "⏸" : "▶";
  });

  const stopScrubbing = () => {
    playback.scrubbing = false;
  };
  controlEls.scrub.addEventListener("pointerdown", () => {
    playback.scrubbing = true;
  });
  controlEls.scrub.addEventListener("pointerup", stopScrubbing);
  controlEls.scrub.addEventListener("pointercancel", stopScrubbing);
  controlEls.scrub.addEventListener("input", () => {
    playback.simTime = Number(controlEls.scrub.value);
    updateCars(playback.simTime);
    controlEls.timeDisplay.textContent = formatTimeRange(playback.simTime, carState.maxT);
  });

  controlEls.speedSelect.addEventListener("change", () => {
    playback.speed = Number(controlEls.speedSelect.value);
  });

  panel.hidden = false;
  updateControlsUI();
}

function setupSettingsUI() {
  const toggleBtn = document.getElementById("settings-toggle-btn");
  const panel = document.getElementById("settings-panel");
  const slider = document.getElementById("exaggeration-slider");
  const valueLabel = document.getElementById("exaggeration-value");

  slider.value = String(verticalExaggeration);
  valueLabel.textContent = `${verticalExaggeration}x`;

  toggleBtn.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
  });

  slider.addEventListener("input", () => {
    verticalExaggeration = Number(slider.value);
    valueLabel.textContent = `${verticalExaggeration}x`;
    localStorage.setItem(EXAGGERATION_STORAGE_KEY, String(verticalExaggeration));
    rebuildGeometry();
  });

  toggleBtn.hidden = false;
}

function updateControlsUI() {
  if (!controlEls || playback.scrubbing) return;
  controlEls.scrub.value = String(playback.simTime);
  controlEls.timeDisplay.textContent = formatTimeRange(playback.simTime, carState.maxT);
}

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${minutes}:${secs}` : `${minutes}:${secs}`;
}

function formatTimeRange(current, total) {
  return `${formatTime(current)} / ${formatTime(total)}`;
}

function updateCars(simTime) {
  for (const car of carState.cars) {
    const { points } = car;

    if (simTime < points[car.cursor].t) {
      car.cursor = 0; // playback looped back to the start
    }
    while (car.cursor < points.length - 2 && points[car.cursor + 1].t <= simTime) {
      car.cursor++;
    }

    const a = points[car.cursor];
    const b = points[Math.min(car.cursor + 1, points.length - 1)];
    const span = b.t - a.t || 1;
    const frac = Math.min(1, Math.max(0, (simTime - a.t) / span));
    car.mesh.position.lerpVectors(a.pos, b.pos, frac);
  }
}

main();
