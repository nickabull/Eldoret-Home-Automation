# Eldoret visual baseline — LOCKED

**Approved visual reference:** the user's screenshot supplied in ChatGPT at **20 November 2026, 00:11 GMT**, showing the Bulldog / Heartbeats screen (four columns × four rows, 16 tiles). That screenshot, **not an inferred earlier Git commit**, is the authoritative appearance reference.

**Important:** The screenshot exists in the conversation and is not yet stored as a repository image. For reliable cross-chat restoration, add a copy to this repository or an enduring design-asset location, record its exact filename here, and verify it. Until then, the written specification below is a safeguard but not a pixel-perfect substitute for the screenshot.

## Non-negotiable rules

1. **Visual-only changes require express user authorisation.** Changes to readings, backend APIs, event capture or labels must not silently alter artwork, photography, image source, CSS background, cropping, colours, typography, spacing, layout, card order, icons, button styling or navigation.
2. **Maintain separate approved baselines** for:
   - Bulldog 800×480 Heartbeats: fixed 4×4, no scrolling, touch popup and Sky Q remote.
   - Main Eldoret dashboard: fixed landscape 16:9, no scrolling, explicit first tap/red outline/top-right CONFIRM, auto-cancel after approximately 10 seconds for potentially disruptive controls.
3. **Synch features, not skins:** for each changed integration, update the relevant data cards in Bulldog, main dashboard and detail pages together, using the same trusted backend fields. Do **not** force one display's design onto another.
4. **Keep existing artwork intact even if a remote image fails**; use only the approved pre-existing fallback. Do not introduce new stock images, external image overrides or replace a working image because it is easier to source.
5. **Verify before reporting success:** inspect source diff for unintended HTML/CSS/asset changes; check the display against the approved screenshot on the actual screen; confirm no scroll/overlap, live/stale semantics, controls and safety rule. Mark source committed separately from device verified.
6. **Rollback only the scoped regression:** do not revert functional data improvements or unrelated controls when fixing a visual regression.
7. **Record each accepted version** and a rollback commit / immutable tag for both surfaces only *after* the user visually confirms it on-device. A current repo SHA alone is NOT proof of a visual baseline.

## Appearance frozen from the 20 Nov 00:11 screenshot

- Dark navy background, teal outlines/heart icons, crisp white headlines and cyan-green live details; four columns by four rows at the Bulldog display's landscape dimensions.
- Row 1: Bulldog has the vivid illuminated home exterior; DrayTek router has blue-lit Ethernet patch-panel/rack art; House and Utility Hue both show the **same warm glowing Hue lamp/bridge photo**.
- Row 2: all four UniFi AP tiles use the **same blue-lit white ceiling-mounted round access-point photo**.
- Row 3: both dishwashers show **the same open dishwasher with dishes/racks**; both ovens show **the same lit oven with food**.
- Row 4: hob shows a **steaming pan on dark induction hob**; extractor shows a **lit cooker hood**; Sky Q uses **live programme imagery** when valid, with the established approved fallback; PS5 tile uses the dark illuminated-home photo.
- Readable category, AP/appliance title, event headline, metric line, animated heartbeat and a clock top right; footer last checks, fullscreen and refresh. All 16 remain visible without vertical or horizontal scrolling.

## Approved data changes without visual changes

- Per-AP connected clients from direct SNMPv3 when fresh; count unknown rather than fabricated when unavailable. Do not claim the UniFi controller's exact 'Excellent' label from an unrelated ping metric.
- Dishwasher actual active programme and locally decreasing remaining time when supported and fresh; clearly show unknown/unavailable when omitted. Read-only Home Connect remains read-only.
- Sky programme title and programme-image feed can change dynamically as programming changes. The *mechanism and card styling* remain locked.
- A proposed DrayTek sparkline, revised Hue aggregation, or any extra graphic affects the layout and therefore needs user-approved visual design first.

## Source / evidence at lock creation (not acceptance claims)

- Current `heartbeats.html` blob SHA read from GitHub: `b0494149b2170a9957328304580741e145e614a7`.
- Current `index.html` blob SHA read from GitHub: `3ac7e1c32339d92db4f5980dc650165c3bfb5d99`.
- **Warning:** Neither source SHA is declared 'visually verified' merely by recording it. The supplied screenshot may reflect different in-browser/cached artwork than these sources. Before any UI rollback, compare actual assets and screenshot. Do not assume a git revert is the same as restoring the user's approved design.

## Standard change request checklist

- [ ] State which surfaces will change and which must be unchanged.
- [ ] Freeze or compare relevant CSS / HTML / artwork assets against the visual reference.
- [ ] Confirm controller/data source and safe fallback/last-seen semantics.
- [ ] Implement narrow data change; do not opportunistically redesign.
- [ ] Inspect diff for artwork/CSS/layout changes.
- [ ] Test both Bulldog and main Eldoret in their intended screen sizes.
- [ ] Only then mark user accepted and update handover.

**Priority:** prevent regressions from chat-length rollovers. Read this lock together with `ELDORET-DONKEY-AIRLITE-PROJECT-HANDOVER.md` before future Eldoret UI edits.
