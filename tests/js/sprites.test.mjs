// Sprite grids: every row of a sprite has the same width, every char is a palette key, and the
// characters keep the dimensions the scenes were composed against.
import test from "node:test";
import assert from "node:assert/strict";
import { SPRITES, PALETTE } from "../../app/js/sprites.js";

test("all sprites are rectangular and use only palette keys", () => {
  for (const [name, sp] of Object.entries(SPRITES)) {
    const w = sp.rows[0].length;
    for (const row of sp.rows) {
      assert.equal(row.length, w, `${name}: ragged row ${row}`);
      for (const ch of row) assert.ok(ch === "." || ch in PALETTE, `${name}: unknown char ${ch}`);
    }
  }
});

test("hero is 10x16 and dad is 10x18 (taller)", () => {
  assert.deepEqual([SPRITES.hero.rows[0].length, SPRITES.hero.rows.length], [10, 16]);
  assert.deepEqual([SPRITES.dad.rows[0].length, SPRITES.dad.rows.length], [10, 18]);
});

test("every prop sprite added for composable art exists and is small enough to read at story size", () => {
  for (const n of ["hat", "mud", "hut", "bun", "sock", "rod", "pot", "map", "bow", "pan", "nut", "web", "raft", "log", "bell", "junk", "gold_pig"]) {
    assert.ok(SPRITES[n], n);
    assert.ok(SPRITES[n].rows.length <= 14 && SPRITES[n].rows[0].length <= 16, `${n} size`);
  }
});

test("E1 story sprites exist, are small, and keep the sizes the scenes were composed against", () => {
  for (const n of ["chest_open", "pit", "bag", "rug", "bathtub", "steam", "catnip", "sand", "x_mark", "splash_big"]) {
    assert.ok(SPRITES[n], n);
    assert.ok(SPRITES[n].rows.length <= 14 && SPRITES[n].rows[0].length <= 20, `${n} size`);
  }
  // boat, web and bun were redrawn: the 'boat' scene keys place the boat by its 18x8 grid.
  assert.deepEqual([SPRITES.boat.rows[0].length, SPRITES.boat.rows.length], [18, 8]);
  assert.deepEqual([SPRITES.web.rows[0].length, SPRITES.web.rows.length], [13, 13]);
});

test("pit opening is wide enough for a person; sand differs from dirt", () => {
  const opening = SPRITES.pit.rows[2].replace(/[^a]/g, "").length;
  assert.ok(opening >= 12, `pit opening ${opening}`);
  assert.notDeepEqual(SPRITES.sand.rows, SPRITES.dirt.rows);
  assert.ok(!SPRITES.sand.rows.join("").includes("n"), "sand must not use dirt brown");
});

const VILLAGERS = ["librarian", "armorer", "weaponsmith", "toolsmith", "farmer", "fletcher", "cleric",
  "cartographer", "shepherd", "butcher", "fisherman", "mason", "leatherworker"].map((p) => `villager_${p}`);
const JOB_BLOCKS = ["lectern", "blast_furnace", "grindstone", "smithing_table", "composter", "fletching_table",
  "brewing_stand", "cartography_table", "loom", "smoker", "barrel", "stonecutter", "cauldron"];
const VILLAGE_ITEMS = ["badge_stone", "badge_iron", "badge_gold", "badge_emerald", "badge_diamond", "village_bell",
  "magic_portal", "enchanted_book", "spawn_egg", "diamond_sword", "diamond_pickaxe", "diamond_chestplate", "bow",
  "elytra", "golden_apple", "totem", "netherite_ingot", "name_tag", "saddle", "trident", "xp_bottle", "ender_pearl",
  "sapling", "music_disc"];

test("village: every villager, the trader, his llama and the locked silhouette exist at the shared 14x24 size", () => {
  for (const n of [...VILLAGERS, "wandering_trader", "villager_locked"]) {
    assert.ok(SPRITES[n], n);
    assert.deepEqual([SPRITES[n].rows[0].length, SPRITES[n].rows.length], [14, 24], `${n} size`);
  }
  assert.ok(SPRITES.trader_llama);
});

test("village: villagers keep the base look (green eyes, unibrow row, nose) and differ from each other", () => {
  const seen = new Set();
  for (const n of [...VILLAGERS, "wandering_trader"]) {
    const rows = SPRITES[n].rows;
    assert.ok(rows[5].includes("HHHH"), `${n} unibrow`);
    assert.ok(rows[6].includes("L"), `${n} green eyes`);
    assert.ok(rows[7].includes("jj"), `${n} nose`);
    const key = rows.join("|");
    assert.ok(!seen.has(key), `${n} is identical to another villager`);
    seen.add(key);
  }
  assert.ok(!SPRITES.villager_locked.rows.join("").match(/[iL]/), "locked is a silhouette (no face colours)");
});

test("village: job-site blocks and treasure/badge/portal sprites exist and fit the prop size limits", () => {
  for (const n of [...JOB_BLOCKS, ...VILLAGE_ITEMS]) {
    assert.ok(SPRITES[n], n);
    if (n === "magic_portal") continue;
    assert.ok(SPRITES[n].rows.length <= 14 && SPRITES[n].rows[0].length <= 16, `${n} size`);
  }
  assert.ok(SPRITES.magic_portal.rows.length >= 20, "portal is big enough for the send scene");
});

