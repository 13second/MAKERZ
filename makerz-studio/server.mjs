#!/usr/bin/env node
/**
 * @fileoverview MAKERZ Studio — Local ECAD + MCAD Viewer & Project Registry Server.
 *
 * Provides a zero-dependency Node.js HTTP server for browsing hardware projects
 * stored under the MAKERZ workspace root, serving 3D CAD assets (GLB/STEP/STL),
 * KiCad SVG renders, BOM/CPL CSVs, Gerber archives, and triggering on-demand
 * Python ECAD/MCAD regeneration scripts.
 *
 * @module makerz-studio/server
 */

import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";

/** @type {string} Absolute path to the directory containing this server module. */
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {string} Absolute path to the MAKERZ workspace root directory. */
const MAKERZ_ROOT = path.resolve(__dirname, "..");

/** @type {string} Absolute path to the static frontend assets directory. */
const PUBLIC_DIR = path.join(__dirname, "public");

/** @type {string} Path to the JSON registry storing project pins, notes, and open history. */
const REGISTRY_FILE = path.join(MAKERZ_ROOT, ".makerz_registry.json");

/** @type {number} TCP port the local HTTP server listens on (override via PORT env var). */
const PORT = Number(process.env.PORT || 4173);

/** @type {number} Maximum allowed request body size in bytes (1 MiB). */
const MAX_BODY_BYTES = 1024 * 1024;

/**
 * MIME content-type lookup table for static and project file serving.
 * @type {Readonly<Record<string, string>>}
 */
const MIME = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".stl": "application/sla",
  ".step": "application/step",
  ".csv": "text/csv; charset=utf-8",
  ".zip": "application/zip",
});

/**
 * @typedef {Object} ProjectState
 * @property {number} openCount - Number of times the project has been opened.
 * @property {string|null} lastOpened - ISO-8601 timestamp of the last open event.
 * @property {boolean} pinned - Whether the project is pinned to the top of the sidebar.
 * @property {string} notes - User-authored markdown/plain-text project notes.
 */

/**
 * @typedef {Object} HistoryEntry
 * @property {string} id - Project identifier.
 * @property {string} openedAt - ISO-8601 timestamp when the project was opened.
 */

/**
 * @typedef {Object} RegistryData
 * @property {Record<string, ProjectState>} projects - Per-project state keyed by project ID.
 * @property {HistoryEntry[]} history - Chronological list of recently opened projects.
 */

/**
 * Resolves the Python executable used for ECAD/MCAD regeneration scripts.
 * Checks `MAKERZ_PYTHON` env var, then `~/.gemini/config/cad-venv/bin/python`,
 * falling back to `python3` on PATH.
 *
 * @returns {string} Path or command name for the Python interpreter.
 */
function resolvePythonBin() {
  if (process.env.MAKERZ_PYTHON && fs.existsSync(process.env.MAKERZ_PYTHON)) {
    return process.env.MAKERZ_PYTHON;
  }
  const venvPy = path.join(os.homedir(), ".gemini", "config", "cad-venv", "bin", "python");
  return fs.existsSync(venvPy) ? venvPy : "python3";
}

/**
 * Checks whether a resolved filesystem path is safely contained within a base directory,
 * preventing directory traversal and sibling-prefix bypasses.
 *
 * @param {string} baseDir - Trusted absolute root directory.
 * @param {string} targetPath - Candidate resolved path to validate.
 * @returns {boolean} True if `targetPath` is equal to or nested inside `baseDir`.
 */
function isPathInside(baseDir, targetPath) {
  const normalizedBase = path.resolve(baseDir);
  const normalizedTarget = path.resolve(targetPath);
  return (
    normalizedTarget === normalizedBase ||
    normalizedTarget.startsWith(normalizedBase + path.sep)
  );
}

/**
 * Loads the persisted MAKERZ project registry from disk.
 * Returns an empty default structure if the file does not exist or cannot be parsed.
 *
 * @returns {RegistryData} Parsed registry object.
 */
function loadRegistry() {
  try {
    if (fs.existsSync(REGISTRY_FILE)) {
      return JSON.parse(fs.readFileSync(REGISTRY_FILE, "utf-8"));
    }
  } catch {
    // Fall back to empty registry on corrupted or unreadable JSON.
  }
  return { projects: {}, history: [] };
}

/**
 * Persists the MAKERZ project registry to disk as formatted JSON.
 *
 * @param {RegistryData} reg - Registry data to serialize.
 * @returns {void}
 */
function saveRegistry(reg) {
  fs.writeFileSync(REGISTRY_FILE, JSON.stringify(reg, null, 2), "utf-8");
}

/**
 * Scans `MAKERZ_ROOT` for subdirectories containing a valid `project.json` manifest,
 * merges persisted registry state (pins, notes, open counts), and sorts pinned and
 * recently opened projects first.
 *
 * @returns {{ projects: Object[], history: HistoryEntry[], root: string }}
 *   Discovered project list, recent open history, and workspace root path.
 */
