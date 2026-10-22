// Real Minecraft textures, LOCAL ONLY. The images live in app/assets/mc/ (gitignored, extracted from Dad's own
// client jar by tools/extract_mc_textures.py). This module resolves a game sprite id to a loaded texture image.
//
// Two explicit modes (never a silent fallback):
//   "off"  - real textures are not used; getTexture() returns null and the hand-drawn sprite is drawn.
//   "real" - a MAPPED id must have its texture: if the manifest/file is missing, load() rejects and
//            getTexture() throws McTextureError. An id deliberately classified UNMAPPED (characters, mobs,
//            story props) returns null so the caller draws the hand-drawn sprite on purpose. An id that is in
//            neither list is a bug (new sprite not classified in mctextures_map.json) and throws.
//
// Data contracts (docs/textures.md):
//   mctextures_map.json  {"v":1,"entries":{id:{kind,...}},"unmapped":{id:reason}}
//   assets/mc/manifest.json {"v":1,"source_jar","jar_sha256","minecraft_version","files":{rel:{w,h,sha256}},"sprites":{id:rel}}

export const MODES = ["off", "real"];

export class McTextureError extends Error {
  constructor(message) {
    super(message);
    this.name = "McTextureError";
  }
}

// Validates the mapping file shape; throws on anything unexpected rather than coercing.
export function validateMapping(m) {
  if (!m || m.v !== 1 || typeof m.entries !== "object" || typeof m.unmapped !== "object") {
    throw new McTextureError("mctextures_map.json: expected {v:1, entries:{}, unmapped:{}}");
  }
  const both = Object.keys(m.entries).filter((id) => id in m.unmapped);
  if (both.length) throw new McTextureError(`mctextures_map.json: ids both mapped and unmapped: ${both.join(", ")}`);
  return m;
}

// Validates the extractor's manifest and that it covers every mapped id. Lists ALL problems at once.
export function validateManifest(man, mapping) {
  const problems = [];
  if (!man || man.v !== 1 || typeof man.files !== "object" || typeof man.sprites !== "object") {
    throw new McTextureError("manifest.json: expected {v:1, files:{}, sprites:{}} - re-run tools/extract_mc_textures.py");
  }
  for (const id of Object.keys(mapping.entries)) {
    const rel = man.sprites[id];
    if (!rel) problems.push(`no texture extracted for sprite id "${id}"`);
    else if (!(rel in man.files)) problems.push(`manifest lists "${id}" -> ${rel} but not in files`);
  }
  if (problems.length) {
    throw new McTextureError(`manifest.json is incomplete (${problems.length}): ${problems.join("; ")} - re-run tools/extract_mc_textures.py`);
  }
  return man;
}

// Builds a texture set. Injectable fetchJson/loadImage keep it testable without a DOM or network.
//   mode: "off" | "real"; mapping: parsed mctextures_map.json; fetchJson(url) -> parsed JSON;
//   loadImage(url) -> Promise<image>; baseUrl: where manifest-relative files live (ends with "/").
export function createTextures({ mode = "off", mapping, fetchJson, loadImage, manifestUrl, baseUrl }) {
  if (!MODES.includes(mode)) throw new McTextureError(`unknown texture mode "${mode}" (use ${MODES.join(" or ")})`);
  validateMapping(mapping);
  const images = new Map(); // sprite id -> loaded image
  let manifest = null;
  let loaded = false;

  async function load() {
    if (mode === "off") { loaded = true; return; }
    let man;
    try {
      man = await fetchJson(manifestUrl);
    } catch (e) {
      throw new McTextureError(`cannot read ${manifestUrl} (${e.message}) - run tools/extract_mc_textures.py, or set art mode to "off"`);
    }
    manifest = validateManifest(man, mapping);
    const byFile = new Map();
    const failures = [];
    for (const rel of new Set(Object.keys(manifest.files))) {
      byFile.set(rel, loadImage(baseUrl + rel).catch((e) => { failures.push(`${rel}: ${e.message || e}`); return null; }));
    }
    for (const [rel, p] of byFile) byFile.set(rel, await p);
    if (failures.length) throw new McTextureError(`could not load ${failures.length} texture file(s): ${failures.join("; ")}`);
    for (const id of Object.keys(mapping.entries)) images.set(id, byFile.get(manifest.sprites[id]));
    loaded = true;
  }

  return {
    mode,
    load,
    // true when this id is drawn from a real texture in the current mode
    usesReal(id) { return mode === "real" && id in mapping.entries; },
    // image for a sprite id, or null when the hand-drawn sprite should be used (mode off / deliberately unmapped)
    getTexture(id) {
      if (mode === "off") return null;
      if (id in mapping.unmapped) return null;
      if (!(id in mapping.entries)) {
        throw new McTextureError(`sprite id "${id}" is not classified in mctextures_map.json (add it to entries or unmapped)`);
      }
      if (!loaded) throw new McTextureError(`texture "${id}" requested before load() finished`);
      const img = images.get(id);
      if (!img) throw new McTextureError(`texture for "${id}" is missing - re-run tools/extract_mc_textures.py`);
      return img;
    },
    isMapped(id) { return id in mapping.entries; },
    // sprite ids from `ids` that are drawn hand-drawn on purpose (shown to Dad); unclassified ids are reported separately
    unmapped(ids) { return ids.filter((id) => id in mapping.unmapped); },
    unclassified(ids) { return ids.filter((id) => !(id in mapping.entries) && !(id in mapping.unmapped)); },
    reason(id) { return mapping.unmapped[id] || null; },
    info() { return manifest ? { version: manifest.minecraft_version, jar_sha256: manifest.jar_sha256 } : null; },
  };
}

