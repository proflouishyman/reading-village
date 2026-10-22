// Loads and validates app/data/*.json. Problems throw with the file name (never defaulted).
import { LETTERS, confusablesIn } from "./rules.js";
import { validateSwapOrder } from "./swap.js";
import { PATTERNS } from "./levels.js";

async function fetchJson(file) {
  let res;
  try {
    res = await fetch(file, { cache: "no-store" });
  } catch (e) {
    throw new Error(`${file}: could not fetch (${e.message})`);
  }
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`);
  try {
    return await res.json();
  } catch (e) {
    throw new Error(`${file}: not valid JSON (${e.message})`);
  }
}

/** cues.json: { letter: { cue: string, picture?: "bed", bedNote?: string } } for all 8 letters. */
export async function loadCues() {
  const file = "data/cues.json";
  const cues = await fetchJson(file);
  for (const l of LETTERS) {
    const c = cues[l];
    if (!c || typeof c.cue !== "string" || !c.cue) throw new Error(`${file}: letter "${l}" needs a non-empty "cue"`);
    if (c.picture !== undefined && c.picture !== "bed") throw new Error(`${file}: letter "${l}" has unknown picture "${c.picture}"`);
    if (c.picture === "bed" && typeof c.bedNote !== "string") throw new Error(`${file}: letter "${l}" needs "bedNote" with picture "bed"`);
  }
  return cues;
}

/**
 * words.json: {"v":2,"words":[{word, focus, level, pattern}]}. `word` lowercase letters; `focus` a confusable letter inside
 * the word, or null when the word has none; `level` 1-6 and `pattern` the phonics ladder rung it belongs to
 * (cvc 1, blend 2, digraph 3, silent_e 4, vowel_team 5, two_syllable 6, see levels.js PATTERNS). Throws naming the entry.
 */
export function validateWords(obj, file = "data/words.json") {
  if (!obj || obj.v !== 2 || !Array.isArray(obj.words) || obj.words.length === 0) throw new Error(`${file}: must be {"v":2,"words":[...]} with at least one word`);
  const seen = new Set();
  obj.words.forEach((w, i) => {
    const at = `${file}: words[${i}]`;
    if (!w || typeof w !== "object") throw new Error(`${at} must be an object`);
    for (const k of Object.keys(w)) if (!["word", "focus", "level", "pattern"].includes(k)) throw new Error(`${at}: unknown field "${k}"`);
    if (typeof w.word !== "string" || !/^[a-z]+$/.test(w.word)) throw new Error(`${at}: "word" must be lowercase letters`);
    if (seen.has(w.word)) throw new Error(`${at}: duplicate word "${w.word}"`);
    seen.add(w.word);
    const conf = confusablesIn(w.word);
    if (conf.length === 0 ? w.focus !== null : !conf.includes(w.focus)) throw new Error(`${at}: focus ${JSON.stringify(w.focus)} must be a confusable letter in "${w.word}" (null only when it has none)`);
    if (!PATTERNS.includes(w.pattern)) throw new Error(`${at}: "${w.word}" pattern ${JSON.stringify(w.pattern)} must be one of ${PATTERNS.join(", ")}`);
    if (w.level !== PATTERNS.indexOf(w.pattern) + 1) throw new Error(`${at}: "${w.word}" level ${JSON.stringify(w.level)} does not match pattern ${w.pattern} (level ${PATTERNS.indexOf(w.pattern) + 1})`);
  });
  return obj.words;
}

export async function loadWords() {
  const file = "data/words.json";
  return validateWords(await fetchJson(file), file);
}

/** swap_order.json: { v: 1, order: [26 unique a-z letters] }, the order lowercase letters replace small caps. */
export async function loadSwapOrder() {
  const file = "data/swap_order.json";
  return validateSwapOrder(await fetchJson(file), file);
}
