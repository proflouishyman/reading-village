import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SPRITE_NAMES } from "../../app/js/sprites.js";
import {
  resolveSprite, standInsUsed, STAND_IN, validateEarn, validateVillage, validateTreasure, validateEventResult, treasureCount,
  validatePromotions, validatePromoteReply, promotable, promotionHint, offerStatus, canTrade, unlockChoices, toggleSelection, pileSections, pileSignature, villagerSprite, badgesFor, LEVEL_BADGE,
} from "../../app/js/villagelogic.js";

const CFG = JSON.parse(readFileSync(new URL("../../config/minecraft.json", import.meta.url)));

/** A GET /api/village body built from the shipped config (what the server returns, minus derived numbers). */
function villageBody(over = {}) {
  const v = CFG.village;
  return {
    enabled: true, wallet: { emerald: 10, wood: 0 }, points: 50, level: { index: 1, name: "Apprentice", next_at: 80 },
    levels: v.levels, bells: { earned: 1, spent: 0, available: 1 }, promotions: { earned: 3, used: 0, available: 3, spent: 54, next_at: 70 }, first_free: true, earn: CFG.earn, trades: CFG.trades, rev: 0,
    professions: v.professions.map((p) => ({ id: p.id, name: p.name, job_block_sprite: p.job_block_sprite, unlock_emeralds: p.unlock_emeralds,
      requires: p.requires ?? null, unlocked: false, can_unlock: p.id !== "wandering_trader", level: 0, level_name: "Novice", can_promote: false,
      offers: p.offers.map((o) => ({ ...o, locked: o.min_level > 1 })) })),
    ...over,
  };
}

test("every sprite name in the shipped config resolves (own sprite or a listed stand-in)", () => {
  const names = new Set();
  for (const p of CFG.village.professions) {
    names.add(p.job_block_sprite);
    p.offers.forEach((o) => names.add(o.sprite));
  }
  for (const rolls of Object.values(CFG.tiers)) rolls.forEach((r) => names.add(r.sprite));
  for (const t of CFG.trades) [...Object.keys(t.give), ...Object.keys(t.get)].forEach((k) => names.add(k));
  for (const n of names) assert.ok(SPRITE_NAMES.includes(resolveSprite(n)), n);
});

test("every profession has its own villager sprite; stand-ins point at real sprites", () => {
  for (const p of CFG.village.professions) assert.ok(SPRITE_NAMES.includes(villagerSprite(p)), p.id);
  for (const [k, v] of Object.entries(STAND_IN)) {
    assert.ok(SPRITE_NAMES.includes(v), `stand-in ${k} -> ${v}`);
    assert.ok(!SPRITE_NAMES.includes(k), `${k} is now drawn: remove its stand-in`);
  }
  assert.deepEqual(badgesFor(CFG.village.levels.names), ["badge_stone", "badge_iron", "badge_gold", "badge_emerald", "badge_diamond"]);
});

test("resolveSprite throws loudly for an unknown name and a stand-in whose target is missing", () => {
  assert.throws(() => resolveSprite("no_such_thing"), /no_such_thing/);
  assert.throws(() => resolveSprite("sword", ["bow"]), /no stand-in|not in sprites/);
  assert.throws(() => resolveSprite(7), /string/);
  assert.equal(resolveSprite("sword"), "diamond_sword");
  assert.deepEqual(standInsUsed(["bow", "sword", "sword", "apple"]), ["apple", "sword"]);
});

test("validateEarn requires the four positive integer rates and nothing else", () => {
  assert.deepEqual(validateEarn(CFG.earn), CFG.earn);
  assert.throws(() => validateEarn({ ...CFG.earn, word_emerald: 0 }), /word_emerald/);
  assert.throws(() => validateEarn({ ...CFG.earn, craft_emerald: "1" }), /craft_emerald/);
  assert.throws(() => validateEarn({ ...CFG.earn, extra: 1 }), /unknown field/);
  const { story_first_emerald, ...rest } = CFG.earn;
  assert.throws(() => validateEarn(rest), /story_first_emerald/);
  assert.throws(() => validateEarn(null), /object/);
});

