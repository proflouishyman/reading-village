import test from "node:test";
import assert from "node:assert/strict";
import { sessionsFrom, letterReport, confusions, trickyWords } from "../../app/js/stats.js";

const ev = (o) => ({ v: 1, ts: "2026-10-18T09:00:00-04:00", session_id: "s1", ...o });

test("sessions: duration from start to end, or to last event when not ended", () => {
  const s = sessionsFrom([
    ev({ type: "session_start" }), ev({ type: "session_end", ts: "2026-10-18T09:10:00-04:00" }),
    ev({ session_id: "s2", type: "session_start" }), ev({ session_id: "s2", type: "card", ts: "2026-10-18T09:01:30-04:00" }),
  ]);
  assert.deepEqual(s.map((x) => [x.seconds, x.ended]), [[600, true], [90, false]]);
});

test("letter report, confusions, tricky words", () => {
  const events = [
    ev({ type: "card", item: "b", result: "correct" }), ev({ type: "card", item: "b", result: "assisted" }),
    ev({ type: "match", item: "b", result: "miss", chosen: "d" }), ev({ type: "match", item: "b", result: "miss", chosen: "d" }),
    ev({ type: "tricky_word", item: "pig", story_id: "x" }), ev({ type: "tricky_word", item: "pig", story_id: "x" }),
    ev({ type: "tricky_word", item: "bed", story_id: "x" }),
  ];
  assert.deepEqual(letterReport(events, "b"), { independent: 1, assisted: 1, miss: 2, trend: [0.25] });
  assert.deepEqual(confusions(events), [{ target: "b", chosen: "d", n: 2 }]);
  assert.deepEqual(trickyWords(events), [{ word: "pig", n: 2 }, { word: "bed", n: 1 }]);
});

import { smallcapsPasses, wordAccuracy } from "../../app/js/stats.js";

const sev = (type, ts, extra = {}) => ({ v: 1, ts, session_id: "s1", type, track: "smallcaps", story_id: "gold-pig", ...extra });

test("smallcapsPasses: seconds per page and taps per 10 pages", () => {
  const events = [
    sev("story_page", "2026-10-18T10:00:00-04:00", { page: 0 }),
    sev("story_page", "2026-10-18T10:00:10-04:00", { page: 1 }),
    sev("tricky_word", "2026-10-18T10:00:12-04:00", { item: "dog" }),
    sev("story_page", "2026-10-18T10:00:30-04:00", { page: 2 }),
    sev("story_page", "2026-10-18T10:00:40-04:00", { page: 3 }),
    sev("story_page", "2026-10-18T10:00:00-04:00", { page: 0, track: "lowercase" }), // ignored
  ];
  const [r, ...rest] = smallcapsPasses(events);
  assert.equal(rest.length, 0);
  assert.equal(r.pages, 4);
  assert.equal(r.seconds, 40);
  assert.equal(r.secPerPage, 40 / 3);
  assert.equal(r.taps, 1);
  assert.equal(r.tapsPer10, 2.5);
});

test("wordAccuracy: last n small-caps words, independent-correct only", () => {
  const w = (result, track = "smallcaps") => ({ type: "word", track, result });
  assert.equal(wordAccuracy([]), null);
  const a = wordAccuracy([w("miss"), w("correct"), w("assisted"), w("correct"), w("correct", "lowercase")], 3);
  assert.deepEqual(a, { n: 3, correct: 2, share: 2 / 3 });
});

import { swapByPercent } from "../../app/js/stats.js";

test("swapByPercent: per-percent seconds per page and taps per 10 pages", () => {
  const e = (type, ts, extra) => ({ type, ts, session_id: "s", story_id: "g", track: "lowercase", percent: 30, ...extra });
  const out = swapByPercent([
    e("swap_page", "2026-10-18T10:00:00-04:00"), e("swap_page", "2026-10-18T10:00:20-04:00"),
    e("tricky_word", "2026-10-18T10:00:21-04:00", { item: "x" }),
    e("swap_page", "2026-10-18T10:05:00-04:00", { percent: 50 }),
    e("swap_page", "2026-10-18T10:05:10-04:00", { percent: 50 }),
  ]);
  assert.deepEqual(out, [
    { percent: 30, pages: 2, secPerPage: 20, tapsPer10: 5 },
    { percent: 50, pages: 2, secPerPage: 10, tapsPer10: 0 }]);
});
