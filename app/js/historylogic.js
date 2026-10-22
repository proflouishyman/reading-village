// Pure logic for the Treasure Book and Dad's "Rewards history" (no DOM, so node can test it).
// GET /api/history[?kind=K] returns {v:1, kind:null|string, count, lines:[...], totals:{...}}: the lines of the
// append-only data/rewards_history.jsonl, oldest first (`lines` filtered by kind, `totals` always over the whole file).
// The reply and every line are validated at the boundary; a mismatch throws naming the field, nothing is coerced.
//
// Line contract (docs/design.md "Rewards history"; the server writes it in minecraft_bridge.History):
//   {v:1, ts:ISO string, kind, what:{...}, wallet_after:{inventory}|null, ref:string}
//   kind -> `what` fields this client reads (extra fields are allowed and only appear in the CSV):
//     earn      {resources:{res:n>0}, last_event:object|null}
//     spend     {resource:string, amount:n>0, on:string}
//     trade     {trade_id, give:{res:n}, get:{res:n}}
//     treasure  {tid, label, items:[{item,count?}], source:{kind,ref}}          (no sprite: see pictureFor)
//     unlock    {profession:id, name, paid:"free"|"bell"|"emeralds"}
//     level     {index:int, name, points:int}                                    (old shared village levels; no new ones)
//     promote   {profession:id, name, from_level:int, level:int (= from_level+1), level_name, spent:int}
//     send      {tids:[string], items:[{item,count?}]}
//     delivered {delivery, tid, label, items:[{item,count?}], chest:{x,y,z}, log:[string]}
//     delivery_failed {delivery, tid, error}
//   totals: {earned:{res:n}, spent:{res:n}, sent:{item:n}, delivered:{item:n}, unlocked:[profession ids], levels:[indexes]}
import { SPRITE_NAMES, itemSprite } from "./sprites.js";
import { resolveSprite, badgesFor } from "./villagelogic.js";

export const KINDS = ["earn", "spend", "trade", "treasure", "unlock", "level", "promote", "send", "delivered", "delivery_failed"];
/** The kinds the child sees in his Treasure Book: what he earned and what he sent (bookkeeping kinds are Dad's). */
export const BOOK_KINDS = ["earn", "treasure", "unlock", "level", "promote", "send", "delivered"];
export const PAID = ["free", "bell", "emeralds"];
export const PLACEHOLDER_SPRITE = "chest";
const LINE_KEYS = ["v", "ts", "kind", "what", "wallet_after", "ref"];
const TOTAL_KEYS = ["earned", "spent", "sent", "delivered", "unlocked", "levels"];

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const isNat = (x) => Number.isInteger(x) && x >= 0;
function need(cond, at, what) {
  if (!cond) throw new Error(`${at}: ${what}`);
}
const countMap = (m, at) => {
  need(isObj(m) && Object.keys(m).length > 0, at, "must be a non-empty {name: positive integer}");
  for (const [k, n] of Object.entries(m)) need(Number.isInteger(n) && n > 0, `${at}.${k}`, `must be a positive integer (got ${JSON.stringify(n)})`);
};
const str = (x) => typeof x === "string" && x !== "";
const items = (x, at) => {
  need(Array.isArray(x) && x.length > 0, at, "must be a non-empty array of {item,count?}");
  x.forEach((it, i) => need(isObj(it) && str(it.item) && (it.count === undefined || (Number.isInteger(it.count) && it.count > 0)), `${at}[${i}]`, "needs item (and a positive integer count if present)"));
};

