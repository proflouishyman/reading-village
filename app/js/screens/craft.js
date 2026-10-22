// Crafting Table: the child taps letter blocks into a 3-slot grid to spell the picture's word, then presses Craft!.
// Dad says the word; there is no judging and no miss: a wrong block just wiggles (silently) and stays in the tray.
import { stageLayout, interlude } from "../layout.js";
import { SPRITE_NAMES, spriteElement } from "../sprites.js";
import { h, setKid, popReward } from "../ui.js";
import { playJingle } from "../sounds.js";
import { commitUntilSaved, earnRates } from "../store.js";
import { CRAFT_WORDS_PER_ROUND, CRAFT_DISTRACTORS } from "../constants.js";
import { PATTERNS, pickAtLevel, trackerFor } from "../levels.js";
import { resolveSprite } from "../villagelogic.js";
import { childName } from "../family.js";

const FILE = "data/craft_words.json";
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

/**
 * Validate craft_words.json ({v:2, words:[{word, level, pattern, sprite}]}). `word`: 3 to 10 capital letters, unique;
 * `pattern` one of the phonics ladder (levels.js PATTERNS) and `level` the matching rung 1-6; `sprite` must be drawn (a name in
 * sprites.js or one with a stand-in, villagelogic.js resolveSprite). At least one level-1 word must exist. Throws naming the file and entry; there is no default and no
 * skipping. `known` is injectable for tests.
 */
export function validateCraftWords(obj, file = FILE, known = SPRITE_NAMES) {
  if (!obj || obj.v !== 2 || !Array.isArray(obj.words)) throw new Error(`${file}: must be {"v":2,"words":[...]}`);
  const seen = new Set();
  obj.words.forEach((w, i) => {
    const at = `${file}: words[${i}]`;
    if (!w || typeof w !== "object") throw new Error(`${at} must be an object`);
    for (const k of Object.keys(w)) if (!["word", "level", "pattern", "sprite"].includes(k)) throw new Error(`${at}: unknown field "${k}"`);
    if (typeof w.word !== "string" || !/^[A-Z]{3,10}$/.test(w.word)) throw new Error(`${at}: "word" must be 3 to 10 capital letters (got ${JSON.stringify(w.word)})`);
    if (seen.has(w.word)) throw new Error(`${at}: duplicate word "${w.word}"`);
    seen.add(w.word);
    if (!PATTERNS.includes(w.pattern)) throw new Error(`${at}: "${w.word}" pattern ${JSON.stringify(w.pattern)} must be one of ${PATTERNS.join(", ")}`);
    if (w.level !== PATTERNS.indexOf(w.pattern) + 1) throw new Error(`${at}: "${w.word}" level ${JSON.stringify(w.level)} does not match pattern ${w.pattern} (level ${PATTERNS.indexOf(w.pattern) + 1})`);
    try { resolveSprite(w.sprite, known); } catch { throw new Error(`${at}: "${w.word}" uses unknown sprite ${JSON.stringify(w.sprite)} (not in sprites.js, no stand-in)`); }
  });
  if (!obj.words.some((w) => w.level === 1)) throw new Error(`${file}: needs at least one level 1 word`);
  return obj.words;
}

/** Seeded LCG (same constants as the textures in ui.js): returns a function giving ints in [0, n). */
function lcg(seed) {
  let s = seed >>> 0;
  return (n) => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return Math.floor((s / 4294967296) * n);
  };
}

/**
 * The letter-block tray for a word: its letters plus `distractors` letters not in the word, shuffled. The tray is small
 * caps, whose shapes do not mirror, so a distractor may be any letter (the confusable-letter gate is lowercase-only).
 * Deterministic: depends only on (word, index), never on Math.random. `index` is the word's position in
 * craft_words.json. Returns [{id, letter}] (id = position in the tray). The first slots are never already in order.
 */
