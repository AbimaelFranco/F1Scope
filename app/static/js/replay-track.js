/* Static 3D track view for issue #11: fetch the track shape from the
 * internal replay API (/api/session/<key>/track, cache-backed — see
 * app/routes/replay.py) and render it with Three.js. No cars/playback
 * yet — that's #12 (animate) and #13 (controls). */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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
  initScene(track.points);
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

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

main();
