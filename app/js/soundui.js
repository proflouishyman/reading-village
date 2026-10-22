// Mute toggle for the Dad areas (stage Dad bar, Home Dad corner, dashboard). Saves settings.sound.
import { h } from "./ui.js";
import { store, saveProgress } from "./store.js";
import { playPop } from "./sounds.js";

const isOn = () => (store.progress.settings.sound ?? "on") === "on"; // missing reads as "on"
const labelNow = () => (isOn() ? "Sound: on (click to mute)" : "Sound: off (click to turn on)");

/** A small button that flips settings.sound and relabels itself; turning sound on plays one pop to confirm. */
export function soundToggleButton() {
  const btn = h("button", { class: "btn small sound-toggle", text: labelNow() });
  btn.addEventListener("click", async () => {
    const target = isOn() ? "off" : "on"; // explicit target, so a re-applied mutation after a 409 is idempotent
    await saveProgress((q) => { q.settings.sound = target; });
    btn.textContent = labelNow();
    if (target === "on") playPop();
  });
  return btn;
}
