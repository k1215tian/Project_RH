# excalidraw_for_odoo

Excalidraw whiteboard embedded as a **chatter tool for every record** in
Odoo 19 Community — a pencil button next to the paperclip, a drawing picker,
and a fullscreen editor. The vendored library (`@excalidraw/excalidraw`
0.18.1, MIT) plus its fonts are bundled inside the module with esbuild, so
the editor works fully offline and behind proxies — no external CDN is
contacted.

## Usage

1. Open any record that has a chatter and save it if it is new (the button
   only renders on saved records: drawings attach to a `res_id`).
2. Click the pencil button (**Add or edit a drawing…**) next to the
   paperclip in the chatter.
3. Pick an existing drawing or start a **New drawing** — the fullscreen
   editor opens.
4. Draw. Saves happen automatically:
   - 45 s after you stop editing (inactivity debounce),
   - at least every 60 s while the dialog is open (max-latency guard),
   - immediately when the dialog closes (close flush),
   - unchanged scenes are skipped (content hash — no redundant writes).

Opening an existing drawing from the picker resumes editing exactly where it
was left (the scene JSON is the source of truth), at any time, on any
chatter-capable record (partners, tasks, leads, …).

## Storage model

Each drawing is **two `ir.attachment` records** on the host record
(`res_model` / `res_id`):

- `<name>.excalidraw` — the scene JSON (`application/json`), the editable
  source of truth, round-trip compatible with `.excalidraw` files (import /
  export from the editor's own menu). **Internal:** stored with the
  `res_field = 'excalidraw_scene'` marker, which hides it from the chatter
  attachment list (Odoo treats field-marked attachments as internal). It is
  listed and read only through this module's gated routes, never directly.
- `<name>.png` (`res_field = False`) — a PNG render (`image/png`, exported at
  2× scale) so the drawing is visible in the chatter and anywhere attachments
  are shown.

Deleting either attachment is tolerated: the missing twin is regenerated on
the next changed save. Only a `.excalidraw` attachment can be reopened for
editing; a PNG alone is just the last render.

**Removing a drawing:** deleting attachments from the chatter removes the
PNG (the visible half) — the internal scene row persists, so the drawing
stays reopenable from the Excalidraw picker until a dedicated delete tool
ships (documented v1 trade-off). To fully remove a drawing today: delete the
PNG from the chatter, and the scene row manually as an admin (Developer
Tools → Attachments, filtered on `res_field = excalidraw_scene`).

**Concurrency:** concurrent editors of the same drawing are
**last-write-wins** — the last save overwrites both the scene and the PNG.
There is no locking or merge (by design, BR-CONC-1).

## Security

- *Excalidraw / User* — gates the chatter button and all JSON-RPC routes;
  members can create and edit drawings **only on records they can write**
  (the server re-checks access on every request; the button's client-side
  visibility check is a UX nicety, not the enforcement).
- *Excalidraw / Manager* — implies User; reserved for future manager-only
  capabilities (e.g. deleting drawings from the picker).

Groups use the Odoo 19 `res.groups.privilege` pattern and survived the
19.0.2.0.0 update unchanged.

## Breaking change — 19.0.2.0.0 (WIPE)

The standalone **Excalidraw** application (menus, views, and the
`excalidraw.drawing` model) was removed. Updating from 19.0.x to
**19.0.2.0.0**:

- deletes the model, its views, menus and ACLs from the registry
  (automatic on `-u`);
- does **not migrate** any standalone drawings — previously stored
  `excalidraw.drawing` rows are **permanently destroyed** (one-way wipe,
  accepted by design; there is no rollback once the update has run);
- keeps the security groups — they now gate the chatter tool.

### Deploy runbook (target databases)

Odoo 19 keeps the table of a removed model on upgrade (module tables are
only dropped at *uninstall*), so the registry cleanup alone leaves the old
table behind. On every target database, run the update first, then reclaim
the table explicitly:

```sql
DROP TABLE IF EXISTS excalidraw_drawing;
```

Alternatively, uninstall the module before updating — the destructive effect
on standalone drawings is identical. Either way, **back up the database
first** if the old drawings matter.

## Technical notes

- `static/lib/excalidraw/` contains the esbuild bundle
  (`excalidraw.vendor.js` + code-split chunks) plus the `fonts/` tree.
- The bundle is **not** registered in `web.assets_backend`; it is loaded
  through a native dynamic `import()` in
  `static/src/js/excalidraw_loader.js` so its relative chunk URLs resolve.
- Fonts resolve through `window.EXCALIDRAW_ASSET_PATH` pointing at the
  module static folder.
- The chatter button is an OWL patch of `mail.Chatter` (injected after the
  attach-files button); the picker and the editor are fullscreen OWL dialogs
  (`static/src/js/excalidraw_dialogs.js`).
- Three JSON-RPC controller routes (`/excalidraw/chatter/save`,
  `/excalidraw/chatter/scene` and `/excalidraw/chatter/list`) enforce, in
  order: group gate → chatter-capable-model gate → record-existence gate →
  write/read access — before anything is stored or returned.

Rebuilding the vendor bundle:

```bash
npm i @excalidraw/excalidraw@0.18.1 react@18.3.1 react-dom@18.3.1 esbuild
cat > excalidraw.vendor.js <<'JS'
export * from "@excalidraw/excalidraw";
export * as React from "react";
export * as ReactDOMClient from "react-dom/client";
JS
npx esbuild excalidraw.vendor.js --bundle --format=esm --minify --splitting \
  --target=es2020 --legal-comments=external --outdir=static/lib/excalidraw
cp node_modules/@excalidraw/excalidraw/dist/prod/fonts -R static/lib/excalidraw/fonts
cp node_modules/@excalidraw/excalidraw/dist/prod/index.css static/lib/excalidraw/excalidraw.css
```

## Licenses

- Module code: LGPL-3.
- Vendored assets: `@excalidraw/excalidraw` (MIT), `react` / `react-dom`
  (MIT) — notices kept in `static/lib/excalidraw/*.LEGAL.txt`,
  `LICENSE-excalidraw` and `LICENSE-react`.

## Roadmap

- Reopen a drawing by clicking its attachment in the chatter.
- Delete-drawing action in the picker (manager capability).
- Real-time multi-user collaboration (requires a collaboration backend).
