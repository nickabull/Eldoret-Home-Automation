# Bulldog Design Centre — handover

## Goal
Replace repeated back-and-forth layout changes with a visual editor that lets the owner place and modify artwork and specify the data/actions needed for each UI element. ChatGPT implements/validates behaviour **without rearranging the approved design**. Based on workflow lessons from the Tiverton Town Programme Designer, but implemented independently for Eldoret.

## V1 committed 21 November 2026
- UI: `/design-centre.html` (GitHub files `design-centre.html`, `design-centre.js`).
- Screens: `wide` 1920×1080 (16:9); `ipad` 1024×768 (4:3); `pi` provisional 800×480. Actual Pi resolution to verify against hardware before final deployment.
- Independent draft for each `page` + `preset` combination (e.g. `pioneer-wide.json`).
- Editable text, buttons, panels, artwork by asset path; drag, resize, position and dimension fields, layer naming/order, duplicate, lock, undo/redo, colours, opacity, editable behaviour instructions.
- File export/import JSON, API save/load on Bulldog: GET/POST `/api/design-centre?name=pioneer&preset=wide`.
- Local persistence at `~/eldoret-connector/design-centre/<page>-<preset>.json`, atomic replace with restrictive file mode.
- POST requires same-origin `http://10.0.0.34:8765` (or local loopback), JSON, bounded payload, allowed page/preset, validated layers; no remote tunnel writes. GET blocked on remote tunnel too.
- Image URLs accepted only as same-origin static asset paths (e.g. `pioneer-bg.jpg`), not arbitrary external URLs or uploaded files. File upload/library browsing **not implemented yet**.
- **No publishing implementation yet**. Saving a design never edits a live device page. Hand-off uses exported JSON + layer behaviour text for human/assistant code integration and separate commit/verification.

## V2 planned
1. Searchable library of currently used artwork, thumbnails, upload/store/recover, and cross-page asset reuse. Avoid inline heavy image base64; originals stored durably and safely.
2. Resizable background images with opacity; snapping, guides, multi-selection and font catalogue including existing Eldoret/Tivvy typography.
3. Structured data binding for live widgets (status/number/image/interactive buttons) with a menu of allowlisted device actions and sources. Behaviour descriptions survive publish and remain human-readable.
4. Preview live-data placeholders in editor with realistic sample values; separate device control simulation to prevent accidental commands.
5. Publish pipeline: preview/diff, explicit approve, versioned commit, automatic backup and rollback, size-specific layout rendering; no blind overwrites.
6. Site-wide template/brand presets, exact existing artwork imports, page defaults, responsive output at Pi native dimensions.

## Safety requirements
- No arbitrary HTML/JS injection from design content; use textContent and validated fields.
- Never store API keys/secrets in design JSON.
- Keep SKY_PASSIVE_ISOLATION = True; no new background Sky Q polling.
- No Pioneer command polling; Pioneer fault still under investigation.
- Design editor must not use device commands except in separately implemented, confirmed live controls after explicit approval.

## First trial
Open `http://10.0.0.34:8765/design-centre.html`, select `pioneer` and `wide`, add a button and artwork, drag, edit Behaviour text, click Save draft on Bulldog. Reload and select Load saved draft; verify persistence. Repeat for iPad and Pi. The file can be exported as JSON. Live site unchanged.

## Known V1 limitations
- Pi dimensions provisional; no automatic measurement of Raspberry Pi display.
- No editor-managed binary upload, device data widgets or automated publish yet.
- Pointer manipulation and saving have been committed but **not yet tested live on Bulldog or across browsers**.

## V1.1 Tivvy-style toolbar — 21 November 2026
- Based on the actual `PROGRAMME-DESIGNER-V3-PLAN.md` in `nickabull/Tiverton-Town-Control-Centre`; migrated common controls, not all of the entire editor.
- Added layer-level bold, italic, underline, strikethrough, left/centre/right text alignment, font selection; selected formatting buttons highlighted gold.
- Added editable font-size and opacity sliders, zoom Fit/25–400%, canvas centring/alignment controls, layer lock toggle, arrow-key 1px nudging, Shift+arrow 10px nudging, Ctrl/Cmd+D duplicate, Delete remove.
- Existing draft JSON remains backwards-compatible; optional formatting fields validated server-side. Source JSON cannot run JavaScript.
- Not yet ported: rich text formatting of *individual words within one box*, multi-selection, snapping guides, native tables, stroke/outline, crop and protected artwork replacement, keyboard shortcuts for copy/paste, asset library, one-click publish. These require further work and separate tests.
- JS syntax compilation checked. Full browser/runtime verification remains pending.

## V1.2 — Tivvy visual workspace parity (21 November 2026, ~11:48)
- User supplied side-by-side screenshots showing Bulldog's poor canvas fit and Tivvy's preferred high-density editor. The required target is the actual Tivvy style: compact top toolbar, full central artwork preview, layers at left, precise inspector at right.
- Rebuilt editor into fixed-height three-column workspace, dark charcoal/yellow accent, with compact top text toolbar and layers before the add controls.
- Fixed **critical Fit zoom bug**: formerly 1920px-wide stage was CSS transformed but continued occupying 1920px layout width, so only the left side appeared with horizontal scroll. Now a stageholder is sized to the scaled dimensions so 16:9 fits within the viewport. Absolute layer coordinates remain full-resolution.
- Added sliders and +/- with matching number fields for X, Y, width, height, scale %, and rotation degrees; toggle layer visibility (including layer list), lock/unlock, snap-to-10px toggle, and gold/dashed selected layer outline. Snapping can be disabled for 1px precision.
- Duplicated bold/underline/strikethrough/text-alignment actions on top toolbar like Tivvy. Inspector still supports italic and font family.
- Backend `design_centre_validate` now accepts and bounds optional `hidden: bool`, `scale: 20..300`, and `rotation: -180..180`, preserving compatibility with old JSON.
- JS syntax and required element IDs verified through the connected repository tool. **Not yet verified in an actual live browser after Pi pulls these commits.** No existing saved drafts or live page publishing altered.
- Remaining gaps from Tivvy: word-level rich text spans, multi-selection, crop, fully searchable artwork library, asset upload, history/version restore, guided snap lines and preview/publish. Avoid claiming full parity yet.
