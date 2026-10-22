// Word Blocks: CVC words in small caps only (his strong track); Dad judges each word.
import { stageLayout } from "../layout.js";
import { runJudged } from "./judged.js";
import { renderText } from "../smallcaps.js";
import { rewardForWord } from "../rules.js";
import { pickAtLevel, trackerFor } from "../levels.js";
import { getEvents } from "../api.js";
import { playJingle } from "../sounds.js";
import { commitUntilSaved, earnRates } from "../store.js";
import { h, inventoryRow } from "../ui.js";
import { childName } from "../family.js";

const WORDS_PER_SESSION = 10; // ~2 minutes

/**
 * The words for a session at `level` (levels.js pickAtLevel): 80% at the level and 20% review from the level below
 * (2 of 10), least-practised first (`practised` = {word: times read on file}), random among equals. Word Blocks is
 * small caps only, whose shapes do not mirror, so every word at the level is usable (the confusable-letter gate is
 * lowercase-only). Returns {picked: [word entries], short}; throws if the list has no word at or below the level.
 */
export function pickBlocksWords(words, practised, level, n = WORDS_PER_SESSION, rng = Math.random) {
  const items = words.map((w, index) => ({ ...w, index, count: practised[w.word] ?? 0 }));
  return pickAtLevel(items, level, n, { rng });
}

export async function run(app) {
  const { progress } = app.store;
  const L = stageLayout(app.root, { title: "Word Blocks", dadHint: `${childName()} reads the word in small caps.` });
  const events = await getEvents();
  const tracker = await trackerFor(app, "blocks", events);
  const practised = {};
  for (const e of events) if (e.type === "word") practised[e.item] = (practised[e.item] ?? 0) + 1;
  const roundLevel = tracker.level; // fixed for the whole session: a mid-round level-up must not retag the rest of it
  const { picked: words, short } = pickBlocksWords(app.words, practised, roundLevel);
  if (short) L.setHint(`Level ${roundLevel}: there are few words at this level yet, so some are easier ones. ${childName()} reads the word in small caps.`);
  L.setLevel(...tracker.lines());
  const entries = words.map((w) => ({ word: w.word, level: w.level, track: "smallcaps", id: `${w.word}-sc` }));
  const tray = h("div", { class: "tray" });
  const refreshTray = () => tray.replaceChildren(inventoryRow(app.store.progress.inventory, ["wood", "stone", "emerald"]));
  let rewarded = 0;

  const show = (entry) => {
    const card = h("div", { class: "card word-card" }, h("div", { class: "big-word", html: renderText(entry.word, entry.track) }));
    L.play.replaceChildren(card, tray);
    refreshTray();
    return card;
  };

  const record = async (entry, result) => {
    const block = rewardForWord(result, rewarded);
    const emeralds = earnRates().word_emerald; // a correct or assisted word also earns emeralds for the village
    const level = entry.level; // the word's OWN level: a mixed-in easier word never counts toward the current level
    await commitUntilSaved({ type: "word", track: entry.track, item: entry.word, result, level }, (p) => {
      if (block) { p.inventory[block] += 1; p.inventory.emerald += emeralds; }
    });
    tracker.record(result, level);
    L.setLevel(...tracker.lines());
    if (block) {
      rewarded += 1;
      playJingle(); // a correct (or assisted) word; a miss earns nothing and makes no sound
    }
    refreshTray();
    return block;
  };

  // No letter cue here: Word Blocks is the small-caps track, and the cues (lowercase b/d, the bed picture)
  // belong only to the lowercase track's Letter Mine and Bridge Match. Dad's bar tells him what to do instead.
  return runJudged(L, { entries, show, cueFor: () => [], record, againHint: "Sound it out together, then tap." });
}
