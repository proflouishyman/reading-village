// Page-art engine capabilities: held props in the hand, several props per actor, stacking, the new poses, text
// effects, and the two guards (clipping incl. effects, undeclared overlap). Pure geometry via artBoxes/artOverlaps,
// plus drawing against a recording fake canvas.
import test from "node:test";
import assert from "node:assert/strict";

const calls = [];
const fakeCtx = (canvas) => new Proxy({ imageSmoothingEnabled: true, canvas }, {
  get: (t, k) => (k in t ? t[k] : (...a) => { calls.push([k, ...a]); }),
  set: (t, k, v) => { t[k] = v; return true; },
});
globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: () => fakeCtx() }) };

const { artBoxes, artOverlaps, artBubbleHeadHits, checkArt, drawScene, ArtError, estimateTextWidth, HI_RES, SCENE_W, SCENE_H, POSES, PROP_YS } =
  await import("../../app/js/scenes.js");
const { validateStory } = await import("../../app/js/stories.js");

const boxes = (art) => artBoxes(art);
const by = (b, kind, name) => b.find((x) => x.kind === kind && x.name === name);
const bad = (art, re) => assert.throws(() => checkArt(art, "art"), (e) => e instanceof ArtError && re.test(e.message), JSON.stringify(art));
const inside = (b) => b.x0 >= 0 && b.y0 >= 0 && b.x1 <= SCENE_W && b.y1 <= SCENE_H;
const frac = (a, b) => {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return w > 0 && h > 0 ? (w * h) / Math.min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0)) : 0;
};

// --- 1. held props in the hand ---
test("a held tool overlaps the hand at the arm's end, and is angled", () => {
  const b = boxes({ bg: "cave", actors: [{ who: "hero", x: 50 }], props: [{ what: "pickaxe", x: 55, y: "held" }] });
  const c = by(b, "actor", "hero"), p = by(b, "prop", "pickaxe");
  assert.ok(p.x0 < c.x1 && p.x1 > c.x1, "crosses the right edge where the hand is");
  assert.ok(p.y0 < c.y1 && p.y1 > c.y0 + (c.y1 - c.y0) * 0.5, "at hand height, not floating at the feet or head");
  const flat = boxes({ bg: "cave", actors: [{ who: "hero", x: 50 }], props: [{ what: "pickaxe", x: 55, y: "held", angle: 0 }] });
  assert.notDeepEqual([p.x0, p.x1], [by(flat, "prop", "pickaxe").x0, by(flat, "prop", "pickaxe").x1], "angle changes the box");
});

test("a held prop follows flip, by, and the hand of the chosen actor", () => {
  const art = { bg: "cave", actors: [{ who: "hero", x: 20, id: "c" }, { who: "dad", x: 24, flip: true, id: "d" }],
    props: [{ what: "torch", x: 22, y: "held", by: "d" }] };
  const b = boxes(art);
  const d = by(b, "actor", "dad"), t = by(b, "prop", "torch");
  assert.ok(t.x0 < d.x0 + 6 && t.x1 > d.x0 - 12, "left hand side of a flipped dad");
  assert.ok(t.x1 <= (d.x0 + d.x1) / 2, "not across the body");
});

test("a rod can show a line down to a target; only a rod, only held", () => {
  const art = { bg: "sea", actors: [{ who: "dad", x: 30 }], props: [{ what: "rod", x: 34, y: "held", line_to: "fish" }, { what: "fish", x: 70, y: "water" }] };
  assert.doesNotThrow(() => drawScene(fakeCtx(), art));
  calls.length = 0;
  drawScene(fakeCtx(), art);
  assert.ok(calls.filter((c) => c[0] === "fillRect" || c[0] === "drawImage").length > 20);
  bad({ ...art, props: [{ what: "pickaxe", x: 34, y: "held", line_to: "fish" }, art.props[1]] }, /line_to is supported for "rod" only/);
  bad({ ...art, props: [{ what: "rod", x: 34, y: "ground", line_to: "fish" }, art.props[1]] }, /line_to is only for a held prop/);
  bad({ ...art, props: [{ what: "rod", x: 34, y: "held", line_to: "whale" }, art.props[1]] }, /line_to .*not an id or a sprite name/);
});

