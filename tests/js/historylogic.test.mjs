// historylogic.js: strict validation of GET /api/history, Dad's summary, Sam's book rows and pictures.
import test from "node:test";
import assert from "node:assert/strict";
import { validateHistory, validateHistoryLine, summary, describeLine, bookRow, pictureFor, newestFirst, KINDS, BOOK_KINDS } from "../../app/js/historylogic.js";

const line = (kind, what, over = {}) => ({ v: 1, ts: "2026-10-18T09:00:00-04:00", kind, what, wallet_after: null, ref: "r1", ...over });
const TAG = [{ item: "minecraft:name_tag", count: 2 }];
const LINES = [
  line("earn", { resources: { wood: 1, emerald: 1 }, last_event: { type: "word", item: "pig" } }, { wallet_after: { emerald: 3, wood: 4 } }),
  line("earn", { resources: { emerald: 5 }, last_event: null }),
  line("trade", { trade_id: "wood10", give: { wood: 10 }, get: { emerald: 1 } }),
  line("spend", { resource: "emerald", amount: 2, on: "Name Tags", offer_id: "lib_nametag" }),
  line("treasure", { tid: "t000001", label: "Name Tags", items: TAG, source: { kind: "shop", ref: "lib_nametag" } }),
  line("unlock", { profession: "librarian", name: "Librarian", paid: "free" }),
  line("level", { index: 1, name: "Apprentice", points: 30 }),
  line("send", { tids: ["t000001"], items: TAG }),
  line("delivered", { delivery: "d000001", tid: "t000001", label: "Name Tags", items: TAG, chest: { x: 1, y: 2, z: 3 }, log: ["Dropped 2 [Name Tag]"] }),
  line("delivery_failed", { delivery: "d000002", tid: "t000002", error: "chest full" }),
];
const PROMOTE = line("promote", { profession: "armorer", name: "Armorer", from_level: 0, level: 1, level_name: "Apprentice", spent: 54 }, { ref: "armorer" });
const body = (lines = LINES, over = {}) => ({ v: 1, kind: null, count: lines.length, lines,
  totals: { earned: { wood: 1, emerald: 6 }, spent: { emerald: 2 }, sent: { "minecraft:name_tag": 2 }, delivered: { "minecraft:name_tag": 2 }, unlocked: ["librarian"], levels: [1] }, ...over });
const PILE = new Map([["t000001", { sprite: "name_tag", label: "Name Tags" }]]);

test("every kind has a valid example and the shipped reply shape is accepted", () => {
  assert.deepEqual([...new Set([...LINES, PROMOTE].map((l) => l.kind))].sort(), [...KINDS].sort());
  assert.ok(validateHistory(body([...LINES, PROMOTE])));
  const b = body();
  assert.equal(validateHistory(b), b);
  assert.ok(validateHistory(body([])));
});

test("validation is strict: reply shape, count, kind filter, line fields, versions", () => {
  assert.throws(() => validateHistory(LINES), /must be an object/);
  assert.throws(() => validateHistory(body(LINES, { count: 3 })), /count/);
  assert.throws(() => validateHistory(body(LINES, { v: 2 })), /\.v/);
  assert.throws(() => validateHistory(body([LINES[0]], { kind: "send" })), /asked for send/);
  assert.ok(validateHistory(body([LINES[7]], { kind: "send" })));
  const { totals, ...noTotals } = body();
  assert.throws(() => validateHistory(noTotals), /totals/);
  assert.throws(() => validateHistory(body(LINES, { totals: { ...body().totals, extra: 1 } })), /unknown field "extra"/);
  assert.throws(() => validateHistory(body(LINES, { totals: { ...body().totals, earned: { wood: 0 } } })), /totals\.earned/);
  assert.throws(() => validateHistory(body([LINES[0], line("earn", { resources: { wood: 0 }, last_event: null })])), /lines\[1\].*resources\.wood/);
  assert.throws(() => validateHistoryLine(line("mystery", {})), /kind/);
  assert.throws(() => validateHistoryLine(line("earn", LINES[0].what, { v: 2 })), /\.v/);
  assert.throws(() => validateHistoryLine({ ...LINES[0], extra: 1 }), /unknown field "extra"/);
  const { wallet_after, ...noWallet } = LINES[0];
  assert.throws(() => validateHistoryLine(noWallet), /missing "wallet_after"/);
  assert.throws(() => validateHistoryLine(line("earn", LINES[0].what, { ts: "yesterday" })), /ISO/);
  assert.throws(() => validateHistoryLine(line("earn", LINES[0].what, { wallet_after: { wood: -1 } })), /wallet_after/);
  assert.throws(() => validateHistoryLine(line("unlock", { profession: "x", name: "X", paid: "gold" })), /paid/);
  assert.throws(() => validateHistoryLine(line("send", { tids: [], items: TAG })), /tids/);
  assert.throws(() => validateHistoryLine(line("delivered", { ...LINES[8].what, log: "one string" })), /log/);
  assert.throws(() => validateHistoryLine(line("treasure", { tid: "t1", label: "x", items: [], source: { kind: "shop", ref: "r" } })), /items/);
});