test("validateVillage accepts the shipped shape and names the field that is wrong", () => {
  assert.ok(validateVillage(villageBody()));
  assert.throws(() => validateVillage(villageBody({ points: "50" })), /points/);
  assert.throws(() => validateVillage(villageBody({ bells: { earned: 1, spent: 0 } })), /bells/);
  assert.throws(() => validateVillage(villageBody({ levels: { names: ["a"], thresholds: [0] } })), /no badge sprite/);
  const bad = villageBody();
  bad.professions[0].offers[0].sprite = "mystery";
  assert.throws(() => validateVillage(bad), /mystery/);
  const bad2 = villageBody();
  bad2.professions[3].requires = "some";
  assert.throws(() => validateVillage(bad2), /requires/);
  const bad3 = villageBody();
  delete bad3.professions[0].offers[0].locked;
  assert.throws(() => validateVillage(bad3), /locked/);
});

test("validateVillage checks the per-villager level and the promotions block (breaking shape change: no silent defaults)", () => {
  const withProm = (over) => villageBody({ promotions: { earned: 3, used: 1, available: 2, spent: 54, next_at: 70 }, ...over });
  assert.ok(validateVillage(withProm()));
  for (const k of ["earned", "used", "available", "spent", "next_at"]) {
    const pr = { earned: 3, used: 1, available: 2, spent: 54, next_at: 70 };
    delete pr[k];
    assert.throws(() => validateVillage(withProm({ promotions: pr })), new RegExp(k));
  }
  assert.throws(() => validateVillage(villageBody({ promotions: undefined })), /promotions/);
  assert.throws(() => validateVillage(withProm({ promotions: { earned: 3, used: 1, available: 3, spent: 54, next_at: 70 } })), /earned - used/);
  assert.throws(() => validateVillage(withProm({ promotions: { earned: 3, used: 1, available: 2, spent: 54, next_at: 54 } })), /next_at/);
  assert.throws(() => validatePromotions({ earned: 1, used: 0, available: 1, spent: 10, next_at: 25, extra: 1 }), /extra/);
  const noLevel = villageBody();
  delete noLevel.professions[0].level;
  assert.throws(() => validateVillage(noLevel), /level/);
  const wrongName = villageBody();
  wrongName.professions[0].level_name = "Master";
  assert.throws(() => validateVillage(wrongName), /level_name/);
  const beyond = villageBody();
  beyond.professions[0].level = 5;
  assert.throws(() => validateVillage(beyond), /level/);
  const locked = villageBody();
  locked.professions[1].level = 1; locked.professions[1].level_name = "Apprentice"; // not unlocked yet
  assert.throws(() => validateVillage(locked), /not unlocked/);
  const noFlag = villageBody();
  delete noFlag.professions[0].can_promote;
  assert.throws(() => validateVillage(noFlag), /can_promote/);
});

test("the promotion helpers: who can be promoted, and the countdown text", () => {
  const v = villageBody();
  v.professions[0].unlocked = true; v.professions[0].can_promote = true;
  v.professions[2].unlocked = true; v.professions[2].can_promote = true;
  assert.deepEqual(promotable(v).map((p) => p.id), [v.professions[0].id, v.professions[2].id]);
  assert.equal(promotionHint({ earned: 3, used: 0, available: 3, spent: 54, next_at: 70 }), "Spend 16 more emeralds for a promotion");
  assert.equal(promotionHint({ earned: 1, used: 0, available: 1, spent: 24, next_at: 25 }), "Spend 1 more emerald for a promotion");
});

test("validatePromoteReply requires the promoted villager's new level to agree with the village it ships", () => {
  const v = villageBody();
  v.professions[1].unlocked = true; v.professions[1].level = 1; v.professions[1].level_name = "Apprentice";
  const p = v.professions[1];
  const reply = { village: v, wallet: { emerald: 3 }, profession: { id: p.id, name: p.name, level: 1, level_name: "Apprentice" }, rev: 4 };
  assert.equal(validatePromoteReply(reply), reply);
  assert.throws(() => validatePromoteReply({ ...reply, profession: { ...reply.profession, level: 2, level_name: "Journeyman" } }), /disagrees/);
  assert.throws(() => validatePromoteReply({ ...reply, rev: undefined }), /rev/);
  assert.throws(() => validatePromoteReply({ ...reply, profession: { id: p.id, name: p.name } }), /profession/);
});

