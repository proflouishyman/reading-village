import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {
  validateLevels, deriveLevels, effectiveLevel, makeTracker, pickAtLevel, runsDeck, pairsDeck, shuffledDeck,
  matchChoices, matchChoiceCount, levelNames, step, startState,
} from "../../app/js/levels.js";
import { mineDeck } from "../../app/js/screens/mine.js";
import { matchDeck } from "../../app/js/screens/match.js";
import { pickBlocksWords } from "../../app/js/screens/blocks.js";
import { validateWords } from "../../app/js/data.js";
import { PARTNER } from "../../app/js/rules.js";
import { setFamily } from "../../app/js/family.js";

setFamily({ v: 1, child: { name: "Sam" }, village_name: "Sam's Village", home_grown_up: "Dad", away_label: "Mom's house" });

const shipped = JSON.parse(fs.readFileSync(new URL("../../app/data/levels.json", import.meta.url)));
const cfg = validateLevels(shipped);
const ev = (type, result, level) => ({ type, result, ...(level === undefined ? {} : { level }) });
const many = (type, results, level) => results.map((r) => ev(type, r, level));
const rep = (r, n) => Array(n).fill(r);

function lcg(seed = 1) {
  let s = seed;
  return () => ((s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296);
}

test("levels.json validates; every game has the four fields and need <= window", () => {
  assert.deepEqual(Object.keys(cfg.games), ["craft", "blocks", "mine", "match"]);
  for (const g of Object.values(cfg.games)) assert.ok(g.need <= g.window && g.max >= 2);
  assert.equal(cfg.games.craft.max, 6);
});

test("validateLevels is loud: version, unknown game or field, need > window, max beyond the defined levels", () => {
  const bad = (f) => { const c = structuredClone(shipped); f(c); return () => validateLevels(c, "levels.json"); };
  assert.throws(bad((c) => (c.v = 2)), /must be/);
  assert.throws(bad((c) => (c.games.craft.need = 11)), /must not exceed window/);
  assert.throws(bad((c) => (c.games.craft.extra = 1)), /unknown field "extra"/);
  assert.throws(bad((c) => (c.games.dance = c.games.craft)), /unknown game "dance"/);
  assert.throws(bad((c) => delete c.games.mine), /games.mine is missing/);
  assert.throws(bad((c) => (c.games.mine.max = 9)), /higher than the 4 levels/);
  assert.throws(bad((c) => (c.games.match.window = "10")), /integer >= 1/);
});

test("promotion happens at exactly 8 of 10 independent with at least 10 attempts; 7 of 10 does not", () => {
  const seven = many("craft", [...rep("correct", 7), ...rep("assisted", 3)]);
  assert.equal(deriveLevels(seven, cfg).craft.level, 1);
  const eight = many("craft", [...rep("assisted", 2), ...rep("correct", 8)]);
  const d = deriveLevels(eight, cfg).craft;
  assert.equal(d.level, 2);
  assert.deepEqual([d.attempts, d.independent], [0, 0], "the count restarts at the new level");
});

test("fewer than 10 attempts never promote, even at 100%", () => {
  assert.equal(deriveLevels(many("word", rep("correct", 9)), cfg).blocks.level, 1);
  assert.equal(deriveLevels(many("word", rep("correct", 10)), cfg).blocks.level, 2);
});

test("only the LAST 10 attempts count: an early miss streak falls out of the window", () => {
  const evs = many("card", [...rep("miss", 5), ...rep("correct", 8)]); // attempts 4..13 = 2 miss... 8 correct in the last 10 once 13 tries exist
  assert.equal(deriveLevels(evs, cfg).mine.level, 2);
});

test("assisted and miss are not independent", () => {
  assert.equal(deriveLevels(many("match", [...rep("assisted", 10)]), cfg).match.level, 1);
  assert.equal(deriveLevels(many("match", [...rep("miss", 5), ...rep("assisted", 5)]), cfg).match.level, 1);
});

test("old events without level count as level 1; events for another level do not count", () => {
  assert.equal(deriveLevels(many("craft", rep("correct", 10)), cfg).craft.level, 2);
  const atTwo = many("craft", rep("correct", 10), 2); // made under Dad's override while the derived level is still 1
  assert.equal(deriveLevels(atTwo, cfg).craft.level, 1);
  const both = [...many("craft", rep("correct", 10)), ...many("craft", rep("correct", 10), 2)];
  assert.equal(deriveLevels(both, cfg).craft.level, 3);
  assert.equal(deriveLevels([...many("craft", rep("correct", 10)), ...many("craft", rep("correct", 10), 1)], cfg).craft.level, 2, "level-1 events after reaching 2 are ignored");
});

test("never demotes: later misses at the level do not lower it", () => {
  const evs = [...many("craft", rep("correct", 10)), ...many("craft", rep("assisted", 30), 2)];
  assert.equal(deriveLevels(evs, cfg).craft.level, 2);
});

test("the level stops at max; each game derives only from its own event types", () => {
  const evs = [];
  for (let lv = 1; lv <= 8; lv++) evs.push(...many("card", rep("correct", 10), lv));
  assert.equal(deriveLevels(evs, cfg).mine.level, cfg.games.mine.max);
  const d = deriveLevels(evs, cfg);
  assert.deepEqual([d.craft.level, d.blocks.level, d.match.level], [1, 1, 1]);
});

test("override wins; clearing it returns to the derived level; a bad override is loud", () => {
  const d = deriveLevels(many("craft", rep("correct", 10)), cfg);
  assert.equal(effectiveLevel("craft", d, undefined), 2);
  assert.equal(effectiveLevel("craft", d, { craft: 5 }), 5);
  assert.equal(effectiveLevel("craft", d, { blocks: 3 }), 2, "another game's override is not this game's");
  assert.throws(() => effectiveLevel("craft", d, { craft: 7 }), /1\.\.6/);
  assert.throws(() => effectiveLevel("craft", d, { craft: 0 }), /1\.\.6/);
  assert.throws(() => makeTracker("craft", [], cfg, { craft: 7 }), /1\.\.6/);
});

test("tracker: starts from events, records at the level in force, reports a level-up, and shows the lines", () => {
  const t = makeTracker("craft", many("craft", [...rep("assisted", 2), ...rep("correct", 6)]), cfg, undefined);
  assert.equal(t.level, 1);
  assert.deepEqual(t.lines(), ["Level 1: short vowel words", "6 of 8 right at level 1"]);
  assert.equal(t.record("correct", 1), false); // 9 attempts
  assert.equal(t.record("correct", 1), true); // 10th attempt, 8 correct
  assert.equal(t.level, 2);
  assert.deepEqual(t.lines(), ["Level 2: blends", "0 of 8 right at level 2"]);
  const top = makeTracker("mine", Array.from({ length: 3 }, (_, i) => many("card", rep("correct", 10), i + 1)).flat(), cfg);
  assert.deepEqual(top.lines(), ["Level 4: everything mixed", "top level"]);
});

test("tracker with an override: events carry the override level and do not move the derived level", () => {
  const t = makeTracker("blocks", [], cfg, { blocks: 3 });
  assert.equal(t.level, 3);
  for (let i = 0; i < 12; i++) assert.equal(t.record("correct", 3), false);
  assert.equal(t.derived, 1);
  assert.deepEqual(t.lines(), ["Level 3: digraphs", "level chosen by Dad"]);
});

test("step ignores an event at another level and reports exactly the attempt that promotes", () => {
  const s = startState();
  const g = cfg.games.craft;
  for (let i = 0; i < 9; i++) assert.equal(step(s, { result: "correct" }, g), false);
  assert.equal(step(s, { result: "correct", level: 3 }, g), false);
  assert.equal(step(s, { result: "correct", level: 1 }, g), true);
});

const items = (spec) => spec.map(([word, level, count], index) => ({ word, level, count, index }));

test("pickAtLevel: level 1 is least-practised first with file order on ties", () => {
  const { picked, short } = pickAtLevel(items([["a", 1, 2], ["b", 1, 0], ["c", 1, 0], ["d", 1, 1], ["e", 2, 0]]), 1, 3);
  assert.deepEqual(picked.map((x) => x.word), ["b", "c", "d"]);
  assert.equal(short, false);
});

test("pickAtLevel: above level 1 is 4 at the level plus 1 review from the level below, review first", () => {
  const pool = items([["l1", 1, 0], ["l2", 1, 1], ["k1", 2, 0], ["k2", 2, 0], ["m1", 3, 0], ["m2", 3, 1], ["m3", 3, 2], ["m4", 3, 3], ["m5", 3, 4], ["h1", 4, 0]]);
  const { picked, short } = pickAtLevel(pool, 3, 5);
  assert.deepEqual(picked.map((x) => x.word), ["k1", "m1", "m2", "m3", "m4"], "review from N-1 (not the unpractised level 1), then 4 at N");
  assert.equal(short, false);
  assert.ok(!picked.some((x) => x.level > 3), "never a harder word");
});

test("pickAtLevel: n=10 is 8 at the level and 2 review, opening and closing on a review word", () => {
  const spec = [];
  for (let i = 0; i < 4; i++) spec.push([`k${i}`, 2, i]);
  for (let i = 0; i < 10; i++) spec.push([`m${i}`, 3, i]);
  const { picked } = pickAtLevel(items(spec), 3, 10);
  assert.deepEqual(picked.map((x) => x.level), [2, 3, 3, 3, 3, 3, 3, 3, 3, 2]);
});

test("pickAtLevel: too few at the level tops up with easier ones and says short; nothing at all is loud", () => {
  const pool = items([["l1", 1, 0], ["l2", 1, 0], ["l3", 1, 0], ["l4", 1, 0], ["m1", 2, 0]]);
  const { picked, short } = pickAtLevel(pool, 2, 5);
  assert.equal(short, true);
  assert.equal(picked.length, 5);
  assert.equal(picked.filter((x) => x.level === 2).length, 1);
  assert.throws(() => pickAtLevel([], 2, 5), /no items/);
  assert.deepEqual(pickAtLevel(items([["m1", 2, 0]]), 3, 5).picked.map((x) => x.word), ["m1"], "only lower words exist: use them, flagged short");
  assert.deepEqual(pickAtLevel(items([["a", 1, 0], ["m1", 3, 0], ["m2", 3, 0]]), 3, 3).picked.map((x) => x.word), ["a", "m1", "m2"], "N-1 empty: review comes from further down");
});

const fixtureWords = validateWords({ v: 2, words: [
  { word: "bat", focus: "b", level: 1, pattern: "cvc" },
  { word: "bed", focus: "b", level: 1, pattern: "cvc" },
  { word: "dad", focus: "d", level: 1, pattern: "cvc" },
  { word: "crab", focus: "b", level: 2, pattern: "blend" },
  { word: "sled", focus: "d", level: 2, pattern: "blend" },
  { word: "frog", focus: null, level: 2, pattern: "blend" },
  { word: "snap", focus: "n", level: 2, pattern: "blend" },
  { word: "ship", focus: "p", level: 3, pattern: "digraph" },
] });

test("blocks pick: no confusable gate (small caps), 80% at the level + 20% review from N-1, least-practised first", () => {
  const rng = lcg(7);
  const { picked } = pickBlocksWords(fixtureWords, { crab: 3 }, 2, 5, rng);
  const names = picked.map((w) => w.word);
  assert.ok(names.includes("snap"), "n is not active but small caps does not mirror: usable");
  assert.equal(picked.length, 5);
  const level2 = picked.filter((w) => w.level === 2).map((w) => w.word);
  assert.equal(level2.length, 4);
  assert.equal(level2[level2.length - 1], "crab", "crab (practised 3 times) comes last among level 2");
  assert.equal(picked.filter((w) => w.level === 1).length, 1, "one review word");
  assert.equal(picked[0].level, 1, "the round opens on the review word");
  assert.ok(!names.includes("ship"), "never a harder word");
  assert.throws(() => pickBlocksWords([], {}, 1, 5, rng), /no items/);
});

test("validateWords: v2 contract, focus rule, pattern/level agreement, duplicates", () => {
  const w = (o) => ({ v: 2, words: [{ word: "bat", focus: "b", level: 1, pattern: "cvc", ...o }] });
  assert.equal(validateWords(w({})).length, 1);
  assert.throws(() => validateWords([{ word: "bat", focus: "b" }]), /must be/);
  assert.throws(() => validateWords(w({ level: 2 })), /does not match pattern/);
  assert.throws(() => validateWords(w({ pattern: "magic" })), /pattern/);
  assert.throws(() => validateWords(w({ focus: "d" })), /focus/);
  assert.throws(() => validateWords(w({ word: "frog", focus: "f" })), /focus/);
  assert.equal(validateWords(w({ word: "frog", focus: null, level: 2, pattern: "blend" }))[0].focus, null);
  assert.throws(() => validateWords(w({ extra: 1 })), /unknown field/);
  assert.throws(() => validateWords({ v: 2, words: [w({}).words[0], w({}).words[0]] }), /duplicate/);
});

const drill = ["b", "d", "p", "q"];

test("Letter Mine level 1: runs of three of the same letter", () => {
  const deck = mineDeck(1, drill, {}, 12, lcg(3));
  assert.equal(deck.length, 12);
  for (let i = 0; i < 12; i += 3) assert.ok(deck[i] === deck[i + 1] && deck[i] === deck[i + 2], deck.join(""));
  assert.ok(new Set(deck).size > 1);
});

test("Letter Mine level 3: mirror pairs alternate (b d b d), only letters whose partner is drilled; none is loud", () => {
  const deck = mineDeck(3, ["b", "d", "n"], {}, 8, lcg(4));
  assert.ok(!deck.includes("n"), "n has no drilled partner");
  assert.equal(deck.length, 8);
  for (let i = 1; i < 4; i++) assert.equal(deck[i], PARTNER[deck[i - 1]]);
  assert.throws(() => mineDeck(3, ["b"], {}, 8), /no letter has its mirror partner/);
});

test("Letter Mine level 4: every drilled letter, never the same twice in a row; level 2 is the original mix; level 5 is loud", () => {
  const deck = mineDeck(4, drill, {}, 200, lcg(5));
  for (let i = 1; i < deck.length; i++) assert.notEqual(deck[i], deck[i - 1]);
  assert.deepEqual([...new Set(deck)].sort(), [...drill].sort());
  assert.equal(mineDeck(2, drill, {}, 12, lcg(6)).length, 12);
  assert.throws(() => mineDeck(5, drill, {}), /no design/);
});

test("Bridge Match: choices grow 2, 2, 3, 4 and always hold the target and its mirror partner", () => {
  assert.deepEqual([1, 2, 3, 4].map(matchChoiceCount), [2, 2, 3, 4]);
  for (const level of [1, 2, 3, 4]) {
    const c = matchChoices(level, "b", drill, lcg(level));
    assert.equal(c.length, matchChoiceCount(level));
    assert.ok(c.includes("b") && c.includes("d"));
    assert.equal(new Set(c).size, c.length);
    assert.ok(c.every((x) => drill.includes(x)), "only letters he has been shown");
  }
  assert.equal(matchChoices(4, "b", ["b", "d"], lcg(1)).length, 2, "never more choices than letters drilled");
  assert.equal(matchDeck(1, drill, {}, 8, lcg(2)).length, 8);
  assert.throws(() => matchDeck(0, drill, {}), /no design/);
});

test("deck helpers: runsDeck n cards, pairsDeck needs pairs, shuffledDeck with one letter repeats it", () => {
  assert.deepEqual(runsDeck(["b"], 5), ["b", "b", "b", "b", "b"]);
  assert.equal(pairsDeck(drill, 9, lcg(1)).length, 9);
  assert.deepEqual(shuffledDeck(["b"], 3), ["b", "b", "b"]);
});

test("level names exist for every level up to each game's max", () => {
  for (const [g, c] of Object.entries(cfg.games)) assert.ok(levelNames(g).length >= c.max, g);
});

test("tracker.record needs the event's level (loud), and a mid-round level-up does not credit the rest of the round to the new level", () => {
  const t = makeTracker("mine", many("card", rep("correct", 9), 1), cfg, undefined);
  assert.throws(() => t.record("correct"), /level must be an integer/);
  // The round started at level 1 (roundLevel); the 10th answer levels up, the remaining answers still carry level 1.
  assert.equal(t.record("correct", 1), true);
  assert.equal(t.level, 2);
  for (let i = 0; i < 4; i++) assert.equal(t.record("correct", 1), false);
  assert.equal(t.independent, 0, "the rest of the round is not credited to level 2");
  assert.deepEqual(t.lines(), ["Level 2: letters mixed", "0 of 8 right at level 2"]);
  // and the server rule agrees: the same events derive level 2 with nothing counted at it
  const events = [...many("card", rep("correct", 14), 1)];
  const d = deriveLevels(events, cfg);
  assert.equal(d.mine.level, 2);
  assert.equal(d.mine.attempts, 0);
});

test("craft/blocks: mixed-in easier words (tagged with their own level) never count toward the current level", () => {
  const t = makeTracker("craft", many("craft", rep("correct", 8), 1).concat(many("craft", rep("assisted", 2), 1)), cfg, undefined);
  assert.equal(t.level, 2);
  // a round at level 2: easier word, then level-2 words, then an easier one
  const round = [1, 2, 2, 2, 1];
  for (const lv of round) t.record("correct", lv);
  assert.equal(t.independent, 3, "only the three level-2 words count");
  const events = round.map((lv) => ev("craft", "correct", lv));
  const d = deriveLevels([...many("craft", rep("correct", 8), 1), ...many("craft", rep("assisted", 2), 1), ...events], cfg);
  assert.equal(d.craft.independent, 3);
  // a level-up at level 2 needs 8 of 10 independent on level-2 words: ten easier words never do it
  const u = makeTracker("blocks", many("word", rep("correct", 10), 1), cfg, undefined);
  for (let i = 0; i < 12; i++) assert.equal(u.record("correct", 1), false);
  assert.equal(u.level, 2);
  assert.equal(u.independent, 0);
});