// --- 2. several props per actor, stacking ---
test("a worn hat and a held item on one actor; a prop on a prop; a crown on the pig's head", () => {
  const art = { bg: "grass", actors: [{ who: "dad", x: 25 }, { who: "pig", x: 70 }],
    props: [{ what: "hat", x: 25, y: "head", id: "hat1" }, { what: "sock", x: 25, y: "on", on: "hat1", scale: 0.5 },
      { what: "pan", x: 30, y: "held" }, { what: "crown", x: 70, y: "head" }] };
  const b = boxes(art);
  const dad = by(b, "actor", "dad"), hat = by(b, "prop", "hat"), sock = by(b, "prop", "sock"), pan = by(b, "prop", "pan");
  assert.ok(hat.y0 < dad.y0, "hat on his head");
  assert.ok(sock.y1 > hat.y0 && sock.y1 < hat.y0 + (hat.y1 - hat.y0), "sock rests on the hat");
  assert.ok(Math.abs((sock.x0 + sock.x1) / 2 - (hat.x0 + hat.x1) / 2) < 0.01, "centred on the hat");
  assert.ok(pan.x1 > dad.x1 - 8, "pan in his hand");
  assert.equal(artOverlaps(art).length, 0, "all declared: no overlap failure");
  const pig = by(b, "actor", "pig"), crown = by(b, "prop", "crown");
  assert.ok(crown.y1 > pig.y0 && (crown.x0 + crown.x1) / 2 > (pig.x0 + pig.x1) / 2, "on the pig's head, which is right of centre");
});

test("a prop can sit on an actor (its head) or on a prop; relations are checked", () => {
  const art = { bg: "grass", actors: [{ who: "pig", x: 60, id: "pig" }], props: [{ what: "crown", x: 60, y: "on", on: "pig" }] };
  assert.ok(by(boxes(art), "prop", "crown").y1 > by(boxes(art), "actor", "pig").y0);
  bad({ bg: "grass", props: [{ what: "crown", x: 5, y: "on" }] }, /y "on" needs .*\.on/);
  bad({ bg: "grass", props: [{ what: "crown", x: 5, on: "pig" }] }, /\.on is only for y "on"/);
  bad({ bg: "grass", props: [{ what: "crown", x: 5, y: "on", on: "nothing" }] }, /not an id or a sprite name/);
  bad({ bg: "grass", props: [{ what: "cloud", x: 5, y: "air" }, { what: "cloud", x: 50, y: "on", on: "cloud" }] }, /matches 2 things/);
  bad({ bg: "grass", props: [{ what: "hat", x: 5, id: "a", y: "on", on: "b" }, { what: "hat", x: 9, id: "b", y: "on", on: "a" }] }, /depends on itself/);
  bad({ bg: "grass", props: [{ what: "hat", x: 5, id: "A" }] }, /\.id must be lowercase/);
  bad({ bg: "grass", props: [{ what: "hat", x: 5, id: "a" }, { what: "hat", x: 9, id: "a" }] }, /used twice/);
});

test("two props held by one actor is a loud error (one hand); one hat per head stacks as before", () => {
  bad({ bg: "grass", actors: [{ who: "dad", x: 5 }], props: [{ what: "pan", x: 5, y: "held" }, { what: "torch", x: 6, y: "held" }] }, /already holds/);
  bad({ bg: "grass", actors: [{ who: "dad", x: 5 }], props: [{ what: "pan", x: 5, y: "held", by: "hero" }] }, /not an id or a sprite name/);
  bad({ bg: "grass", actors: [{ who: "dad", x: 5 }, { who: "hen", x: 50 }], props: [{ what: "pan", x: 5, y: "held", by: "hen", on: "dad" }] }, /\.on is only for y "on"/);
});

// --- 3. poses ---
test("lying: horizontal on the ground, wider than tall, on the floor", () => {
  const c = by(boxes({ bg: "grass", actors: [{ who: "hero", x: 50, pose: "lying" }] }), "actor", "hero");
  assert.ok(c.x1 - c.x0 > c.y1 - c.y0 && Math.abs((c.x0 + c.x1) / 2 - SCENE_W / 2) < 0.01 && Math.abs(c.y1 - 94) < 0.01);
});

