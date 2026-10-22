// Pure logic for the Village, shop and Treasure Pile screens (no DOM, so node can test it).
// Every shape the server sends is validated here at the boundary and throws loudly on a mismatch
// (docs/design.md "Villager shop and Magic Chest"); nothing is coerced or defaulted.
import { SPRITE_NAMES } from "./sprites.js";
import { getTextures } from "./mctextures.js";

export const EARN_KEYS = ["word_emerald", "story_first_emerald", "story_replay_emerald", "craft_emerald"];
/**
 * The badge sprite of each level NAME (real Minecraft villager levels). The server's levels (config
 * village.levels.names) decide how many levels exist; every one of them must have a badge here.
 */
export const LEVEL_BADGE = {
  novice: "badge_stone", apprentice: "badge_iron", journeyman: "badge_gold", expert: "badge_emerald", master: "badge_diamond",
};

/** One badge sprite per level name, in level order. A level with no badge (or a badge with no sprite) throws. */
export function badgesFor(names, known = SPRITE_NAMES) {
  return names.map((n) => {
    const b = typeof n === "string" ? LEVEL_BADGE[n.toLowerCase()] : undefined;
    if (!b) throw new Error(`level "${n}" has no badge sprite (add it to LEVEL_BADGE in villagelogic.js and draw it in sprites.js)`);
    if (!known.includes(b)) throw new Error(`level "${n}" maps to badge "${b}" which is not in sprites.js`);
    return b;
  });
}
export const TREASURE_STATES = ["kept", "on_the_way", "in_chest", "failed"];
export const PROFESSION_SPRITE_PREFIX = "villager_";

/**
 * Stand-ins for sprite names that the server vocabulary (ITEM_SPRITES / JOB_BLOCK_SPRITES in minecraft_bridge.py)
 * allows but sprites.js does not draw yet. A name is drawn by its own sprite when it exists; otherwise by the
 * stand-in listed here; a name in neither place is an error. This is an explicit, counted gap (standInsUsed), not a
 * silent fallback: the dashboard lists every stand-in in use so real art can replace them.
 */
export const STAND_IN = {
  apple: "golden_apple", arrow: "bow", axe: "pickaxe", banner: "rug", book: "enchanted_book", bookshelf: "lectern",
  boots: "diamond_chestplate", leggings: "diamond_chestplate", helmet: "diamond_chestplate",
  chestplate: "diamond_chestplate", horse_armor: "diamond_chestplate", bottle: "xp_bottle", potion: "xp_bottle",
  bread: "bun", cookie: "bun", cake: "bun", pie: "bun", brick: "stone", quartz: "stone", dripstone: "stone",
  terracotta: "stone", bucket: "cauldron", bundle: "bag", carrot: "chest", meat: "chest", coral: "sapling",
  flower: "sapling", lichen: "sapling", pumpkin: "chest", sea_pickle: "chest", nautilus: "chest", key: "chest",
  redstone: "chest", crossbow: "bow", glowstone: "sun", hoe: "pickaxe", shovel: "pickaxe", shears: "pickaxe",
  // Crafting Table words (levels 2-6) with no hand-drawn sprite: animals show the spawn egg they deliver.
  frog: "spawn_egg", squid: "spawn_egg", goat: "spawn_egg", sheep: "spawn_egg", cow: "spawn_egg", rabbit: "spawn_egg",
  panda: "spawn_egg", camel: "spawn_egg", parrot: "spawn_egg", turtle: "spawn_egg", piglin: "spawn_egg", hoglin: "spawn_egg",
  flint: "stone", nest: "barrel", hive: "composter", ship: "boat", stick: "rod", clock: "moon", shell: "ender_pearl",
  bone: "pup", mule: "saddle", slime: "emerald_item", vine: "sapling", leaf: "sapling", tube: "diamond_item",
  bee: "gold_item", snow: "cloud", rail: "iron_item", cactus: "sapling", candle: "torch",
  heart_of_sea: "emerald", ice: "diamond", netherite: "netherite_ingot", painting: "map", shield: "badge_stone",
  sniffer_egg: "spawn_egg", fish_bucket: "fish", sword: "diamond_sword", wool: "rug", llama: "trader_llama",
  // CHICK and BLAZE have their own ids so real mode can show the baby chicken and the blaze (mctextures_map.json);
  // in hand mode they are drawn exactly as before (the hen, the torch).
  chick: "hen", blaze: "torch",
  // Own ids so real mode shows the right item (MILK: milk bucket, ROCKET: firework rocket); hand mode keeps the stand-in.
  milk: "cauldron", rocket: "bow",
  // BOAT: real mode shows the oak boat item; hand mode draws the hand-drawn boat (SHIP draws that boat in both modes).
  oak_boat: "boat",
};

