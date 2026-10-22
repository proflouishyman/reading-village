// Minigame levels (docs/design.md "Levels"). Pure logic plus one fetch: no DOM, so node can test it.
//
// Levels are DERIVED from events, never stored: per game (craft, blocks, mine, match) the level is 1 + the number of
// consecutive level-ups earned. A level-up happens when at least `window` attempts were made AT the current level and at
// least `need` of the last `window` are independent "correct" (assisted and miss do not count). Never demotes; the count
// restarts at each new level. server.py derive_levels is the same rule (the server uses it for the level-up surprise);
// keep the two in sync. Dad can override a game's level (progress.settings.level_override.<game>); the override wins for
// what is shown and drilled, while the derived level keeps counting on its own.
import { getEvents } from "./api.js";
import { PARTNER } from "./rules.js";
import { shuffle } from "./util.js";
import { grownUp } from "./family.js";

export const GAMES = ["craft", "blocks", "mine", "match"];
/** Event type -> the game whose level it counts toward. */
export const EVENT_GAME = { craft: "craft", word: "blocks", card: "mine", match: "match" };
/** Phonics ladder: pattern id for level n is PATTERNS[n - 1] (craft and blocks). */
export const PATTERNS = ["cvc", "blend", "digraph", "silent_e", "vowel_team", "two_syllable"];
export const PATTERN_NAMES = {
  cvc: "short vowel words", blend: "blends", digraph: "digraphs", silent_e: "silent e", vowel_team: "vowel teams", two_syllable: "two syllables",
};
/** Letter Mine and Bridge Match levels (design in docs/design.md "Levels"). */
export const MINE_LEVEL_NAMES = ["one letter at a time", "letters mixed", "mirror pairs", "everything mixed"];
export const MATCH_LEVEL_NAMES = ["two choices, one letter at a time", "two choices, mixed", "three choices", "four choices"];
/** Name shown to the child in the level-up celebration ("Crafting level 3!"). */
export const GAME_TITLES = { craft: "Crafting", blocks: "Word Blocks", mine: "Letter Mine", match: "Bridge Match" };

const isInt = (x) => Number.isInteger(x);

/** Validate levels.json ({v:1, games:{craft,blocks,mine,match:{max,window,need}}}); throws naming file and field. */
export function validateLevels(obj, file = "data/levels.json") {
  if (!obj || typeof obj !== "object" || obj.v !== 1 || !obj.games || typeof obj.games !== "object") throw new Error(`${file}: must be {"v":1,"games":{...}}`);
  for (const k of Object.keys(obj)) if (k !== "v" && k !== "games") throw new Error(`${file}: unknown field "${k}"`);
  for (const g of Object.keys(obj.games)) if (!GAMES.includes(g)) throw new Error(`${file}: unknown game "${g}"`);
  for (const g of GAMES) {
    const c = obj.games[g];
    if (!c || typeof c !== "object") throw new Error(`${file}: games.${g} is missing`);
    for (const k of Object.keys(c)) if (!["max", "window", "need"].includes(k)) throw new Error(`${file}: games.${g}: unknown field "${k}"`);
    for (const k of ["max", "window", "need"]) if (!isInt(c[k]) || c[k] < 1) throw new Error(`${file}: games.${g}.${k} must be an integer >= 1`);
    if (c.need > c.window) throw new Error(`${file}: games.${g}: need (${c.need}) must not exceed window (${c.window})`);
    if (c.max > levelNames(g).length) throw new Error(`${file}: games.${g}.max ${c.max} is higher than the ${levelNames(g).length} levels this game defines`);
  }
  return obj;
}

/** The level names (what each level is) for a game, index = level - 1. */
export function levelNames(game) {
  if (game === "craft" || game === "blocks") return PATTERNS.map((p) => PATTERN_NAMES[p]);
  if (game === "mine") return MINE_LEVEL_NAMES;
  if (game === "match") return MATCH_LEVEL_NAMES;
  throw new Error(`levelNames: unknown game "${game}"`);
}

