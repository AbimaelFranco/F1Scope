# Vendored third-party JS

Self-hosted rather than loaded from a CDN, so F1Scope stays a self-contained
Docker image with no external JS dependency at runtime.

| File | Package | Version | License |
|---|---|---|---|
| `three.module.js` | [three](https://www.npmjs.com/package/three) | 0.186.0 | MIT (see `LICENSE`) |
| `three.core.js` | `three/build/three.core.js` | 0.186.0 | MIT (see `LICENSE`) |
| `OrbitControls.js` | `three/examples/jsm/controls/OrbitControls.js` | 0.186.0 | MIT (see `LICENSE`) |

Since three.js 0.17x, `three.module.js` is a thin re-export that itself imports
everything from `three.core.js` (self-contained, no further sibling imports) — both
files are required, not just the one named "three.module.js".

Fetched from unpkg (`https://unpkg.com/three@0.186.0/...`). To upgrade, re-download
all three files at a newer version, re-check `three.module.js` still only depends on
`three.core.js` (`grep "from '\./" three.module.js`), and that `OrbitControls.js`'s
bare `from "three"` import still resolves via the import map in
`app/templates/replay.html`.
