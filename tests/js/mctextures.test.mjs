// mctextures.js: lookup, explicit modes, and loud failure when a mapped real texture is missing.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createTextures, McTextureError, validateMapping, getArtMode, setArtMode, artToTextureMode, manifestAvailable, setCurrentTextures, ART_KEY } from "../../app/js/mctextures.js";
import { SPRITE_NAMES, SPRITES, itemSprite, spriteSize, isRealOnly, REAL_ONLY_BOX } from "../../app/js/sprites.js";
import { STAND_IN, resolveSprite } from "../../app/js/villagelogic.js";

const repoMapping = JSON.parse(readFileSync(new URL("../../app/js/mctextures_map.json", import.meta.url)));
const mapping = {
  v: 1,
  entries: { diamond: { kind: "block", jar: "block/diamond_ore" }, bed: { kind: "composite", name: "bed" } },
  unmapped: { hero: "character" },
};
const manifest = { v: 1, files: { "blocks/diamond_ore.png": {}, "blocks/bed.png": {} },
  sprites: { diamond: "blocks/diamond_ore.png", bed: "blocks/bed.png" }, minecraft_version: "26.3", jar_sha256: "x" };

const make = (mode, over = {}) => createTextures({
  mode, mapping,
  fetchJson: async () => manifest,
  loadImage: async (url) => ({ url }),
  manifestUrl: "m.json", baseUrl: "/mc/", ...over,
});

test("every sprite id is classified exactly once (mapped or deliberately unmapped)", () => {
  validateMapping(repoMapping);
  const t = createTextures({ mode: "off", mapping: repoMapping });
  assert.deepEqual(t.unclassified(SPRITE_NAMES), [], "new sprite ids must be added to mctextures_map.json");
  // an id is a hand-drawn sprite, or a real-only picture that hand mode draws through its STAND_IN (the mobs)
  for (const id of [...Object.keys(repoMapping.entries), ...Object.keys(repoMapping.unmapped)]) {
    assert.ok(SPRITE_NAMES.includes(id) || Object.hasOwn(STAND_IN, id), `${id} is in the mapping but is neither a sprite nor a stand-in`);
  }
});

test("off mode returns null for everything (hand-drawn art)", async () => {
  const t = make("off");
  await t.load();
  assert.equal(t.getTexture("diamond"), null);
  assert.equal(t.usesReal("diamond"), false);
});

test("real mode returns the loaded image for mapped ids, null for deliberately unmapped", async () => {
  const t = make("real");
  await t.load();
  assert.deepEqual(t.getTexture("diamond"), { url: "/mc/blocks/diamond_ore.png" });
  assert.equal(t.getTexture("hero"), null);
  assert.deepEqual(t.unmapped(["hero", "diamond", "bed"]), ["hero"]);
  assert.equal(t.reason("hero"), "character");
  assert.equal(t.info().version, "26.3");
});

test("real mode throws on an unclassified id", async () => {
  const t = make("real");
  await t.load();
  assert.throws(() => t.getTexture("mystery"), McTextureError);
});

test("real mode load() rejects when the manifest cannot be read", async () => {
  const t = make("real", { fetchJson: async () => { throw new Error("HTTP 404"); } });
  await assert.rejects(t.load(), /cannot read m\.json.*404/);
});

test("real mode load() rejects when the manifest lacks a mapped id, naming it", async () => {
  const t = make("real", { fetchJson: async () => ({ ...manifest, sprites: { diamond: "blocks/diamond_ore.png" } }) });
  await assert.rejects(t.load(), /no texture extracted for sprite id "bed"/);
});

test("real mode load() rejects when an image file fails to load", async () => {
  const t = make("real", { loadImage: async (u) => { if (u.endsWith("bed.png")) throw new Error("404"); return {}; } });
  await assert.rejects(t.load(), /blocks\/bed\.png: 404/);
});

test("real mode getTexture before load() throws instead of returning nothing", () => {
  assert.throws(() => make("real").getTexture("diamond"), /before load/);
});

test("unknown mode is rejected", () => {
  assert.throws(() => make("sometimes"), McTextureError);
});

