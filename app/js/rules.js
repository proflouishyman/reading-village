// Pure game rules: letter introduction, review mix, rewards, word picking.
// Constants that also appear in server.py (letters, inventory keys, blocks) must stay in sync.

export const LETTERS = ["b", "d", "p", "q", "m", "w", "n", "u"];
/** Introduction order: one confusable group at a time (docs/design.md). */
export const LETTER_GROUPS = [["b", "d"], ["p"], ["q"], ["n", "u"], ["m", "w"]];
/** Mirror partner offered as the wrong choice in Bridge Match. */
export const PARTNER = { b: "d", d: "b", p: "q", q: "p", n: "u", u: "n", m: "w", w: "m" };
export const WINDOW = 10; // results kept per letter
export const MASTERY = 0.8; // share of the window that must be independent-correct
export const REVIEW_SHARE = 0.2; // how often mastered letters reappear
export const ORES = ["coal", "iron", "gold", "diamond"];
export const GRID_W = 12;
export const GRID_H = 8;
/** Decorations unlock one per finished story pass, in this order; each costs 1 emerald. */
export const DECORATIONS = ["door", "torch", "pig", "bed", "chest"];
export const BUILD_BLOCKS = ["wood", "stone"]; // cost 1 of the same inventory item

/** Share of the last WINDOW tries that were independent-correct; null until WINDOW tries exist. */
export function accuracy(stat) {
  if (!stat || stat.recent.length < WINDOW) return null;
  return stat.recent.filter((r) => r === "correct").length / WINDOW;
}

export function isMastered(stat) {
  const a = accuracy(stat);
  return a !== null && a >= MASTERY;
}

/**
 * Introduction rule: the first group not fully active is added once every currently
 * active letter is mastered (>= 80% of the last 10). Returns {active, added}.
 */
export function nextActiveLetters(active, stats) {
  const allMastered = active.every((l) => isMastered(stats[l]));
  if (!allMastered) return { active, added: [] };
  const next = LETTER_GROUPS.find((g) => g.some((l) => !active.includes(l)));
  if (!next) return { active, added: [] };
  const added = next.filter((l) => !active.includes(l));
  return { active: [...active, ...added], added };
}

/** Why the rule has not advanced (for the dashboard); null when it already can/has nothing to add. */
export function introductionStatus(active, stats) {
  const next = LETTER_GROUPS.find((g) => g.some((l) => !active.includes(l)));
  if (!next) return { next: null, waitingOn: [] };
  const waitingOn = active.filter((l) => !isMastered(stats[l]));
  return { next: next.filter((l) => !active.includes(l)), waitingOn };
}

/**
 * Letter deck of n cards: ~20% review of mastered active letters, the rest focus
 * (not-yet-mastered) letters. Avoids repeating the previous letter when it can.
 */
export function buildLetterDeck(active, stats, n, rng = Math.random) {
  const review = active.filter((l) => isMastered(stats[l]));
  const focus = active.filter((l) => !isMastered(stats[l]));
  const deck = [];
  for (let i = 0; i < n; i++) {
    const useReview = review.length > 0 && (focus.length === 0 || rng() < REVIEW_SHARE);
    const pool = useReview ? review : focus;
    const prev = deck[deck.length - 1];
    const options = pool.length > 1 ? pool.filter((l) => l !== prev) : pool;
    deck.push(options[Math.floor(rng() * options.length)]);
  }
  return deck;
}

/** Returns a new stat with one result applied (stat may be undefined for a first try). */
export function applyResult(stat, result) {
  const s = stat ?? { recent: [], total_correct: 0, total_tries: 0 };
  return {
    recent: [...s.recent, result].slice(-WINDOW),
    total_correct: s.total_correct + (result === "correct" ? 1 : 0),
    total_tries: s.total_tries + 1,
  };
}

/** Ore for a letter-card success: climbs coal -> iron -> gold -> diamond with the in-session streak. */
export function rewardForCard(result, streak) {
  if (result === "miss") return null;
  // streak counts consecutive independent-correct cards including this one; assisted resets it to 0.
  return ORES[Math.min(Math.floor(Math.max(streak - 1, 0) / 2), ORES.length - 1)];
}

/** Block for a finished word: wood and stone alternate. Misses earn nothing. */
export function rewardForWord(result, wordsRewardedSoFar) {
  if (result === "miss") return null;
  return wordsRewardedSoFar % 2 === 0 ? "wood" : "stone";
}

/** Shown when Bridge Match / Letter Mine have no swapped-in mirror letter to drill (a deliberate skip). */
export const NOT_YET_NOTE = "Not yet: the mirror letters come in later.";

// Emerald earning (word, story first pass / replay, craft) is configured server-side (config/minecraft.json `earn`)
// and read at boot with loadVillageRates (store.js); there are no emerald constants here.

/**
 * Every stage must end on a success. Given the results so far, return the item to show
 * once more as a victory card, or null when the last result already was a clean success.
 * `fallback` is used only if nothing has been correct yet this stage.
 */
export function victoryItem(history, fallback) {
  if (history.length === 0) return null;
  if (history[history.length - 1].result === "correct") return null;
  for (let i = history.length - 1; i >= 0; i--) if (history[i].result === "correct") return history[i].item;
  return fallback;
}

/** Mirror-prone letters in a word; "qu" counts only as q. */
export function confusablesIn(word) {
  return [...word.replace(/qu/g, "q")].filter((c) => LETTERS.includes(c));
}

/**
 * Words usable in LOWERCASE presentations (lowercase track, swap-in pages): every confusable letter they contain is active (the confusable-letter gate; "qu" counts as q).
 * A word's focus letter is one of its confusables, so it is covered by the same test; words with no confusable at all
 * (focus null, e.g. "frog") are always eligible. Small-caps screens (Crafting Table, Word Blocks) do not use this gate:
 * small-caps shapes do not mirror.
 */
export function eligibleWords(words, active) {
  return words.filter((w) => confusablesIn(w.word).every((c) => active.includes(c)));
}

/** Pick up to n distinct eligible words, shuffled. */
export function pickWords(words, active, n, rng = Math.random) {
  const pool = eligibleWords(words, active).slice();
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, n);
}

/** Decorations Dad & the child have unlocked: one per finished story pass. */
export function unlockedDecorations(progress) {
  const passes = Object.values(progress.stories).reduce((n, s) => n + s.smallcaps_done + s.lowercase_done, 0);
  return DECORATIONS.slice(0, passes);
}
