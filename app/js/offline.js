// The in-browser backend for the static website copy (docs/away-from-home.md §1). api.js routes every call here when
// runmode.js says STATIC. It answers with the same reply shapes as server.py and throws ApiError(message, status) on
// failure. the child's play lives in localStorage["cv_offline_v1"] (the "local state"); Dad's snapshot.json is read-only.
// Loud failure: nothing here defaults or coerces. A bad snapshot, bad local state, or storage that cannot be written
// stops with a visible error (boot errors are plain Errors -> the "Could not start" screen; write errors are
// ApiErrors -> the PROGRESS NOT SAVED banner).
import { ApiError } from "./apierror.js";
import { deriveLevels, loadLevels, EVENT_GAME } from "./levels.js";
import { KINDS as HISTORY_KINDS } from "./historylogic.js";
import { localIso } from "./util.js";
import { childPoss, grownUpPoss } from "./family.js";

export const STORAGE_KEY = "cv_offline_v1";
export const CLIENT_OWNED = ["inventory", "active_letters", "letter_stats", "house", "stories", "crafted", "settings"];
const SERVER_OWNED = ["village", "treasure"];
// What a missing server-owned key reads as; mirrors server.py DEFAULT_SERVER_OWNED.
const DEFAULT_SERVER_OWNED = { village: { unlocked: [], bells_spent: 0 }, treasure: [] };
const houseNote = () => `That happens at ${grownUpPoss()} house`;

// --- Event validation: a port of server.py validate_event. KEEP IN SYNC with server.py. -------------------------------
// EVENT_FIELDS mirrors server.py EVENT_FIELDS: type -> [required fields, optional fields] beyond v/ts/session_id/type.
export const EVENT_FIELDS = {
  session_start: [[], []],
  session_end: [[], []],
  card: [["track", "item", "result"], ["level"]],
  match: [["item", "result", "chosen"], ["level"]],
  word: [["track", "item", "result"], ["level"]],
  story_page: [["track", "story_id", "page"], []],
  story_done: [["track", "story_id"], []],
  tricky_word: [["item", "story_id"], ["track", "percent"]],
  swap_page: [["track", "story_id", "page", "percent"], []],
  swap_done: [["track", "story_id", "percent"], []],
  block_placed: [["cell", "block"], []],
  craft: [["track", "item", "result"], ["level"]],
  adventure_done: [["adventure"], []],
};
const BASE_FIELDS = ["v", "ts", "session_id", "type"];
// Mirror server.py LETTERS, RESULTS, TRACKS, BLOCKS, ADVENTURES, GRID_W/GRID_H, LEVEL_FIELD_MAX, MAX_PERCENT.
const LETTERS = ["b", "d", "p", "q", "m", "w", "n", "u"];
const RESULTS = ["correct", "assisted", "miss"];
const TRACKS = ["smallcaps", "lowercase"];
const BLOCKS = ["wood", "stone", "door", "torch", "pig", "bed", "chest"];
const ADVENTURES = ["smallcaps", "lowercase"];
const GRID_W = 12, GRID_H = 8;
const LEVEL_FIELD_MAX = 99;
const MAX_PERCENT = 100;
const CRAFT_RESULTS = ["correct", "assisted"];
const ISO_WITH_OFFSET = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$/;

const isInt = (x) => Number.isInteger(x);
const isStr = (x) => typeof x === "string" && x.length > 0;
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const fail = (status, message) => { throw new ApiError(message, status); };
const bad = (field, message) => fail(400, `${field}: ${message}`);
const clone = (x) => JSON.parse(JSON.stringify(x));
const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);
/** Canonical JSON (object keys sorted at every depth) so equal progress always gives an equal string. */
const canon = (x) => JSON.stringify(x, (_k, v) => (isObj(v) ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v));

