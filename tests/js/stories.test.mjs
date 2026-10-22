import test from "node:test";
import assert from "node:assert/strict";
import { validateStory, validateIndex, StoryError } from "../../app/js/stories.js";
import { SCENE_KEYS, drawScene } from "../../app/js/scenes.js";
import { SPRITES, PALETTE } from "../../app/js/sprites.js";
import { localIso } from "../../app/js/util.js";

const good = () => ({
  v: 1, id: "gold-pig", title: "Sam and the Gold Pig", subtitle: "A Minecraft Tale",
  focus_letters: ["b", "d"], pages: [{ text: "Sam had a map.", art: "map" }],
});

test("a valid story passes", () => assert.equal(validateStory(good(), "x").id, "gold-pig"));

test("unknown art key is rejected, naming file and page", () => {
  const s = good();
  s.pages.push({ text: "Boo.", art: "dragon" });
  assert.throws(() => validateStory(s, "stories/gold-pig.json"), (e) =>
    e instanceof StoryError && e.message.includes("stories/gold-pig.json") && e.message.includes("pages[1]") && e.message.includes("dragon"));
});

test("missing and unknown fields, bad types are rejected", () => {
  for (const mut of [
    (s) => delete s.title, (s) => (s.extra = 1), (s) => (s.v = 2), (s) => (s.pages = []),
    (s) => (s.pages[0].text = ""), (s) => delete s.pages[0].art, (s) => (s.pages[0].note = "x"),
    (s) => (s.focus_letters = ["z"]), (s) => (s.id = "Gold Pig"),
  ]) {
    const s = good();
    mut(s);
    assert.throws(() => validateStory(s, "f"), StoryError);
  }
  assert.throws(() => validateStory(null, "f"), StoryError);
});

test("index must list ids", () => {
  assert.deepEqual(validateIndex({ v: 1, stories: ["a"] }), ["a"]);
  assert.throws(() => validateIndex(["a", "b"]), StoryError);
  assert.throws(() => validateIndex({ stories: ["a"] }), StoryError);
  assert.throws(() => validateIndex({ v: 1 }), StoryError);
  assert.throws(() => validateIndex({ v: 1, stories: [] }), StoryError);
});

test("the spec's 30 scene keys exist and unknown keys throw", () => {
  const want = "title map hill cave dark torch bat creeper run boom pool wall chest hat king rock bed dig pup web sun night boat river house end hen fox duck fish".split(" ");
  assert.deepEqual([...SCENE_KEYS].sort(), want.sort());
  assert.throws(() => drawScene({}, "nope"), /Unknown scene key/);
});

test("sprites are rectangular and use only palette chars", () => {
  for (const [name, s] of Object.entries(SPRITES)) {
    const w = s.rows[0].length;
    s.rows.forEach((r, i) => {
      assert.equal(r.length, w, `${name} row ${i}`);
      for (const ch of r) assert.ok(ch === "." || ch in PALETTE || (s.swap && ch in s.swap), `${name}: ${ch}`);
    });
  }
});

test("localIso includes a UTC offset", () => {
  assert.match(localIso(new Date(2026, 9, 18, 9, 5, 3)), /^2026-10-18T09:05:03[+-]\d\d:\d\d$/);
});

import { readFileSync } from "node:fs";
import { confusablesIn, LETTERS } from "../../app/js/rules.js";

test("words.json: v2, unique words, focus is a confusable in the word (null only when it has none), level matches pattern", async () => {
  const { validateWords } = await import("../../app/js/data.js");
  const obj = JSON.parse(readFileSync(new URL("../../app/data/words.json", import.meta.url)));
  const words = validateWords(obj, "words.json");
  assert.ok(words.length >= 60);
  assert.equal(new Set(words.map((w) => w.word)).size, words.length);
  for (let level = 1; level <= 6; level++) assert.ok(words.some((w) => w.level === level), `level ${level} has words`);
});

test("cues.json: every letter has a cue", () => {
  const cues = JSON.parse(readFileSync(new URL("../../app/data/cues.json", import.meta.url)));
  assert.deepEqual(Object.keys(cues).sort(), [...LETTERS].sort());
  for (const c of Object.values(cues)) assert.ok(c.cue.length > 5);
});

test("L2: non-ASCII letters in page text are rejected; curly quotes, apostrophes and dashes are allowed", () => {
  for (const bad of ["Caf\u00e9 time.", "Stra\u00dfe.", "\ufb01sh.", "\u01c6 x", "Dad \u0131s."]) {
    const s = good();
    s.pages[0].text = bad;
    assert.throws(() => validateStory(s, "f"), (e) => e instanceof StoryError && e.message.includes("pages[0].text") && e.message.includes("non-ASCII"), bad);
  }
  const ok = good();
  ok.pages[0].text = "Dad\u2019s \u201chat\u201d \u2018big\u2019 \u2014 a map\u2026";
  assert.doesNotThrow(() => validateStory(ok, "f"));
});
