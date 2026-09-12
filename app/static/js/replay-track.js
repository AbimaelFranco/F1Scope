/* 3D track + car replay. #11 built the static track shape, #12 animated
 * the cars along it (fetched from /api/session/<key>/cars, cache-backed
 * — see app/routes/replay.py). This (#13) adds play/pause, a speed
 * control, and a time scrub bar on top of that same animation clock. */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const DEFAULT_PLAYBACK_SPEED = 20; // sim-seconds per real second

const canvas = document.getElementById("replay-canvas");
const status = document.getElementById("replay-status");
const sessionKey = document.getElementById("replay-track-script").dataset.sessionKey;

// Shared playback state: the animate() loop and the control panel both
// read/write this, so a scrub-bar drag and the auto-advancing clock never
// fight each other (advancement pauses while playback.scrubbing is true).
const playback = { simTime: 0, speed: DEFAULT_PLAYBACK_SPEED, playing: true, scrubbing: false };
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

  // OpenF1's (x, y) is the ground plane and z is elevation (small
  // variance vs. x/y in real data); Three.js is Y-up, so z maps to Y.
  const vectors = points.map((p) => new THREE.Vector3(p.x, p.z, p.y));

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
  const material = new THREE.MeshStandardMaterial({
    color: 0x18e0ff,
    emissive: 0x083744,
    roughness: 0.4,
    metalness: 0.1,
  });
  const trackMesh = new THREE.Mesh(geometry, material);
  scene.add(trackMesh);

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

    // Same OpenF1 (x,y,z) -> Three.js (x,z,y) mapping and re-centering
    // used for the track itself, so cars line up with it.
    const points = driver.points.map((p) => ({
      t: p.t,
      pos: new THREE.Vector3(p.x, p.z, p.y).sub(center),
    }));
    mesh.position.copy(points[0].pos);
    scene.add(mesh);

    carState.cars.push({ driverNumber: driver.driver_number, points, mesh, cursor: 0 });
    maxT = Math.max(maxT, points[points.length - 1].t);
  }
  carState.maxT = maxT;

  const carCount = carState.cars.length;
  status.textContent += ` · ${carCount} auto${carCount === 1 ? "" : "s"} animándose`;

  setupControls();
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
