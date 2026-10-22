// What the child sees when the server reports new treasure ("A surprise for your Treasure Pile!") and minigame level-ups.
// The toast never blocks; the level-up celebration is queued and shown at the next calm moment (between stages
// or on Home) by celebrateLevelUp(), so it never interrupts a word he is reading. (Villager promotions are chosen
// and celebrated on the Village screen; the old shared village level-up is gone.)
import { h } from "./ui.js";
import { spriteElement } from "./sprites.js";
import { resolveSprite, validateEventResult } from "./villagelogic.js";
import { playFanfare, playSparkle } from "./sounds.js";
import { interlude } from "./layout.js";
import { GAME_TITLES } from "./levels.js";

const TOAST_MS = 4200;
/** Minigame level-ups ([{game,level}]) waiting to be celebrated. */
export const pending = { gameLevelUps: [] };

let toastEl = null;
let toastTimer = null;

function host() {
  if (!toastEl) {
    toastEl = h("div", { id: "surprise", "aria-live": "polite" });
    document.body.append(toastEl);
  }
  return toastEl;
}

/** Show the surprise toast for new treasure entries [{label, sprite}] (replaces any toast still up). */
export function showSurprise(entries) {
  if (!entries.length) return;
  const el = host();
  el.replaceChildren(h("div", { class: "surprise-card" },
    h("div", { class: "surprise-sprites" }, entries.slice(0, 4).map((t) => spriteElement(resolveSprite(t.sprite), 4))),
    h("div", { class: "surprise-text" },
      h("div", { class: "surprise-title", kid: "A surprise for your Treasure Pile!" }),
      h("div", { class: "surprise-what", kid: entries.map((t) => t.label).join(", ") }))));
  el.classList.add("show");
  playSparkle(0);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), TOAST_MS);
}

/** Wire for the committer's onEvent: validate the reply, toast new treasure, queue minigame level-ups. */
export function handleEventReply(reply) {
  validateEventResult(reply);
  if (reply.treasure) showSurprise(reply.treasure);
  for (const g of reply.game_level_ups ?? []) {
    if (!pending.gameLevelUps.some((x) => x.game === g.game && x.level === g.level)) pending.gameLevelUps.push(g);
  }
}

/** Is any celebration (a minigame level) waiting? */
export const celebrationWaiting = () => pending.gameLevelUps.length > 0;

/**
 * Show the waiting celebrations, one screen each (resolve when the child taps on): each minigame level ("Crafting
 * level 3!"). No-op when nothing is waiting.
 */
export async function celebrateLevelUp(root) {
  while (pending.gameLevelUps.length) {
    const g = pending.gameLevelUps.shift();
    playFanfare();
    playSparkle(0.8);
    await interlude(root, {
      title: `${GAME_TITLES[g.game]} level ${g.level}!`,
      body: "A surprise is waiting in your Treasure Pile!",
      buttonText: "Yay!",
      sprite: "diamond",
    });
  }
}
