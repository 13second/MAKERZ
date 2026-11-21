# MAKERZ Code Review Report

This document summarizes the static analysis, security audit, bug fixes, and documentation improvements performed across the entire **MAKERZ** repository (`makerz-studio`, `IU-MIC_ORIGIN`, and `SPIRIT-IP_LDC`).

---

## Summary of Findings & Applied Fixes

### 1. Security — Path Traversal Hardening (`makerz-studio/server.mjs`)
- **Issue:** File-serving routes checked `resolved.startsWith(MAKERZ_ROOT)` and `staticPath.startsWith(PUBLIC_DIR)` without a trailing path separator, allowing sibling-directory prefix bypasses (e.g., `/MAKERZ_other`). Additionally, `decodeURIComponent(url.pathname)` was unguarded and could throw a `URIError` on malformed URLs.
- **Fix:** Added an `isPathInside(baseDir, targetPath)` helper enforcing `target === base || target.startsWith(base + path.sep)` with `path.resolve()`, and wrapped URL decoding in a `try/catch` returning HTTP `400 Bad Request`.

### 2. Security — Request Body Size Limit (`makerz-studio/server.mjs`)
- **Issue:** `readBody(req)` buffered incoming POST payloads indefinitely without a size limit or error listener.
- **Fix:** Added a 1 MiB (`MAX_BODY_BYTES`) guard returning HTTP `413 Payload Too Large` and handled stream errors cleanly.

### 3. Security — DOM XSS Prevention (`makerz-studio/public/app.js`)
- **Issue:** Project metadata (`name`, `subtitle`, `specs`), 3D part labels, and BOM CSV cells were interpolated directly into `innerHTML`.
- **Fix:** Added `escapeHtml()` and applied it to every dynamic value injected into HTML templates, alongside `encodeURI()` / `encodeURIComponent()` on dynamic URLs.

### 4. Bug — Header-Aware BOM CSV Parsing (`makerz-studio/public/app.js`)
- **Issue:** `renderBomTable()` indexed BOM columns by hardcoded positions (`r[0]`..`r[9]`) matching `IU-MIC_ORIGIN/hardware/bom_lcsc.csv`. Because `SPIRIT-IP_LDC/hardware/bom_lcsc.csv` uses a different column order (`Designator, Board, Comment, MPN, ...`), columns rendered misaligned and unit prices evaluated to `€ 0,00`.
- **Fix:** Added `parseBomCsv()` to map columns dynamically by header name, ensuring both projects display accurate BOM fields and EUR totals.

### 5. Bug — Three.js GPU Memory Leak & Exploded View Coverage (`makerz-studio/public/app.js`)
- **Issue:** Switching projects removed meshes from the Three.js scene without calling `.dispose()` on geometries/materials. In addition, `explodeOffsets` only mapped `IU-MIC_ORIGIN` part IDs, leaving `SPIRIT-IP_LDC` parts stationary when dragging the explode slider.
- **Fix:** Added `disposeGroup()` to release GPU resources on project switch and added axial explode offsets for all `SPIRIT-IP_LDC` parts.

### 6. Bug — On-Demand ECAD Regeneration for Multi-Project Support (`makerz-studio/server.mjs`)
- **Issue:** `POST /api/projects/:id/export-gerbers` only looked for `hardware/generate_ecad.py`, returning 404 for `SPIRIT-IP_LDC` (`spirit_build.py`).
- **Fix:** Extended script lookup to check `generate_ecad.py`, `spirit_build.py`, and `stage1_sync_build.py` in order.

### 7. Portability — Removal of Hardcoded User Home Paths
- **Issue:** Absolute user-specific paths (`/Users/simonegaudimonte/...`) and hardcoded KiCad paths were present in `makerz-studio/server.mjs`, `SPIRIT-IP_LDC/hardware/spirit_autoroute.py`, `IU-MIC_ORIGIN/hardware/t4_build_kicad_sch.py`, and `IU-MIC_ORIGIN/hardware/t5_build_kicad_pcb.py`.
- **Fix:** Replaced with environment variable overrides (`MAKERZ_PYTHON`, `KICAD_SHARE_DIR`, `FREEROUTING_JAR`, `JAVA_BIN`), `Path.home()` / `os.homedir()`, and `shutil.which("kicad-cli")` fallbacks.

### 8. Dead Code Cleanup (`SPIRIT-IP_LDC/hardware/spirit_build.py` & `IU-MIC_ORIGIN/hardware/t5_build_kicad_pcb.py`)
- **Issue:** `spirit_build.py` contained an unused inner function `patch_pad()` inside `load_kicad_mod()`. `t5_build_kicad_pcb.py` had an empty `elif rot != 0.0: pass` branch.
- **Fix:** Removed dead code and unified pad rotation handling.

### 9. Documentation Standardization (JSDoc + Python Docstrings in English)
- Added complete **JSDoc** annotations (`@fileoverview`, `@typedef`, `@param`, `@returns`) to `makerz-studio/server.mjs` and `makerz-studio/public/app.js`.
- Added complete **English Google-style Python docstrings** and English inline comments across all 11 Python scripts in `IU-MIC_ORIGIN` and `SPIRIT-IP_LDC`.
- Added root `README.md` and `.gitignore` (explicitly excluding macOS `._*` AppleDouble files created on exFAT external drives).