test("summary: the server's totals plus villager and level names and the failed count", () => {
  const s = summary(body());
  assert.deepEqual(s.earned, { wood: 1, emerald: 6 });
  assert.deepEqual(s.delivered, { "minecraft:name_tag": 2 });
  assert.deepEqual(s.villagers, ["Librarian"]);
  assert.deepEqual(s.levels, ["Apprentice"]);
  assert.equal(s.failed, 1);
});

test("Sam's book shows only earned and sent kinds, with pictures, newest first", () => {
  const rows = newestFirst(LINES).filter((l) => BOOK_KINDS.includes(l.kind)).map((l) => bookRow(l, PILE));
  assert.equal(rows.length, 7);
  assert.equal(rows[0].text, "Name Tags is in your Magic Chest!", "newest first (the failure line is Dad's)");
  assert.deepEqual(bookRow(LINES[0], PILE).sprites, [{ name: "wood" }, { name: "emerald_item" }]);
  assert.deepEqual(bookRow(LINES[5], PILE).sprites, [{ name: "villager_librarian" }]);
  assert.deepEqual(bookRow(LINES[6], PILE).sprites, [{ name: "badge_iron" }]);
  assert.deepEqual(bookRow(LINES[7], PILE), { sprites: [{ name: "name_tag" }], text: "You sent 1 treasure!", placeholders: 0 });
  assert.equal(bookRow(LINES[2], PILE), null, "trade is Dad's bookkeeping");
  assert.equal(newestFirst(LINES)[0], LINES[9]);
  assert.equal(LINES[0].kind, "earn", "newestFirst does not mutate its input");
});

test("a treasure's picture: the pile's sprite, else its item's sprite, else a COUNTED chest placeholder", () => {
  assert.deepEqual(pictureFor("t000001", TAG, PILE), { name: "name_tag", source: "pile" });
  assert.deepEqual(pictureFor("t9", [{ item: "minecraft:diamond" }], PILE), { name: "diamond", source: "item" });
  assert.deepEqual(pictureFor("t9", [{ item: "minecraft:no_such_thing" }], PILE), { name: "chest", source: "placeholder" });
  const r = bookRow(LINES[4], new Map()); // pile archived by a reset: name_tag still has its own sprite
  assert.equal(r.placeholders, 0);
  const unknown = line("treasure", { tid: "t7", label: "Odd", items: [{ item: "minecraft:no_such_thing" }], source: { kind: "shop", ref: "x" } });
  assert.equal(bookRow(unknown, new Map()).placeholders, 1);
});

test("a level with no badge makes the book row throw loudly", () => {
  assert.throws(() => bookRow(line("level", { index: 9, name: "Grandmaster", points: 999 })), /no badge sprite/);
});

test("Dad's description of every kind is one plain line", () => {
  for (const l of LINES) assert.match(describeLine(l), /\S/);
  assert.match(describeLine(LINES[9]), /^DELIVERY FAILED/);
  assert.match(describeLine(LINES[8]), /chest 1 2 3/);
  assert.match(describeLine(LINES[0]), /from word pig/);
});

test("a promote line is validated, described for Dad and shown to Sam with the villager and its new badge", () => {
  assert.equal(validateHistoryLine(PROMOTE), PROMOTE);
  assert.ok(BOOK_KINDS.includes("promote"));
  assert.equal(describeLine(PROMOTE), "Promoted Armorer to Apprentice (54 emeralds spent so far)");
  assert.deepEqual(bookRow(PROMOTE), { sprites: [{ name: "villager_armorer" }, { name: "badge_iron" }], text: "The Armorer is now Apprentice!", placeholders: 0 });
  assert.throws(() => validateHistoryLine(line("promote", { ...PROMOTE.what, level: 3 })), /level/);
  const { level_name, ...rest } = PROMOTE.what;
  assert.throws(() => validateHistoryLine(line("promote", rest)), /level_name/);
  assert.throws(() => bookRow(line("promote", { ...PROMOTE.what, level_name: "Grandmaster" })), /no badge sprite/);
});
