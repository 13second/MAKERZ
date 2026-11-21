/**
 * @fileoverview MAKERZ Studio — Frontend Workbench Application.
 *
 * Renders the interactive Three.js 3D CAD assembly viewer (with exploded view,
 * wireframe toggle, and per-part visibility/downloads), pan-and-zoom SVG stages
 * for KiCad schematics and PCB layouts, a header-aware BOM table with Octopart
 * pricing links, and a persistent project registry sidebar.
 *
 * @module makerz-studio/public/app
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

/**
 * @typedef {Object} NormalizedBomRow
 * @property {string} ref - Component reference designator (e.g., "U1").
 * @property {string} comment - Component value or description.
 * @property {string} footprint - KiCad footprint name.
 * @property {number} qty - Component quantity per board.
 * @property {string} lcsc - LCSC / JLCPCB part number.
 * @property {string} mfr - Manufacturer name.
 * @property {string} mpn - Manufacturer part number.
 * @property {string} board - Target PCB identifier (e.g., "MAIN", "TIP", "Headamp 2L").
 * @property {string} notes - Engineering or sourcing notes.
 * @property {number} unitEur - Estimated unit cost in EUR.
 */

/** @type {Object[]} Discovered projects returned by `/api/projects`. */
let projects = [];

/** @type {Object|null} Currently selected project manifest. */
let activeProject = null;

/** @type {NormalizedBomRow[]} Parsed and normalized BOM rows for the active project. */
let bomRows = [];

/** @type {number|null} Debounce timer handle for autosaving project notes. */
let notesTimer = null;

// --- Three.js Scene State ---
/** @type {THREE.WebGLRenderer} */
let renderer;
/** @type {THREE.Scene} */
let scene;
/** @type {THREE.PerspectiveCamera} */
let camera;
/** @type {OrbitControls} */
let controls;

/**
 * Loaded 3D part groups indexed by part ID.
 * @type {Map<string, { group: THREE.Object3D, explodeDx: number }>}
 */
const loadedParts = new Map();

/** @type {boolean} Global wireframe rendering toggle state. */
let wireframeOn = false;

/**
 * Escapes HTML special characters to prevent XSS when rendering dynamic data.
 *
 * @param {*} str - Raw value to escape.
 * @returns {string} HTML-safe escaped string.
 */
function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Recursively disposes Three.js geometries and materials inside an object group
 * to prevent WebGL GPU memory leaks when switching projects.
 *
 * @param {THREE.Object3D} group - Root object group to dispose.
 * @returns {void}
 */
function disposeGroup(group) {
  group.traverse((obj) => {
    if (obj.isMesh) {
      obj.geometry?.dispose();
      if (Array.isArray(obj.material)) {
        obj.material.forEach((m) => m.dispose());
      } else {
        obj.material?.dispose();
      }
    }
  });
}

/**
 * Initializes the Three.js WebGL renderer, lighting rig, orbit controls,
 * responsive resize observer, and animation loop.
 *
 * @returns {void}
 */
function init3D() {
  const canvas = document.getElementById("canvas3d");
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(40, 1, 0.5, 2000);
  camera.position.set(160, 110, 175);

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  // Three-point studio lighting setup
  scene.add(new THREE.AmbientLight(0xdbeafe, 0.85));
  const key = new THREE.DirectionalLight(0xffffff, 1.8);
  key.position.set(140, 220, 160);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x38bdf8, 0.9);
  rim.position.set(-150, -80, -120);
  scene.add(rim);

  const grid = new THREE.GridHelper(320, 32, 0x334155, 0x1e293b);
  grid.position.y = -32;
  scene.add(grid);

  const resize = () => {
    const rect = canvas.parentElement.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    camera.aspect = rect.width / rect.height;
    camera.updateProjectionMatrix();
    renderer.setSize(rect.width, rect.height, false);
  };
  new ResizeObserver(resize).observe(canvas.parentElement);
  resize();

  const animate = () => {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  };
  animate();
}

/**
 * Loads all GLB 3D parts declared in a project manifest into the Three.js scene
 * and populates the HUD part-visibility & download list.
 *
 * @param {Object} proj - Active project manifest object.
 * @returns {Promise<void>}
 */