/** Throws ApiError(400) naming the offending field. Same rules as server.py validate_event. */
export function validateEvent(ev) {
  if (!isObj(ev)) fail(400, "event: must be an object");
  const allFields = new Set(BASE_FIELDS);
  for (const [r, o] of Object.values(EVENT_FIELDS)) for (const k of [...r, ...o]) allFields.add(k);
  for (const k of Object.keys(ev)) if (!allFields.has(k)) bad(k, "unknown field");
  for (const k of BASE_FIELDS) if (!(k in ev)) bad(k, "is required");
  if (ev.v !== 1) bad("v", "must be the integer 1");
  if (typeof ev.type !== "string" || !(ev.type in EVENT_FIELDS)) bad("type", `must be one of ${Object.keys(EVENT_FIELDS).sort().join(", ")}`);
  const [required, optional] = EVENT_FIELDS[ev.type];
  for (const k of Object.keys(ev)) if (!BASE_FIELDS.includes(k) && !required.includes(k) && !optional.includes(k)) bad(k, `not allowed for type ${ev.type}`);
  for (const k of required) if (!(k in ev)) bad(k, `is required for type ${ev.type}`);
  if (!isStr(ev.session_id)) bad("session_id", "must be a non-empty string");
  if (typeof ev.ts !== "string" || !ISO_WITH_OFFSET.test(ev.ts) || Number.isNaN(Date.parse(ev.ts))) bad("ts", "must be an ISO-8601 timestamp with a UTC offset");
  if ("track" in ev && !TRACKS.includes(ev.track)) bad("track", `must be one of ${TRACKS.join(", ")}`);
  for (const k of ["item", "chosen", "story_id"]) if (k in ev && !isStr(ev[k])) bad(k, "must be a non-empty string");
  if ("result" in ev && !RESULTS.includes(ev.result)) bad("result", `must be one of ${RESULTS.join(", ")}`);
  if ("level" in ev && !(isInt(ev.level) && ev.level >= 1 && ev.level <= LEVEL_FIELD_MAX)) bad("level", `must be an integer 1..${LEVEL_FIELD_MAX}`);
  if ("page" in ev && !(isInt(ev.page) && ev.page >= 0)) bad("page", "must be an integer >= 0");
  if ("percent" in ev && !(isInt(ev.percent) && ev.percent >= 0 && ev.percent <= MAX_PERCENT)) bad("percent", "must be an integer 0..100");
  if (ev.type === "swap_page" || ev.type === "swap_done") if (ev.track !== "lowercase") bad("track", `must be "lowercase" for ${ev.type}`);
  if (ev.type === "card" || ev.type === "match") if (!LETTERS.includes(ev.item)) bad("item", `must be one of ${LETTERS.join("")} for type ${ev.type}`);
  if (ev.type === "craft") {
    if (ev.track !== "smallcaps") bad("track", 'must be "smallcaps" for craft');
    if (!CRAFT_RESULTS.includes(ev.result)) bad("result", `must be one of ${CRAFT_RESULTS.join(", ")} for craft`);
    if (!/^[A-Z]{3,10}$/.test(ev.item)) bad("item", "must be a 3 to 10 letter capital word for craft");
  }
  if ("adventure" in ev && !ADVENTURES.includes(ev.adventure)) bad("adventure", `must be one of ${ADVENTURES.join(", ")}`);
  if ("cell" in ev) {
    const c = ev.cell;
    if (!(Array.isArray(c) && c.length === 2 && c.every(isInt) && c[0] >= 0 && c[0] < GRID_W && c[1] >= 0 && c[1] < GRID_H)) bad("cell", `must be [x, y] integers with 0<=x<${GRID_W}, 0<=y<${GRID_H}`);
  }
  if ("block" in ev && !BLOCKS.includes(ev.block)) bad("block", `must be one of ${BLOCKS.join(", ")}`);
}

// --- Snapshot and local-state shapes (docs/away-from-home.md §1.1, §2) --------------------------------------------------
function validateSnapshot(s) {
  const need = (ok, what) => { if (!ok) throw new Error(`snapshot.json: ${what}`); };
  need(isObj(s), "must be a JSON object");
  need(s.format === "reading-village-snapshot", `format must be "reading-village-snapshot" (got ${JSON.stringify(s.format)})`);
  need(s.v === 1, `v must be 1 (got ${JSON.stringify(s.v)})`);
  need(isStr(s.snapshot_id), "snapshot_id must be a non-empty string");
  need(isObj(s.progress) && isInt(s.progress.rev), "progress must be an object with an integer rev");
  need(Array.isArray(s.events), "events must be an array");
  need(isObj(s.village), "village must be an object");
  need(isObj(s.treasure) && Array.isArray(s.treasure.treasure), "treasure must be an object with a treasure array");
  need(isObj(s.history) && Array.isArray(s.history.lines), "history must be an object with a lines array");
  need(isObj(s.imported), "imported must be an object");
  for (const [id, r] of Object.entries(s.imported)) need(isObj(r) && isStr(r.base_snapshot_id) && isInt(r.events) && r.events >= 0, `imported["${id}"] must be {base_snapshot_id, events}`);
  return s;
}