/**
 * The sprite actually drawn for a server sprite name. Throws for a name that has neither a sprite nor a stand-in.
 * In real art mode a stand-in name that mctextures_map.json maps to a real picture (the mobs: frog, goat, bee, ...)
 * is drawn as that picture, not as its stand-in (the spawn egg); hand mode always uses the stand-in.
 */
export function resolveSprite(name, known = SPRITE_NAMES, standIn = STAND_IN) {
  if (typeof name !== "string") throw new Error(`sprite name must be a string (got ${JSON.stringify(name)})`);
  if (known.includes(name)) return name;
  if (Object.hasOwn(standIn, name) && getTextures()?.usesReal(name)) return name;
  if (Object.hasOwn(standIn, name) && known.includes(standIn[name])) return standIn[name];
  throw new Error(`sprite "${name}" is not in sprites.js and has no stand-in (see STAND_IN in villagelogic.js)`);
}

/** Sorted list of the names (of `names`) that are drawn by a stand-in, for the dashboard. */
export function standInsUsed(names, known = SPRITE_NAMES) {
  return [...new Set(names)].filter((n) => !known.includes(n)).sort();
}

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const isNat = (x) => Number.isInteger(x) && x >= 0;

function need(cond, at, what) {
  if (!cond) throw new Error(`${at}: ${what}`);
}

/** `earn` = {word_emerald, story_first_emerald, story_replay_emerald, craft_emerald}, positive integers, nothing else. */
export function validateEarn(earn, at = "earn") {
  need(isObj(earn), at, "must be an object");
  for (const k of EARN_KEYS) need(Number.isInteger(earn[k]) && earn[k] > 0, `${at}.${k}`, `must be a positive integer (got ${JSON.stringify(earn[k])})`);
  for (const k of Object.keys(earn)) need(EARN_KEYS.includes(k), at, `unknown field "${k}"`);
  return earn;
}

/** `promotions` = {earned, used, available, spent, next_at}: non-negative integers, available = earned - used, next_at > spent. */
export function validatePromotions(pr, at = "promotions") {
  need(isObj(pr), at, "must be an object");
  for (const k of ["earned", "used", "available", "spent", "next_at"]) need(isNat(pr[k]), `${at}.${k}`, `must be a non-negative integer (got ${JSON.stringify(pr[k])})`);
  for (const k of Object.keys(pr)) need(["earned", "used", "available", "spent", "next_at"].includes(k), at, `unknown field "${k}"`);
  need(pr.available === pr.earned - pr.used, `${at}.available`, "must equal earned - used");
  need(pr.next_at > pr.spent, `${at}.next_at`, "must be beyond the emeralds spent");
  return pr;
}

/** Validate a POST /api/village/promote reply: {village, wallet, profession:{id,name,level,level_name}, rev}. */
export function validatePromoteReply(r, known = SPRITE_NAMES) {
  const at = "/api/village/promote reply";
  need(isObj(r) && isObj(r.profession) && isNat(r.rev), at, "must be {village, wallet, profession, rev}");
  need(typeof r.profession.id === "string" && typeof r.profession.name === "string" && isNat(r.profession.level) && r.profession.level >= 1 && typeof r.profession.level_name === "string", `${at}.profession`, "must be {id, name, level >= 1, level_name}");
  need(isObj(r.wallet) && isNat(r.wallet.emerald), `${at}.wallet`, "must be an inventory");
  validateVillage(r.village, known);
  const p = r.village.professions.find((q) => q.id === r.profession.id);
  need(p && p.level === r.profession.level && p.level_name === r.profession.level_name, `${at}.profession`, "disagrees with the village it came with");
  return r;
}

/** The villagers the child may promote right now (unlocked, below Master, and a promotion is available). */
export const promotable = (v) => v.professions.filter((p) => p.can_promote);

