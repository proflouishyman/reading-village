// Dad's settings screen: font, sound, lowercase track, dashboard link, and a non-destructive progress reset.
// Everything here is Dad-facing normal text, so the whole screen sits inside .dad-only (the small-caps walk skips it).
import { h, applyFont, showFatal } from "../ui.js";
import { store, saveProgress, loadProgress, endSession } from "../store.js";
import { soundToggleButton } from "../soundui.js";
import { lowercaseOn } from "../constants.js";
import { STATIC } from "../runmode.js";
import { ApiError, getEvents } from "../api.js";
import { GAMES, GAME_TITLES, deriveLevels, levelNames } from "../levels.js";
import { SPRITE_NAMES } from "../sprites.js";
import { configureTextures, getTextures, getArtMode, setArtMode, artToTextureMode, manifestAvailable } from "../mctextures.js";
import { childPoss, grownUp } from "../family.js";

export const RESET_PHRASE = "RESET";

/** Font toggle (plain <-> OpenDyslexic); `onChange` runs after it is saved. Shared by Home and Settings. */
export function fontToggleButton(onChange) {
  const label = store.progress.settings.font === "opendyslexic" ? "Font: OpenDyslexic (click for plain)" : "Font: plain (click for OpenDyslexic)";
  return h("button", { class: "btn small", text: label, onclick: async () => {
    await saveProgress((q) => { q.settings.font = q.settings.font === "opendyslexic" ? "system" : "opendyslexic"; });
    applyFont(store.progress.settings.font);
    onChange();
  } });
}

/** Lowercase-track toggle; turning it on asks for confirmation (same wording as the dashboard). */
export function lowercaseTrackButton(onChange) {
  const on = lowercaseOn(store.progress);
  return h("button", { class: "btn small", text: on ? "Turn lowercase track off" : "Start lowercase track", onclick: async () => {
    if (!on && !confirm("Turn the lowercase track on? Home will show a Lowercase track button (Bridge Match, Letter Mine, lowercase story).")) return;
    const target = on ? "off" : "on"; // explicit target, so a re-applied mutation after a 409 is idempotent
    await saveProgress((q) => { q.settings.lowercase_track = target; });
    onChange();
  } });
}

/**
 * Fill `box` with the art-mode control. "Real Minecraft textures" is offered only when app/assets/mc/manifest.json is
 * served; with it on, the sprites that stay hand-drawn on purpose are listed with their reasons. Switching loads the
 * textures first and saves the mode only if that worked (a failure is shown, the old art stays), then `onChange`.
 */
export async function artModeControls(box, onChange) {
  try {
    const mode = getArtMode();
    const available = await manifestAvailable();
    const row = h("div", { class: "settings-row" });
    if (!available && mode !== "real") {
      row.append(h("span", { id: "art-state", text: "Art: hand-drawn. Real Minecraft textures are not installed (run tools/extract_mc_textures.py)." }));
    } else {
      row.append(h("button", { class: "btn small", id: "art-toggle",
        text: mode === "real" ? "Art: real Minecraft textures (click for hand-drawn)" : "Art: hand-drawn (click for real Minecraft textures)",
        onclick: async () => {
          const next = mode === "real" ? "hand" : "real";
          try {
            await configureTextures(artToTextureMode(next)); // loads every texture; rejects loudly if any is missing
            setArtMode(next);
          } catch (e) {
            showFatal("Art mode not changed", e.message);
            return;
          }
          onChange();
        } }));
    }
    box.replaceChildren(h("h2", { text: "Art" }), row);
    const t = getTextures();
    if (mode === "real" && t) {
      const ids = t.unmapped(SPRITE_NAMES);
      box.append(h("p", { text: `${ids.length} of ${SPRITE_NAMES.length} pictures stay hand-drawn on purpose (no flat Minecraft texture):` }),
        h("ul", { id: "art-unmapped" }, ids.map((id) => h("li", { "data-id": id, text: `${id}: ${t.reason(id)}` }))));
    }
  } catch (e) {
    showFatal("Art settings failed", e.message);
  }
}

/**
 * Dad's level override per game (docs/design.md "Levels"): "Automatic" uses the derived level; a chosen level is saved as
 * progress.settings.level_override.<game> and wins until cleared. `onChange` runs after a save.
 */
