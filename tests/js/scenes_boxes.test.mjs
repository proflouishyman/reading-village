// "head" props (worn) and the clipping guard's bounding boxes (artBoxes), pure functions: no canvas needed.
import test from "node:test";
import assert from "node:assert/strict";
import { artBoxes, checkArt, ArtError, PROP_YS, SCENE_W, SCENE_H } from "../../app/js/scenes.js";
import { SPRITES, SPRITE_NAMES } from "../../app/js/sprites.js";

const NEW_PROPS = ["hat", "mud", "hut", "bun", "sock", "rod", "pot", "map", "bow", "pan", "nut", "web", "raft", "log",
  "bell", "junk", "gold_pig"];

test("the new prop sprites exist, and gold_pig is pig recoloured", () => {
  for (const n of NEW_PROPS) assert.ok(SPRITE_NAMES.includes(n), n);
  assert.equal(SPRITES.gold_pig.rows, SPRITES.pig.rows);
  assert.deepEqual(SPRITES.gold_pig.swap, { p: "y", P: "Y" });
  assert.ok(SPRITES.hat.rows.join("").includes("r"), "hat is red");
});

test('y "head" is a known prop y and puts the hat above the actor, over its head, drawn last', () => {
  assert.ok(PROP_YS.includes("head"));
  const art = { bg: "grass", actors: [{ who: "dad", x: 50 }], props: [{ what: "hat", x: 50, y: "head" }] };
  const [dad, hat] = artBoxes(art);
  assert.ok(Math.abs((hat.x0 + hat.x1) / 2 - (dad.x0 + dad.x1) / 2) < 0.01, "centred on dad");
  assert.ok(hat.y0 < dad.y0, "hat top is above the head top");
  assert.ok(hat.y1 > dad.y0 && hat.y1 < dad.y0 + (dad.y1 - dad.y0) / 2, "hat bottom overlaps the head only");
});

test('y "head" goes to the NEAREST actor, follows a head that is off-centre, and mirrors with flip', () => {
  const mk = (flip) => ({ bg: "grass", actors: [{ who: "dad", x: 10 }, { who: "hen", x: 80, flip }],
    props: [{ what: "crown", x: 75, y: "head" }] });
  const [dad, hen, crown] = artBoxes(mk(false));
  assert.ok(crown.x0 > dad.x1, "not on dad");
  assert.ok((crown.x0 + crown.x1) / 2 > (hen.x0 + hen.x1) / 2, "hen's head is to the right of its centre");
  const [, hen2, crown2] = artBoxes(mk(true));
  assert.ok((crown2.x0 + crown2.x1) / 2 < (hen2.x0 + hen2.x1) / 2, "flipped hen's head is on the left");
});

test('y "head" is a loud error with no actor, or when the nearest actor is not upright', () => {
  const bad = [
    { bg: "grass", props: [{ what: "hat", x: 5, y: "head" }] },
    { bg: "grass", actors: [{ who: "dad", x: 5, pose: "sleep" }], props: [{ what: "hat", x: 5, y: "head" }] },
    { bg: "grass", actors: [{ who: "dad", x: 5, pose: "sleep" }, { who: "hero", x: 90 }], props: [{ what: "hat", x: 6, y: "head" }] },
  ];
  for (const a of bad) assert.throws(() => checkArt(a, "art"), ArtError, JSON.stringify(a));
  checkArt({ bg: "grass", actors: [{ who: "dad", x: 5, pose: "sleep" }, { who: "hero", x: 90 }],
    props: [{ what: "hat", x: 91, y: "head" }] });
});

test('"held" is in the hand of the nearest actor, on the side it faces, overlapping the arm', () => {
  const [dad, pan] = artBoxes({ bg: "grass", actors: [{ who: "dad", x: 50 }], props: [{ what: "pan", x: 55, y: "held" }] });
  assert.ok(pan.x1 > dad.x1, "reaches out to the right of dad");
  assert.ok(pan.x0 < dad.x1, "but overlaps dad's hand at the arm's end");
  const [d2, p2] = artBoxes({ bg: "grass", actors: [{ who: "dad", x: 50, flip: true }], props: [{ what: "pan", x: 45, y: "held" }] });
  assert.ok(p2.x0 < d2.x0 && p2.x1 > d2.x0, "mirrored for a flipped dad");
});

test("artBoxes: sizes scale with the canvas and a fully visible element has clip 0", () => {
  const art = { bg: "grass", actors: [{ who: "hero", x: 50 }] };
  const [a] = artBoxes(art), [b] = artBoxes(art, SCENE_W * 4, SCENE_H * 4);
  assert.equal(a.clip, 0);
  assert.ok(Math.abs((b.x1 - b.x0) - 4 * (a.x1 - a.x0)) < 1e-9);
  assert.deepEqual([a.kind, a.name], ["actor", "hero"]);
});

test("artBoxes: an actor half off the left edge is 50% clipped; a prop past the right edge too", () => {
  const [c] = artBoxes({ bg: "grass", actors: [{ who: "dad", x: 0 }] });
  assert.ok(Math.abs(c.clip - 0.5) < 1e-9, String(c.clip));
  const [p] = artBoxes({ bg: "grass", actors: [], props: [{ what: "tree", x: 100 }] });
  assert.ok(Math.abs(p.clip - 0.5) < 1e-9);
});

test("artBoxes: mid-fall actors at the side count (the rotated box is measured)", () => {
  const inside = artBoxes({ bg: "sea", actors: [{ who: "hero", x: 50, pose: "fall" }] })[0];
  assert.equal(inside.clip, 0);
  const side = artBoxes({ bg: "grass", actors: [{ who: "hero", x: 95, pose: "fall" }] })[0];
  assert.ok(side.clip > 0.05, String(side.clip));
  const flipped = artBoxes({ bg: "grass", actors: [{ who: "hero", x: 95, pose: "fall", flip: true }] })[0];
  assert.ok(flipped.clip < side.clip, "falling toward the middle stays more in frame");
});

test("artBoxes: a boom replaces its target, which is not listed; bad art throws with the path", () => {
  const boxes = artBoxes({ bg: "grass", actors: [{ who: "dad", x: 30 }], props: [{ what: "creeper", x: 70 }], fx: "boom" });
  assert.deepEqual(boxes.map((b) => b.name), ["dad", "fx:boom"]); // the creeper is replaced by the blast
  assert.throws(() => artBoxes({ bg: "nope" }, 800, 450, "story p3 art"), /story p3 art\.bg/);
});
