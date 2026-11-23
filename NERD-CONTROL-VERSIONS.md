# Eldoret Nerd Central — version and stable-address policy

## One permanent user-facing address
- **http://10.0.0.34:8765/nerd-control.html** is the permanent iPad Home Screen URL.
- The Python `connector.py` static route maps that exact URL to the current approved **versioned file**. As of 23 November 2026, the mapping is `ipad14.html` — screen title **NERD CENTRAL 2.14**.
- Do not rename the stable URL; do not make users change their bookmark when a new release is approved.
- Device pages (starting with `ariya-ipad.html`) must link Home to `nerd-control.html`, not `index.html` or a specific `ipadXX.html`.

## Immutable archive and release workflow
1. Prototype a new version in its own file, e.g. `ipad15.html`, leaving `ipad14.html` untouched.
2. Make its on-screen header explicitly say **NERD CENTRAL 2.15** (not the previous version). Test real data, page navigation and iPad no-scroll layout.
3. When the user approves, change only the stable route in `connector.py` from `("ipad14.html", ...)` to `("ipad15.html", ...)`, then deploy/restart and verify.
4. Never overwrite an archived `ipadXX.html` once promoted. On regressions roll back the single route mapping. Preserve previous versions and live integrations.
5. The main version label is the existing top-left `ELDORET / NERD CENTRAL 2.14` header. The stable address is independent of this label.

## Archive inventory (source files)
- `ipad11.html` — last working 2.11 baseline
- `ipad12.html` — artwork 2.12 preview
- `ipad13.html` — double-height TV and Appliances 2.13
- `ipad14.html` — latest 2.14 acceptance layout, first Ariya full-tile link and manually safe Sky Q status
- `ariya-ipad.html` — first dedicated 4:3 control page; climate default 25°C and select/confirm workflow

## Operational caveat
Source commits do **not** prove the Bulldog installation has been updated. The operator must deploy new source files and restart `eldoret.service`. Last confirmed Home Connect reading at ~14:39 was `cloud_http_429` with one-hour cooldown and no last-good snapshot yet; do not claim six Home Connect appliances are live until an actual response succeeds. Sky Q passive polling remains deliberately isolated.