/** Validate one history line. Returns it unchanged; throws naming `at` and the field. */
export function validateHistoryLine(l, at = "history line") {
  need(isObj(l), at, "must be an object");
  for (const k of LINE_KEYS) need(k in l, at, `missing "${k}"`);
  for (const k of Object.keys(l)) need(LINE_KEYS.includes(k), at, `unknown field "${k}"`);
  need(l.v === 1, `${at}.v`, `must be 1 (got ${JSON.stringify(l.v)})`);
  need(str(l.ts) && !Number.isNaN(Date.parse(l.ts)), `${at}.ts`, "must be an ISO timestamp");
  need(KINDS.includes(l.kind), `${at}.kind`, `must be one of ${KINDS.join("|")} (got ${JSON.stringify(l.kind)})`);
  need(isObj(l.what), `${at}.what`, "must be an object");
  need(l.wallet_after === null || (isObj(l.wallet_after) && Object.values(l.wallet_after).every(isNat)), `${at}.wallet_after`, "must be null or an inventory of non-negative integers");
  need(typeof l.ref === "string", `${at}.ref`, "must be a string");
  const w = l.what, wa = `${at}.what`;
  switch (l.kind) {
    case "earn": countMap(w.resources, `${wa}.resources`); need(w.last_event === null || isObj(w.last_event), `${wa}.last_event`, "must be an object or null"); break;
    case "spend": need(str(w.resource) && Number.isInteger(w.amount) && w.amount > 0 && str(w.on), wa, "needs resource, a positive integer amount and on"); break;
    case "trade": need(str(w.trade_id), `${wa}.trade_id`, "must be a string"); countMap(w.give, `${wa}.give`); countMap(w.get, `${wa}.get`); break;
    case "treasure":
      need(str(w.tid) && str(w.label) && isObj(w.source) && str(w.source.kind) && str(w.source.ref), wa, "needs tid, label and source {kind,ref}");
      items(w.items, `${wa}.items`);
      break;
    case "unlock": need(str(w.profession) && str(w.name) && PAID.includes(w.paid), wa, `needs profession, name and paid (${PAID.join("|")})`); break;
    case "level": need(isNat(w.index) && str(w.name) && isNat(w.points), wa, "needs index, name and points"); break;
    case "promote": need(str(w.profession) && str(w.name) && isNat(w.from_level) && isNat(w.level) && w.level === w.from_level + 1 && str(w.level_name) && isNat(w.spent), wa, "needs profession, name, from_level, level (= from_level + 1), level_name and spent"); break;
    case "send":
      need(Array.isArray(w.tids) && w.tids.length > 0 && w.tids.every(str), `${wa}.tids`, "must be a non-empty array of tids");
      items(w.items, `${wa}.items`);
      break;
    case "delivered":
      need(str(w.delivery) && str(w.tid) && str(w.label) && isObj(w.chest) && ["x", "y", "z"].every((k) => Number.isInteger(w.chest[k])) && Array.isArray(w.log) && w.log.every((x) => typeof x === "string"), wa, "needs delivery, tid, label, chest {x,y,z} and log [string]");
      items(w.items, `${wa}.items`);
      break;
    case "delivery_failed": need(str(w.delivery) && str(w.tid) && str(w.error), wa, "needs delivery, tid and error"); break;
    default: throw new Error(`${at}: unreachable kind`);
  }
  return l;
}

/** Validate a GET /api/history body. Returns it unchanged. */
export function validateHistory(body) {
  const at = "/api/history";
  need(isObj(body), at, "must be an object {v,kind,count,lines,totals}");
  need(body.v === 1, `${at}.v`, `must be 1 (got ${JSON.stringify(body.v)})`);
  need(body.kind === null || KINDS.includes(body.kind), `${at}.kind`, "must be null or a known kind");
  need(Array.isArray(body.lines) && body.count === body.lines.length, `${at}.count`, "must equal the number of lines");
  body.lines.forEach((l, i) => {
    validateHistoryLine(l, `${at}.lines[${i}]`);
    need(body.kind === null || l.kind === body.kind, `${at}.lines[${i}].kind`, `is ${l.kind} but the request asked for ${body.kind}`);
  });
  const t = body.totals;
  need(isObj(t), `${at}.totals`, "must be an object");
  for (const k of TOTAL_KEYS) need(k in t, `${at}.totals`, `missing "${k}"`);
  for (const k of Object.keys(t)) need(TOTAL_KEYS.includes(k), `${at}.totals`, `unknown field "${k}"`);
  for (const k of ["earned", "spent", "sent", "delivered"]) need(isObj(t[k]) && Object.values(t[k]).every((n) => Number.isInteger(n) && n > 0), `${at}.totals.${k}`, "must be {name: positive integer}");
  need(Array.isArray(t.unlocked) && t.unlocked.every(str), `${at}.totals.unlocked`, "must be an array of profession ids");
  need(Array.isArray(t.levels) && t.levels.every(isNat), `${at}.totals.levels`, "must be an array of level indexes");
  return body;
}

/** Newest first (a new array). */
export const newestFirst = (lines) => [...lines].reverse();

/** Dad's summary: the server's totals plus the villager and level NAMES (taken from the unlock / level lines). */
export function summary(body) {
  const names = { villagers: [], levels: [] };
  let failed = 0;
  for (const l of body.lines) {
    if (l.kind === "unlock") names.villagers.push(l.what.name);
    else if (l.kind === "level") names.levels.push(l.what.name);
    else if (l.kind === "delivery_failed") failed += 1;
  }
  return { ...body.totals, ...names, failed };
}

const list = (m) => Object.entries(m).map(([k, n]) => `${n} ${k}`).join(", ");
const itemList = (its) => its.map((it) => `${it.count ?? 1} ${it.item.replace(/^minecraft:/, "")}`).join(", ");

