import test from "node:test";
import assert from "node:assert/strict";

// A recording fake canvas: sprites build offscreen canvases through document.createElement.
const calls = [];
const fakeCtx = () => new Proxy({ imageSmoothingEnabled: true }, {
  get: (t, k) => (k in t ? t[k] : (...a) => { calls.push([k, ...a]); }),
  set: (t, k, v) => { t[k] = v; return true; },
});
globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: fakeCtx }) };

const { drawScene, checkArt, ArtError, BG_NAMES, POSES, FX_NAMES, PROP_YS, SCENE_KEYS } = await import("../../app/js/scenes.js");
const { validateStory, findRepeatedArt, StoryError } = await import("../../app/js/stories.js");
const { SPRITE_NAMES } = await import("../../app/js/sprites.js");

const art = (over = {}) => ({ bg: "grass", actors: [{ who: "hero", x: 30 }, { who: "dad", x: 70 }], ...over });
const story = (a) => ({ v: 1, id: "t", title: "T", subtitle: "S", focus_letters: ["b"], pages: [{ text: "Hi.", art: a }] });

test("the documented name lists are exact", () => {
  assert.deepEqual(BG_NAMES, "grass hill cave dark_cave night river sea inside_house sandpit hilltop sunset pond sky wall".split(" "));
  assert.deepEqual(POSES, "stand run jump sit fall upside_down hug hide sleep lying up in sit_on dig".split(" "));
  assert.deepEqual(FX_NAMES, "boom splash sneeze hiss sparkle mud_splat zzz stink tap text".split(" "));
  assert.deepEqual(PROP_YS, ["ground", "air", "water", "held", "head", "on"]);
});

test("object art validates inside a story", () => {
  assert.doesNotThrow(() => validateStory(story(art({ props: [{ what: "tree", x: 10 }], fx: "sparkle" })), "f"));
});

test("every background draws", () => {
  for (const bg of BG_NAMES) assert.doesNotThrow(() => drawScene(fakeCtx(), art({ bg })), bg);
});

test("every pose draws (hug and hide with their needs)", () => {
  // Poses with relations (in, sit_on, dig, lying) are exercised in scenes_engine.test.mjs.
  for (const pose of POSES.filter((p) => !["in", "sit_on", "dig"].includes(p))) {
    const a = { bg: "grass", actors: [{ who: "hero", x: 30, pose }, { who: "dad", x: 70, pose: pose === "hug" ? "hug" : "stand" }], props: [{ what: "chest", x: 50 }] };
    calls.length = 0;
    assert.doesNotThrow(() => drawScene(fakeCtx(), a), pose);
    assert.ok(calls.some((c) => c[0] === "drawImage"), `${pose} drew something`);
  }
  assert.doesNotThrow(() => drawScene(fakeCtx(), art({ actors: [{ who: "pig", x: 50, pose: "run", flip: true, scale: 1.5 }] })));
});

test("every fx draws", () => {
  for (const fx of FX_NAMES.filter((n) => n !== "text")) { // text needs the object form (scenes_engine.test.mjs)
    const a = { bg: "river", actors: [{ who: "hero", x: 30 }], props: [{ what: "fish", x: 60, y: "water" }], fx };
    assert.doesNotThrow(() => drawScene(fakeCtx(), a), fx);
    assert.doesNotThrow(() => drawScene(fakeCtx(), { bg: "cave", actors: [{ who: "dad", x: 50, pose: "sleep" }], fx }), `${fx} on a sleeper`);
  }
});

test("every prop position draws", () => {
  const props = [{ what: "torch", x: 20 }, { what: "bat", x: 40, y: "air" }, { what: "boat", x: 60, y: "water" }, { what: "pickaxe", x: 31, y: "held" }];
  assert.doesNotThrow(() => drawScene(fakeCtx(), { bg: "sea", actors: [{ who: "hero", x: 30 }], props }));
});

test("every sprite works as an actor and as a prop", () => {
  for (const n of SPRITE_NAMES) {
    assert.doesNotThrow(() => drawScene(fakeCtx(), { bg: "grass", actors: [{ who: n, x: 50 }], props: [{ what: n, x: 20 }] }), n);
  }
});