// ---- art modes (docs/textures.md): hand-drawn vs real textures -------------------------------------------------
import { spriteSize, spriteCanvas, spriteImage, spriteElement, drawSprite, REAL_SCALE } from "../../app/js/sprites.js";
import { createTextures, setCurrentTextures, McTextureError } from "../../app/js/mctextures.js";
import { readFileSync } from "node:fs";

const MAPPING = JSON.parse(readFileSync(new URL("../../app/js/mctextures_map.json", import.meta.url)));

/** A minimal fake canvas/document: records drawImage calls, no pixels. */
function fakeDom() {
  const made = [];
  globalThis.document = { createElement: (tag) => {
    assert.equal(tag, "canvas");
    const cv = { width: 0, height: 0, calls: [], getContext() { return { imageSmoothingEnabled: true, fillRect() {}, set fillStyle(v) {}, drawImage: (...a) => cv.calls.push(a) }; } };
    made.push(cv);
    return cv;
  } };
  return made;
}

/** A texture set where every mapped id has a fake image of the given size (no Mojang files needed). */
async function fakeSet(mode, size = { width: 16, height: 16 }) {
  const files = {}, sprites = {};
  for (const id of Object.keys(MAPPING.entries)) { files[`f/${id}.png`] = {}; sprites[id] = `f/${id}.png`; }
  const t = createTextures({ mode, mapping: MAPPING, fetchJson: async () => ({ v: 1, files, sprites, minecraft_version: "t", jar_sha256: "x" }),
    loadImage: async (u) => ({ url: u, ...size }), manifestUrl: "m", baseUrl: "/" });
  await t.load();
  return t;
}

test("hand mode: the canvas is the hand-drawn grid at logical size, and spriteImage is that same canvas", async () => {
  fakeDom();
  setCurrentTextures(await fakeSet("off"));
  const { w, h } = spriteSize("villager_librarian");
  const cv = spriteCanvas("villager_librarian");
  assert.deepEqual([cv.width, cv.height], [w, h]);
  assert.equal(spriteImage("villager_librarian"), cv);
  const el = spriteElement("villager_librarian", 5);
  assert.deepEqual([el.width, el.height], [w * 5, h * 5]);
});

test("real mode: a mapped sprite is a hi-res canvas of spriteSize * REAL_SCALE, bottom-centred, drawn at the logical size", async () => {
  fakeDom();
  setCurrentTextures(await fakeSet("real", { width: 120, height: 216 }));
  const { w, h } = spriteSize("villager_librarian");
  assert.deepEqual([w, h], [14, 24], "the logical size stays the hand-drawn grid");
  const img = spriteImage("villager_librarian");
  assert.deepEqual([img.width, img.height], [w * REAL_SCALE, h * REAL_SCALE]);
  // 120x216 fits the 140x240 box at integer scale 1, bottom-aligned and centred
  assert.deepEqual(img.calls[0].slice(1), [10, 24, 120, 216]);
  // spriteCanvas (scenes slice it by logical pixel) is still the hand-drawn grid in real mode
  assert.deepEqual([spriteCanvas("villager_librarian").width, spriteCanvas("villager_librarian").height], [w, h]);
  // the element and drawSprite size by spriteSize * scale, not by the hi-res canvas width
  const el = spriteElement("villager_librarian", 5);
  assert.deepEqual([el.width, el.height], [w * 5, h * 5]);
  const calls = [];
  drawSprite({ drawImage: (...a) => calls.push(a), imageSmoothingEnabled: true }, "villager_librarian", 3, 4, 2);
  assert.deepEqual(calls[0].slice(1), [3, 4, w * 2, h * 2]);
  assert.equal(calls[0][0], img, "cached per texture and id");
});

test("real mode: a small item texture is upscaled by an integer factor; unmapped ids stay hand-drawn", async () => {
  fakeDom();
  setCurrentTextures(await fakeSet("real", { width: 16, height: 16 }));
  const { w, h } = spriteSize("coal");
  const img = spriteImage("coal");
  assert.deepEqual([img.width, img.height], [w * REAL_SCALE, h * REAL_SCALE]);
  const [, dx, dy, dw, dh] = img.calls[0];
  assert.equal(dw, dh);
  assert.equal(dw % 16, 0, "integer upscale keeps pixels square");
  assert.equal(dy + dh, h * REAL_SCALE, "bottom aligned");
  assert.equal(spriteImage("hero"), spriteCanvas("hero"), "unmapped = deliberately hand-drawn");
});

test("real mode with a missing texture for a mapped id throws instead of drawing the hand-drawn sprite", async () => {
  fakeDom();
  const t = await fakeSet("real");
  setCurrentTextures({ ...t, getTexture: () => { throw new McTextureError("missing"); } });
  assert.throws(() => spriteImage("coal"), McTextureError);
});

test.after(() => { setCurrentTextures(null); delete globalThis.document; });

test("forest, pirate and witch story sprites exist; the two characters have the sizes scenes.js tables assume", () => {
  const props = ["owl", "mushroom", "berry_bush", "deer", "bunny", "tent", "campfire", "pine", "pirate_hat", "pirate_flag", "flag",
    "polly", "spyglass", "plank", "witch_hat", "broom", "flask", "black_cat"];
  for (const n of props) {
    assert.ok(SPRITES[n], n);
    assert.ok(SPRITES[n].rows.length <= 16 && SPRITES[n].rows[0].length <= 20, `${n} size`);
  }
  assert.deepEqual([SPRITES.pirate.rows[0].length, SPRITES.pirate.rows.length], [10, 17]);
  assert.deepEqual([SPRITES.witch.rows[0].length, SPRITES.witch.rows.length], [10, 18]);
});
