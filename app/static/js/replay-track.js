/* 3D track + car replay. Issue #11 built the static track shape; this
 * (#12) adds the moving cars, fetched from /api/session/<key>/cars
 * (cache-backed — see app/routes/replay.py) and animated along their
 * real downsampled position-over-time data. Playback is a fixed
 * accelerated auto-loop for now — play/pause/speed/scrub controls land
 * in #13. */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const PLAYBACK_SPEED = 20; // sim-seconds per real second, until #13 adds a control for this

const canvas = document.getElementById("replay-canvas");
const status = document.getElementById("replay-status");
const sessionKey = document.getElementById("replay-track-script").dataset.sessionKey;

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
  let simTime = 0;

  function animate() {
    requestAnimationFrame(animate);
    controls.update();

    if (carState.maxT > 0) {
      simTime = (simTime + clock.getDelta() * PLAYBACK_SPEED) % carState.maxT;
      updateCars(simTime);
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
