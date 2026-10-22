// The in-browser backend for the static website copy (docs/away-from-home.md §1): routes, rev and server-owned checks,
// event validation, level-up detection, the snapshot adoption rule and the export file shape.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createOffline, STORAGE_KEY, shouldAdopt, unsentParts, validateEvent, EVENT_FIELDS, CLIENT_OWNED } from "../../app/js/offline.js";
import { ApiError } from "../../app/js/api.js";
import { setFamily } from "../../app/js/family.js";

setFamily({ v: 1, child: { name: "Sam" }, village_name: "Sam's Village", home_grown_up: "Dad", away_label: "Mom's house" });

const LEVELS = JSON.parse(readFileSync(new URL("../../app/data/levels.json", import.meta.url)));
const TS = "2026-10-21T10:00:00-04:00";

function progress(rev = 5) {
  return {
    v: 1, rev, active_letters: ["b", "d"], letter_stats: {}, house: [], stories: {}, crafted: { CAT: 1 },
    inventory: { coal: 0, iron: 0, gold: 0, diamond: 0, wood: 2, stone: 0, emerald: 7 },
    settings: { font: "system", lowercase_track: "off", lowercase_percent: 0, sound: "on" },
    village: { unlocked: ["farmer"], bells_spent: 1, emeralds_spent: 3, levels: {} },
    treasure: [{ tid: "t000001", label: "Apple", sprite: "apple", items: [], source: { kind: "surprise", ref: "x" }, status: "kept" }],
  };
}
const ev = (fields) => ({ v: 1, ts: TS, session_id: "s1", ...fields });
const word = (result = "correct") => ev({ type: "word", track: "smallcaps", item: "cat", result, level: 1 });

function snapshot(id = "snap1", extra = {}) {
  return {
    format: "reading-village-snapshot", v: 1, snapshot_id: id, published_at: TS, source: { commit: "abc", progress_rev: 5 },
    progress: progress(), events: [ev({ type: "session_start" })],
    village: { enabled: true, wallet: { emerald: 99 }, points: 3 },
    treasure: { treasure: [], enabled: true, server_running: true, problem: null, rev: 5 },
    history: { v: 1, kind: null, count: 2, lines: [{ kind: "earn" }, { kind: "treasure" }], totals: { earned: {} } },
    imported: {}, ...extra,
  };
}

/** A fake Storage; `failWrites` makes setItem throw (quota). */
function fakeStorage(initial = {}) {
  const m = new Map(Object.entries(initial));
  return { m, failWrites: false, getItem(k) { return m.has(k) ? m.get(k) : null; }, setItem(k, v) { if (this.failWrites) throw new Error("quota exceeded"); m.set(k, v); } };
}

async function boot({ snap = snapshot(), storage = fakeStorage(), now = new Date(2026, 9, 21, 9, 5), ids } = {}) {
  let n = 0;
  const b = await createOffline({
    fetchJson: async () => structuredClone(snap), getStorage: () => storage, loadLevelsCfg: async () => LEVELS,
    now: () => now, uuid: ids ?? (() => `uuid-${++n}`),
  }).boot();
  return { b, storage, snap };
}
const rejects = async (p, status, re) => {
  await assert.rejects(Promise.resolve().then(p), (e) => { assert.ok(e instanceof ApiError, `ApiError expected, got ${e}`); assert.equal(e.status, status); if (re) assert.match(e.message, re); return true; });
};
const saved = (storage) => JSON.parse(storage.getItem(STORAGE_KEY));

test("boot adopts the snapshot in a fresh browser and persists the local state", async () => {
  const { b, storage } = await boot();
  const s = saved(storage);
  assert.equal(s.v, 1);
  assert.equal(s.device_id, "uuid-1");
  assert.equal(s.base.snapshot_id, "snap1");
  assert.deepEqual(s.progress, progress());
  assert.deepEqual(s.events, []);
  assert.equal(s.last_export, null);
  assert.deepEqual(b.request("GET", "/api/progress"), progress());
});