function validateLocal(s) {
  const need = (ok, what) => { if (!ok) throw new Error(`local state ${STORAGE_KEY}: ${what}`); };
  need(isObj(s), "must be an object");
  need(s.v === 1, `v must be 1 (got ${JSON.stringify(s.v)})`);
  need(isStr(s.device_id), "device_id must be a non-empty string");
  need(isObj(s.base) && isStr(s.base.snapshot_id) && isObj(s.base.progress), "base must be {snapshot_id, progress}");
  need(isObj(s.progress) && isInt(s.progress.rev), "progress must be an object with an integer rev");
  need(Array.isArray(s.events), "events must be an array");
  need(Array.isArray(s.celebrated) && s.celebrated.every((c) => isObj(c) && isStr(c.game) && isInt(c.level)), "celebrated must be [{game, level}]");
  need(s.last_export === null || (isObj(s.last_export) && isStr(s.last_export.at) && isInt(s.last_export.events) && isStr(s.last_export.progress_fp)), "last_export must be null or {at, events, progress_fp}");
  return s;
}

/** A fresh local state that adopts `snapshot` as its base (§1.1 "Adopting a snapshot"). */
function adopt(snapshot, deviceId) {
  return {
    v: 1, device_id: deviceId,
    base: { snapshot_id: snapshot.snapshot_id, progress: clone(snapshot.progress) },
    progress: clone(snapshot.progress), events: [], celebrated: [], last_export: null,
  };
}

/** Fingerprint of the client-owned progress (canonical JSON; excludes rev, which a no-op save also bumps). */
export function progressFp(progress) { return canon(clientOwned(progress)); }

/** Is there play here that Dad has not been sent? events: made since the last export (or base); progress: the
 *  client-owned progress differs from what the last export contained (or from the base when never exported). */
export function unsentParts(local) {
  const le = local.last_export;
  return {
    events: local.events.length - (le ? le.events : 0),
    progress: progressFp(local.progress) !== (le ? le.progress_fp : progressFp(local.base.progress)),
  };
}

/**
 * §1.1: a newer published snapshot replaces the local base only when nothing local would be lost. Never merges two
 * bases in the browser. Adopt when either
 *   (a) nothing was made here: no events and the client-owned progress equals the base's; or
 *   (b) Dad's receipt for this device on this base covers every local event AND the progress is unchanged since the
 *       last export (or since the base, when never exported), so the receipt's export had it all.
 * Residual: the receipt carries only an event count, so two exports with the same count and different progress cannot
 * be told apart; the later one is assumed to be the one that was emailed.
 */
export function shouldAdopt(local, snapshot) {
  if (snapshot.snapshot_id === local.base.snapshot_id) return false;
  if (local.events.length === 0 && progressFp(local.progress) === progressFp(local.base.progress)) return true;
  const r = snapshot.imported[local.device_id];
  return !!r && r.base_snapshot_id === local.base.snapshot_id && r.events >= local.events.length && !unsentParts(local).progress;
}

/** The client-owned slice of a progress, in the export's key order. `crafted` absent reads as {} (the same documented
 *  default as craft.js craftedOf; not imported from there because that module pulls in the DOM). */
export function clientOwned(progress) {
  const out = {};
  for (const k of CLIENT_OWNED) {
    if (k === "crafted") out.crafted = clone(progress.crafted ?? {});
    else if (k in progress) out[k] = clone(progress[k]);
    else throw new Error(`progress has no "${k}", cannot build the export`);
  }
  return out;
}