// Browser singleton. configure() once at startup (main.js) with the art mode; then await texturesReady().
let current = null;
let ready = null;

export function configureTextures(mode) {
  const fetchJson = async (url) => {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  };
  const loadImage = (url) => new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => rej(new Error("image failed to load"));
    im.src = url;
  });
  ready = (async () => {
    const mapping = await fetchJson(new URL("mctextures_map.json", import.meta.url));
    const t = createTextures({
      mode, mapping, fetchJson, loadImage,
      manifestUrl: new URL("../assets/mc/manifest.json", import.meta.url).href,
      baseUrl: new URL("../assets/mc/", import.meta.url).href,
    });
    await t.load();
    current = t; // only a fully loaded set becomes current: a failed switch leaves the previous art in place
    return t;
  })();
  return ready;
}

// ---- Dad's art-mode setting -------------------------------------------------------------------------------------
// "hand" (default, hand-drawn sprites) | "real" (local Minecraft textures). Kept in this browser's localStorage, NOT in
// progress.json: the server validates progress.settings strictly (unknown keys are a 400) and the textures exist only
// on this machine. The textures-module mode for "hand" is "off".
export const ART_MODES = ["hand", "real"];
export const ART_KEY = "reading_village_art_mode";
export const artToTextureMode = (art) => (art === "real" ? "real" : "off");

/** The saved art mode; absent = "hand". A stored value that is not one of ART_MODES is a loud error. */
export function getArtMode(storage = globalThis.localStorage) {
  let v = null;
  try { v = storage ? storage.getItem(ART_KEY) : null; } catch { v = null; } // storage blocked: the documented default
  if (v === null) return "hand";
  if (!ART_MODES.includes(v)) throw new McTextureError(`saved art mode "${v}" is not one of ${ART_MODES.join("|")} (open /?art=hand to reset it)`);
  return v;
}

/** Save the art mode. Throws if the value is invalid or the browser refuses to store it (never silently unsaved). */
export function setArtMode(art, storage = globalThis.localStorage) {
  if (!ART_MODES.includes(art)) throw new McTextureError(`art mode must be one of ${ART_MODES.join("|")} (got ${JSON.stringify(art)})`);
  try { storage.setItem(ART_KEY, art); } catch (e) { throw new McTextureError(`could not save the art mode (${e.message})`); }
}

/** True when the extracted textures are installed (app/assets/mc/manifest.json is served). Network errors throw. */
export async function manifestAvailable(fetchFn = fetch) {
  const r = await fetchFn(new URL("../assets/mc/manifest.json", import.meta.url).href, { cache: "no-cache" });
  if (r.status === 404) return false;
  if (!r.ok) throw new McTextureError(`manifest.json: HTTP ${r.status}`);
  return true;
}

/** Install an already-built textures object as the current one (tests; configureTextures does this itself). */
export function setCurrentTextures(t) {
  current = t;
  ready = Promise.resolve(t);
}

/** The current textures object (for the settings screen), or null before configureTextures. */
export const getTextures = () => current;

export function texturesReady() {
  if (!ready) throw new McTextureError("configureTextures(mode) was never called");
  return ready;
}

// Convenience used by the drawing code: image or null (hand-drawn). Throws in real mode on a missing texture.
export function getTexture(id) {
  return current ? current.getTexture(id) : null;
}