test("boot failures are loud plain Errors: snapshot fetch, bad snapshot, no storage, bad local state", async () => {
  const mk = (over) => createOffline({ fetchJson: async () => snapshot(), getStorage: () => fakeStorage(), loadLevelsCfg: async () => LEVELS, ...over }).boot();
  await assert.rejects(mk({ fetchJson: async () => { throw new Error("HTTP 404"); } }), /Could not load Sam's status from the website: HTTP 404/);
  await assert.rejects(mk({ fetchJson: async () => ({ ...snapshot(), v: 2 }) }), /snapshot\.json: v must be 1/);
  await assert.rejects(mk({ getStorage: () => { throw new Error("denied"); } }), /cannot keep Sam's progress \(denied\)/);
  const noWrite = fakeStorage(); noWrite.failWrites = true;
  await assert.rejects(mk({ getStorage: () => noWrite }), /cannot keep Sam's progress \(quota exceeded\)/);
  await assert.rejects(mk({ getStorage: () => fakeStorage({ [STORAGE_KEY]: "{nope" }) }), /not valid JSON/);
  await assert.rejects(mk({ getStorage: () => fakeStorage({ [STORAGE_KEY]: JSON.stringify({ v: 1 }) }) }), /device_id must be a non-empty string/);
});

test("PUT /api/progress: rev+1, drops cause, rejects a stale rev with the server's text", async () => {
  const { b, storage } = await boot();
  const p = b.request("GET", "/api/progress");
  p.inventory.wood += 1;
  const out = b.request("PUT", "/api/progress", { ...p, cause: word() });
  assert.equal(out.rev, 6);
  assert.equal(out.inventory.wood, 3);
  assert.ok(!("cause" in out));
  assert.equal(saved(storage).progress.rev, 6);
  await rejects(() => b.request("PUT", "/api/progress", p), 409, /^rev mismatch: saved progress is at rev 6, this save was based on rev 5$/);
});

test("PUT /api/progress: village and treasure are server-owned (400), missing reads as the default", async () => {
  const { b } = await boot();
  const p = b.request("GET", "/api/progress");
  await rejects(() => b.request("PUT", "/api/progress", { ...p, village: { ...p.village, bells_spent: 0 } }), 400, /^village: is owned by the server and cannot be changed by a save$/);
  await rejects(() => b.request("PUT", "/api/progress", { ...p, treasure: [] }), 400, /^treasure: is owned by the server/);
  await rejects(() => b.request("PUT", "/api/progress", { ...p, cause: { type: "word" } }), 400);
  assert.equal(b.request("GET", "/api/progress").rev, 5, "a refused save changes nothing");
});

test("a failed storage write is an ApiError and leaves the state as it was", async () => {
  const { b, storage } = await boot();
  const p = b.request("GET", "/api/progress");
  storage.failWrites = true;
  await rejects(() => b.request("PUT", "/api/progress", p), 500, /could not save in this browser \(quota exceeded\)/);
  await rejects(() => b.request("POST", "/api/event", word()), 500, /could not save/);
  assert.equal(b.request("GET", "/api/progress").rev, 5);
  assert.equal(b.request("GET", "/api/events").length, 1);
  storage.failWrites = false;
  assert.equal(b.request("PUT", "/api/progress", p).rev, 6);
});

test("event field table matches the server's per-type table, and bad events are 400 naming the field", async () => {
  const src = readFileSync(new URL("../../server.py", import.meta.url), "utf8");
  const block = src.slice(src.indexOf("EVENT_FIELDS = {"), src.indexOf("}", src.indexOf("EVENT_FIELDS = {")));
  const py = [...block.matchAll(/"(\w+)": \(\(([^)]*)\), \(([^)]*)\)\)/g)].map((m) => [m[1], [m[2], m[3]].map((t) => [...t.matchAll(/"(\w+)"/g)].map((x) => x[1]))]);
  assert.equal(py.length, Object.keys(EVENT_FIELDS).length);
  for (const [type, fields] of py) assert.deepEqual(EVENT_FIELDS[type], fields, `EVENT_FIELDS.${type} drifted from server.py`);

  const { b } = await boot();
  const bad = (e, re) => rejects(() => b.request("POST", "/api/event", e), 400, re);
  await bad(ev({ type: "word", track: "smallcaps", item: "cat" }), /^result: is required for type word/);
  await bad(ev({ type: "word", track: "smallcaps", item: "cat", result: "correct", bogus: 1 }), /^bogus: unknown field/);
  await bad(ev({ type: "session_start", item: "x" }), /^item: not allowed for type session_start/);
  await bad(ev({ type: "nope" }), /^type: must be one of/);
  await bad({ ...word(), ts: "2026-10-21T10:00:00" }, /^ts: must be an ISO-8601/);
  await bad({ ...word(), v: 2 }, /^v: /);
  await bad({ ...word(), level: 7 }, /^level: 7 is above the top level of blocks \(6\)/);
  await bad(ev({ type: "card", track: "lowercase", item: "z", result: "correct" }), /^item: must be one of/);
  await bad(ev({ type: "craft", track: "smallcaps", item: "cat", result: "correct" }), /^item: must be a 3 to 10 letter capital/);
  await bad(ev({ type: "block_placed", cell: [12, 0], block: "wood" }), /^cell: /);
  await bad(ev({ type: "swap_done", track: "smallcaps", story_id: "s", percent: 50 }), /^track: must be "lowercase"/);
  assert.equal(b.request("GET", "/api/events").length, 1, "refused events are not stored");
  assert.deepEqual(b.request("POST", "/api/event", ev({ type: "block_placed", cell: [3, 2], block: "wood" })), { ok: true });
  assert.doesNotThrow(() => validateEvent(ev({ type: "adventure_done", adventure: "smallcaps" })));
});

test("POST /api/event appends, GET /api/events is snapshot + local, no treasure in the reply", async () => {
  const { b, storage } = await boot();
  const r = b.request("POST", "/api/event", word());
  assert.deepEqual(r, { ok: true });
  const all = b.request("GET", "/api/events");
  assert.equal(all.length, 2);
  assert.equal(all[0].type, "session_start");
  assert.equal(all[1].type, "word");
  assert.equal(saved(storage).events.length, 1);
});

test("level-up: the 10th independent correct word reaches blocks level 2 once; celebrated and snapshot levels are not repeated", async () => {
  const { b, storage } = await boot();
  const replies = [];
  for (let i = 0; i < 10; i++) replies.push(b.request("POST", "/api/event", word()));
  assert.ok(replies.slice(0, 9).every((r) => r.game_level_ups === undefined));
  assert.deepEqual(replies[9].game_level_ups, [{ game: "blocks", level: 2 }]);
  assert.deepEqual(saved(storage).celebrated, [{ game: "blocks", level: 2 }]);
  assert.equal(b.request("POST", "/api/event", word()).game_level_ups, undefined);

  // A level reached on Dad's side (in the snapshot's events) is not "new" here.
  const snapEvents = Array.from({ length: 10 }, () => word());
  const { b: b2 } = await boot({ snap: snapshot("snap1", { events: snapEvents }) });
  assert.equal(b2.request("POST", "/api/event", ev({ ...word(), level: 2 })).game_level_ups, undefined);

  // Already celebrated here (e.g. a reload with celebrated stored) -> not shown again even if re-derived.
  const s = saved(storage);
  s.events = []; s.celebrated = [{ game: "blocks", level: 2 }];
  const st2 = fakeStorage({ [STORAGE_KEY]: JSON.stringify(s) });
  const { b: b3 } = await boot({ storage: st2 });
  let last;
  for (let i = 0; i < 10; i++) last = b3.request("POST", "/api/event", word());
  assert.equal(last.game_level_ups, undefined);
});

test("GET routes: village wallet = local inventory, treasure/minecraft are off, history filters by kind", async () => {
  const { b } = await boot();
  const p = b.request("GET", "/api/progress");
  p.inventory.emerald = 12;
  b.request("PUT", "/api/progress", p);
  const v = b.request("GET", "/api/village");
  assert.equal(v.wallet.emerald, 12);
  assert.equal(v.points, 3);
  const t = b.request("GET", "/api/treasure");
  assert.equal(t.enabled, false); assert.equal(t.server_running, false); assert.equal(t.problem, "Sending happens at Dad's house");
  assert.equal(t.treasure.length, 0);
  assert.deepEqual(b.request("GET", "/api/minecraft"), { enabled: false, worker_running: false, server_running: false, pending: [], failed: [], recent: [], chests: [], problem: "Minecraft is at Dad's house" });
  const all = b.request("GET", "/api/history");
  assert.equal(all.kind, null); assert.equal(all.count, 2);
  const earn = b.request("GET", "/api/history?kind=earn");
  assert.equal(earn.kind, "earn"); assert.equal(earn.count, 1); assert.deepEqual(earn.totals, { earned: {} });
  await rejects(() => b.request("GET", "/api/history?kind=zzz"), 400, /only \?kind=/);
  await rejects(() => b.request("GET", "/api/history?x=1"), 400, /only \?kind=/);
  await rejects(() => b.request("GET", "/api/nothing"), 404);
});

test("village, shop, send and reset POSTs are 409 \"That happens at Dad's house\"", async () => {
  const { b } = await boot();
  for (const path of ["/api/village/unlock", "/api/village/promote", "/api/shop/buy", "/api/shop/trade", "/api/treasure/send", "/api/reset"]) {
    await rejects(() => b.request("POST", path, {}), 409, /^That happens at Dad's house$/);
  }
});

test("snapshot adoption rule (§1.1)", async () => {
  const mkLocal = (events, progressChanged = false) => ({ device_id: "dev", base: { snapshot_id: "snap1", progress: progress() }, progress: progressChanged ? { ...progress(), rev: 9, stories: { s: { page: 2 } } } : progress(), events });
  const snap = (imported) => ({ snapshot_id: "snap2", imported });
  assert.equal(shouldAdopt(mkLocal([word()]), { snapshot_id: "snap1", imported: {} }), false, "same snapshot: nothing to adopt");
  assert.equal(shouldAdopt(mkLocal([word()]), snap({})), false, "unsent play keeps the old base");
  assert.equal(shouldAdopt(mkLocal([word(), word()]), snap({ dev: { base_snapshot_id: "snap1", events: 1 } })), false, "import covers fewer events");
  assert.equal(shouldAdopt(mkLocal([word()]), snap({ dev: { base_snapshot_id: "other", events: 5 } })), false, "receipt for a different base");
  assert.equal(shouldAdopt(mkLocal([word()]), snap({ other: { base_snapshot_id: "snap1", events: 5 } })), false, "receipt for a different device");
  assert.equal(shouldAdopt(mkLocal([word(), word()]), snap({ dev: { base_snapshot_id: "snap1", events: 2 } })), true);
  assert.equal(shouldAdopt(mkLocal([word()]), snap({ dev: { base_snapshot_id: "snap1", events: 3 } })), true);
  assert.equal(shouldAdopt(mkLocal([]), snap({})), true, "nothing made here: nothing to lose");
  assert.equal(shouldAdopt(mkLocal([], true), snap({})), false, "progress changed without events: keep it");

  // End to end through boot: play, then a newer snapshot with and without the import receipt.
  const storage = fakeStorage();
  const { b } = await boot({ storage });
  b.request("POST", "/api/event", word());
  const deviceId = saved(storage).device_id;
  const keep = await boot({ storage, snap: snapshot("snap2") });
  assert.equal(saved(storage).base.snapshot_id, "snap1");
  assert.equal(keep.b.unsentCount(), 1);
  assert.equal(keep.b.request("GET", "/api/events").length, 2, "snapshot(snap2) events + 1 local event, old base kept");
  const adopted = await boot({ storage, snap: snapshot("snap2", { imported: { [deviceId]: { base_snapshot_id: "snap1", events: 1 } }, progress: { ...progress(8) } }) });
  const s = saved(storage);
  assert.equal(s.base.snapshot_id, "snap2");
  assert.equal(s.device_id, deviceId, "device id never changes");
  assert.deepEqual(s.events, []);
  assert.equal(s.progress.rev, 8);
  assert.equal(adopted.b.unsentCount(), 0);
});

test("review fix: progress changed without an event is unsent and blocks adoption until exported and imported", async () => {
  const mk = (over = {}) => ({ device_id: "dev", base: { snapshot_id: "snap1", progress: progress() }, progress: progress(), events: [word()], last_export: null, ...over });
  const covers = { snapshot_id: "snap2", imported: { dev: { base_snapshot_id: "snap1", events: 1 } } };
  const changed = { ...progress(), stories: { s: { page: 3 } } };
  assert.equal(shouldAdopt(mk(), covers), true, "events covered, progress as at base");
  assert.equal(shouldAdopt(mk({ progress: changed }), covers), false, "receipt covers events but a progress change was never exported");
  // End to end: story resume page saved with no event after the export.
  const storage = fakeStorage();
  const { b } = await boot({ storage });
  b.request("POST", "/api/event", word());
  b.makeExport();
  assert.equal(b.unsentCount(), 0);
  const p = b.request("GET", "/api/progress");
  p.stories = { s: { page: 4 } };
  b.request("PUT", "/api/progress", p);
  assert.deepEqual(unsentParts(saved(storage)), { events: 0, progress: true });
  assert.equal(b.unsentCount(), 1, "Home must not say All sent");
  const id = saved(storage).device_id;
  const imp = { imported: { [id]: { base_snapshot_id: "snap1", events: 1 } } };
  await boot({ storage, snap: snapshot("snap2", imp) });
  assert.equal(saved(storage).base.snapshot_id, "snap1", "unsent progress must not be discarded by adopting");
  assert.equal(saved(storage).progress.stories.s.page, 4);
  b.makeExport();
  assert.equal(b.unsentCount(), 0);
  await boot({ storage, snap: snapshot("snap2", imp) });
  assert.equal(saved(storage).base.snapshot_id, "snap2", "once exported (and imported) the new base is adopted");
});

test("export file shape (§3): client-owned keys only, cumulative, last_export recorded, state not cleared", async () => {
  const { b, storage } = await boot({ now: new Date(2026, 9, 21, 9, 5) });
  b.request("POST", "/api/event", word());
  const p = b.request("GET", "/api/progress");
  p.inventory.wood += 1;
  b.request("PUT", "/api/progress", p);
  assert.equal(b.unsentCount(), 2, "1 event + progress changed");

  const x = b.makeExport();
  assert.equal(x.filename, "reading-village-2026-10-21-0905.json");
  assert.equal(x.count, 1);
  const f = JSON.parse(x.text);
  assert.deepEqual(Object.keys(f), ["format", "v", "export_id", "device_id", "created", "base", "progress", "events"]);
  assert.equal(f.format, "reading-village-export");
  assert.equal(f.v, 1);
  assert.equal(f.export_id, "uuid-2");
  assert.equal(f.device_id, "uuid-1");
  assert.match(f.created, /^2026-10-21T09:05:00[+-]\d\d:\d\d$/);
  assert.equal(f.base.snapshot_id, "snap1");
  assert.deepEqual(Object.keys(f.base.progress).sort(), [...CLIENT_OWNED].sort());
  assert.deepEqual(Object.keys(f.progress).sort(), [...CLIENT_OWNED].sort());
  assert.equal(f.base.progress.inventory.wood, 2);
  assert.equal(f.progress.inventory.wood, 3);
  assert.equal("village" in f.progress || "treasure" in f.progress || "rev" in f.progress, false);
  assert.equal(f.events.length, 1);
  assert.equal(f.events[0].type, "word");

  const s = saved(storage);
  assert.deepEqual(s.last_export, { at: s.last_export.at, events: 1, progress_fp: s.last_export.progress_fp });
  assert.match(s.last_export.progress_fp, /^\{/, "the export's progress fingerprint is recorded");
  assert.equal(s.events.length, 1, "exports are cumulative: local state is not cleared");
  assert.equal(b.unsentCount(), 0);
  b.request("POST", "/api/event", word());
  assert.equal(b.unsentCount(), 1);
  assert.equal(JSON.parse(b.makeExport().text).events.length, 2, "the next export carries everything since base");
});

test("export of a progress with no `crafted` writes crafted:{} (the documented default); other missing keys are loud", async () => {
  const snap = snapshot(); delete snap.progress.crafted;
  const { b } = await boot({ snap });
  assert.deepEqual(JSON.parse(b.makeExport().text).progress.crafted, {});
  const snap2 = snapshot(); delete snap2.progress.house;
  const { b: b2 } = await boot({ snap: snap2 });
  assert.throws(() => b2.makeExport(), /no "house"/);
});

test("an export that cannot be recorded throws and does not pretend it was sent", async () => {
  const { b, storage } = await boot();
  b.request("POST", "/api/event", word());
  storage.failWrites = true;
  assert.throws(() => b.makeExport(), (e) => e instanceof ApiError && /could not save/.test(e.message));
  assert.equal(b.unsentCount(), 1);
});

test("a second tab cannot overwrite the first tab's events: the write is refused with a 409", async () => {
  const storage = fakeStorage();
  const { b: tab1 } = await boot({ storage });
  const { b: tab2 } = await boot({ storage }); // booted earlier than tab1's play, same storage
  for (let i = 0; i < 5; i++) tab1.request("POST", "/api/event", word());
  assert.equal(saved(storage).events.length, 5);
  await rejects(() => tab2.request("POST", "/api/event", ev({ type: "session_start" })), 409, /another tab/);
  assert.equal(saved(storage).events.length, 5);
});
