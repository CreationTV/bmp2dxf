# Retro Workbench — design reference

This folder is the visual prototype for the retro “desktop software” version of
the bmp2dxf web workbench. It is intentionally self-contained (no network, no
build step) so the layout and styling can be reviewed in isolation.

- `home.html` — full-page prototype with the same three-column workspace used
  by the application.
- `tokens.css` — color, type, spacing, radius and grain tokens.
- `app.css` — the desktop surface and component styles.
- `assets/` — sample images and a vector preview produced by the real engine.

The production integration of this design lives in `bmp2dxf/web/static/` and
uses the real conversion API. The previous dark interface is kept as a
rollback reference in `bmp2dxf/web/legacy/`.
