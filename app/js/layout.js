// Shared stage layout: a big area for the child and a visually separate DAD bar at the bottom.
import { h, setKid } from "./ui.js";
import { soundToggleButton } from "./soundui.js";
import { spriteElement } from "./sprites.js";
import { grownUp } from "./family.js";

// main.js registers what the gear button does (leave the stage, then show Settings); layout stays screen-agnostic.
let settingsOpener = null;
export function setSettingsOpener(fn) { settingsOpener = fn; }

/**
 * Build the stage frame inside root.
 * Returns { play, dad, cue, choose, quitted } where
 *  - play: the area the child looks at
 *  - cue: container under the card for cue text
 *  - choose(altAgainLabel?, {allowAgain}): Promise<"got"|"again"|"quit"> from Dad's buttons
 *    (allowAgain: false hides "Let's try again", used on victory cards)
 *  - quitted: Promise resolving when Dad taps Home (screens abandon the stage)
 */
export function stageLayout(root, { title, onQuit, dadHint, reserveCue = false }) {
  const play = h("div", { class: "play" });
  const cue = h("div", { class: `cue-slot${reserveCue ? " reserve" : ""}` });
  let resolveChoice = null;
  const gotBtn = h("button", { class: "btn dad-btn good", text: "Got it!", disabled: "", onclick: () => answer("got") });
  const againBtn = h("button", { class: "btn dad-btn again", text: "Let's try again", disabled: "", onclick: () => answer("again") });
  const hint = h("div", { class: "dad-hint", text: dadHint || "" });
  const dadButtons = h("div", { class: "dad-buttons" }, gotBtn, againBtn);
  const dad = h("div", { class: "dad-bar" },
    h("div", { class: "dad-label" }, spriteElement("dad", 2), h("span", { text: grownUp().toUpperCase() })),
    dadButtons,
    hint,
    soundToggleButton(),
    h("button", { class: "btn small settings-gear", text: "⚙ Settings", onclick: () => {
      if (!settingsOpener) throw new Error("stageLayout: no settings opener registered (main.js must call setSettingsOpener)");
      settingsOpener(); // flags Home to open Settings; leaving the stage then runs the usual quit path
      resolveQuit("quit"); onQuit?.();
    } }));
  let resolveQuit;
  const quitted = new Promise((r) => (resolveQuit = r));
  const homeBtn = h("button", { class: "btn small dad-only", kid: "Home", onclick: () => { resolveQuit("quit"); onQuit?.(); } });
  const progress = h("div", { class: "stage-progress", hidden: "" });
  // Level line (docs/design.md "Levels"): "Level 2: blends" and "7 of 8 right at level 2", small caps, under the title.
  const levelTitle = h("div", { class: "level-title" });
  const levelSub = h("div", { class: "level-sub" });
  const levelLine = h("div", { class: "level-line", hidden: "" }, levelTitle, levelSub);
  const bar = h("div", { class: "stage-top" }, homeBtn, h("div", { class: "stage-head" }, h("div", { class: "stage-title", kid: title }), levelLine), progress);
  root.replaceChildren(h("div", { class: "stage" }, bar, h("div", { class: "stage-main" }, play, cue), dad));

  function answer(what) {
    gotBtn.disabled = againBtn.disabled = true;
    const r = resolveChoice;
    resolveChoice = null;
    if (r) r(what);
  }

  return {
    play, cue, dad, hint, quitted,
    /** Enable Dad's buttons and wait for a click (or Home). */
    choose(againLabel = "Let's try again", { allowAgain = true } = {}) {
      againBtn.textContent = againLabel;
      againBtn.classList.toggle("off", !allowAgain); // victory cards offer only "Got it!"
      gotBtn.disabled = againBtn.disabled = false;
      return Promise.race([new Promise((r) => (resolveChoice = r)), quitted]);
    },
    setHint(t) { hint.textContent = t; },
    /**
     * the child's progress row: `total` block icons, the first `done` filled, the next one highlighted, plus
     * "n / total" in small caps (n = the card he is on). A done card is just filled, whatever its result, and a
     * re-queued card simply makes `total` bigger: nothing here ever shows a miss.
     */
    setProgress(done, total) {
      if (!Number.isInteger(done) || !Number.isInteger(total) || done < 0 || total < 1 || done > total) {
        throw new Error(`setProgress: bad counts done=${done} total=${total}`);
      }
      const pips = Array.from({ length: total }, (_, i) => h("span", { class: `pip${i < done ? " done" : i === done ? " cur" : ""}` }));
      const count = setKid(h("span", { class: "pip-count" }), `${Math.min(done + 1, total)} / ${total}`);
      progress.replaceChildren(...pips, count);
      progress.hidden = false;
    },
    /** Show the level line: `title` ("Level 2: blends") and `sub` ("7 of 8 right at level 2"). Called again after each attempt. */
    setLevel(title, sub) {
      setKid(levelTitle, title);
      setKid(levelSub, sub);
      levelLine.hidden = false;
    },
    /** Hide Dad's two buttons on stages that do not use them (only the hint remains). */
    disableButtons() { dadButtons.classList.add("off"); },
  };
}

/**
 * Between-stage / end screen with one big button; resolves "next". All text is small caps (the child's).
 * `dadNote` (optional) adds a Dad bar underneath explaining why the child is seeing this screen.
 */
export function interlude(root, { title, body, buttonText, sprite, dadNote }) {
  return new Promise((resolve) => {
    const screen = h("div", { class: `interlude${dadNote ? " with-dad" : ""}` },
      sprite ? spriteElement(sprite, 8) : null,
      h("h1", { kid: title }),
      body ? h("p", { kid: body }) : null,
      h("button", { class: "btn big", kid: buttonText, onclick: () => resolve("next") }));
    const dad = dadNote ? h("div", { class: "dad-bar" },
      h("div", { class: "dad-label" }, spriteElement("dad", 2), h("span", { text: grownUp().toUpperCase() })),
      h("div", { class: "dad-hint", text: dadNote })) : null;
    root.replaceChildren(screen, ...(dad ? [dad] : []));
  });
}
