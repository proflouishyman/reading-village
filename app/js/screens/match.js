// Bridge Match: small-caps letter -> pick its lowercase twin from {target, mirror partner}.
// Only the correct choice counts; a wrong click wiggles gently and shows the cue.
import { stageLayout, interlude } from "../layout.js";
import { drillLetters } from "../swap.js";
import { toSmallCaps } from "../smallcaps.js";
import { buildLetterDeck, applyResult, victoryItem, NOT_YET_NOTE } from "../rules.js";
import { trackerFor, runsDeck, shuffledDeck, matchChoices } from "../levels.js";
import { commitUntilSaved } from "../store.js";
import { h, cueBox } from "../ui.js";
import { childName } from "../family.js";

const ROUNDS = 8; // ~2 minutes

/**
 * The target letters for a Bridge Match level (design in docs/design.md "Levels"): 1 runs of the same letter, 2 and 3 the
 * review-weighted mix, 4 every drilled letter shuffled. The number of choices per round grows with the level
 * (levels.js matchChoices: 2, 2, 3, 4). `rng` is injectable for tests.
 */
export function matchDeck(level, drill, stats, n = ROUNDS, rng = Math.random) {
  if (level === 1) return runsDeck(drill, n, 4, rng);
  if (level === 2 || level === 3) return buildLetterDeck(drill, stats, n, rng);
  if (level === 4) return shuffledDeck(drill, n, rng);
  throw new Error(`matchDeck: no design for level ${level}`);
}

export async function run(app) {
  const { progress } = app.store;
  const drill = drillLetters(progress.active_letters, app.swapOrder, progress.settings.lowercase_percent ?? 0);
  if (drill.length === 0) {
    // Deliberate rule, not a fallback: a letter is drilled only when it AND its partner are swapped in; none yet -> calm skip.
    await interlude(app.root, { title: "Bridge Match", body: NOT_YET_NOTE, buttonText: "OK", sprite: "pig" });
    return "done";
  }
  const L = stageLayout(app.root, { title: "Bridge Match", dadHint: `${childName()} clicks. A wrong click is logged quietly — no judging needed.`, reserveCue: true });
  L.disableButtons();
  const tracker = await trackerFor(app, "match");
  L.setLevel(...tracker.lines());
  const roundLevel = tracker.level; // fixed for the whole round: a mid-round level-up must not retag the rest of it
  const letters = matchDeck(roundLevel, drill, progress.letter_stats);
  const history = [];

  /**
   * One round; resolves with "correct"/"assisted" once the right letter is clicked, or "quit".
   * A victory round (the stage's last card) can never record a miss: a wrong click only wiggles, and the
   * right click is recorded as `victoryResult`.
   */
  async function round(target, { victory = false, victoryResult = "correct" } = {}) {
    const choices = matchChoices(roundLevel, target, drill);
    const prompt = h("div", { class: "card sc-card" }, h("div", { class: "big-letter sc-letter", html: toSmallCaps(target) }));
    const buttons = choices.map((c) => h("button", { class: "btn choice", text: c, "data-letter": c }));
    const row = h("div", { class: "choices" }, buttons);
    L.cue.replaceChildren();
    L.setProgress(history.length, letters.length + 1); // the victory round counts as the last pip
    L.play.replaceChildren(h("div", { class: "match-prompt", kid: "Which one is the same letter?" }), prompt, row);
    let missed = false;
    return new Promise((resolve) => {
      L.quitted.then(() => resolve("quit"));
      buttons.forEach((b) => b.addEventListener("click", async () => {
        const chosen = b.dataset.letter;
        const right = chosen === target;
        const result = victory ? victoryResult : right ? (missed ? "assisted" : "correct") : "miss";
        buttons.forEach((x) => (x.disabled = true));
        if (!victory || right) {
          await commitUntilSaved({ type: "match", item: target, result, chosen, level: roundLevel }, (p) => {
            p.letter_stats[target] = applyResult(p.letter_stats[target], result);
          });
          tracker.record(result, roundLevel);
          L.setLevel(...tracker.lines());
        }
        if (right) {
          prompt.classList.add("shine");
          setTimeout(() => resolve(result), 1000);
        } else {
          missed = true;
          b.classList.add("wiggle");
          L.cue.replaceChildren(cueBox(app.cues[target]));
          setTimeout(() => {
            b.classList.remove("wiggle");
            buttons.forEach((x) => (x.disabled = x === b));
          }, 500);
        }
      }));
    });
  }

  for (const target of letters) {
    const r = await round(target);
    if (r === "quit") return "quit";
    history.push({ item: target, result: r });
  }
  const again = victoryItem(history, letters[0]);
  if (again === null) L.setProgress(history.length, history.length); // clean finish: no victory round, all filled
  if (again !== null) {
    const independent = history.some((x) => x.result === "correct");
    if ((await round(again, { victory: true, victoryResult: independent ? "correct" : "assisted" })) === "quit") return "quit";
    L.setProgress(letters.length + 1, letters.length + 1);
  }
  return "done";
}