test("string scene keys still work, and every key draws", () => {
  for (const k of SCENE_KEYS) assert.doesNotThrow(() => drawScene(fakeCtx(), k), k);
  assert.doesNotThrow(() => validateStory({ ...story("map") }, "f"));
  assert.throws(() => drawScene(fakeCtx(), "nope", "pg 3 art"), /pg 3 art: Unknown scene key "nope"/);
});

test("unknown names throw loud errors naming story, page and field", () => {
  const cases = [
    [art({ bg: "moonbase" }), /pages\[0\]\.art\.bg "moonbase" is not a known background/],
    [art({ actors: [{ who: "dragon", x: 5 }] }), /pages\[0\]\.art\.actors\[0\]\.who "dragon" is not a known sprite/],
    [art({ actors: [{ who: "dad", x: 5, pose: "dance" }] }), /actors\[0\]\.pose "dance" is not a known pose/],
    [art({ props: [{ what: "ufo", x: 5 }] }), /props\[0\]\.what "ufo" is not a known sprite/],
    [art({ props: [{ what: "tree", x: 5, y: "moon" }] }), /props\[0\]\.y "moon" is not a known prop y/],
    [art({ fx: "laser" }), /pages\[0\]\.art\.fx "laser" is not a known fx/],
  ];
  for (const [a, re] of cases) {
    assert.throws(() => validateStory(story(a), "stories/t.json"), (e) => e instanceof StoryError && e.message.includes("stories/t.json") && re.test(e.message), String(re));
    assert.throws(() => drawScene(fakeCtx(), a, "t page 0 art"), (e) => e instanceof ArtError && e.message.includes("t page 0 art"));
  }
});

test("shape errors: unknown fields, bad x, missing bg, bad scale, and the semantic rules", () => {
  const bad = [
    { actors: [] },
    art({ extra: 1 }),
    art({ actors: [{ who: "dad", x: 101 }] }),
    art({ actors: [{ who: "dad", x: "5" }] }),
    art({ actors: [{ who: "dad", x: 5, color: "red" }] }),
    art({ actors: [{ who: "dad", x: 5, flip: "yes" }] }),
    art({ actors: [{ who: "dad", x: 5, scale: 0 }] }),
    art({ props: [{ what: "tree", x: 5, y: "water" }] }),                 // grass has no water
    art({ actors: [], props: [{ what: "tree", x: 5, y: "held" }] }),       // nobody to hold it
    art({ actors: [{ who: "dad", x: 5, pose: "hug" }] }),                  // a hug needs a pair
    art({ actors: [{ who: "dad", x: 5, pose: "hide" }] }),                 // nothing to hide behind
    { bg: "grass", fx: "boom" },                                           // fx needs somewhere to appear
    [],
  ];
  for (const a of bad) assert.throws(() => checkArt(a, "art"), ArtError, JSON.stringify(a));
});

test("x means the same fraction of the canvas: x 50 is the middle", () => {
  calls.length = 0;
  drawScene(fakeCtx(), { bg: "cave", actors: [{ who: "dad", x: 50 }] });
  const t = calls.filter((c) => c[0] === "transform"); // the actor's frame: transform(a, b, c, d, e, f)
  assert.equal(t.at(-1)[5], 96); // e = 50% of the 192-wide logical canvas
});

test("findRepeatedArt reports consecutive identical art only", () => {
  const s = story("map");
  s.pages = ["map", "map", art(), art(), "hill", "map"].map((a, i) => ({ text: `P${i}.`, art: a }));
  assert.deepEqual(findRepeatedArt(s), [{ page: 1, same_as: 0 }, { page: 3, same_as: 2 }]);
});

// Every page of every listed story must validate and draw, whether its art is a scene key or an object.
test("every story page validates and draws", async () => {
  const { readFileSync } = await import("node:fs");
  const read = (p) => JSON.parse(readFileSync(new URL(`../../stories/${p}`, import.meta.url)));
  for (const id of read("index.json").stories) {
    const s = read(`${id}.json`);
    validateStory(s, `stories/${id}.json`);
    s.pages.forEach((p, i) => assert.doesNotThrow(() => drawScene(fakeCtx(), p.art), `${id} page ${i}`));
  }
});