export async function loadLevels() {
  const file = "data/levels.json";
  let res;
  try { res = await fetch(file, { cache: "no-store" }); } catch (e) { throw new Error(`${file}: could not fetch (${e.message})`); }
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`);
  let obj;
  try { obj = await res.json(); } catch (e) { throw new Error(`${file}: not valid JSON (${e.message})`); }
  return validateLevels(obj, file);
}

/** Fresh derivation state for one game. */
export const startState = () => ({ level: 1, results: [], attempts: 0 });

/**
 * Apply one attempt to a game's state (mutates and returns it). `ev` = {level?, result}. An event whose level is not
 * the current derived level is ignored (an earlier level is already passed; a higher one came from Dad's override).
 * Returns true when this attempt earned a level-up.
 */
export function step(state, ev, cfg) {
  if ((ev.level ?? 1) !== state.level) return false;
  state.results = [...state.results, ev.result].slice(-cfg.window);
  state.attempts += 1;
  if (state.level < cfg.max && state.attempts >= cfg.window && state.results.filter((r) => r === "correct").length >= cfg.need) {
    state.level += 1;
    state.results = [];
    state.attempts = 0;
    return true;
  }
  return false;
}

/**
 * Derived state for every game from the events on file: {game: {level, max, window, need, attempts, independent}}
 * (`independent` = correct answers among the last `window` attempts at that level).
 */
export function deriveLevels(events, cfg) {
  const out = {};
  for (const g of GAMES) {
    const s = startState();
    for (const e of events) if (EVENT_GAME[e.type] === g) step(s, e, cfg.games[g]);
    out[g] = { level: s.level, ...cfg.games[g], attempts: s.attempts, independent: s.results.filter((r) => r === "correct").length };
  }
  return out;
}

/**
 * The level in force for a game: Dad's override when set, else the derived level. `override` is
 * progress.settings.level_override (undefined = none); a value outside 1..max is a loud error.
 */
export function effectiveLevel(game, derived, override) {
  const o = override?.[game];
  if (o === undefined) return derived[game].level;
  if (!isInt(o) || o < 1 || o > derived[game].max) throw new Error(`settings.level_override.${game} must be an integer 1..${derived[game].max} (got ${JSON.stringify(o)})`);
  return o;
}

/** "Level 2: blends" (what the child and Dad see for a level). */
export const levelTitle = (game, level) => `Level ${level}: ${levelNames(game)[level - 1]}`;

/**
 * A tracker for one game on one screen: starts from the events on file, answers "which level do I drill" and
 * "how far to the next", and absorbs each new attempt locally (the server derives the same thing from the same events).
 */
export function makeTracker(game, events, cfg, override) {
  const g = cfg.games[game];
  const state = startState();
  for (const e of events) if (EVENT_GAME[e.type] === game) step(state, e, g);
  const overridden = override?.[game];
  if (overridden !== undefined && (!isInt(overridden) || overridden < 1 || overridden > g.max)) {
    throw new Error(`settings.level_override.${game} must be an integer 1..${g.max} (got ${JSON.stringify(overridden)})`);
  }
  return {
    game, max: g.max, window: g.window, need: g.need,
    /** The level in force (Dad's override, else derived): drill this one and put it on every event. */
    get level() { return overridden ?? state.level; },
    get derived() { return state.level; },
    get overridden() { return overridden !== undefined; },
    /** Independent-correct answers among the last `window` attempts at the derived level. */
    get independent() { return state.results.filter((r) => r === "correct").length; },
    /**
     * Absorb one attempt tagged with `level` (what the event carries: the round's level, or a word's own level), so the
     * local count matches derive_levels exactly; an attempt at another level than the derived one is ignored.
     * Returns true if it earned a derived level-up.
     */
    record(result, level) {
      if (!isInt(level)) throw new Error(`tracker.record: level must be an integer (got ${JSON.stringify(level)})`);
      return step(state, { level, result }, g);
    },
    /** [title, progress] lines for the screen, e.g. ["Level 2: blends", "7 of 8 right at level 2"]. */
    lines() {
      const title = levelTitle(game, this.level);
      if (this.overridden) return [title, `level chosen by ${grownUp()}`];
      if (state.level >= g.max) return [title, "top level"];
      return [title, `${this.independent} of ${g.need} right at level ${state.level}`];
    },
  };
}

/** Build a tracker from the events on file (fetched unless the caller already has them); screens call this once at the start. */
export async function trackerFor(app, game, events = null) {
  if (!app.levels) throw new Error("levels.json was not loaded at boot");
  return makeTracker(game, events ?? await getEvents(), app.levels, app.store.progress.settings.level_override);
}

const REVIEW_FRACTION = 0.2;
/** How many of an `n`-item round are review words from below the current level: 0 at level 1, else 20% (at least 1). */
export const reviewCount = (level, n) => (level <= 1 || n < 2 ? 0 : Math.min(n - 1, Math.max(1, Math.round(n * REVIEW_FRACTION))));

/**
 * Pick up to `n` items for a level. `items` = [{level, count (times practised), index (file order), ...}].
 * Level 1: the n least-practised level-1 items. Level L > 1: 80% at level L and 20% review (`reviewCount`: 1 of 5, 2 of 10),
 * each group least-practised first. The review words come from level L-1; only if L-1 has too few do they come from the
 * next level down, and so on. The round opens with one review word and, when there are several, ends with one, so it
 * starts on something he has already learned. Ties: file order (or `rng` order if given).
 * If level L has too few items the round tops up with more review words (any level below) and `short` is true so the
 * screen can tell Dad; if the levels below cannot fill their share the rest comes from level L; if there is nothing at
 * all, it throws. Returns {picked, short}.
 */
export function pickAtLevel(items, level, n, { rng = null } = {}) {
  const order = rng ? shuffle(items, rng) : items;
  const sorted = (arr) => arr.slice().sort((a, b) => a.count - b.count || (rng ? 0 : a.index - b.index));
  const cur = sorted(order.filter((x) => x.level === level));
  // Below-level words, nearest level first (L-1, then L-2 ...), least-practised first within each level.
  const lowLevels = [...new Set(order.filter((x) => x.level < level).map((x) => x.level))].sort((a, b) => b - a);
  const low = lowLevels.flatMap((lv) => sorted(order.filter((x) => x.level === lv)));
  if (cur.length + low.length === 0) throw new Error(`no items at level ${level} or below (check the word lists)`);
  const wantLow = reviewCount(level, n);
  let lowPick = low.slice(0, wantLow);
  let curPick = cur.slice(0, n - wantLow);
  let short = false;
  if (curPick.length < n - wantLow) { // not enough at this level: top up with more review words
    short = true;
    lowPick = low.slice(0, Math.min(low.length, n - curPick.length));
  } else if (lowPick.length < wantLow) { // not enough review words: top up with more of this level
    curPick = cur.slice(0, Math.min(cur.length, n - lowPick.length));
  }
  return { picked: [...lowPick.slice(0, 1), ...curPick, ...lowPick.slice(1)], short };
}

// --- Letter Mine / Bridge Match level designs ---------------------------------------------------------------------
// Mine levels: 1 runs of the same letter (three in a row), 2 letters mixed (the review-weighted mix), 3 mirror pairs
// alternate (b d b d), 4 every drilled letter shuffled, never the same twice in a row.
// Match levels: the same deck for levels 1-2 and 4, plus the number of CHOICES grows: 2, 2, 3, 4 (the mirror partner is
// always among them). No timers, no losing: a wrong choice still just wiggles and shows the cue.

/** n cards in runs of `run` of the same letter, letters in shuffled order. */
export function runsDeck(letters, n, run = 3, rng = Math.random) {
  const order = shuffle(letters, rng);
  const deck = [];
  for (let i = 0; deck.length < n; i++) for (let k = 0; k < run && deck.length < n; k++) deck.push(order[i % order.length]);
  return deck;
}

/** n cards alternating a letter and its mirror partner (b d b d), one pair after another; needs both in `letters`. */
export function pairsDeck(letters, n, rng = Math.random) {
  const seen = new Set();
  const pairs = [];
  for (const l of letters) {
    if (!letters.includes(PARTNER[l]) || seen.has(l)) continue;
    seen.add(l); seen.add(PARTNER[l]);
    pairs.push([l, PARTNER[l]]);
  }
  if (pairs.length === 0) throw new Error(`pairsDeck: no letter has its mirror partner in ${JSON.stringify(letters)}`);
  const deck = [];
  const order = shuffle(pairs, rng);
  for (let i = 0; deck.length < n; i++) for (let k = 0; k < 4 && deck.length < n; k++) deck.push(order[i % order.length][k % 2]);
  return deck;
}

/** n cards, every letter equally likely, never the same letter twice in a row (unless there is only one letter). */
export function shuffledDeck(letters, n, rng = Math.random) {
  const deck = [];
  for (let i = 0; i < n; i++) {
    const prev = deck[deck.length - 1];
    const pool = letters.length > 1 ? letters.filter((l) => l !== prev) : letters;
    deck.push(pool[Math.floor(rng() * pool.length)]);
  }
  return deck;
}

/** How many choices Bridge Match offers at a level: 2, 2, 3, 4 (never more than the letters drilled plus the partner). */
export const matchChoiceCount = (level) => (level <= 2 ? 2 : level);

/** The choices for one Bridge Match round: target, its mirror partner, then other drilled letters up to the level's count. */
export function matchChoices(level, target, drill, rng = Math.random) {
  const extra = shuffle(drill.filter((l) => l !== target && l !== PARTNER[target]), rng).slice(0, matchChoiceCount(level) - 2);
  return shuffle([target, PARTNER[target], ...extra], rng);
}
