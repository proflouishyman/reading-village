import test from "node:test";
import assert from "node:assert/strict";
import { toSmallCaps, escapeHtml, renderWords, cleanWord } from "../../app/js/smallcaps.js";

test("lowercase letters become uppercase span.sc", () => {
  assert.equal(toSmallCaps("pig"), '<span class="sc">P</span><span class="sc">I</span><span class="sc">G</span>');
});

test("capitals, digits, spaces and punctuation are untouched", () => {
  assert.equal(toSmallCaps("A 1, B!"), "A 1, B!");
  assert.equal(toSmallCaps("Sam"), 'S<span class="sc">A</span><span class="sc">M</span>');
});

test("HTML special characters are escaped", () => {
  assert.equal(toSmallCaps('<&">'), "&lt;&amp;&quot;&gt;");
  assert.ok(!toSmallCaps("<script>").includes("<script>"));
  assert.equal(escapeHtml("a<b"), "a&lt;b");
});

test("empty string", () => assert.equal(toSmallCaps(""), ""));

test("renderWords wraps each word with its cleaned form", () => {
  const html = renderWords("Dad's big pig.", "lowercase");
  assert.match(html, /data-word="dad&#39;s"/);
  assert.match(html, /data-word="pig">pig\.</);
  assert.throws(() => renderWords("x", "upper"));
});

import { toMixedCase } from "../../app/js/smallcaps.js";
import { validateSwapOrder, swappedLetters, nextSwapLetter, drillLetters, swapCount, percentForCount } from "../../app/js/swap.js";

const ORDER = ["a","e","o","t","s","i","r","h","c","l","g","f","k","y","v","x","z","j","n","u","m","w","p","q","b","d"];

test("toMixedCase: 0% equals small caps, all letters equals plain lowercase", () => {
  assert.equal(toMixedCase("Dad's big pig.", new Set()), toSmallCaps("Dad's big pig."));
  assert.equal(toMixedCase("Dad<s> big", new Set(ORDER)), "Dad&lt;s&gt; big");
});

test("toMixedCase: exactly the chosen letters are lowercase", () => {
  assert.equal(toMixedCase("pat", new Set(["a", "t"])), '<span class="sc">P</span>at');
});

test("swap: percent maps to the first N letters, deterministic", () => {
  assert.deepEqual(swappedLetters(ORDER, 0), []);
  assert.deepEqual(swappedLetters(ORDER, 4), ["a"]);
  assert.deepEqual(swappedLetters(ORDER, 30), ORDER.slice(0, 8));
  assert.equal(swappedLetters(ORDER, 100).length, 26);
  assert.equal(nextSwapLetter(ORDER, 30), "c");
  assert.equal(nextSwapLetter(ORDER, 100), null);
  assert.throws(() => swappedLetters(ORDER, 30.5));
});

test("drillLetters: only active mirror letters already swapped in", () => {
  assert.deepEqual(drillLetters(["b", "d"], ORDER, 50), []);
  assert.deepEqual(drillLetters(["b", "d"], ORDER, 100), ["b", "d"]);
  // n/u are drilled only once BOTH are swapped in (u is the 20th letter: 20 letters = 77%).
  assert.deepEqual(drillLetters(["b", "d", "n", "u"], ORDER, 73), []);
  assert.deepEqual(drillLetters(["b", "d", "n", "u"], ORDER, 77), ["n", "u"]);
});

test("M4: a mirror letter needs its partner swapped in too (b/d, p/q, n/u, m/w)", () => {
  const all = ["b", "d", "p", "q", "n", "u", "m", "w"];
  for (const [a, b] of [["b", "d"], ["p", "q"], ["n", "u"], ["m", "w"]]) {
    for (let n = 0; n <= 26; n++) {
      const swapped = new Set(ORDER.slice(0, n));
      const got = drillLetters(all, ORDER, percentForCount(n));
      assert.equal(got.includes(a), swapped.has(a) && swapped.has(b), `${a} at ${n} letters`);
      assert.equal(got.includes(b), swapped.has(a) && swapped.has(b), `${b} at ${n} letters`);
    }
  }
  assert.deepEqual(drillLetters(all, ORDER, 100), all);
});

test("L1: the slider counts letters; every n 0..26 round-trips and each step adds exactly one letter", () => {
  let prev = null;
  for (let n = 0; n <= 26; n++) {
    const p = percentForCount(n);
    assert.equal(p, Math.round((n * 100) / 26));
    assert.equal(Math.round((26 * p) / 100), n, `n=${n} p=${p}`); // the documented inverse
    assert.equal(swapCount(ORDER, p), n);
    assert.equal(swappedLetters(ORDER, p).length, n);
    if (prev !== null) assert.deepEqual(swappedLetters(ORDER, p).slice(prev.length).length, 1, `step to ${n}`);
    prev = swappedLetters(ORDER, p);
  }
  assert.equal(percentForCount(26), 100);
  assert.throws(() => percentForCount(27));
  assert.throws(() => percentForCount(1.5));
});

test("validateSwapOrder: strict", () => {
  assert.deepEqual(validateSwapOrder({ v: 1, order: ORDER }), ORDER);
  assert.throws(() => validateSwapOrder({ v: 1, order: ORDER.slice(1) }), /26/);
  assert.throws(() => validateSwapOrder({ v: 1, order: [...ORDER.slice(1), "e"] }), /duplicate/);
  assert.throws(() => validateSwapOrder({ v: 1, order: [...ORDER.slice(0, 25), "A"] }), /not a single letter/);
  assert.throws(() => validateSwapOrder({ order: ORDER }));
});

test("M3: cleanWord treats the curly apostrophe like the straight one", () => {
  assert.equal(cleanWord("Dad\u2019s"), "dad's");
  assert.equal(cleanWord("Dad's"), "dad's");
  assert.equal(cleanWord("\u2014"), "");
});

test("M3: a token with no letters is shown but is not a tappable word", () => {
  const html = renderWords("Dad ran \u2014 2 ... \"!\" ' \u2019 ok", "smallcaps");
  assert.equal((html.match(/class="w"/g) ?? []).length, 3); // Dad, ran, ok
  assert.equal((html.match(/class="t"/g) ?? []).length, 6);
  assert.ok(!/data-word=""/.test(html));
  assert.ok(!/data-word="&#39;"/.test(html)); // a lone apostrophe is not a word either
  assert.match(renderWords("Dad\u2019s", "lowercase"), /data-word="dad&#39;s"/);
});