async function loadProject3D(proj) {
  for (const { group } of loadedParts.values()) {
    scene.remove(group);
    disposeGroup(group);
  }
  loadedParts.clear();
  const partsListEl = document.getElementById("partsList");
  partsListEl.innerHTML = "";
  document.getElementById("explodeSlider").value = "0";

  const parts = proj.assets?.model_parts || [];
  if (!parts.length) {
    partsListEl.innerHTML = `<div style="color:#64748b;font-size:11px">No 3D models available.</div>`;
    return;
  }

  const loader = new GLTFLoader();

  /** @type {Record<string, number>} Axial X-offsets (mm) for exploded assembly views. */
  const explodeOffsets = {
    // IU-MIC_ORIGIN parts
    rear_cap: -48,
    xlr_hardware: -48,
    main_pcb: -18,
    body_main: 0,
    serigraphy: 0,
    nose_cone: 46,
    mems_tip_pcb: 74,
    // SPIRIT-IP_LDC parts
    bottom_cap: -52,
    body_clear: 0,
    headamp_pcb: 24,
    headamp_shield_sh1: 36,
    capsule_saddle: 50,
    capsule_shockmount_tpu: 66,
    capsule_34mm: 80,
    grille_316l: 96,
  };

  for (const part of parts) {
    const url = `/project-files/${proj.folder}/${part.glb}?t=${Date.now()}`;
    try {
      const gltf = await loader.loadAsync(url);
      const grp = gltf.scene;
      // Rotate Z-up CAD model to horizontal display along X-axis centered near origin
      grp.rotation.y = Math.PI / 2;
      grp.position.x = -92;
      grp.traverse((obj) => {
        if (obj.isMesh) {
          obj.material = new THREE.MeshStandardMaterial({
            color: part.color || "#38bdf8",
            roughness: part.roughness ?? 0.38,
            metalness: part.metalness ?? 0.35,
            wireframe: wireframeOn,
          });
        }
      });
      scene.add(grp);
      loadedParts.set(part.id, { group: grp, explodeDx: explodeOffsets[part.id] ?? 0 });

      const row = document.createElement("div");
      row.className = "part-row";
      const stepLink = part.step
        ? `<a class="part-dl" href="/project-files/${encodeURI(proj.folder)}/${encodeURI(part.step)}" download>STEP</a>`
        : "";
      const stlLink = part.stl
        ? `<a class="part-dl" href="/project-files/${encodeURI(proj.folder)}/${encodeURI(part.stl)}" download>STL</a>`
        : "";
      row.innerHTML = `
        <label><input type="checkbox" checked data-part="${escapeHtml(part.id)}" /> ${escapeHtml(part.name)}</label>
        <span style="display:flex;gap:6px">${stepLink}${stlLink}</span>
      `;
      row.querySelector("input").addEventListener("change", (e) => {
        grp.visible = e.target.checked;
      });
      partsListEl.appendChild(row);
    } catch (err) {
      console.warn("Failed to load 3D part:", part.id, err);
    }
  }
  resetCamera();
}

/**
 * Resets the 3D viewport camera and orbit target to the default isometric view.
 *
 * @returns {void}
 */
function resetCamera() {
  camera.position.set(125, 85, 165);
  controls.target.set(0, 0, 0);
  controls.update();
}

// --- Pan & Zoom SVG Stages ---

/** @type {Record<string, { scale: number, x: number, y: number }>} */
const svgStates = {
  schematic: { scale: 0.85, x: 0, y: 0 },
  pcb: { scale: 0.85, x: 0, y: 0 },
};

/**
 * Attaches mouse-wheel zoom and click-and-drag pan handlers to an SVG viewer stage.
 *
 * @param {"schematic"|"pcb"} key - Stage identifier matching `#stage-<key>`.
 * @returns {void}
 */