export function trayFor(word, index, distractors = CRAFT_DISTRACTORS) {
  if (!/^[A-Z]{3,10}$/.test(word) || !Number.isInteger(index) || index < 0) throw new Error(`trayFor: bad word/index ${word}/${index}`);
  for (let attempt = 0; attempt < 50; attempt++) {
    const rnd = lcg((index + 1) * 7919 + attempt);
    const spare = [...ALPHABET].filter((c) => !word.includes(c));
    const extra = [];
    while (extra.length < distractors) extra.push(...spare.splice(rnd(spare.length), 1));
    const letters = [...word, ...extra];
    for (let i = letters.length - 1; i > 0; i--) {
      const j = rnd(i + 1);
      [letters[i], letters[j]] = [letters[j], letters[i]];
    }
    if (letters.slice(0, word.length).join("") !== word) return letters.map((letter, id) => ({ id, letter }));
  }
  throw new Error(`trayFor: could not shuffle "${word}" out of order`);
}

/** progress.crafted (word -> count); a progress file without it reads as {} (documented default). */
export const craftedOf = (progress) => progress.crafted ?? {};

/**
 * The words for a round at `level`: every word at the level is usable (small caps does not mirror, so no confusable-letter
 * gate here), picked by levels.js pickAtLevel: 4 at the level and 1 review word from the level below (least-crafted first,
 * ties in file order; at level 1 all 5 are level 1). Deterministic. Returns {round: [{word, sprite, level, pattern, index,
 * count}], short}; `short` says the level had too few words and the round was topped up with easier ones. Throws if the
 * list has no word at or below the level.
 */
export function pickRound(words, crafted, level, n = CRAFT_WORDS_PER_ROUND) {
  const items = words.map((w, index) => ({ ...w, index, count: crafted[w.word] ?? 0 }));
  const { picked, short } = pickAtLevel(items, level, n);
  return { round: picked, short };
}

async function loadCraftWords() {
  let res;
  try { res = await fetch(FILE, { cache: "no-store" }); } catch (e) { throw new Error(`${FILE}: could not fetch (${e.message})`); }
  if (!res.ok) throw new Error(`${FILE}: HTTP ${res.status}`);
  let obj;
  try { obj = await res.json(); } catch (e) { throw new Error(`${FILE}: not valid JSON (${e.message})`); }
  return validateCraftWords(obj);
}

/** Collection chest: every craftable item with its count; never-crafted ones show a dark "?" so nothing is lost. */
function chestView(words, crafted) {
  const total = words.filter((w) => crafted[w.word]).length;
  return h("div", { class: "chest-view" },
    h("div", { class: "chest-title", kid: `Collection chest  ${total} / ${words.length}` }),
    h("div", { class: "chest-grid" }, words.map((w) => {
      const n = crafted[w.word] ?? 0;
      return h("div", { class: `chest-item${n ? "" : " empty"}` },
        n ? spriteElement(resolveSprite(w.sprite), 6) : h("div", { class: "chest-q", kid: "?" }),
        h("div", { class: "chest-name", kid: n ? `${w.word}  x${n}` : "" }));
    })));
}

const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];

/** Interlude title for a round of n crafts ("You crafted five things!"); throws for an n it has no word for. */
export function roundTitle(n) {
  if (!Number.isInteger(n) || n < 1 || n >= NUMBER_WORDS.length) throw new Error(`roundTitle: no number word for ${n}`);
  return `You crafted ${NUMBER_WORDS[n]} ${n === 1 ? "thing" : "things"}!`;
}

