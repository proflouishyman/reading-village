import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { validateCraftWords, trayFor, pickRound, craftedOf, roundTitle } from "../../app/js/screens/craft.js";
import { SPRITE_NAMES } from "../../app/js/sprites.js";
import { PATTERNS } from "../../app/js/levels.js";
import { craftStats } from "../../app/js/stats.js";

const shipped = JSON.parse(fs.readFileSync(new URL("../../app/data/craft_words.json", import.meta.url)));
const mk = (words) => ({ v: 2, words });
// A small fixture in the v2 contract: two per level plus the first level-1 words of the shipped list.
const fx = (word, level, sprite = "pig") => ({ word, level, pattern: PATTERNS[level - 1], sprite });
const eight = [fx("PIG", 1), fx("BAT", 1, "bat"), fx("BED", 1, "bed"), fx("PUP", 1, "pup"), fx("HEN", 1, "hen"), fx("FOX", 1, "fox"),
  fx("SUN", 1, "sun"), fx("DAD", 1, "dad")];

test("the shipped craft_words.json validates against the real sprites and covers every level", () => {
  const words = validateCraftWords(shipped, "craft_words.json", SPRITE_NAMES);
  for (let level = 1; level <= 6; level++) assert.ok(words.filter((w) => w.level === level).length >= 5, `level ${level}`);
});

test("validator throws on an unknown sprite, naming word and sprite", () => {
  const bad = eight.map((w, i) => (i === 0 ? { ...w, sprite: "dragon" } : w));
  assert.throws(() => validateCraftWords(mk(bad), "f.json", SPRITE_NAMES), /unknown sprite "dragon"/);
});

test("validator throws on bad letters, duplicates, extra fields, bad version, level/pattern mismatch, no level 1", () => {
  const swapFirst = (w) => mk(eight.map((x, i) => (i === 0 ? w : x)));
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[0], word: "pig" })), /3 to 10 capital letters/);
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[0], word: "AB" })), /3 to 10 capital letters/);
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[0], word: "ABCDEFGHIJK" })), /3 to 10 capital letters/);
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[1] })), /duplicate/);
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[0], x: 1 })), /unknown field/);
  assert.throws(() => validateCraftWords({ v: 1, words: eight }), /must be/);
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[0], level: 2 })), /does not match pattern/);
  assert.throws(() => validateCraftWords(swapFirst({ ...eight[0], pattern: "magic" })), /pattern/);
  assert.throws(() => validateCraftWords(mk([fx("FROG", 2, "pig")])), /at least one level 1/);
  assert.equal(validateCraftWords(mk([...eight, fx("FROG", 2), fx("PANDA", 6)]), "f.json", SPRITE_NAMES).length, 10);
});

test("tray: word letters + 2 distractors not in the word, deterministic, never the word in order", () => {
  eight.forEach((w, i) => {
    const t = trayFor(w.word, i);
    assert.equal(t.length, 5);
    assert.deepEqual(t.map((x) => x.id), [0, 1, 2, 3, 4]);
    const letters = t.map((x) => x.letter);
    for (const c of w.word) assert.ok(letters.includes(c));
    const extra = letters.filter((c) => !w.word.includes(c));
    assert.equal(extra.length, 2);
    assert.equal(new Set(extra).size, 2);
    assert.notEqual(letters.slice(0, 3).join(""), w.word);
    assert.deepEqual(trayFor(w.word, i), t, "same inputs, same tray");
  });
  assert.notDeepEqual(trayFor("PIG", 0), trayFor("PIG", 1), "the word index changes the shuffle");
});

test("tray keeps both letters of a doubled-letter word (PUP)", () => {
  const letters = trayFor("PUP", 3).map((x) => x.letter);
  assert.equal(letters.filter((c) => c === "P").length, 2);
});

test("round at level 1: least-crafted first, file order on ties, 5 words; missing crafted reads as {}", () => {
  assert.deepEqual(craftedOf({}), {});
  const r0 = pickRound(eight, {}, 1).round.map((w) => w.word);
  assert.deepEqual(r0, eight.slice(0, 5).map((w) => w.word));
  const r1 = pickRound(eight, { PIG: 2, BAT: 1 }, 1).round.map((w) => w.word);
  assert.deepEqual(r1, ["BED", "PUP", "HEN", "FOX", "SUN"]);
  assert.throws(() => pickRound([], {}, 1), /no items/);
});

test("small-caps craft has no confusable gate: words with b/d/p/q/m/w/n/u are all usable (fails if a gate returns)", () => {
  const { round } = pickRound(eight, {}, 1);
  assert.ok(round.some((w) => w.word === "PIG" || w.word === "PUP"), "p words are usable with no letters introduced");
  const r = pickRound(shipped.words, {}, 2);
  assert.equal(r.round.filter((w) => w.level === 2).length, 4, "four level-2 words, none dropped for inactive letters");
});