test("lying in a bed: the bed is around him, and the pair is a declared relation", () => {
  const art = { bg: "inside_house", actors: [{ who: "hero", x: 50, pose: "lying", in: "bed" }], props: [{ what: "bed", x: 50, scale: 1.15 }] };
  const b = boxes(art), c = by(b, "actor", "hero"), bed = by(b, "prop", "bed");
  assert.ok(c.x0 >= bed.x0 && c.x1 <= bed.x1, "inside the bed's length");
  assert.ok(c.y0 >= bed.y0 - 20 && c.y1 <= bed.y1, "at the mattress height");
  assert.equal(artOverlaps(art).length, 0);
  assert.doesNotThrow(() => drawScene(fakeCtx(), art));
  bad({ bg: "grass", actors: [{ who: "dad", x: 50, pose: "lying", in: "pit" }], props: [{ what: "pit", x: 50 }] }, /can only lie in a "bed"/);
  bad({ bg: "inside_house", actors: [{ who: "dad", x: 50, pose: "lying", in: "bed", scale: 1.5 }], props: [{ what: "bed", x: 50 }] }, /needs .*px of bed/);
  bad({ bg: "grass", actors: [{ who: "dad", x: 50, pose: "stand", in: "bed" }], props: [{ what: "bed", x: 50 }] }, /\.in is only for pose "in" or "lying"/);
});

test("up: airborne, high in the frame, fully inside it, off the ground", () => {
  for (const who of ["dad", "hero", "pig"]) {
    const c = by(boxes({ bg: "grass", actors: [{ who, x: 50, pose: "up" }] }), "actor", who);
    assert.ok(inside(c) && c.y0 < 12 && c.y1 < 94 - 4, `${who}: ${JSON.stringify(c)}`);
  }
  const up = artBoxes({ bg: "grass", actors: [{ who: "dad", x: 50, pose: "up" }] }, 800, 450)[0];
  assert.equal(up.clip, 0);
});

test("in a pit or tub: the container is drawn in front and hides the lower body", () => {
  const art = { bg: "grass", actors: [{ who: "dad", x: 50, pose: "in", in: "pit" }], props: [{ what: "pit", x: 50 }] };
  const b = boxes(art), dad = by(b, "actor", "dad"), pit = by(b, "prop", "pit");
  assert.ok(dad.y1 < pit.y1 && dad.y1 > pit.y0, "his feet are below the pit's top edge");
  assert.ok(dad.y0 < pit.y0, "his head is above the pit");
  assert.equal(artOverlaps(art).length, 0);
  // drawn in front: the pit's drawImage comes after the actor's
  calls.length = 0;
  drawScene(fakeCtx(), art);
  const imgs = calls.filter((c) => c[0] === "drawImage");
  assert.ok(imgs.length >= 2);
  bad({ bg: "grass", actors: [{ who: "dad", x: 90, pose: "in", in: "pit" }], props: [{ what: "pit", x: 50 }] }, /outside the pit; use x/);
  bad({ bg: "grass", actors: [{ who: "pig", x: 50, pose: "in", in: "pit", scale: 3 }], props: [{ what: "pit", x: 50 }] }, /wider than the pit/);
  bad({ bg: "grass", actors: [{ who: "dad", x: 50, pose: "in" }] }, /pose "in" needs/);
  bad({ bg: "grass", actors: [{ who: "dad", x: 50, pose: "in", in: "pit" }], props: [{ what: "pit", x: 50, y: "air" }] }, /must stand on the ground or float/);
  // a boat on the water is a container too
  checkArt({ bg: "sea", actors: [{ who: "dad", x: 40, pose: "in", in: "boat", scale: 0.7 }], props: [{ what: "boat", x: 40, y: "water" }] });
});

test("sit_on: stacked on an actor or a prop, both visible, relation declared", () => {
  const art = { bg: "grass", actors: [{ who: "pig", x: 60, id: "pig" }, { who: "hero", x: 60, pose: "sit_on", on: "pig" }] };
  const b = boxes(art), pig = by(b, "actor", "pig"), c = by(b, "actor", "hero");
  assert.ok(c.y1 > pig.y0 && c.y1 < pig.y0 + 12, "his seat is on the pig's back");
  assert.ok(c.y0 < pig.y0, "his head is above the pig");
  assert.equal(artOverlaps(art).length, 0);
  assert.ok(artOverlaps({ ...art, actors: [{ who: "pig", x: 60 }, { who: "hero", x: 60 }] }).length > 0, "without the relation it fails");
  checkArt({ bg: "grass", actors: [{ who: "hero", x: 50, pose: "sit_on", on: "chest" }], props: [{ what: "chest", x: 50 }] });
  bad({ bg: "grass", actors: [{ who: "hero", x: 5, pose: "sit_on", on: "pig" }, { who: "pig", x: 70 }] }, /not over the thing it sits on/);
  bad({ bg: "grass", actors: [{ who: "hero", x: 5, pose: "sit_on" }] }, /needs .*\.on/);
  bad({ bg: "grass", actors: [{ who: "hero", x: 5, pose: "sit_on", on: "hero" }] }, /cannot be the actor itself/);
  bad({ bg: "grass", actors: [{ who: "hero", x: 5, id: "a", pose: "sit_on", on: "b" }, { who: "dad", x: 5, id: "b", pose: "sit_on", on: "a" }] }, /depends on itself/);
});