test("validateTreasure checks states and sprites; event replies check their optional extras", () => {
  const entry = { tid: "t000001", label: "Name Tags", sprite: "name_tag", items: [{ item: "minecraft:name_tag", count: 2 }], source: { kind: "shop", ref: "x" }, status: "kept", state: "kept", delivery: null };
  const body = { treasure: [entry], enabled: true, server_running: false, problem: null, rev: 1 };
  assert.ok(validateTreasure(body));
  assert.throws(() => validateTreasure({ ...body, treasure: [{ ...entry, state: "sent" }] }), /state/);
  assert.throws(() => validateTreasure({ ...body, problem: 3 }), /problem/);
  assert.ok(validateEventResult({ ok: true }));
  assert.ok(validateEventResult({ ok: true, treasure: [{ label: "x", sprite: "sword" }] }));
  assert.throws(() => validateEventResult({ ok: false }), /ok:true/);
  assert.throws(() => validateEventResult({ ok: true, level_up: { index: 2, name: "Journeyman" } }), /no longer exists/);
  assert.throws(() => validateEventResult({ ok: true, treasure: [{ label: "x", sprite: "nope" }] }), /nope/);
  assert.equal(treasureCount({ items: [{ count: 2 }, { count: 8 }, {}] }), 11);
});

test("offers are ok, poor (dimmed) or locked (greyed); trades need the resources; unlock choices follow bells/emeralds", () => {
  assert.equal(offerStatus({ price: 5, locked: false }, { emerald: 5 }), "ok");
  assert.equal(offerStatus({ price: 5, locked: false }, { emerald: 4 }), "poor");
  assert.equal(offerStatus({ price: 1, locked: true }, { emerald: 99 }), "locked");
  assert.equal(canTrade({ give: { wood: 10 } }, { wood: 10 }), true);
  assert.equal(canTrade({ give: { wood: 10 } }, { wood: 9 }), false);
  const p = { can_unlock: true, unlock_emeralds: 20 };
  assert.deepEqual(unlockChoices(villageBody(), p), { free: true, bell: true, emeralds: true });
  const later = villageBody({ first_free: false, bells: { earned: 0, spent: 0, available: 0 }, wallet: { emerald: 19 } });
  assert.deepEqual(unlockChoices(later, p), { free: false, bell: false, emeralds: false });
  assert.deepEqual(unlockChoices({ ...later, bells: { earned: 1, spent: 0, available: 1 }, wallet: { emerald: 20 } }, p), { free: false, bell: true, emeralds: true });
  assert.deepEqual(unlockChoices(later, { ...p, can_unlock: false }), { free: false, bell: false, emeralds: false });
});

test("selection toggles only kept treasure; the pile splits kept from sent and re-renders on a state change", () => {
  const a = { tid: "t1", state: "kept" }, b = { tid: "t2", state: "on_the_way" }, c = { tid: "t3", state: "in_chest" };
  let sel = new Set();
  sel = toggleSelection(sel, a);
  assert.deepEqual([...sel], ["t1"]);
  assert.deepEqual([...toggleSelection(sel, b)], ["t1"], "a sent treasure cannot be chosen");
  assert.deepEqual([...toggleSelection(sel, a)], []);
  assert.equal(sel.size, 1, "toggle returns a new set");
  const { kept, sent } = pileSections([a, b, c]);
  assert.deepEqual(kept.map((t) => t.tid), ["t1"]);
  assert.deepEqual(sent.map((t) => t.tid), ["t3", "t2"], "newest sent first");
  assert.notEqual(pileSignature([a, b]), pileSignature([a, { ...b, state: "in_chest" }]));
});

test("badges are derived from the server's levels: one per level name, a level without a badge is a loud error", () => {
  const names = CFG.village.levels.names;
  assert.equal(badgesFor(names).length, names.length);
  for (const n of names) assert.ok(LEVEL_BADGE[n.toLowerCase()], n);
  // a sixth level in the config must not draw `undefined`: it throws, naming the level
  assert.throws(() => badgesFor([...names, "Grandmaster"]), /"Grandmaster" has no badge sprite/);
  assert.throws(() => validateVillage(villageBody({ levels: { names: [...names, "Grandmaster"], thresholds: [...CFG.village.levels.thresholds, 999] } })), /Grandmaster/);
  // a subset of levels is fine (fewer levels than badges)
  assert.deepEqual(badgesFor(["Novice", "Master"]), ["badge_stone", "badge_diamond"]);
  assert.throws(() => badgesFor(["Novice"], ["badge_iron"]), /not in sprites\.js/);
});
