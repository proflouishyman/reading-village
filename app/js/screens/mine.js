// Letter Mine: lowercase letter flashcards judged by Dad; ores pop out on success.
import { stageLayout, interlude } from "../layout.js";
import { drillLetters } from "../swap.js";
import { runJudged } from "./judged.js";
import { buildLetterDeck, applyResult, rewardForCard, NOT_YET_NOTE } from "../rules.js";
import { trackerFor, runsDeck, pairsDeck, shuffledDeck } from "../levels.js";
import { commitUntilSaved } from "../store.js";
import { h, inventoryRow } from "../ui.js";
import { ORES_ROW } from "../constants.js";
import { playPop } from "../sounds.js";
import { childName } from "../family.js";

const DECK_SIZE = 12; // ~3 minutes at ~15s a card

/**
 * The deck for a Letter Mine level (design in docs/design.md "Levels"): 1 runs of three of the same letter, 2 letters
 * mixed (review-weighted, the original deck), 3 mirror pairs alternating (b d b d), 4 every drilled letter shuffled.
 * Never adds a timer, a loss or a loud miss: the deck is only an order of cards. `rng` is injectable for tests.
 */
export function mineDeck(level, drill, stats, n = DECK_SIZE, rng = Math.random) {
  if (level === 1) return runsDeck(drill, n, 3, rng);
  if (level === 2) return buildLetterDeck(drill, stats, n, rng);
  if (level === 3) return pairsDeck(drill, n, rng);
  if (level === 4) return shuffledDeck(drill, n, rng);
  throw new Error(`mineDeck: no design for level ${level}`);
}

export async function run(app) {
  const { progress } = app.store;
  const drill = drillLetters(progress.active_letters, app.swapOrder, progress.settings.lowercase_percent ?? 0);
  if (drill.length === 0) {
    // Deliberate rule, not a fallback: a letter is drilled only when it AND its partner are swapped in; none yet -> calm skip.
    await interlude(app.root, { title: "Letter Mine", body: NOT_YET_NOTE, buttonText: "OK", sprite: "pig" });
    return "done";
  }
  const L = stageLayout(app.root, { title: "Letter Mine", dadHint: `${childName()} says the sound and a key word. Then you tap.`, reserveCue: true });
  const tracker = await trackerFor(app, "mine");
  L.setLevel(...tracker.lines());
  const roundLevel = tracker.level; // fixed for the whole round: a mid-round level-up must not retag the rest of it
  const deck = mineDeck(roundLevel, drill, progress.letter_stats);
  const entries = deck.map((letter, i) => ({ letter, id: i }));
  const tray = h("div", { class: "tray" });
  const refreshTray = () => tray.replaceChildren(inventoryRow(app.store.progress.inventory, ORES_ROW));
  let streak = 0;

  const show = (entry) => {
    const card = h("div", { class: "card letter-card" }, h("div", { class: "big-letter", text: entry.letter }));
    L.play.replaceChildren(card, tray);
    refreshTray();
    return card;
  };

  const record = async (entry, result) => {
    streak = result === "correct" ? streak + 1 : 0;
    const ore = rewardForCard(result, streak);
    const level = roundLevel;
    await commitUntilSaved({ type: "card", track: "lowercase", item: entry.letter, result, level }, (p) => {
      p.letter_stats[entry.letter] = applyResult(p.letter_stats[entry.letter], result);
      if (ore) p.inventory[ore] += 1;
    });
    tracker.record(result, level);
    L.setLevel(...tracker.lines());
    if (ore) playPop(); // ore from a correct/assisted card; a miss earns nothing and makes no sound
    refreshTray();
    return ore;
  };

  return runJudged(L, { entries, show, cueFor: (e) => [app.cues[e.letter]], record });
}