/** "Spend 6 more emeralds for a promotion" (the gap to the next promotion; never zero on a valid body). */
export const promotionHint = (pr) => `Spend ${pr.next_at - pr.spent} more emerald${pr.next_at - pr.spent === 1 ? "" : "s"} for a promotion`;

/** Validate a GET /api/village body (shape in docs/design.md). Returns it unchanged. */
export function validateVillage(v, known = SPRITE_NAMES) {
  const at = "/api/village";
  need(isObj(v), at, "must be an object");
  need(typeof v.enabled === "boolean", `${at}.enabled`, "must be a boolean");
  need(isObj(v.wallet) && isNat(v.wallet.emerald), `${at}.wallet`, "must be an inventory with an integer emerald");
  need(isNat(v.points), `${at}.points`, "must be an integer");
  need(isObj(v.level) && isNat(v.level.index) && typeof v.level.name === "string" && (v.level.next_at === null || isNat(v.level.next_at)), `${at}.level`, "must be {index,name,next_at}");
  need(isObj(v.levels) && Array.isArray(v.levels.names) && Array.isArray(v.levels.thresholds) && v.levels.names.length > 0 && v.levels.names.length === v.levels.thresholds.length, `${at}.levels`, "must be {names,thresholds}, the same non-zero length");
  badgesFor(v.levels.names, known);
  need(v.level.index < v.levels.names.length, `${at}.level.index`, "is beyond levels.names");
  need(isObj(v.bells) && isNat(v.bells.earned) && isNat(v.bells.spent) && Number.isInteger(v.bells.available), `${at}.bells`, "must be {earned,spent,available}");
  need(typeof v.first_free === "boolean", `${at}.first_free`, "must be a boolean");
  validatePromotions(v.promotions, `${at}.promotions`);
  validateEarn(v.earn, `${at}.earn`);
  need(Array.isArray(v.trades), `${at}.trades`, "must be an array");
  v.trades.forEach((t, i) => {
    need(isObj(t) && typeof t.id === "string" && isObj(t.give) && isObj(t.get), `${at}.trades[${i}]`, "must be {id,give,get}");
    for (const k of [...Object.keys(t.give), ...Object.keys(t.get)]) resolveSprite(k, known);
  });
  need(Array.isArray(v.professions) && v.professions.length > 0, `${at}.professions`, "must be a non-empty array");
  v.professions.forEach((p, i) => {
    const pa = `${at}.professions[${i}]`;
    need(isObj(p) && typeof p.id === "string" && typeof p.name === "string", pa, "needs id and name");
    need(typeof p.unlocked === "boolean" && typeof p.can_unlock === "boolean", pa, "needs boolean unlocked and can_unlock");
    need(isNat(p.unlock_emeralds), `${pa}.unlock_emeralds`, "must be an integer");
    need(isNat(p.level) && p.level < v.levels.names.length, `${pa}.level`, "must be an integer index into levels.names");
    need(p.level_name === v.levels.names[p.level], `${pa}.level_name`, "must be levels.names[level]");
    need(typeof p.can_promote === "boolean", `${pa}.can_promote`, "must be a boolean");
    need(p.unlocked || (p.level === 0 && !p.can_promote), pa, "a villager who is not unlocked is Novice and cannot be promoted");
    need(p.requires === null || p.requires === "all_professions", `${pa}.requires`, "must be null or all_professions");
    resolveSprite(p.job_block_sprite, known);
    resolveSprite(p.id === "wandering_trader" ? "wandering_trader" : PROFESSION_SPRITE_PREFIX + p.id, known);
    need(Array.isArray(p.offers), `${pa}.offers`, "must be an array");
    p.offers.forEach((o, j) => {
      const oa = `${pa}.offers[${j}]`;
      need(isObj(o) && typeof o.id === "string" && typeof o.label === "string" && isNat(o.price) && isNat(o.min_level) && typeof o.locked === "boolean" && Array.isArray(o.items), oa, "needs id, label, price, min_level, locked, items");
      need(o.min_level < v.levels.names.length, `${oa}.min_level`, "is beyond levels.names");
      resolveSprite(o.sprite, known);
    });
  });
  return v;
}