function setupSvgStage(key) {
  const stage = document.getElementById(`stage-${key}`);
  let dragging = false;
  let sx = 0;
  let sy = 0;

  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    const st = svgStates[key];
    st.scale = Math.min(5, Math.max(0.25, st.scale * (e.deltaY < 0 ? 1.12 : 0.89)));
    applySvgTransform(key);
  });
  stage.addEventListener("mousedown", (e) => {
    dragging = true;
    sx = e.clientX - svgStates[key].x;
    sy = e.clientY - svgStates[key].y;
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    svgStates[key].x = e.clientX - sx;
    svgStates[key].y = e.clientY - sy;
    applySvgTransform(key);
  });
  window.addEventListener("mouseup", () => {
    dragging = false;
  });
}

/**
 * Applies the current pan/zoom CSS transform to the active SVG image inside a stage.
 *
 * @param {"schematic"|"pcb"} key - Stage identifier.
 * @returns {void}
 */
function applySvgTransform(key) {
  const img = document.querySelector(`#stage-${key} img`);
  if (!img) return;
  const { scale, x, y } = svgStates[key];
  img.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
}

/**
 * Loads a project SVG render into the specified pan/zoom stage.
 *
 * @param {"schematic"|"pcb"} key - Target stage identifier.
 * @param {string|undefined} relPath - Path relative to the project directory.
 * @returns {void}
 */
function loadSvg(key, relPath) {
  const stage = document.getElementById(`stage-${key}`);
  if (!relPath) {
    stage.innerHTML = `<div style="color:#64748b">No SVG render available for this project.</div>`;
    return;
  }
  svgStates[key] = { scale: 0.82, x: 0, y: 0 };
  stage.innerHTML = `<img src="/project-files/${encodeURI(activeProject.folder)}/${encodeURI(relPath)}?t=${Date.now()}" alt="${escapeHtml(key)}" />`;
  applySvgTransform(key);
}

// --- BOM & Specifications ---

/**
 * Parses a single RFC-4180-style CSV line into unquoted field strings.
 *
 * @param {string} line - Raw CSV row.
 * @returns {string[]} Array of parsed cell values.
 */
function parseCsvLine(line) {
  return line
    .split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/)
    .map((c) => c.trim().replace(/^"|"$/g, ""));
}

/**
 * Parses BOM CSV text using header-name mapping so different project schemas
 * (e.g., IU-MIC_ORIGIN vs SPIRIT-IP_LDC) normalize cleanly into `NormalizedBomRow` objects.
 *
 * @param {string} csvText - Full CSV file content.
 * @returns {NormalizedBomRow[]} Normalized BOM rows.
 */
function parseBomCsv(csvText) {
  const lines = csvText.trim().split(/\r?\n/);
  if (lines.length < 2) return [];

  const headers = parseCsvLine(lines[0]).map((h) => h.toLowerCase());
  const col = (...names) => headers.findIndex((h) => names.some((n) => h.includes(n)));

  const idxRef = col("designator", "ref");
  const idxComment = col("comment", "value");
  const idxFootprint = col("footprint");
  const idxQty = col("quantity", "qty");
  const idxLcsc = col("lcsc", "jlcpcb");
  const idxMfr = col("manufacturer", "mfr");
  const idxMpn = col("mpn");
  const idxBoard = col("board");
  const idxNotes = col("notes", "note");
  const idxEur = col("eur", "price", "cost");

  return lines.slice(1).map((line) => {
    const r = parseCsvLine(line);
    const get = (idx, fallback = "") => (idx >= 0 && r[idx] !== undefined ? r[idx] : fallback);
    return {
      ref: get(idxRef),
      comment: get(idxComment),
      footprint: get(idxFootprint),
      qty: Number(get(idxQty, "1")) || 1,
      lcsc: get(idxLcsc),
      mfr: get(idxMfr),
      mpn: get(idxMpn).trim(),
      board: get(idxBoard),
      notes: get(idxNotes),
      unitEur: Number(get(idxEur, "0")) || 0,
    };
  });
}

/**
 * Populates the specifications grid, project notes textarea, and BOM table
 * for the selected project.
 *
 * @param {Object} proj - Active project manifest.
 * @returns {Promise<void>}
 */