const memStore = (init = {}) => { const d = { ...init }; return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = v; }, d }; };

test("art mode: default hand, saved value round-trips, an invalid saved value is a loud error", () => {
  assert.equal(getArtMode(memStore()), "hand");
  const st = memStore();
  setArtMode("real", st);
  assert.equal(st.d[ART_KEY], "real");
  assert.equal(getArtMode(st), "real");
  assert.throws(() => getArtMode(memStore({ [ART_KEY]: "pretty" })), /not one of hand\|real/);
  assert.throws(() => setArtMode("pretty", memStore()), McTextureError);
  assert.throws(() => setArtMode("real", { setItem() { throw new Error("quota"); } }), /could not save.*quota/);
  assert.equal(artToTextureMode("hand"), "off");
  assert.equal(artToTextureMode("real"), "real");
});

test("manifestAvailable: 200 = installed, 404 = absent, anything else is an error", async () => {
  assert.equal(await manifestAvailable(async () => ({ status: 200, ok: true })), true);
  assert.equal(await manifestAvailable(async () => ({ status: 404, ok: false })), false);
  await assert.rejects(manifestAvailable(async () => ({ status: 500, ok: false })), /HTTP 500/);
});

test("the shipped mapping gives every badge a recognisable item or block texture (not the 2x3 hat-layer sliver)", () => {
  for (const id of ["badge_stone", "badge_iron", "badge_gold", "badge_emerald", "badge_diamond"]) {
    assert.ok(["item", "block"].includes(repoMapping.entries[id].kind), id);
  }
});

test("currency icons: real mode uses the ITEM texture, hand mode draws exactly the old art", () => {
  // Review finding 7: the wallet / prices / Sell showed emerald ORE in real texture mode.
  const jar = (id) => repoMapping.entries[id].jar;
  assert.equal(jar("emerald"), "block/emerald_ore");          // the mine grid still means the ore
  for (const [res, item, jarItem] of [["emerald", "emerald_item", "item/emerald"], ["diamond", "diamond_item", "item/diamond"],
    ["gold", "gold_item", "item/gold_ingot"], ["iron", "iron_item", "item/iron_ingot"], ["coal", "coal_item", "item/coal"]]) {
    assert.equal(itemSprite(res), item);
    assert.equal(jar(item), jarItem);
    assert.deepEqual(SPRITES[item], SPRITES[res], `${item}: hand mode is unchanged`);
  }
  assert.equal(itemSprite("wood"), "wood");                   // anything else passes through
});

// ---- mob pictures (real mode) ------------------------------------------------------------------------------------
const craftWords = JSON.parse(readFileSync(new URL("../../app/data/craft_words.json", import.meta.url))).words;
// craft word -> mob picture it must show in real mode
// PUP is hand-drawn on purpose (the real wolf pup is too small at Crafting Table size; see the unmapped reason).
const MOB_WORDS = { PIG: "pig", BAT: "bat", HEN: "hen", FOX: "fox", FROG: "frog", SQUID: "squid", FISH: "cod",
  CHICK: "chick", MULE: "mule", SLIME: "slime", BLAZE: "blaze", GOAT: "goat", SHEEP: "sheep", BEE: "bee", COW: "cow",
  RABBIT: "rabbit", PANDA: "panda", CAMEL: "camel", PIGLIN: "piglin", HOGLIN: "hoglin" };

test("every mob craft word shows its mob picture in real mode ", () => {
  const byWord = Object.fromEntries(craftWords.map((w) => [w.word, w.sprite]));
  for (const [word, mob] of Object.entries(MOB_WORDS)) {
    assert.ok(word in byWord, `${word} is not a craft word`);
    const e = repoMapping.entries[byWord[word]];
    assert.deepEqual(e, { kind: "mob", mob }, `${word} (sprite ${byWord[word]}) must map to the ${mob} picture`);
  }
  // hand mode is unchanged: BLAZE is still the torch and CHICK the hen (their own ids resolve through STAND_IN)
  assert.equal(resolveSprite("blaze"), "torch");
  assert.equal(resolveSprite("chick"), "hen");
});

