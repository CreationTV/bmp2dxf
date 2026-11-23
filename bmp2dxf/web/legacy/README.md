# Legacy web interface

This folder keeps the previous dark blueprint web interface as a rollback
reference. The live server only serves `bmp2dxf/web/static/`, so these files
are not reachable from the application.

To restore the old layout, copy the three files back into
`bmp2dxf/web/static/` (the previous `static/` version is what was copied here
on 2026-11-23):

- `index.html`
- `style.css`
- `app.js`

The model and conversion API are unchanged; only the presentation layer and the
small DOM bridge in `app.js` differ.