async function loadBomAndSpecs(proj) {
  const grid = document.getElementById("specsGrid");
  grid.innerHTML = "";
  for (const [k, v] of Object.entries(proj.specs || {})) {
    const card = document.createElement("div");
    card.className = "spec-card";
    card.innerHTML = `<div class="spec-k">${escapeHtml(k.replace(/_/g, " "))}</div><div class="spec-v">${escapeHtml(v)}</div>`;
    grid.appendChild(card);
  }

  document.getElementById("projectNotes").value = proj.notes || "";
  bomRows = [];
  if (proj.assets?.bom_csv) {
    const res = await fetch(`/project-files/${proj.folder}/${proj.assets.bom_csv}`);
    if (res.ok) {
      bomRows = parseBomCsv(await res.text());
    }
  }
  renderBomTable("");
}

/**
 * Formats a numeric value as a Euro currency string (e.g., `€ 12,50`).
 *
 * @param {number} val - Numeric amount in EUR.
 * @returns {string} Formatted currency string.
 */
function fmtEur(val) {
  return `€ ${val.toFixed(2).replace(".", ",")}`;
}

/**
 * Renders the filtered BOM table rows and updates the prototype cost summary pills.
 *
 * @param {string} query - Case-insensitive substring filter query.
 * @returns {void}
 */
function renderBomTable(query) {
  const tbody = document.querySelector("#bomTable tbody");
  tbody.innerHTML = "";
  const q = query.toLowerCase();
  let componentsTotal = 0;

  for (const r of bomRows) {
    const lineTotal = r.qty * r.unitEur;
    componentsTotal += lineTotal;

    const searchBlob = `${r.ref} ${r.comment} ${r.footprint} ${r.lcsc} ${r.mfr} ${r.mpn} ${r.board} ${r.notes}`.toLowerCase();
    if (q && !searchBlob.includes(q)) continue;

    const hasValidMpn = r.mpn && r.mfr.toLowerCase() !== "custom" && !r.mpn.startsWith("PAD-");
    const octopartUrl = hasValidMpn
      ? `https://octopart.com/search?q=${encodeURIComponent(r.mpn)}&in_stock_only=1&sort=avg_price&sort_dir=asc`
      : null;

    const valueCell = octopartUrl
      ? `<a class="bom-link" href="${octopartUrl}" target="_blank" rel="noopener noreferrer" title="Compare best price on Octopart (${escapeHtml(r.mpn)})">${escapeHtml(r.comment)} <span class="bom-mpn">${escapeHtml(r.mpn)} ↗</span></a>`
      : escapeHtml(r.comment);

    const tr = document.createElement("tr");
    tr.innerHTML = `<td><b>${escapeHtml(r.ref)}</b></td><td>${valueCell}</td><td>${escapeHtml(r.footprint)}</td><td>${escapeHtml(r.qty)}</td><td class="num">${r.unitEur > 0 ? fmtEur(r.unitEur) : "—"}</td><td class="num"><b>${lineTotal > 0 ? fmtEur(lineTotal) : "—"}</b></td><td style="color:#38bdf8">${escapeHtml(r.lcsc)}</td><td>${escapeHtml(r.mfr)}</td><td>${escapeHtml(r.board)}</td><td style="color:#94a3b8">${escapeHtml(r.notes)}</td>`;
    tbody.appendChild(tr);
  }

  const pcbFab = Number(activeProject?.pricing?.pcb_fab_eur ?? 0);
  const pcbNote = activeProject?.pricing?.pcb_fab_note || "Estimated PCB fabrication (prototype batch)";
  const grandTotal = componentsTotal + pcbFab;
  const summaryEl = document.getElementById("costSummary");
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="cost-pill">
        <span class="cost-label">Components Total (1× prototype)</span>
        <span class="cost-val">${fmtEur(componentsTotal)}</span>
      </div>
      <div class="cost-pill">
        <span class="cost-label">PCB Fabrication (JLCPCB)</span>
        <span class="cost-val">${fmtEur(pcbFab)}</span>
        <span class="cost-sub">${escapeHtml(pcbNote)}</span>
      </div>
      <div class="cost-pill highlight">
        <span class="cost-label">Estimated Total (Components + PCB)</span>
        <span class="cost-val">${fmtEur(grandTotal)}</span>
        <span class="cost-sub">Indicative 1× pricing · click any MPN for live Octopart pricing</span>
      </div>
    `;
  }
}

// --- Project Registry ---

/**
 * Fetches the list of discovered projects from the backend API and updates the sidebar.
 *
 * @param {boolean} [autoOpenFirst=false] - Automatically open the first project if none is active.
 * @returns {Promise<void>}
 */
async function fetchProjects(autoOpenFirst = false) {
  const res = await fetch("/api/projects");
  const data = await res.json();
  projects = data.projects;
  document.getElementById("rootPathLabel").textContent = data.root;
  renderProjectList(document.getElementById("projectSearch").value);
  if (autoOpenFirst && projects.length && !activeProject) {
    openProject(projects[0]);
  }
}

/**
 * Formats an ISO-8601 timestamp into a compact localized date/time string.
 *
 * @param {string|null} iso - ISO timestamp or null if never opened.
 * @returns {string} Human-readable last-opened label.
 */
function formatLastOpened(iso) {
  if (!iso) return "Never opened";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/**
 * Renders the filtered project cards in the sidebar.
 *
 * @param {string} [filter=""] - Case-insensitive search query.
 * @returns {void}
 */
function renderProjectList(filter = "") {
  const list = document.getElementById("projectList");
  list.innerHTML = "";
  const q = filter.toLowerCase();
  for (const p of projects) {
    if (q && !`${p.name} ${p.subtitle}`.toLowerCase().includes(q)) continue;
    const item = document.createElement("div");
    item.className = `proj-item ${activeProject?.id === p.id ? "active" : ""}`;
    item.innerHTML = `
      <div class="proj-top">
        <span class="proj-name">${escapeHtml(p.name)}</span>
        <button class="pin-btn ${p.pinned ? "pinned" : ""}" title="Pin to top">★</button>
      </div>
      <div class="proj-sub">${escapeHtml(p.subtitle || "")}</div>
      <div class="proj-hist">Opened ${escapeHtml(p.openCount)}× · ${escapeHtml(formatLastOpened(p.lastOpened))}</div>
    `;
    item.querySelector(".pin-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/projects/${encodeURIComponent(p.id)}/pin`, { method: "POST" });
      fetchProjects(false);
    });
    item.addEventListener("click", () => openProject(p));
    list.appendChild(item);
  }
}