export async function levelControls(box, app, onChange) {
  try {
    const derived = deriveLevels(await getEvents(), app.levels);
    const override = store.progress.settings.level_override ?? {};
    box.replaceChildren(h("h2", { text: "Levels" }),
      h("p", { text: "Levels rise by themselves (8 of the last 10 right unaided, after at least 10 tries at a level). Choose a level here to override; Automatic returns to the derived level." }),
      ...GAMES.map((g) => {
        const sel = h("select", { id: `level-${g}`, "data-game": g },
          h("option", { value: "", text: `Automatic (now level ${derived[g].level})` }),
          levelNames(g).slice(0, derived[g].max).map((name, i) => h("option", { value: String(i + 1), text: `Level ${i + 1}: ${name}` })));
        sel.value = override[g] === undefined ? "" : String(override[g]);
        sel.addEventListener("change", async () => {
          const value = sel.value === "" ? null : Number(sel.value); // explicit target, so a re-applied mutation after a 409 is idempotent
          await saveProgress((q) => {
            const lo = { ...(q.settings.level_override ?? {}) };
            if (value === null) delete lo[g]; else lo[g] = value;
            if (Object.keys(lo).length === 0) delete q.settings.level_override; else q.settings.level_override = lo;
          });
          onChange();
        });
        return h("div", { class: "settings-row" }, h("label", { for: `level-${g}`, text: `${GAME_TITLES[g]}: ` }), sel);
      }));
  } catch (e) {
    showFatal("Level settings failed", e.message);
  }
}

/** POST /api/reset. Throws ApiError with the server's message on any non-200 (never swallowed). */
export async function postReset() {
  let res;
  try {
    res = await fetch("/api/reset", {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      body: JSON.stringify({ confirm: RESET_PHRASE }),
    });
  } catch (e) {
    throw new ApiError(`server not reachable (${e.message})`);
  }
  const payload = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(`reset failed: HTTP ${res.status}: ${payload?.error ?? "no details"}`, res.status);
  if (!payload || typeof payload.archived_to !== "string") throw new ApiError("reset: server reply has no archived_to", res.status);
  return payload.archived_to;
}

/**
 * Render the settings screen into app.root. `onClose` returns to Home. `archivedTo` (optional) is shown after a reset.
 * A reset first ends the open session (so the archived log is complete), archives on the server, reloads progress
 * through the store, and leaves no session open: the next stage starts a fresh one.
 */
export function showSettings(app, { onClose, archivedTo = null }) {
  const again = () => showSettings(app, { onClose });
  const input = h("input", { type: "text", id: "reset-confirm", autocomplete: "off", placeholder: `Type ${RESET_PHRASE}` });
  const resetBtn = h("button", { class: "btn small", id: "reset-go", text: "Reset progress", disabled: "", onclick: async () => {
    resetBtn.disabled = true;
    await endSession();
    const path = await postReset();
    await loadProgress();
    document.documentElement.dataset.font = store.progress.settings.font;
    showSettings(app, { onClose, archivedTo: path });
  } });
  input.addEventListener("input", () => { resetBtn.disabled = input.value !== RESET_PHRASE; });

  const artBox = h("div", { class: "settings-art", id: "settings-art" });
  const levelsBox = h("div", { class: "settings-levels", id: "settings-levels" });
  app.root.replaceChildren(h("div", { class: "settings dad-only" },
    h("h1", { text: `Settings (${grownUp()})` }),
    h("div", { class: "settings-row" }, fontToggleButton(again), soundToggleButton(), lowercaseTrackButton(again),
      // The website copy has no Dashboard page and no Reset (docs/away-from-home.md §1 "UI in static mode").
      STATIC ? null : h("a", { class: "btn small", href: "dashboard.html", text: "Dashboard" })),
    artBox,
    levelsBox,
    STATIC ? null : h("div", { class: "settings-reset" },
      h("h2", { text: "Reset progress…" }),
      h("p", { text: `Archives ${childPoss()} progress and history into data/archive/ and starts fresh. Nothing is deleted. Type ${RESET_PHRASE} to confirm.` }),
      h("div", { class: "settings-row" }, input, resetBtn),
      archivedTo ? h("p", { class: "settings-archived", text: `Reset done. Old progress and events were archived to: ${archivedTo}` }) : null),
    h("button", { class: "btn small", id: "settings-back", text: "Back to Home", onclick: onClose })));
  artModeControls(artBox, again);
  levelControls(levelsBox, app, again);
}