test("round above level 1: 4 at the level then... 1 review word from the level below, opening the round", () => {
  const words = [...eight, fx("FROG", 2), fx("CRAB", 2, "pig"), fx("SLED", 2), fx("NEST", 2), fx("MILK", 2)];
  const { round, short } = pickRound(words, {}, 2);
  assert.equal(short, false);
  assert.deepEqual(round.map((w) => w.level), [1, 2, 2, 2, 2]);
  assert.deepEqual(round.map((w) => w.word), ["PIG", "FROG", "CRAB", "SLED", "NEST"]);
});

test("review word comes from level N-1 only, never further down while N-1 has words", () => {
  const words = [...eight, fx("FROG", 2), fx("CRAB", 2), fx("SLED", 2), fx("NEST", 2), fx("MILK", 2),
    fx("SHIP", 3), fx("CHIN", 3), fx("THIN", 3), fx("SHED", 3), fx("WHIP", 3)];
  // the level-1 words are the least practised, yet level 3 reviews from level 2
  const { round } = pickRound(words, { FROG: 5, CRAB: 5, SLED: 5, NEST: 5, MILK: 5 }, 3);
  assert.deepEqual(round.map((w) => w.level), [2, 3, 3, 3, 3]);
  // N-1 has no words at all: fall back to the next level down
  const gap = pickRound([...eight, fx("SHIP", 3), fx("CHIN", 3), fx("THIN", 3), fx("SHED", 3)], {}, 3);
  assert.deepEqual(gap.round.map((w) => w.level), [1, 3, 3, 3, 3]);
});

test("a thin level is flagged short and topped up with easier words", () => {
  const thin = pickRound([...eight, fx("FROG", 2)], {}, 2);
  assert.equal(thin.short, true);
  assert.equal(thin.round.length, 5);
});

test("tray works for long words: letters of the word plus 2 spares, doubled letters kept (RABBIT, TURTLE)", () => {
  for (const [w, i] of [["RABBIT", 3], ["TURTLE", 5], ["CHICKEN", 7]]) {
    const t = trayFor(w, i);
    assert.equal(t.length, w.length + 2);
    const letters = t.map((x) => x.letter);
    for (const c of new Set(w)) assert.equal(letters.filter((x) => x === c).length, [...w].filter((x) => x === c).length);
    assert.notEqual(letters.slice(0, w.length).join(""), w);
  }
  assert.throws(() => trayFor("AB", 0), /trayFor/);
});

test("craftStats: counts, assisted share, per word; null when none", () => {
  const ev = (item, result) => ({ type: "craft", item, result, track: "smallcaps" });
  assert.equal(craftStats([{ type: "card" }]), null);
  const s = craftStats([ev("PIG", "correct"), ev("PIG", "assisted"), ev("BED", "correct"), ev("BED", "correct")]);
  assert.deepEqual([s.total, s.assisted, s.independentShare], [4, 1, 0.75]);
  assert.deepEqual(s.words, [{ word: "BED", n: 2, assisted: 0 }, { word: "PIG", n: 2, assisted: 1 }]);
});

test("roundTitle: number word follows the round length; no word, no title", () => {
  assert.equal(roundTitle(5), "You crafted five things!");
  assert.equal(roundTitle(1), "You crafted one thing!");
  assert.equal(roundTitle(8), "You crafted eight things!");
  assert.throws(() => roundTitle(0), /roundTitle/);
  assert.throws(() => roundTitle(13), /roundTitle/);
});

test("small-caps tray distractors may be any letter, including b/d/p/q/m/w/n/u", () => {
  const confusable = new Set("BDPQMWNU");
  const seen = new Set();
  for (const w of shipped.words) for (let i = 0; i < 8; i++) {
    const extra = trayFor(w.word, i).map((x) => x.letter);
    for (const c of w.word) extra.splice(extra.indexOf(c), 1);
    assert.equal(extra.length, 2);
    for (const c of extra) if (confusable.has(c)) seen.add(c);
  }
  assert.ok(seen.size >= 6, `confusables turn up as distractors (saw ${[...seen].join("")})`);
});

test("the removed words are gone from the shipped craft list", () => {
  const names = shipped.words.map((w) => w.word);
  for (const gone of ["WOLF", "TURTLE", "CANDLE", "PARROT"]) assert.ok(!names.includes(gone), gone);
  for (let level = 1; level <= 6; level++) assert.ok(shipped.words.filter((w) => w.level === level).length >= 10, `level ${level} has fewer than 10 craft words`);
});
