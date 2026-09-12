# F1Scope — Planificación (Etapa 0)

> Estado: **Aprobado** por Abimael Franco el 2026-09-10.

## 1. Visión y objetivo

**F1Scope**: visualizador web de telemetría histórica de F1, que reconstruye una carrera en
una escena 3D (trazado + monoplazas moviéndose según su posición real) y permite analizar
telemetría (velocidad, acelerador, freno, RPM, marcha) comparando pilotos, con una estética
cyberpunk/HUD. Datos desde la API gratuita de [OpenF1](https://openf1.org/).

## 2. Realidad de la fuente de datos (condiciona la arquitectura)

- **Tier gratuito**: 18 endpoints, sin autenticación, datos históricos **desde 2023**,
  formatos JSON/CSV.
- **Rate limit gratuito**: 3 req/s y **30 req/min**.
- **Sin datos en vivo** en el tier gratuito (solo tier de pago, €9.90/mes). F1Scope v1 es un
  **replay de carreras históricas**, no live timing.
- Endpoints clave: `sessions` / `meetings` (elegir carrera), `drivers`, `location` (x,y,z
  para el trazado 3D y posición del auto), `car_data` (velocidad/throttle/brake/rpm/gear a
  3.7Hz), `laps`, `position`, `intervals`, `pit`, `stints`, `race_control`, `weather`,
  `team_radio`.
- **Decisión confirmada por el usuario**: los endpoints se pueden descargar en volumen (una
  descarga completa por sesión al seleccionarla) sin necesidad de superar el límite
  gratuito, siempre que se respete el rate limit al hacer la ingesta inicial. No se
  necesita polling continuo ni tier de pago para v1.
- **Consecuencia de diseño**: arquitectura con **capa de ingesta/caché**. Al seleccionar una
  sesión, el backend descarga y guarda localmente los datos necesarios una sola vez; el
  replay y los gráficos consumen esa copia local, no vuelven a golpear OpenF1 en cada frame.
- Volumen: `location`/`car_data` a 3.7 Hz para ~20 pilotos durante una sesión completa
  genera cientos de miles de filas por sesión → caché liviana en disco (SQLite o
  archivos JSON/Parquet locales) en vez de mantenerlo todo en memoria.

## 3. Alcance

### Dentro de alcance – v1 (MVP)
- Selección de temporada → meeting → sesión (`sessions`/`meetings`/`drivers`).
- Descarga y cacheo local de los datos de una sesión seleccionada.
- Replay del trazado en escena 3D (Three.js) usando `location` (x,y,z), con controles de
  reproducción: play/pause, velocidad, scrub por tiempo.
- HUD con posiciones, gaps/intervalos y vueltas en vivo durante el replay (`position`,
  `intervals`, `laps`).
- Módulo de telemetría: comparar 2 pilotos (velocidad, throttle, brake, RPM, marcha) a lo
  largo de **toda la carrera** (revisado 2026-09-12, ver sección 10 — originalmente decía
  "en una vuelta"), con gráficos sincronizados al replay.
- Estética cyberpunk/HUD (tema neón, tipografía técnica, paneles tipo consola).
- Empaquetado en Docker (Dockerfile + docker-compose), ejecutable con un comando.

### Dentro de alcance – v2 (backlog futuro, no bloquea v1)
- Pit stops y stints de neumáticos en el HUD.
- Race control (banderas, safety car) como eventos sobre la línea de tiempo.
- Clima (`weather`) como overlay.
- Team radio (reproducción de audio).
- Comparación de más de 2 pilotos / más variables.
- Modelos 3D de autos más detallados, cámaras tipo onboard/persecución.
- Caché con Redis si el volumen lo justifica.
- CI/CD (GitHub Actions) para tests y build de imagen Docker.

### Fuera de alcance (explícito)
- Datos en vivo / live timing (tier de pago de OpenF1; no es parte de este proyecto).
- Autenticación de usuarios / multiusuario / persistencia remota de preferencias.
- Predicciones o modelos de machine learning sobre rendimiento.
- Optimización para móvil (se apunta a escritorio).

## 4. Arquitectura de alto nivel

- **Backend – Flask**: sirve la app web (Jinja2 + estáticos) y expone una API interna
  (`/api/...`) que el frontend consume para pedir datos ya cacheados.
- **Capa de integración OpenF1**: cliente HTTP con manejo de rate-limit/backoff, y una capa
  de caché local (SQLite o archivos por sesión) que persiste lo descargado.
- **Frontend**:
  - Three.js para la reconstrucción 3D del trazado y el movimiento de los autos.
  - Librería de gráficos (Chart.js o Plotly) para telemetría, sincronizada por timestamp
    con el replay.
  - Tema visual cyberpunk (CSS custom, paneles HUD).
- **Docker**: Dockerfile de la app Flask + `docker-compose.yml`; volumen para persistir la
  caché de sesiones descargadas entre reinicios.

> El detalle visual de esta arquitectura vive en el diagrama generado con `/archify`:
> [`docs/architecture/f1scope-architecture.html`](architecture/f1scope-architecture.html)
> (fuente editable: `docs/architecture/f1scope-architecture.json`).

## 5. Estructura de repositorio propuesta

```
F1Scope/
├── app/
│   ├── routes/          # Blueprints: vistas + API interna
│   ├── services/         # Cliente OpenF1, caché, transformaciones de datos
│   ├── models/            # Estructuras/esquemas de datos internos
│   ├── static/            # JS (three.js, charts), CSS (tema cyberpunk)
│   └── templates/         # Jinja2
├── tests/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/                  # Diagramas (salida de archify), notas de la API
├── .claude/skills/commit/ # Skill local de commits estandarizados
├── requirements.txt
├── .env.example
├── DESCRIPTION.MD
└── README.md
```

## 6. Backlog por épicas (candidatas a Milestones en GitHub)

| # | Épica | Resumen |
|---|-------|---------|
| E1 | Fundamentos del proyecto | Esqueleto Flask, configuración, logging, estructura de carpetas |
| E2 | Integración OpenF1 + caché | Cliente API, manejo de rate limit, ingesta/caché local por sesión |
| E3 | Selección de sesión/carrera | UI para elegir temporada/meeting/sesión/pilotos |
| E4 | Replay 3D del circuito | Escena Three.js, trazado desde `location`, animación de autos, controles de reproducción |
| E5 | Análisis de telemetría | Gráficos comparativos sincronizados (velocidad, throttle, brake, RPM, marcha) |
| E6 | HUD de carrera | Posiciones, gaps, vueltas (y en v2: pits, stints, banderas, clima) |
| E7 | Identidad visual cyberpunk | Sistema de diseño, tema neón, componentes HUD reutilizables |
| E8 | Dockerización y empaquetado | Dockerfile, docker-compose, documentación de despliegue |
| E9 | Calidad y pruebas | Tests unitarios de la capa de datos, pruebas de integración de la API interna |

## 7. Requisitos no funcionales
- Respetar el rate limit gratuito de OpenF1 (3 req/s, 30 req/min) durante la ingesta.
- Replay fluido gracias a datos precargados (no depende de la latencia de red durante la
  reproducción).
- Portabilidad total vía Docker (`docker-compose up` y listo).
- Sin secretos obligatorios en v1 (OpenF1 free tier no requiere API key).

## 8. Pendiente antes de la etapa de issues
El CLI `gh` no está instalado/autenticado en este entorno; se necesitará para crear
milestones/issues desde aquí. Se resuelve al llegar a ese paso.

## 9. Definición de "hecho" de la Etapa 0
1. ✅ Skill de commits local creada (`.claude/skills/commit/SKILL.md`).
2. ✅ Plan aprobado.
3. ✅ Diagrama de arquitectura con `/archify` (`docs/architecture/f1scope-architecture.html`).
4. ✅ Milestones (E1–E9) + 26 issues creados en GitHub: https://github.com/AbimaelFranco/F1Scope/milestones

## 10. Revisiones post-validación

Con E1–E5 mergeados y el servidor corriendo en vivo, el usuario validó la app real y pidió
tres ajustes no contemplados en el alcance original. Se documentan aquí en vez de reescribir
la historia de las secciones anteriores, y quedan trackeados en un milestone nuevo
(`Refinamientos — feedback de validación en vivo`) en vez de reabrir milestones ya cerrados:

- **Telemetría de carrera completa, no solo una vuelta** (issue #47). Revierte la decisión
  original de la sección 3 ("en una vuelta"). Implica rediseñar el eje de tiempo de los
  gráficos (probablemente a tiempo global de sesión, lo que además simplifica el cursor
  sincronizado del issue #16) y aplicar downsampling al volumen resultante.
- **Checkboxes de visibilidad por piloto en el panel de posiciones** (agregado al issue #17,
  milestone E6, aún sin iniciar): mostrar/ocultar el auto de cada piloto en el replay 3D,
  independiente del límite de 2 pilotos para comparar telemetría.
- **Exagerar el eje de elevación del trazado 3D** (issue #48): el mapeo 1:1 de la elevación
  real (z de OpenF1) hace que el circuito se vea casi plano; se necesita un multiplicador de
  exageración vertical calibrable.