/** One treasure entry from GET /api/treasure. */
export function validateTreasureEntry(t, at = "treasure", known = SPRITE_NAMES) {
  need(isObj(t) && typeof t.tid === "string" && typeof t.label === "string" && Array.isArray(t.items), at, "needs tid, label, items");
  need(TREASURE_STATES.includes(t.state), `${at}.state`, `must be one of ${TREASURE_STATES.join("|")} (got ${JSON.stringify(t.state)})`);
  resolveSprite(t.sprite, known);
  return t;
}

/** A GET /api/treasure body. */
export function validateTreasure(r, known = SPRITE_NAMES) {
  need(isObj(r) && Array.isArray(r.treasure), "/api/treasure", "must be {treasure:[...]}");
  need(typeof r.enabled === "boolean" && typeof r.server_running === "boolean", "/api/treasure", "needs boolean enabled and server_running");
  need(r.problem === null || typeof r.problem === "string", "/api/treasure.problem", "must be a string or null");
  r.treasure.forEach((t, i) => validateTreasureEntry(t, `/api/treasure.treasure[${i}]`, known));
  return r;
}

/** The optional extras of a POST /api/event reply: {ok:true, treasure?:[{label,sprite}], game_level_ups?:[{game,level}]}. */
export function validateEventResult(r, known = SPRITE_NAMES) {
  need(isObj(r) && r.ok === true, "/api/event reply", "must be {ok:true,...}");
  if (r.treasure !== undefined) {
    need(Array.isArray(r.treasure), "/api/event reply.treasure", "must be an array");
    r.treasure.forEach((t, i) => {
      need(isObj(t) && typeof t.label === "string", `/api/event reply.treasure[${i}]`, "needs a label");
      resolveSprite(t.sprite, known);
    });
  }
  need(r.level_up === undefined, "/api/event reply.level_up", "the village level-up no longer exists (villagers are promoted instead)");
  if (r.game_level_ups !== undefined) {
    need(Array.isArray(r.game_level_ups) && r.game_level_ups.length > 0, "/api/event reply.game_level_ups", "must be a non-empty array");
    r.game_level_ups.forEach((g, i) => need(isObj(g) && ["craft", "blocks", "mine", "match"].includes(g.game) && Number.isInteger(g.level) && g.level >= 2, `/api/event reply.game_level_ups[${i}]`, "must be {game, level >= 2}"));
  }
  return r;
}

/** How many real items one treasure holds (sum of the item counts; an entry without count is 1). */
export const treasureCount = (t) => t.items.reduce((n, it) => n + (it.count ?? 1), 0);

/** The profession's sprite: its own villager, or the Wandering Trader. */
export const villagerSprite = (p) => (p.id === "wandering_trader" ? "wandering_trader" : PROFESSION_SPRITE_PREFIX + p.id);

/** "ok" (buyable), "poor" (not enough emeralds: dimmed) or "locked" (that villager's level too low: greyed + Reach X!). */
export function offerStatus(offer, wallet) {
  if (offer.locked) return "locked";
  return wallet.emerald >= offer.price ? "ok" : "poor";
}

/** What a sell-stall trade needs: true when every `give` resource is in the inventory. */
export const canTrade = (trade, inventory) => Object.entries(trade.give).every(([k, n]) => (inventory[k] ?? 0) >= n);

/** The unlock choices for one profession: {free} for the first villager, else which payments are possible. */
export function unlockChoices(v, p) {
  if (!p.can_unlock) return { free: false, bell: false, emeralds: false };
  if (v.first_free) return { free: true, bell: true, emeralds: true };
  return { free: false, bell: v.bells.available >= 1, emeralds: v.wallet.emerald >= p.unlock_emeralds };
}

/** Toggle a tid in a selection (returns a new Set). Only "kept" treasure may be selected. */
export function toggleSelection(selected, entry) {
  if (entry.state !== "kept") return selected;
  const next = new Set(selected);
  if (!next.delete(entry.tid)) next.add(entry.tid);
  return next;
}

/** Split the pile into what can still be sent (kept) and what is already on its way / in the chest / failed. */
export function pileSections(treasure) {
  return { kept: treasure.filter((t) => t.state === "kept"), sent: treasure.filter((t) => t.state !== "kept").reverse() };
}

/** A string that changes whenever any entry's state changes (the pile only re-renders then). */
export const pileSignature = (treasure) => treasure.map((t) => `${t.tid}:${t.state}`).join(",");