/** One plain-English line for Dad's chronological list. */
export function describeLine(l) {
  const w = l.what;
  switch (l.kind) {
    case "earn": return `Earned ${list(w.resources)}${w.last_event ? ` (from ${w.last_event.type ?? "an event"}${w.last_event.item ? ` ${w.last_event.item}` : ""})` : ""}`;
    case "spend": return `Spent ${w.amount} ${w.resource} on ${w.on}`;
    case "trade": return `Traded ${list(w.give)} for ${list(w.get)}`;
    case "treasure": return `Treasure: ${w.label} (${w.source.kind}: ${w.source.ref})`;
    case "unlock": return `Unlocked ${w.name} (${w.paid})`;
    case "level": return `Reached level ${w.name} (${w.points} points)`;
    case "promote": return `Promoted ${w.name} to ${w.level_name} (${w.spent} emeralds spent so far)`;
    case "send": return `Sent to Minecraft: ${w.tids.join(", ")} = ${itemList(w.items)}`;
    case "delivered": return `Delivered: ${w.label} (${w.delivery}, chest ${w.chest.x} ${w.chest.y} ${w.chest.z})`;
    case "delivery_failed": return `DELIVERY FAILED: ${w.delivery} (${w.tid}) - ${w.error}`;
    default: throw new Error(`describeLine: unknown kind ${l.kind}`);
  }
}

/**
 * The picture for a treasure id. Treasure lines carry no sprite, so: (1) the pile entry with that tid (GET
 * /api/treasure, `pile` = Map tid -> {sprite,label}); (2) else a sprite named like the first item (minecraft:diamond ->
 * "diamond", through resolveSprite); (3) else the chest placeholder. The result says which, so the placeholders can
 * be counted and shown to Dad (a reset archives the pile, so old tids are legitimately missing from it).
 */
export function pictureFor(tid, itemsList, pile, known = SPRITE_NAMES) {
  const p = pile.get(tid);
  if (p) return { name: resolveSprite(p.sprite, known), source: "pile" };
  for (const it of itemsList ?? []) {
    try { return { name: resolveSprite(it.item.replace(/^minecraft:/, ""), known), source: "item" }; } catch { /* try the next item, then the placeholder */ }
  }
  return { name: PLACEHOLDER_SPRITE, source: "placeholder" };
}

/**
 * What the child sees for one line: {sprites:[{name,n?}], text, placeholders} or null for Dad's bookkeeping kinds.
 * `pile` is the Map tid -> {sprite,label} from GET /api/treasure. Picture names go through resolveSprite.
 */
export function bookRow(l, pile = new Map(), known = SPRITE_NAMES) {
  const w = l.what;
  const sp = (name, n) => ({ name: resolveSprite(name, known), ...(n > 1 ? { n } : {}) });
  const pics = (tid, its) => pictureFor(tid, its, pile, known);
  switch (l.kind) {
    case "earn": return { sprites: Object.entries(w.resources).map(([k, n]) => sp(itemSprite(k), n)), text: "You found treasure!", placeholders: 0 };
    case "treasure": { const p = pics(w.tid, w.items); return { sprites: [{ name: p.name }], text: `${w.label} came to your Treasure Pile`, placeholders: p.source === "placeholder" ? 1 : 0 }; }
    case "unlock": return { sprites: [sp(w.profession === "wandering_trader" ? "wandering_trader" : `villager_${w.profession}`)], text: `The ${w.name} moved in!`, placeholders: 0 };
    case "level": return { sprites: [sp(badgesFor([w.name], known)[0])], text: `Your village is now ${w.name}!`, placeholders: 0 };
    case "promote": return { sprites: [sp(w.profession === "wandering_trader" ? "wandering_trader" : `villager_${w.profession}`), sp(badgesFor([w.level_name], known)[0])], text: `The ${w.name} is now ${w.level_name}!`, placeholders: 0 };
    case "send": {
      const ps = w.tids.map((t) => pics(t, null));
      return { sprites: ps.map((p) => ({ name: p.name })), text: `You sent ${w.tids.length} ${w.tids.length === 1 ? "treasure" : "treasures"}!`, placeholders: ps.filter((p) => p.source === "placeholder").length };
    }
    case "delivered": { const p = pics(w.tid, w.items); return { sprites: [{ name: p.name }, { name: "chest" }], text: `${w.label} is in your Magic Chest!`, placeholders: p.source === "placeholder" ? 1 : 0 }; }
    default: return null;
  }
}

/** Human date for the Treasure Book ("Oct 18"); the caller passes it through the small-caps helper. */
export const bookDate = (ts) => new Date(ts).toLocaleDateString("en-US", { month: "short", day: "numeric" });