/** Run one round of CRAFT_WORDS_PER_ROUND words. Returns "done" or "quit". */
export async function run(app) {
  const words = await loadCraftWords();
  const tracker = await trackerFor(app, "craft");
  const L = stageLayout(app.root, { title: "Crafting Table", dadHint: `Say the word. ${childName()} taps the letters in order, then Craft!` });
  L.disableButtons(); // Dad does not judge here
  const roundLevel = tracker.level; // fixed for the whole round: a mid-round level-up must not retag the rest of it
  const { round, short } = pickRound(words, craftedOf(app.store.progress), roundLevel);
  if (short) L.setHint(`Level ${roundLevel}: there are few words at this level yet, so some are easier ones. Say the word; ${childName()} taps the letters in order, then Craft!`);
  L.setLevel(...tracker.lines());
  const stage = h("div", { class: "craft" });
  const chest = h("div", { class: "chest-wrap", hidden: "" });
  const chestBtn = h("button", { class: "btn small chest-btn", kid: "Collection chest" });
  L.play.replaceChildren(stage, chest, chestBtn);
  let chestOpen = false;
  chestBtn.addEventListener("click", () => {
    chestOpen = !chestOpen;
    if (chestOpen) chest.replaceChildren(chestView(words, craftedOf(app.store.progress)));
    chest.hidden = !chestOpen;
    stage.hidden = chestOpen;
    setKid(chestBtn, chestOpen ? "Back to crafting" : "Collection chest");
  });

  for (let done = 0; done < round.length; done++) {
    L.setProgress(done, round.length);
    const r = await craftOne(L, app, stage, round[done], tracker);
    if (r === "quit") return "quit";
  }
  L.setProgress(round.length, round.length);
  await interlude(app.root, { title: roundTitle(round.length), body: "Look in the collection chest!", buttonText: "Yay!", sprite: "chest" });
  return "done";
}

/** One word: returns "ok" once crafted, or "quit". */
async function craftOne(L, app, stage, entry, tracker) {
  const { word, sprite } = entry;
  const tiles = trayFor(word, entry.index);
  let filled = 0;
  let wrong = false;

  const slots = [...word].map(() => h("div", { class: "craft-slot" }));
  const tileEls = tiles.map((t) => {
    const el = h("button", { class: "btn craft-tile", "data-letter": t.letter, onclick: () => tap(t, el) });
    setKid(el, t.letter);
    return el;
  });
  const craftBtn = h("button", { class: "btn big craft-btn", kid: "Craft!", disabled: "" });
  const target = h("div", { class: "card craft-target" }, spriteElement(resolveSprite(sprite), 12));
  stage.replaceChildren(target, h("div", { class: "craft-grid", style: `--n:${word.length}` }, slots), h("div", { class: "craft-tray" }, tileEls), craftBtn);

  function tap(tile, el) {
    if (filled >= word.length || el.disabled) return;
    if (tile.letter !== word[filled]) {
      // Wrong block: wiggle in place (it never leaves the tray). No sound, no colour: it only marks the attempt as assisted.
      wrong = true;
      el.classList.remove("wiggle");
      void el.offsetWidth; // restart the animation on repeated taps
      el.classList.add("wiggle");
      return;
    }
    setKid(slots[filled], tile.letter);
    slots[filled].classList.add("full");
    el.disabled = true;
    filled += 1;
    if (filled === word.length) {
      craftBtn.disabled = false;
      craftBtn.classList.add("ready");
    }
  }

  const crafted = new Promise((resolve) => {
    craftBtn.addEventListener("click", async () => {
      if (craftBtn.disabled) return;
      craftBtn.disabled = true; // one press only: a double-click must not log or count twice
      craftBtn.classList.remove("ready");
      const result = wrong ? "assisted" : "correct";
      const emeralds = earnRates().craft_emerald;
      const level = entry.level; // the word's OWN level: a mixed-in easier word never counts toward the current level
      await commitUntilSaved({ type: "craft", item: word, result, track: "smallcaps", level }, (p) => {
        p.crafted = { ...(p.crafted ?? {}) };
        p.crafted[word] = (p.crafted[word] ?? 0) + 1;
        p.inventory.emerald += emeralds; // in the same save as the craft count
      });
      playJingle();
      tracker.record(result, level);
      L.setLevel(...tracker.lines());
      popReward(target, resolveSprite(sprite));
      await new Promise((r) => setTimeout(r, 1400));
      resolve("ok");
    });
  });
  return Promise.race([crafted, L.quitted]);
}
