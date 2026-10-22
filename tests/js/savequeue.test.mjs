import test from "node:test";
import assert from "node:assert/strict";
import { createCommitter, SKIP } from "../../app/js/savequeue.js";
import { ApiError } from "../../app/js/api.js";

/** An in-memory server with the real rev rules: PUT must carry the stored rev, else 409. */
function fakeServer(initial) {
  const srv = { progress: { v: 1, rev: 0, inventory: { wood: 0 }, house: [], settings: { font: "system", sound: "on" }, ...initial }, events: [], puts: 0, inflight: 0, maxInflight: 0, failNext: 0 };
  srv.api = {
    getProgress: async () => structuredClone(srv.progress),
    putProgress: async (p) => {
      srv.inflight++; srv.maxInflight = Math.max(srv.maxInflight, srv.inflight);
      await new Promise((r) => setTimeout(r, 5));
      srv.inflight--; srv.puts++;
      if (srv.failNext > 0) { srv.failNext--; throw new ApiError("server said HTTP 500: disk full", 500); }
      if (p.rev !== srv.progress.rev) throw new ApiError(`server said HTTP 409: rev mismatch`, 409);
      srv.progress = { ...structuredClone(p), rev: p.rev + 1 };
      return structuredClone(srv.progress);
    },
    postEvent: async (e) => { srv.events.push(e); return { ok: true }; },
  };
  return srv;
}
function setup(initial) {
  const srv = fakeServer(initial);
  const state = { progress: structuredClone(srv.progress), locked: false };
  const locks = [];
  const c = createCommitter({ api: srv.api, state, makeEvent: (f) => ({ v: 1, ...f }), onProgress: () => {}, onLock: (r, retry) => locks.push({ r, retry }), onUnlock: () => {} });
  return { srv, state, c, locks };
}

test("saves are serialised: overlapping commits never produce overlapping PUTs, and none are lost", async () => {
  const { srv, c, state } = setup();
  await Promise.all(Array.from({ length: 10 }, () => c.commit(null, (p) => { p.inventory.wood += 1; })));
  assert.equal(srv.maxInflight, 1);
  assert.equal(srv.progress.inventory.wood, 10);
  assert.equal(srv.progress.rev, 10);
  assert.equal(state.progress.rev, 10);
});

test("H3: a stale tab gets a 409, re-applies the same mutation to fresh state, and keeps the other tab's change", async () => {
  const { srv, c } = setup();
  srv.progress = { ...srv.progress, rev: 1, settings: { font: "system", sound: "off" }, inventory: { wood: 5 } }; // another tab saved
  await c.commit(null, (p) => { p.inventory.wood += 1; });
  assert.equal(srv.progress.inventory.wood, 6); // 5 from the other tab + ours
  assert.equal(srv.progress.settings.sound, "off"); // not clobbered
  assert.equal(srv.progress.rev, 2);
  assert.equal(srv.puts, 2); // one rejected, one accepted
});

test("a second 409 in a row locks with the NOT SAVED banner instead of looping", async () => {
  const { srv, c, locks, state } = setup();
  const realPut = srv.api.putProgress;
  srv.api.putProgress = async (p) => { srv.progress = { ...srv.progress, rev: srv.progress.rev + 1 }; return realPut(p); }; // always stale
  const done = c.commit(null, (p) => { p.inventory.wood += 1; });
  await new Promise((r) => setTimeout(r, 100));
  assert.equal(state.locked, true);
  assert.equal(locks.length, 1);
  assert.match(locks[0].r, /twice/);
  srv.api.putProgress = realPut;
  await locks[0].retry(); // Dad taps "Try saving again": fresh progress, then the save goes through
  await done;
  assert.equal(state.locked, false);
  assert.equal(srv.progress.inventory.wood, 1);
});

test("H4: a mutation that returns SKIP saves nothing and logs no event (double-click on one Build cell)", async () => {
  const { srv, c } = setup({ inventory: { wood: 1 } });
  const place = () => c.commit({ type: "block_placed" }, (p) => {
    if (p.house.some((b) => b.x === 0 && b.y === 0)) return SKIP;
    if (p.inventory.wood < 1) return SKIP;
    p.inventory.wood -= 1;
    p.house.push({ x: 0, y: 0, block: "wood" });
  });
  const [a, b] = await Promise.all([place(), place()]);
  assert.deepEqual([a, b], [true, false]);
  assert.equal(srv.events.filter((e) => e.type === "block_placed").length, 1);
  assert.equal(srv.progress.house.length, 1);
  assert.equal(srv.progress.inventory.wood, 0);
});

test("with no blocks left the click is ignored before anything is saved", async () => {
  const { srv, c } = setup({ inventory: { wood: 0 } });
  assert.equal(await c.commit({ type: "block_placed" }, (p) => (p.inventory.wood < 1 ? SKIP : undefined)), false);
  assert.equal(srv.puts, 0);
  assert.equal(srv.events.length, 0);
});