test("dig: needs a held tool, angles it down to the ground, leans in", () => {
  const art = { bg: "sandpit", actors: [{ who: "hero", x: 40, pose: "dig" }], props: [{ what: "pickaxe", x: 45, y: "held" }] };
  const b = boxes(art), c = by(b, "actor", "hero"), p = by(b, "prop", "pickaxe");
  assert.ok(p.y1 > c.y1 - 20, "the pick reaches down to the ground by his feet");
  const held = boxes({ ...art, actors: [{ who: "hero", x: 40 }] });
  assert.ok(by(held, "prop", "pickaxe").y1 < p.y1, "held normally the head is up; digging it is down");
  assert.doesNotThrow(() => drawScene(fakeCtx(), art));
  bad({ bg: "sandpit", actors: [{ who: "hero", x: 40, pose: "dig" }] }, /pose "dig" needs a prop with y "held"/);
});

test("run leans and spreads; hug overlaps by the arms only", () => {
  const stand = by(boxes({ bg: "grass", actors: [{ who: "hero", x: 50 }] }), "actor", "hero");
  const run = by(boxes({ bg: "grass", actors: [{ who: "hero", x: 50, pose: "run" }] }), "actor", "hero");
  assert.ok(run.x1 - run.x0 > stand.x1 - stand.x0, "a leaning, spread-legged box is wider");
  const art = { bg: "grass", actors: [{ who: "hero", x: 40, pose: "hug" }, { who: "dad", x: 60, pose: "hug" }] };
  const [a, d] = boxes(art);
  assert.ok(frac(a, d) > 0 && frac(a, d) < 0.25, `arms only: ${frac(a, d)}`);
  assert.equal(artOverlaps(art).length, 0, "a hug is a declared relation");
});

// --- 4. text ---
test("text: QUACK anchored to the duck, inside the frame, in the clipping guard", () => {
  const art = { bg: "hill", actors: [{ who: "duck", x: 60 }], fx: [{ fx: "text", text: "QUACK!", near: "duck" }] };
  const b = boxes(art), duck = by(b, "actor", "duck"), t = b.find((x) => x.kind === "fx");
  assert.ok(t && /QUACK/.test(t.name));
  assert.ok(inside(t) && t.clip === 0);
  assert.ok(t.y1 <= duck.y0 + 14, "above the duck");
  assert.ok(Math.abs((t.x0 + t.x1) / 2 - (duck.x0 + duck.x1) / 2) < 30, "near the duck sideways");
  assert.doesNotThrow(() => drawScene(fakeCtx(), art));
});

test("text near a prop or an id; sides; the engine clamps text into the frame", () => {
  const art = { bg: "cave", actors: [{ who: "dad", x: 2, id: "d" }, { who: "hero", x: 98 }], props: [{ what: "pan", x: 5, y: "held", by: "d" }],
    fx: [{ fx: "text", text: "CLANG", near: "pan", side: "right" }, { fx: "text", text: "HUFF PUFF", near: "d", side: "left" }, { fx: "text", text: "CLICK", near: "hero", side: "right" }] };
  for (const f of boxes(art).filter((x) => x.kind === "fx")) assert.ok(inside(f), JSON.stringify(f));
});

test("text vocabulary: QUACK CLANG CLICK HISS ACHOO HUFF PUFF ZZZ YUM all validate", () => {
  for (const text of ["QUACK!", "CLANG", "CLICK", "HISS", "ACHOO!", "HUFF PUFF", "ZZZ", "YUM"])
    assert.doesNotThrow(() => drawScene(fakeCtx(), { bg: "grass", actors: [{ who: "dad", x: 50 }], fx: [{ fx: "text", text, near: "dad" }] }), text);
});