/** Local time as YYYY-MM-DD-HHMM, for the export file name. */
export function stamp(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

/**
 * Build the backend. Dependencies are injected so node can test it:
 *   fetchJson(url) -> parsed JSON (throws), getStorage() -> a Storage (may throw), loadLevelsCfg() -> levels.json,
 *   now() -> Date, uuid() -> string.
 * Returns {boot()}; boot() resolves to the backend {request, unsentCount, lastExport, makeExport, state}.
 */
export function createOffline({ fetchJson, getStorage, loadLevelsCfg, now = () => new Date(), uuid = () => crypto.randomUUID() }) {
  async function boot() {
    let snapshot;
    try {
      snapshot = await fetchJson("snapshot.json");
    } catch (e) {
      throw new Error(`Could not load ${childPoss()} status from the website: ${e.message}`);
    }
    validateSnapshot(snapshot);
    const levelsCfg = await loadLevelsCfg();

    let storage;
    let raw;
    try {
      storage = getStorage();
      if (!storage) throw new Error("no storage in this browser");
      raw = storage.getItem(STORAGE_KEY);
    } catch (e) {
      throw new Error(`This browser cannot keep ${childPoss()} progress (${e.message}). Play is not allowed without storage. Try a normal (not private) window.`);
    }
    let local;
    let changed = false; // true when the state must be written back at boot (fresh browser, or a newer snapshot adopted)
    if (raw === null) {
      local = adopt(snapshot, uuid());
      changed = true;
    } else {
      try { local = JSON.parse(raw); } catch (e) { throw new Error(`local state ${STORAGE_KEY} is not valid JSON (${e.message})`); }
      validateLocal(local);
      if (shouldAdopt(local, snapshot)) { local = adopt(snapshot, local.device_id); changed = true; }
    }
    const state = { local };
    // The exact string this tab last read or wrote. Another tab that wrote since makes storage differ from it, and
    // writing over it would silently erase that tab's events: refuse instead (the server mode does this with rev).
    let lastWritten = raw;
    const persist = (next) => {
      if (storage.getItem(STORAGE_KEY) !== lastWritten) {
        fail(409, "opened in another tab: reload this page (this tab's change was NOT saved)");
      }
      const text = JSON.stringify(next);
      storage.setItem(STORAGE_KEY, text);
      lastWritten = text;
    };
    if (changed) {
      try { persist(local); } catch (e) { throw new Error(`This browser cannot keep ${childPoss()} progress (${e.message}).`); }
    }

    /** Write `next` to storage, and only then make it the live state: a failed write leaves the old state intact. */
    function commitLocal(next) {
      try { persist(next); } catch (e) { if (e instanceof ApiError) throw e; fail(500, `could not save in this browser (${e.message})`); }
      state.local = next;
    }
    const events = () => state.local.events;

    // --- routes ---
    function putProgress(body) {
      if (!isObj(body)) fail(400, "progress: must be an object");
      const p = clone(body);
      if ("cause" in p) { validateEvent(p.cause); delete p.cause; } // provenance only; never stored (as on the server)
      if (p.v !== 1) bad("v", "must be the integer 1");
      if (!isInt(p.rev) || p.rev < 0) bad("rev", "must be a non-negative integer");
      const cur = state.local.progress;
      if (p.rev !== cur.rev) fail(409, `rev mismatch: saved progress is at rev ${cur.rev}, this save was based on rev ${p.rev}`);
      for (const k of SERVER_OWNED) {
        const have = k in cur ? cur[k] : DEFAULT_SERVER_OWNED[k];
        const sent = k in p ? p[k] : DEFAULT_SERVER_OWNED[k];
        if (!sameJson(have, sent)) bad(k, "is owned by the server and cannot be changed by a save");
      }
      p.rev = cur.rev + 1;
      commitLocal({ ...state.local, progress: p });
      return clone(p);
    }

    function postEvent(body) {
      validateEvent(body);
      const game = EVENT_GAME[body.type];
      if (game && "level" in body && body.level > levelsCfg.games[game].max) bad("level", `${body.level} is above the top level of ${game} (${levelsCfg.games[game].max})`);
      const reply = { ok: true };
      let celebrated = state.local.celebrated;
      if (game) {
        const prior = [...snapshot.events, ...events()];
        const before = deriveLevels(prior, levelsCfg)[game].level;
        const after = deriveLevels([...prior, body], levelsCfg)[game].level;
        const ups = [];
        for (let n = Math.max(before + 1, 2); n <= after; n++) {
          if (!celebrated.some((c) => c.game === game && c.level === n)) ups.push({ game, level: n });
        }
        if (ups.length) { reply.game_level_ups = ups; celebrated = [...celebrated, ...ups]; }
      }
      commitLocal({ ...state.local, events: [...events(), clone(body)], celebrated });
      return reply;
    }

    function village() {
      const v = clone(snapshot.village);
      v.wallet = clone(state.local.progress.inventory);
      return v;
    }

    function history(query) {
      const keys = [...query.keys()];
      const kind = query.get("kind");
      if (keys.some((k) => k !== "kind") || query.getAll("kind").length > 1 || (kind !== null && !HISTORY_KINDS.includes(kind))) {
        bad("query", `only ?kind= is allowed, one of ${JSON.stringify(HISTORY_KINDS)}`);
      }
      const h = clone(snapshot.history);
      const lines = kind === null ? h.lines : h.lines.filter((l) => l.kind === kind);
      return { ...h, kind, count: lines.length, lines };
    }

    function request(method, path, body) {
      const url = new URL(path, "http://offline.invalid");
      const route = `${method} ${url.pathname}`;
      switch (route) {
        case "GET /api/progress": return clone(state.local.progress);
        case "PUT /api/progress": return putProgress(body);
        case "POST /api/event": return postEvent(body);
        case "GET /api/events": return clone([...snapshot.events, ...events()]);
        case "GET /api/village": return village();
        case "GET /api/treasure": return { ...clone(snapshot.treasure), enabled: false, server_running: false, problem: `Sending happens at ${grownUpPoss()} house` };
        case "GET /api/minecraft":
          return { enabled: false, worker_running: false, server_running: false, pending: [], failed: [], recent: [], chests: [], problem: `Minecraft is at ${grownUpPoss()} house` };
        case "GET /api/history": return history(url.searchParams);
        case "POST /api/village/unlock": case "POST /api/village/promote": case "POST /api/shop/buy":
        case "POST /api/shop/trade": case "POST /api/treasure/send": case "POST /api/reset":
          return fail(409, houseNote());
        default: return fail(404, `no such API route: ${route}`);
      }
    }

    /** The Home button's "N new things to send": events since the last export, plus 1 when progress changed without
     *  an event (a story page, a new letter, a setting) since the last export. */
    const unsentCount = () => { const u = unsentParts(state.local); return u.events + (u.progress ? 1 : 0); };

    /**
     * The export file (§3): everything made here since `base`, cumulative. Records last_export, then returns
     * {filename, text, count}. A storage failure throws and nothing is recorded (the caller must not claim "sent").
     */
    function makeExport() {
      const d = now();
      const l = state.local;
      const out = {
        format: "reading-village-export", v: 1, export_id: uuid(), device_id: l.device_id, created: localIso(d),
        base: { snapshot_id: l.base.snapshot_id, progress: clientOwned(l.base.progress) },
        progress: clientOwned(l.progress),
        events: clone(l.events),
      };
      commitLocal({ ...l, last_export: { at: localIso(d), events: l.events.length, progress_fp: progressFp(l.progress) } });
      return { filename: `reading-village-${stamp(d)}.json`, text: JSON.stringify(out, null, 2), count: out.events.length };
    }

    return { request, unsentCount, makeExport, lastExport: () => state.local.last_export, get state() { return state.local; } };
  }
  return { boot };
}

// --- The real singleton (browser) ---------------------------------------------------------------------------------
let booted = null; // the boot promise; a failed boot stays failed so every later call shows the same loud error
let ready = null; // the backend once boot resolved, for the synchronous Home-screen reads

/** The booted backend (a promise). Same promise on every call. */
export function offlineBackend() {
  if (!booted) {
    booted = createOffline({
      fetchJson: async (url) => {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
        return res.json();
      },
      getStorage: () => globalThis.localStorage,
      loadLevelsCfg: loadLevels,
    }).boot().then((b) => { ready = b; return b; });
  }
  return booted;
}

/** The backend, synchronously; only valid after the first API call finished (the app loads progress at boot). */
export function offlineNow() {
  if (!ready) throw new Error("offline backend is not booted yet");
  return ready;
}