test("a failing save locks loudly, and resumes (without double-logging the event) after Dad retries", async () => {
  const { srv, c, locks, state } = setup();
  srv.failNext = 1;
  const done = c.commit({ type: "word" }, (p) => { p.inventory.wood += 1; });
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(state.locked, true);
  assert.match(locks[0].r, /disk full/);
  assert.equal(srv.events.length, 0);
  await locks[0].retry();
  await done;
  assert.equal(srv.events.filter((e) => e.type === "word").length, 1);
  assert.equal(srv.progress.inventory.wood, 1);
});

test("a progress document without an integer rev is a loud error, not a default", async () => {
  const { srv, c } = setup();
  srv.api.getProgress = async () => ({ v: 1, inventory: {} });
  await assert.rejects(c.load(), /rev/);
});

test("onEvent receives every event reply; a reply with treasure refreshes progress (no stale-rev 409 next save)", async () => {
  const srv = fakeServer();
  const state = { progress: structuredClone(srv.progress), locked: false };
  const replies = [];
  srv.api.postEvent = async (e) => {
    srv.events.push(e);
    if (e.type === "craft") { srv.progress = { ...srv.progress, rev: srv.progress.rev + 1, treasure: [{ tid: "t1" }] }; return { ok: true, treasure: [{ label: "x", sprite: "pig" }] }; }
    return { ok: true };
  };
  const c = createCommitter({ api: srv.api, state, makeEvent: (f) => ({ v: 1, ...f }), onProgress: () => {}, onLock: () => {}, onUnlock: () => {}, onEvent: (r) => replies.push(r) });
  await c.commit({ type: "word" }, (p) => { p.inventory.wood += 1; });
  await c.commit({ type: "craft" }, (p) => { p.inventory.wood += 1; });
  assert.equal(replies.length, 2);
  assert.deepEqual(replies[1].treasure, [{ label: "x", sprite: "pig" }]);
  assert.equal(state.progress.rev, srv.progress.rev, "client copy was refreshed after the treasure reply");
  assert.deepEqual(state.progress.treasure, [{ tid: "t1" }]);
});

test("an onEvent that throws (a malformed reply) propagates: no silent swallow", async () => {
  const srv = fakeServer();
  const state = { progress: structuredClone(srv.progress), locked: false };
  const c = createCommitter({ api: srv.api, state, makeEvent: (f) => ({ v: 1, ...f }), onProgress: () => {}, onLock: () => {}, onUnlock: () => {}, onEvent: () => { throw new Error("bad reply"); } });
  await assert.rejects(c.commit({ type: "word" }, null), /bad reply/);
});

test("a retried event is the IDENTICAL event (same ts): the real makeEvent stamps a new ts on every call", async () => {
  const srv = fakeServer();
  const state = { progress: structuredClone(srv.progress), locked: false };
  const locks = [];
  let clock = 0;
  const makeEvent = (f) => ({ v: 1, ts: `t${++clock}`, session_id: "s", ...f }); // like store.js makeEvent: fresh ts per call
  let failEvent = 1;
  srv.api.postEvent = async (e) => {
    if (failEvent-- > 0) throw new ApiError("server said HTTP 500: events.jsonl: disk full", 500);
    srv.events.push(e);
    return { ok: true };
  };
  const c = createCommitter({ api: srv.api, state, makeEvent, onProgress: () => {}, onLock: (r, retry) => locks.push(retry), onUnlock: () => {} });
  const done = c.commit({ type: "craft", item: "PIG" }, (p) => { p.inventory.wood += 1; });
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(state.locked, true);
  await locks[0]();
  await done;
  assert.equal(srv.events.length, 1);
  assert.equal(srv.events[0].ts, "t1", "the event posted after the retry is the one built before the first attempt");
  assert.equal(clock, 1, "makeEvent ran once");
});

test("the progress PUT carries the event it belongs to as `cause` (so earn/spend history lines name it)", async () => {
  const srv = fakeServer();
  const state = { progress: structuredClone(srv.progress), locked: false };
  const causes = [];
  const realPut = srv.api.putProgress;
  srv.api.putProgress = async (p, cause) => { causes.push(cause); return realPut(p); };
  const c = createCommitter({ api: srv.api, state, makeEvent: (f) => ({ v: 1, ts: "t", ...f }), onProgress: () => {}, onLock: () => {}, onUnlock: () => {} });
  await c.commit({ type: "word", item: "pig" }, (p) => { p.inventory.wood += 1; });
  await c.commit(null, (p) => { p.inventory.wood += 1; });
  assert.deepEqual(causes, [srv.events[0], undefined]);
});