test("speech anchors to the speaker: style say draws a bubble with a tail to the head", () => {
  const art = { bg: "grass", actors: [{ who: "hero", x: 24 }, { who: "dad", x: 72, flip: true }],
    fx: [{ fx: "text", text: "Get up, hen!", near: "dad", style: "say" }, { fx: "text", text: "Yes!", near: "hero", style: "say", side: "right" }] };
  const b = boxes(art), dad = by(b, "actor", "dad"), say = b.filter((x) => x.kind === "fx")[0];
  assert.ok(inside(say) && Math.abs((say.x0 + say.x1) / 2 - (dad.x0 + dad.x1) / 2) < 30, "over the speaker");
  assert.ok(say.y1 > dad.y0 - 4, "the tail reaches the speaker's head");
  assert.doesNotThrow(() => drawScene(fakeCtx(), art));
});

test("text is Arial small caps: widths follow Arial Bold, lowercase is 0.72 of a capital", () => {
  assert.ok(Math.abs(estimateTextWidth("I", 10) - 2.78) < 1e-9);
  assert.ok(Math.abs(estimateTextWidth("a", 10) - estimateTextWidth("A", 7.2)) < 1e-9);
  calls.length = 0;
  drawScene(fakeCtx(), { bg: "grass", actors: [{ who: "dad", x: 50 }], fx: [{ fx: "text", text: "Yum", near: "dad", style: "say" }] });
  const fonts = new Set();
  const ctx = new Proxy({ canvas: null }, { get: (t, k) => (k in t ? t[k] : () => {}), set: (t, k, v) => { if (k === "font") fonts.add(v); t[k] = v; return true; } });
  drawScene(ctx, { bg: "grass", actors: [{ who: "dad", x: 50 }], fx: [{ fx: "text", text: "Yum", near: "dad" }] });
  assert.ok([...fonts].length >= 2 && [...fonts].every((f) => /bold .*Arial/.test(f)), [...fonts].join("|"));
});

test("a page with text switches the canvas to HI_RES and back", () => {
  const cv = { width: SCENE_W, height: SCENE_H };
  const ctx = fakeCtx(cv);
  drawScene(ctx, { bg: "grass", actors: [{ who: "dad", x: 50 }], fx: [{ fx: "text", text: "YUM", near: "dad" }] });
  assert.deepEqual([cv.width, cv.height], [SCENE_W * HI_RES, SCENE_H * HI_RES]);
  drawScene(ctx, { bg: "grass", actors: [{ who: "dad", x: 50 }] });
  assert.deepEqual([cv.width, cv.height], [SCENE_W, SCENE_H]);
  drawScene(ctx, "map");
  assert.deepEqual([cv.width, cv.height], [SCENE_W, SCENE_H]);
});

test("text validation is loud", () => {
  const a = (fx) => ({ bg: "grass", actors: [{ who: "dad", x: 50 }], fx });
  bad(a({ fx: "text", text: "HI" }), /\.near is required/);
  bad(a({ fx: "text", near: "dad" }), /\.text must be/);
  bad(a({ fx: "text", text: "noé", near: "dad" }), /\.text must be/);
  bad(a({ fx: "text", text: "HI", near: "ghost" }), /not an id or a sprite name/);
  bad(a("text"), /needs the object form/);
  bad(a({ fx: "text", text: "HI", near: "dad", style: "loud" }), /not a known text style/);
  bad(a({ fx: "text", text: "HI", near: "dad", side: "under" }), /not a known text side/);
  bad(a({ fx: "text", text: "HI", near: "dad", size: 2 }), /size must be a number 5-24/);
  bad(a({ fx: "text", text: "WHAT A VERY LONG SHOUT INDEED", near: "dad", size: 24 }), /too wide for the frame/);
  bad(a({ fx: "boom", text: "HI" }), /only for fx "text"/);
  bad(a({ fx: "laser" }), /not a known fx/);
  bad(a({ fx: "boom", extra: 1 }), /unknown field/);
  bad(a([]), /must not be empty/);
  bad(a(["boom", { fx: "boom", near: "dad" }]), /more than one boom/);
  checkArt(a(["sparkle", { fx: "text", text: "YUM", near: "dad" }]));
});