// Regression: STICK showed the fishing rod because "stick" had no texture of its own and
// real mode drew its stand-in ("rod"). A craft word drawn through a stand-in must have its OWN real picture, except
// the explicit list below; and the items the parent named must point at the right texture.
const STAND_IN_OK = {};
test("craft words never borrow an unrelated real picture through a stand-in", () => {
  for (const w of craftWords) {
    if (!(w.sprite in STAND_IN) || w.sprite in STAND_IN_OK) continue;
    assert.ok(w.sprite in repoMapping.entries || w.sprite in repoMapping.unmapped,
      `${w.word}: sprite "${w.sprite}" has no real picture of its own, so real mode would show its stand-in "${STAND_IN[w.sprite]}"`);
  }
  const jar = (id) => repoMapping.entries[id]?.jar;
  const byWord = Object.fromEntries(craftWords.map((w) => [w.word, w.sprite]));
  for (const [word, want] of Object.entries({ STICK: "item/stick", MILK: "item/milk_bucket", ROCKET: "item/firework_rocket",
    BUCKET: "item/bucket", BONE: "item/bone", PUMPKIN: "block/carved_pumpkin", HELMET: "item/iron_helmet" })) {
    assert.equal(jar(byWord[word]), want, `${word} must show ${want}`);
  }
  // BOAT shows the real oak boat item (own id oak_boat); SHIP deliberately shows the hand-drawn sailing boat (classified unmapped).
  assert.equal(byWord.BOAT, "oak_boat");
  assert.equal(jar("oak_boat"), "item/oak_boat", "BOAT must show the real oak boat item");
  assert.equal(byWord.SHIP, "boat");
  assert.ok(SPRITE_NAMES.includes("boat") && "boat" in repoMapping.unmapped && !("boat" in repoMapping.entries), "SHIP uses the hand-drawn boat on purpose");
  // FLAG: the jar has no flat banner texture (the stand-in "banner" -> rug showed a rug), so the word uses its own
  // hand-drawn "flag" on purpose, in both modes: it exists as a sprite and is classified unmapped, like PUP/BED/MUD/RAFT.
  assert.equal(byWord.FLAG, "flag", "FLAG must use the hand-drawn flag, not the banner stand-in");
  assert.ok(SPRITE_NAMES.includes("flag") && "flag" in repoMapping.unmapped && !("flag" in repoMapping.entries), "flag is hand-drawn on purpose");
  assert.deepEqual(repoMapping.entries.leaf.tint, [72, 181, 24], "leaves are grey in the jar: they need the foliage tint");
});

test("resolveSprite: real mode draws the mob picture, hand mode keeps the stand-in", async () => {
  const realMap = { v: 1, entries: { frog: { kind: "mob", mob: "frog" }, pig: { kind: "mob", mob: "pig" } }, unmapped: {} };
  const man = { v: 1, files: { "mobs/frog.png": {}, "mobs/pig.png": {} }, sprites: { frog: "mobs/frog.png", pig: "mobs/pig.png" } };
  const mk = (mode) => createTextures({ mode, mapping: realMap, fetchJson: async () => man, loadImage: async (u) => ({ u }), manifestUrl: "m", baseUrl: "/mc/" });
  try {
    const real = mk("real");
    await real.load();
    setCurrentTextures(real);
    assert.equal(resolveSprite("frog"), "frog");
    assert.ok(isRealOnly("frog"));
    assert.deepEqual(spriteSize("frog"), REAL_ONLY_BOX);
    assert.equal(resolveSprite("pig"), "pig");            // hand-drawn id: unchanged
    assert.ok(!isRealOnly("pig"));
    assert.equal(resolveSprite("goat"), "spawn_egg");    // not mapped in this fake set: stand-in
    const off = mk("off");
    await off.load();
    setCurrentTextures(off);
    assert.equal(resolveSprite("frog"), "spawn_egg");
    assert.ok(!isRealOnly("frog"));
    assert.throws(() => spriteSize("frog"), /unknown sprite/);
  } finally {
    setCurrentTextures(null);
  }
});
