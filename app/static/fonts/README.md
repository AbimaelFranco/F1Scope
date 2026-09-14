# Vendored fonts

Self-hosted rather than loaded from Google Fonts' CDN, for the same reason as
`app/static/js/vendor/`: F1Scope stays a self-contained Docker image with no
external dependency at runtime (and no third-party request leaking the
viewer's IP on every page load).

| File | Family | Weight(s) | License |
|---|---|---|---|
| `orbitron-variable.woff2` | [Orbitron](https://fonts.google.com/specimen/Orbitron) | variable (400–900) | OFL 1.1 (see `orbitron-OFL.txt`) |
| `share-tech-mono-regular.woff2` | [Share Tech Mono](https://fonts.google.com/specimen/Share+Tech+Mono) | 400 | OFL 1.1 (see `share-tech-mono-OFL.txt`) |

Used by the design system (`app/static/css/theme.css`): Orbitron for
headings/labels/numeric HUD readouts (angular, technical display face),
Share Tech Mono for body copy and tabular data (telemetry values, lap
times) where a monospace face keeps digits aligned.

Fetched from `fonts.gstatic.com` (the URLs Google Fonts' CSS API resolves
to for the `latin` subset). To upgrade or add a weight: fetch
`https://fonts.googleapis.com/css2?family=<Family>:wght@<weights>` with a
browser-like `User-Agent` (plain `curl` without one gets served legacy TTF,
not woff2), copy the resulting `src: url(...)` file(s) here, and update
`theme.css`'s `@font-face` rules to match.