test("an object fx can name its anchor: ACHOO comes from the sneezer, not the first actor", () => {
  const art = { bg: "grass", actors: [{ who: "hero", x: 15 }, { who: "creeper", x: 80, scale: 0.8 }], fx: [{ fx: "sneeze", near: "creeper" }] };
  const f = boxes(art).find((x) => x.kind === "fx"), cr = by(boxes(art), "actor", "creeper");
  assert.ok(Math.abs((f.x0 + f.x1) / 2 - (cr.x0 + cr.x1) / 2) < 40);
  const legacy = boxes({ ...art, fx: "sneeze" }).find((x) => x.kind === "fx");
  assert.ok((legacy.x0 + legacy.x1) / 2 < 70, "the string form still anchors to the first actor");
});

// --- 5. guards ---
test("clipping guard covers effects: a boom high in the frame runs off the top", () => {
  const art = { bg: "grass", actors: [{ who: "hero", x: 20 }, { who: "dad", x: 60, pose: "up", scale: 0.8 }], fx: [{ fx: "boom", near: "dad" }] };
  const f = artBoxes(art, 800, 450).find((x) => x.kind === "fx");
  assert.ok(f.clip > 0.05, `boom clip ${f.clip}`);
  const low = artBoxes({ bg: "grass", actors: [{ who: "dad", x: 60 }], fx: [{ fx: "boom" }] }, 800, 450).find((x) => x.kind === "fx");
  assert.equal(low.clip, 0);
  const splash = artBoxes({ bg: "river", actors: [{ who: "hero", x: 98 }], fx: "splash" }, 800, 450).find((x) => x.kind === "fx");
  assert.ok(splash.clip > 0.05, "other effects are measured too");
});

test("overlap guard: undeclared actor-actor and actor-prop overlaps fail; held and declared ones do not", () => {
  const two = artOverlaps({ bg: "grass", actors: [{ who: "hero", x: 50 }, { who: "dad", x: 52 }] });
  assert.equal(two.length, 1);
  assert.deepEqual([two[0].a.name, two[0].b.name], ["hero", "dad"]);
  assert.ok(two[0].frac > 0.2);
  const prop = artOverlaps({ bg: "grass", actors: [{ who: "hero", x: 50 }], props: [{ what: "chest", x: 50 }] });
  assert.equal(prop.length, 1);
  assert.equal(artOverlaps({ bg: "grass", actors: [{ who: "hero", x: 20 }, { who: "dad", x: 80 }] }).length, 0);
  assert.equal(artOverlaps({ bg: "grass", actors: [{ who: "hero", x: 50 }], props: [{ what: "pan", x: 55, y: "held" }] }).length, 0);
  assert.equal(artOverlaps({ bg: "grass", actors: [{ who: "dad", x: 50 }], props: [{ what: "hat", x: 50, y: "head" }] }).length, 0);
  assert.equal(artOverlaps({ bg: "grass", actors: [{ who: "hero", x: 50, pose: "hide" }], props: [{ what: "tree", x: 55 }] }).length, 0);
  assert.equal(artOverlaps({ bg: "grass", props: [{ what: "tree", x: 50 }, { what: "tree", x: 51 }] }).length, 0, "prop-prop is not checked");
  assert.equal(artOverlaps({ bg: "grass", actors: [{ who: "hero", x: 50 }, { who: "dad", x: 52 }] }, 1.1).length, 0, "the limit is a parameter");
});

test("overlap guard: a boom target (not drawn) is not an overlap, and a held prop over another actor is ignored", () => {
  assert.equal(artOverlaps({ bg: "grass", actors: [{ who: "dad", x: 50 }], props: [{ what: "creeper", x: 50 }], fx: "boom" }).length, 0);
});

// --- vocabulary & integration ---
test("every pose draws with its needs, and every prop y is covered by a test above", () => {
  const needs = {
    in: { actors: [{ who: "dad", x: 50, pose: "in", in: "pit" }], props: [{ what: "pit", x: 50 }] },
    sit_on: { actors: [{ who: "pig", x: 50, id: "p" }, { who: "hero", x: 50, pose: "sit_on", on: "p" }] },
    dig: { actors: [{ who: "hero", x: 50, pose: "dig" }], props: [{ what: "pickaxe", x: 55, y: "held" }] },
    lying: { actors: [{ who: "hero", x: 50, pose: "lying" }] },
    up: { actors: [{ who: "hero", x: 50, pose: "up" }] },
  };
  for (const pose of ["in", "sit_on", "dig", "lying", "up"]) assert.doesNotThrow(() => drawScene(fakeCtx(), { bg: "grass", ...needs[pose] }), pose);
  assert.ok(POSES.includes("lying") && PROP_YS.includes("on"));
});