/**
 * Activates a project across all workbench tabs (3D, Schematic, PCB, BOM)
 * and records the open event in the backend registry.
 *
 * @param {Object} proj - Project manifest to activate.
 * @returns {Promise<void>}
 */
async function openProject(proj) {
  activeProject = proj;
  await fetch(`/api/projects/${encodeURIComponent(proj.id)}/open`, { method: "POST" });
  document.getElementById("activeProjectName").textContent = proj.name;
  document.getElementById("activeProjectBadge").textContent = `v${proj.version || "1.0"} · ${proj.status || ""}`;
  document.getElementById("activeProjectMeta").textContent = proj.folder;

  loadProject3D(proj);
  loadSvg("schematic", proj.assets?.schematic_svg);
  loadSvg("pcb", proj.assets?.pcb_front_svg);
  loadBomAndSpecs(proj);
  updateGerberLinks(proj);
  fetchProjects(false);
}

/**
 * Updates download button `href` attributes and visibility based on available project assets.
 *
 * @param {Object} proj - Active project manifest.
 * @returns {void}
 */
function updateGerberLinks(proj) {
  const bind = (id, rel) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (rel) {
      el.href = `/project-files/${encodeURI(proj.folder)}/${encodeURI(rel)}`;
      el.style.display = "inline-flex";
    } else {
      el.style.display = "none";
    }
  };
  bind("dlGerberMain", proj.assets?.gerber_main_zip);
  bind("dlGerberTip", proj.assets?.gerber_tip_zip);
  bind("dlBomCsv", proj.assets?.bom_jlcpcb_smt_csv || proj.assets?.bom_csv);
  bind("dlCplCsv", proj.assets?.cpl_csv);
  bind("dl3dZip", proj.assets?.model_print_zip);
  bind("dl3dStep", proj.assets?.model_assembly_step);
  bind("dl3dGlb", proj.assets?.model_assembly_glb);
}

// --- Regeneration Action Handlers ---

