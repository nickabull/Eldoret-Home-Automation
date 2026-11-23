# Eldoret 2.12 artwork deployment (preview only)

The approved 11-image package is supplied in chat as `Eldoret-Artwork-v1.1.zip`. The existing real-house artwork is **not** included or replaced.

## Upload (once)

1. Unzip the package on your Mac/PC.
2. Open https://github.com/nickabull/Eldoret-Home-Automation and go to the repository **root**, not a subfolder.
3. Choose **Add file → Upload files**.
4. Drag in **only the 11 JPG files** named `eldoret-*.jpg` (do not upload the HTML preview, manifest, text file, or ZIP). Commit directly to `main`.
5. Confirm the files appear alongside `ipad12.html` and `eldoret-artwork-v1.css`.

## Preview

On Bulldog/iPad open `http://10.0.0.34:8765/ipad12.html` and refresh. The controller already registers `/ipad12.html` and the 11 image routes.

**Caution:** If any photo is missing, the preview may show a blank/dark panel. The working 2.11 remains `http://10.0.0.34:8765/ipad11.html`. Do not replace 2.11 until the user signs off the artwork.

The Home Summary panel intentionally uses the existing `/eldoret-house-night.webp` (artwork depicting the user's actual house), not the generic generated house photo.

## Visual QA

- All 12 cards must have subject-specific art.
- Check actual house image on Home Summary.
- Check 16:9 iPad no scrolling, text contrast, highlight dots, all equipment readouts, and filter alert.
- Once approved, reuse the same image paths on 4:3 detail pages.
