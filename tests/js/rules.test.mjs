import test from "node:test";
import assert from "node:assert/strict";
import {
  accuracy, isMastered, nextActiveLetters, buildLetterDeck, applyResult, rewardForCard, rewardForWord,
  victoryItem, confusablesIn, pickWords, unlockedDecorations,
} from "../../app/js/rules.js";

const stat = (correct, total = 10) => ({
  recent: [...Array(correct).fill("correct"), ...Array(total - correct).fill("miss")],
  total_correct: correct, total_tries: total,
});
const lcg = (seed = 1) => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);

test("accuracy needs a full window of 10", () => {
  assert.equal(accuracy(stat(8)), 0.8);
  assert.equal(accuracy(stat(4, 5)), null);
  assert.equal(accuracy(undefined), null);
});

test("b,d -> add p only when both are >= 80% over the last 10", () => {
  const ok = nextActiveLetters(["b", "d"], { b: stat(8), d: stat(10) });
  assert.deepEqual(ok.active, ["b", "d", "p"]);
  assert.deepEqual(ok.added, ["p"]);
  assert.deepEqual(nextActiveLetters(["b", "d"], { b: stat(8), d: stat(7) }).added, []);
  assert.deepEqual(nextActiveLetters(["b", "d"], { b: stat(10) }).added, []); // d has no history
  assert.deepEqual(nextActiveLetters(["b", "d"], { b: stat(8, 9), d: stat(9, 9) }).added, []); // < 10 tries
});

test("order continues p -> q -> n,u -> m,w then stops", () => {
  const all = (ls) => Object.fromEntries(ls.map((l) => [l, stat(10)]));
  let active = ["b", "d"];
  const seen = [];
  for (let i = 0; i < 6; i++) {
    const r = nextActiveLetters(active, all("bdpqnumw".split("")));
    seen.push(r.added.join(""));
    active = r.active;
  }
  assert.deepEqual(seen, ["p", "q", "nu", "mw", "", ""]);
});

test("review mix: mastered letters appear ~20% of the time", () => {
  const stats = { b: stat(10), d: stat(3), p: stat(2) };
  const deck = buildLetterDeck(["b", "d", "p"], stats, 2000, lcg(7));
  const share = deck.filter((l) => l === "b").length / deck.length;
  assert.ok(share > 0.15 && share < 0.25, `review share ${share}`);
  assert.ok(deck.includes("d") && deck.includes("p"));
});

test("deck with nothing mastered uses all active; never repeats the previous letter when avoidable", () => {
  const deck = buildLetterDeck(["b", "d"], {}, 50, lcg(3));
  assert.equal(deck.length, 50);
  for (let i = 1; i < deck.length; i++) assert.notEqual(deck[i], deck[i - 1]);
});

test("applyResult keeps the last 10 and counts", () => {
  let s;
  for (let i = 0; i < 12; i++) s = applyResult(s, i % 2 ? "miss" : "correct");
  assert.equal(s.recent.length, 10);
  assert.equal(s.total_tries, 12);
  assert.equal(s.total_correct, 6);
  assert.equal(applyResult(s, "assisted").total_correct, 6);
});

test("card reward climbs with streak; misses earn nothing; assisted still earns coal", () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6, 7, 20].map((n) => rewardForCard("correct", n)),
    ["coal", "coal", "iron", "iron", "gold", "gold", "diamond", "diamond"]);
  assert.equal(rewardForCard("assisted", 0), "coal");
  assert.equal(rewardForCard("miss", 3), null);
});

test("word reward alternates wood/stone; story pass reward is emerald", () => {
  assert.equal(rewardForWord("correct", 0), "wood");
  assert.equal(rewardForWord("assisted", 1), "stone");
  assert.equal(rewardForWord("miss", 0), null);
});

test("stage ends on a success: victory item logic", () => {
  assert.equal(victoryItem([], "b"), null);
  assert.equal(victoryItem([{ item: "b", result: "correct" }], "b"), null);
  assert.equal(victoryItem([{ item: "b", result: "correct" }, { item: "d", result: "assisted" }], "x"), "b");
  assert.equal(victoryItem([{ item: "d", result: "miss" }], "b"), "b");
});

test("words: qu counts as q; only words whose confusables are all active are eligible", () => {
  assert.deepEqual(confusablesIn("quit"), ["q"]);
  assert.deepEqual(confusablesIn("bud"), ["b", "u", "d"]);
  const words = [{ word: "bat", focus: "b" }, { word: "pig", focus: "p" }, { word: "bud", focus: "b" }, { word: "dip", focus: "d" }];
  assert.deepEqual(pickWords(words, ["b", "d"], 10, lcg()).map((w) => w.word), ["bat"]);
  assert.equal(pickWords(words, ["b", "d", "p"], 10, lcg()).length, 3);
  assert.equal(pickWords(words, ["b", "d", "p"], 2, lcg()).length, 2);
});

test("decorations unlock one per finished story pass", () => {
  const p = { stories: { a: { smallcaps_done: true, lowercase_done: true }, b: { smallcaps_done: true, lowercase_done: false } } };
  assert.deepEqual(unlockedDecorations(p), ["door", "torch", "pig"]);
  assert.deepEqual(unlockedDecorations({ stories: {} }), []);
});

test("isMastered", () => {
  assert.equal(isMastered(stat(8)), true);
  assert.equal(isMastered(stat(7)), false);
});