document.getElementById("regen3dBtn")?.addEventListener("click", async (e) => {
  if (!activeProject) return;
  const btn = e.currentTarget;
  btn.textContent = "⏳";
  btn.disabled = true;
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(activeProject.id)}/export-3d`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      btn.textContent = "✓";
      await loadProject3D(activeProject);
    } else {
      btn.textContent = "✗";
      alert(data.error || "Failed to regenerate 3D models");
    }
  } finally {
    setTimeout(() => {
      btn.textContent = "↻ 3D";
      btn.disabled = false;
    }, 1800);
  }
});

document.getElementById("regenGerberBtn")?.addEventListener("click", async (e) => {
  if (!activeProject) return;
  const btn = e.currentTarget;
  btn.textContent = "⏳ Building...";
  btn.disabled = true;
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(activeProject.id)}/export-gerbers`, { method: "POST" });
    const data = await res.json();
    btn.textContent = res.ok ? "✓ Gerbers Ready" : "✗ Error";
    if (!res.ok) alert(data.error || "Failed to regenerate Gerbers");
  } finally {
    setTimeout(() => {
      btn.textContent = "↻ Rebuild";
      btn.disabled = false;
    }, 1800);
  }
});

// --- UI Event Listeners ---

document.querySelectorAll("#viewTabs .tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#viewTabs .tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
  });
});

document.querySelectorAll("[data-pcb-view]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-pcb-view]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    if (!activeProject) return;
    const map = {
      front: activeProject.assets?.pcb_front_svg,
      back: activeProject.assets?.pcb_back_svg,
      tip: activeProject.assets?.pcb_tip_svg,
    };
    loadSvg("pcb", map[btn.dataset.pcbView]);
  });
});

document.querySelectorAll("[data-zoom]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const key = btn.dataset.target;
    const st = svgStates[key];
    if (btn.dataset.zoom === "in") st.scale = Math.min(5, st.scale * 1.25);
    if (btn.dataset.zoom === "out") st.scale = Math.max(0.25, st.scale * 0.8);
    if (btn.dataset.zoom === "reset") {
      st.scale = 0.82;
      st.x = 0;
      st.y = 0;
    }
    applySvgTransform(key);
  });
});

document.getElementById("explodeSlider").addEventListener("input", (e) => {
  const f = Number(e.target.value) / 100;
  for (const { group, explodeDx } of loadedParts.values()) {
    group.position.x = -92 + explodeDx * f;
  }
});

document.getElementById("resetCamBtn").addEventListener("click", resetCamera);
document.getElementById("wireframeBtn").addEventListener("click", () => {
  wireframeOn = !wireframeOn;
  for (const { group } of loadedParts.values()) {
    group.traverse((o) => {
      if (o.isMesh) o.material.wireframe = wireframeOn;
    });
  }
});

document.getElementById("projectSearch").addEventListener("input", (e) => renderProjectList(e.target.value));
document.getElementById("bomFilter").addEventListener("input", (e) => renderBomTable(e.target.value));

document.getElementById("projectNotes").addEventListener("input", (e) => {
  if (!activeProject) return;
  clearTimeout(notesTimer);
  notesTimer = setTimeout(async () => {
    await fetch(`/api/projects/${encodeURIComponent(activeProject.id)}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: e.target.value }),
    });
    const msg = document.getElementById("notesSavedMsg");
    msg.textContent = "Saved ✓";
    setTimeout(() => {
      msg.textContent = "";
    }, 1500);
  }, 400);
});

const dialog = document.getElementById("newProjectDialog");
document.getElementById("newProjectBtn").addEventListener("click", () => dialog.showModal());
document.getElementById("cancelNewProj").addEventListener("click", () => dialog.close());
document.getElementById("newProjectForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("newProjName").value;
  const subtitle = document.getElementById("newProjSub").value;
  const res = await fetch("/api/projects/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, subtitle }),
  });
  if (res.ok) {
    dialog.close();
    document.getElementById("newProjName").value = "";
    document.getElementById("newProjSub").value = "";
    await fetchProjects(false);
  }
});

// --- Application Bootstrap ---
init3D();
setupSvgStage("schematic");
setupSvgStage("pcb");
fetchProjects(true);