function discoverProjects() {
  const reg = loadRegistry();
  const entries = fs.readdirSync(MAKERZ_ROOT, { withFileTypes: true });
  const list = [];

  for (const ent of entries) {
    if (!ent.isDirectory() || ent.name.startsWith(".") || ent.name === "makerz-studio") continue;
    const pJsonPath = path.join(MAKERZ_ROOT, ent.name, "project.json");
    if (!fs.existsSync(pJsonPath)) continue;
    try {
      const meta = JSON.parse(fs.readFileSync(pJsonPath, "utf-8"));
      const state = reg.projects[meta.id] || {
        openCount: 0,
        lastOpened: null,
        pinned: false,
        notes: "",
      };
      list.push({
        ...meta,
        folder: ent.name,
        openCount: state.openCount || 0,
        lastOpened: state.lastOpened || null,
        pinned: Boolean(state.pinned),
        notes: state.notes || "",
      });
    } catch {
      // Skip folders with malformed project.json manifests.
    }
  }

  list.sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    const ta = a.lastOpened ? Date.parse(a.lastOpened) : 0;
    const tb = b.lastOpened ? Date.parse(b.lastOpened) : 0;
    return tb - ta || a.name.localeCompare(b.name);
  });

  return { projects: list, history: reg.history.slice(0, 20), root: MAKERZ_ROOT };
}

/**
 * Sends a JSON HTTP response with cache-disabling headers.
 *
 * @param {http.ServerResponse} res - Node.js HTTP response object.
 * @param {number} status - HTTP status code.
 * @param {*} data - JSON-serializable payload.
 * @returns {void}
 */
function sendJson(res, status, data) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store, no-cache, must-revalidate",
  });
  res.end(JSON.stringify(data));
}

/**
 * Reads and parses a JSON request body with a size guard (`MAX_BODY_BYTES`).
 *
 * @param {http.IncomingMessage} req - Node.js HTTP request object.
 * @returns {Promise<Record<string, any>>} Parsed JSON object, or `{}` on empty/invalid body.
 */
function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    let bytes = 0;
    req.on("data", (chunk) => {
      bytes += chunk.length;
      if (bytes > MAX_BODY_BYTES) {
        req.destroy();
        reject(new Error("Request body too large"));
        return;
      }
      raw += chunk;
    });
    req.on("error", () => resolve({}));
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        resolve({});
      }
    });
  });
}

/**
 * Streams a single file to the HTTP response with its appropriate MIME type.
 * Responds with 404 if the file does not exist or is a directory.
 *
 * @param {http.ServerResponse} res - Node.js HTTP response object.
 * @param {string} filePath - Absolute path of the file to serve.
 * @returns {void}
 */
function serveFile(res, filePath) {
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    res.writeHead(404);
    res.end("Not Found");
    return;
  }
  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, {
    "Content-Type": MIME[ext] || "application/octet-stream",
    "Cache-Control": "no-store, no-cache, must-revalidate",
  });
  fs.createReadStream(filePath).pipe(res);
}