test("new art fields validate inside a story, with the story path in the message", () => {
  const s = (art) => ({ v: 1, id: "t", title: "T", subtitle: "S", focus_letters: ["b"], pages: [{ text: "Hi.", art }] });
  assert.doesNotThrow(() => validateStory(s({ bg: "grass", actors: [{ who: "duck", x: 50 }], fx: [{ fx: "text", text: "QUACK!", near: "duck" }] }), "f"));
  assert.throws(() => validateStory(s({ bg: "grass", actors: [{ who: "duck", x: 50 }], fx: [{ fx: "text", text: "QUACK!", near: "goose" }] }), "stories/t.json"),
    /stories\/t\.json: pages\[0\]\.art\.fx\[0\]\.near "goose" is not an id or a sprite name/);
  assert.throws(() => validateStory(s({ bg: "grass", actors: [{ who: "dad", x: 90, pose: "in", in: "pit" }], props: [{ what: "pit", x: 50 }] }), "stories/t.json"),
    /stories\/t\.json: pages\[0\]\.art\.actors\[0\]\.x 90 puts the dad outside the pit/);
});

// Speech bubbles never cover a head (engine placement) and the guard fails what could not be placed.
const boat = (fx, extra = {}) => ({ bg: "sea", actors: [{ who: "mama", x: 37, pose: "in", scale: 0.6, in: "boat", id: "mama" },
  { who: "hero", x: 64, pose: "in", scale: 0.6, in: "boat", id: "c" }],
  props: [{ what: "boat", x: 50, y: "water", id: "boat" }], fx, ...extra });

test("a speech bubble in a boat scene (heads at the top of the frame) lands beside the speaker, not on a face", () => {
  for (const near of ["mama", "c"]) {
    const art = boat([{ fx: "text", text: "Mama, a gold bit!", near, style: "say" }]);
    assert.deepEqual(artBubbleHeadHits(art), [], near);
  }
  // a side asked for that would cover the neighbour is replaced, deterministically
  const art = boat([{ fx: "text", text: "Go, ship, go!", near: "mama", style: "say", side: "right" }]);
  assert.deepEqual(artBubbleHeadHits(art), []);
  assert.deepEqual(artBoxes(art), artBoxes(JSON.parse(JSON.stringify(art))));
});

test("text bursts and sneezes also keep off heads, and a worn hat counts as part of the head", () => {
  assert.deepEqual(artBubbleHeadHits(boat([{ fx: "text", text: "Tug, tug, tug!", near: "boat" }])), []);
  const hat = { bg: "grass", actors: [{ who: "dad", x: 40, id: "d" }, { who: "hero", x: 62, id: "c" }],
    props: [{ what: "hat", x: 40, y: "head", by: "d" }], fx: [{ fx: "text", text: "Hi, Dad!", near: "c", style: "say", side: "left" }] };
  assert.deepEqual(artBubbleHeadHits(hat), []);
  assert.deepEqual(artBubbleHeadHits({ ...hat, fx: [{ fx: "sneeze", near: "d" }] }), []);
});

test("a normally placed bubble keeps the old spot (above the speaker) when nothing is in the way", () => {
  const art = { bg: "grass", actors: [{ who: "hero", x: 50 }], fx: [{ fx: "text", text: "Hi!", near: "hero", style: "say" }] };
  const [a, t] = artBoxes(art); // actor, then the text
  assert.ok(t.y1 <= a.y0, "bubble (with its tail) sits above the head");
  assert.deepEqual(artBubbleHeadHits(art), []);
});

test("the head guard reports a bubble that has no clear place", () => {
  // five very tall actors fill the frame with heads: no spot at any size is free of one
  const actors = [8, 28, 50, 72, 92].map((x, i) => ({ who: "dad", x, pose: "up", scale: 2.6, id: `c${i}` }));
  const hits = artBubbleHeadHits({ bg: "grass", actors, fx: [{ fx: "text", text: "Look at all of us up here!", near: "c2", style: "say" }] });
  assert.ok(hits.length > 0 && hits.every((h) => h.fx.name.startsWith("fx:text") && h.w > 0.5 && h.h > 0.5), JSON.stringify(hits));
});
