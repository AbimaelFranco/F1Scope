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

| File | Package | Version | License |
|---|---|---|---|
| `chart.auto.js` | `chart.js/auto` | 4.5.1 | MIT (see `chart.js-LICENSE`) |
| `chart.js` | [chart.js](https://www.npmjs.com/package/chart.js) | 4.5.1 | MIT (same license) |
| `chunks/helpers.dataset.js` | `chart.js/dist/chunks/helpers.dataset.js` | 4.5.1 | MIT (same license) |
| `kurkle-color.esm.js` | [@kurkle/color](https://www.npmjs.com/package/@kurkle/color) | 0.5.1 | MIT (see `kurkle-color-LICENSE`) |

The import map maps bare specifier `"chart.js"` to **`chart.auto.js`**, not `chart.js`
directly — `chart.auto.js` is `chart.js/auto`'s entry (registerables auto-registered)
with its own import rewritten from the package's `../dist/chart.js` to the flat local
`./chart.js`, since nothing here preserves the original `dist/`/`auto/` folder split.
`chart.js` itself imports its `chunks/helpers.dataset.js` chunk via a **relative**
path, so that one resolves on its own as long as the two stay in the same relative
layout — no import map entry needed for it. It also imports the bare specifier
`@kurkle/color`, which does need an import map entry pointing at
`kurkle-color.esm.js`. Both entries live in `app/templates/replay.html`. To upgrade:
re-download `chart.js` + `chunks/helpers.dataset.js` + `@kurkle/color`'s ESM build at
newer versions, regenerate `chart.auto.js` from the package's `auto/auto.js` (rewrite
its `../dist/chart.js` import to `./chart.js`), and re-check the import shapes still
hold (`grep "^import" chart.js chunks/helpers.dataset.js`).