/**
 * Main HTTP request router handling REST API endpoints, project file serving,
 * and static frontend delivery.
 */
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    res.writeHead(400);
    return res.end("Bad Request");
  }

  // API: List all discovered projects and recent open history
  if (req.method === "GET" && pathname === "/api/projects") {
    return sendJson(res, 200, discoverProjects());
  }

  // API: Record a project open event and update history
  const openMatch = pathname.match(/^\/api\/projects\/([^/]+)\/open$/);
  if (req.method === "POST" && openMatch) {
    const id = openMatch[1];
    const reg = loadRegistry();
    const cur = reg.projects[id] || { openCount: 0, lastOpened: null, pinned: false, notes: "" };
    cur.openCount = (cur.openCount || 0) + 1;
    cur.lastOpened = new Date().toISOString();
    reg.projects[id] = cur;
    reg.history = [
      { id, openedAt: cur.lastOpened },
      ...reg.history.filter((h) => h.id !== id),
    ].slice(0, 30);
    saveRegistry(reg);
    return sendJson(res, 200, { ok: true, state: cur });
  }

  // API: Toggle pinned status for a project
  const pinMatch = pathname.match(/^\/api\/projects\/([^/]+)\/pin$/);
  if (req.method === "POST" && pinMatch) {
    const id = pinMatch[1];
    const reg = loadRegistry();
    const cur = reg.projects[id] || { openCount: 0, lastOpened: null, pinned: false, notes: "" };
    cur.pinned = !cur.pinned;
    reg.projects[id] = cur;
    saveRegistry(reg);
    return sendJson(res, 200, { ok: true, pinned: cur.pinned });
  }

  // API: Save user notes for a project
  const notesMatch = pathname.match(/^\/api\/projects\/([^/]+)\/notes$/);
  if (req.method === "POST" && notesMatch) {
    const id = notesMatch[1];
    let body;
    try {
      body = await readBody(req);
    } catch {
      return sendJson(res, 413, { error: "Payload too large" });
    }
    const reg = loadRegistry();
    const cur = reg.projects[id] || { openCount: 0, lastOpened: null, pinned: false, notes: "" };
    cur.notes = String(body.notes || "");
    reg.projects[id] = cur;
    saveRegistry(reg);
    return sendJson(res, 200, { ok: true });
  }

  // API: Regenerate ECAD / JLCPCB Gerber outputs on demand
  const gerberMatch = pathname.match(/^\/api\/projects\/([^/]+)\/export-gerbers$/);
  if (req.method === "POST" && gerberMatch) {
    const id = gerberMatch[1];
    const { projects } = discoverProjects();
    const proj = projects.find((p) => p.id === id);
    if (!proj) return sendJson(res, 404, { error: "Project not found" });
    const hwDir = path.join(MAKERZ_ROOT, proj.folder, "hardware");
    const candidates = ["generate_ecad.py", "spirit_build.py", "stage1_sync_build.py"];
    const scriptName = candidates.find((c) => fs.existsSync(path.join(hwDir, c)));
    if (!scriptName) {
      return sendJson(res, 404, { error: "No ECAD build script found in hardware/" });
    }
    const py = resolvePythonBin();
    return execFile(py, [path.join(hwDir, scriptName)], (err, stdout, stderr) => {
      if (err) return sendJson(res, 500, { error: stderr || err.message });
      return sendJson(res, 200, { ok: true, message: stdout.trim() });
    });
  }

  // API: Regenerate 3D CAD models (STEP, STL, GLB, ZIP) on demand
  const cadMatch = pathname.match(/^\/api\/projects\/([^/]+)\/export-3d$/);
  if (req.method === "POST" && cadMatch) {
    const id = cadMatch[1];
    const { projects } = discoverProjects();
    const proj = projects.find((p) => p.id === id);
    if (!proj) return sendJson(res, 404, { error: "Project not found" });
    const encDir = path.join(MAKERZ_ROOT, proj.folder, "enclosure");
    const pyScript = fs.existsSync(encDir)
      ? fs.readdirSync(encDir).find((f) => f.endsWith(".py") && !f.startsWith("."))
      : null;
    if (!pyScript) return sendJson(res, 404, { error: "No Python CAD script found in enclosure/" });
    const py = resolvePythonBin();
    return execFile(py, [path.join(encDir, pyScript)], (err, stdout, stderr) => {
      if (err) return sendJson(res, 500, { error: stderr || err.message });
      return sendJson(res, 200, { ok: true, message: stdout.trim() });
    });
  }

  // API: Create a new blank hardware project scaffold in MAKERZ_ROOT
  if (req.method === "POST" && pathname === "/api/projects/create") {
    let body;
    try {
      body = await readBody(req);
    } catch {
      return sendJson(res, 413, { error: "Payload too large" });
    }
    const name = String(body.name || "").trim().replace(/[^a-zA-Z0-9_-]/g, "_");
    if (!name) return sendJson(res, 400, { error: "Invalid project name" });
    const dir = path.resolve(MAKERZ_ROOT, name);
    if (!isPathInside(MAKERZ_ROOT, dir)) return sendJson(res, 403, { error: "Forbidden path" });
    if (fs.existsSync(dir)) return sendJson(res, 409, { error: "A folder with this name already exists" });

    for (const sub of ["hardware", "enclosure", "exports/3d", "exports/renders", "docs"]) {
      fs.mkdirSync(path.join(dir, sub), { recursive: true });
    }
    const meta = {
      id: name.toLowerCase().replace(/_/g, "-"),
      name,
      subtitle: String(body.subtitle || "New ECAD + MCAD hardware project"),
      version: "0.1.0",
      status: "Draft",
      created_at: new Date().toISOString(),
      specs: {},
      assets: { model_parts: [] },
    };
    fs.writeFileSync(path.join(dir, "project.json"), JSON.stringify(meta, null, 2), "utf-8");
    return sendJson(res, 201, { ok: true, project: meta });
  }

  // Serve project files safely from MAKERZ_ROOT
  if (pathname.startsWith("/project-files/")) {
    const rel = pathname.slice("/project-files/".length);
    const resolved = path.resolve(MAKERZ_ROOT, rel);
    if (!isPathInside(MAKERZ_ROOT, resolved)) {
      res.writeHead(403);
      return res.end("Forbidden");
    }
    return serveFile(res, resolved);
  }

  // Serve static frontend files safely from PUBLIC_DIR
  const relStatic = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
  const staticPath = path.resolve(PUBLIC_DIR, relStatic);
  if (isPathInside(PUBLIC_DIR, staticPath) && fs.existsSync(staticPath)) {
    return serveFile(res, staticPath);
  }
  res.writeHead(404);
  res.end("Not Found");
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`MAKERZ Studio running at http://127.0.0.1:${PORT}`);
  console.log(`Projects root: ${MAKERZ_ROOT}`);
});
