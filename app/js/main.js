// App shell: boot, home screen, stage launching, the adventure sequence, and the Dad-only clock.
import { loadProgress, store, ensureSession, endSession, saveProgress, commitUntilSaved, loadVillageRates } from "./store.js";
import { celebrateLevelUp, celebrationWaiting } from "./surprise.js";
import { mcStatusNode } from "./mcstatus.js";
import { STATIC } from "./runmode.js";
import { sendToDadButton, sendToDadPrompt } from "./senddad.js";
import { loadCues, loadWords, loadSwapOrder } from "./data.js";
import { loadLevels } from "./levels.js";
import { installTextures, showFatal, h, inventoryRow, applyFont, dadNote } from "./ui.js";
import { soundToggleButton } from "./soundui.js";
import { setSoundReporter } from "./sounds.js";
import { interlude, setSettingsOpener } from "./layout.js";
import { showSettings, fontToggleButton } from "./screens/settings.js";
import { spriteElement } from "./sprites.js";
import { configureTextures, getArtMode, setArtMode, artToTextureMode } from "./mctextures.js";
import { nextActiveLetters } from "./rules.js";
import { formatClock } from "./util.js";
import { ALL_INVENTORY, SMALLCAPS_ADVENTURE, LOWERCASE_TRACK, LOWERCASE_STAGES, lowercaseOn } from "./constants.js";
import { loadFamily, childPoss, grownUp } from "./family.js";
import { lockedNote } from "./constants.js";

const SUGGEST_AT_SECONDS = 600; // gentle "Great mining today!" nudge; Dad can keep going

const root = document.getElementById("app");
const app = { root, store, cues: null, words: null, swapOrder: null, levels: null, settingsPending: false };

// The stage gear leaves the stage (the usual quit path ends in home()); home() then shows Settings instead.
setSettingsOpener(() => { app.settingsPending = true; });

const STAGES = {
  mine: { label: "Letter Mine", icon: "coal", module: () => import("./screens/mine.js") },
  match: { label: "Bridge Match", icon: "bed", module: () => import("./screens/match.js") },
  blocks: { label: "Word Blocks", icon: "wood", module: () => import("./screens/blocks.js") },
  story: { label: "Story", icon: "chest", module: () => import("./screens/story.js") },
  build: { label: "Build", icon: "door", module: () => import("./screens/build.js") },
  village: { label: "", icon: "village_bell", module: () => import("./screens/village.js"), noSession: true },
  treasure: { label: "Treasure Pile", icon: "chest", module: () => import("./screens/treasure.js"), noSession: true },
  craft: { label: "Crafting Table", icon: "pickaxe", module: () => import("./screens/craft.js") },
};
// Home-screen button order only. Build is no longer a tile (Village replaces it); its screen stays in the adventure.
const ORDER = ["blocks", "story", "match", "mine", "craft", "village", "treasure"];

function fatal(title, err) {
  showFatal(title, err instanceof Error ? `${err.message}\n\n${err.stack ?? ""}` : String(err));
}
window.addEventListener("error", (e) => fatal("Something broke", e.error ?? e.message));
window.addEventListener("unhandledrejection", (e) => fatal("Something broke", e.reason));

// --- Dad-only session clock ---------------------------------------------------
let suggested = false;
setInterval(() => {
  const clock = document.getElementById("clock");
  if (!store.sessionStartMs) {
    clock.textContent = "";
    suggested = false;
    return;
  }
  const secs = (Date.now() - store.sessionStartMs) / 1000;
  clock.textContent = formatClock(secs);
  if (secs >= SUGGEST_AT_SECONDS && !suggested) {
    suggested = true;
    const toast = document.getElementById("toast");
    toast.replaceChildren("Great mining today! A good place to stop. ", h("button", { class: "btn small", text: "Keep going", onclick: () => toast.replaceChildren() }));
  }
}, 1000);

// --- Starting things ------------------------------------------------------------
/** Begin the session (if needed). The letter-introduction rule runs only while the lowercase track is on. */
async function begin() {
  await ensureSession();
  if (!lowercaseOn(store.progress)) return;
  const { active, added } = nextActiveLetters(store.progress.active_letters, store.progress.letter_stats);
  if (added.length) {
    await saveProgress((p) => { p.active_letters = active; });
    app.note = `New letters added: ${added.join(", ")}`;
  }
}

async function runStage(name, opts) {
  const mod = await STAGES[name].module();
  return mod.run(app, opts);
}

/** Run one stage, then return home. Errors are shown loudly. */
async function launch(name, opts) {
  try {
    // Village and Treasure Pile are not reading practice: browsing them must not open a session.
    if (!STAGES[name].noSession) await begin();
    // Standalone Story button = small-caps story picker; the lowercase track has its own buttons.
    await runStage(name, opts ?? (name === "story" ? { track: "smallcaps", pick: true } : undefined));
  } catch (e) {
    fatal(`${STAGES[name].label} failed`, e);
    return;
  }
  home();
}

/** Run a sequence of stages with interludes between them, then close the session. */
async function runSequence(steps, adventure) {
  try {
    await begin();
    for (let i = 0; i < steps.length; i++) {
      const r = await runStage(steps[i].stage, { track: steps[i].track, pick: steps[i].pick });
      if (r === "quit") return home();
      await celebrateLevelUp(root); // a level reached during the stage, shown at this calm moment
      const nxt = steps[i + 1];
      if (nxt) {
        await interlude(root, { title: "Nice work!", body: `Next: ${nxt.label}`, buttonText: "Let's go!", sprite: STAGES[steps[i].stage].icon });
      }
    }
    // Finishing the whole sequence earns the server's "adventure_done" surprise (once per session and adventure).
    await commitUntilSaved({ type: "adventure_done", adventure }, null);
    await celebrateLevelUp(root);
    await interlude(root, { title: "Great mining today!", body: "See you next time, miners!", buttonText: "Finish", sprite: "diamond" });
    await endSession();
    // Website copy: adventure_done and session_end are both made now, so one prompt offers the export for both.
    if (STATIC) await sendToDadPrompt(root);
  } catch (e) {
    fatal("The adventure failed", e);
    return;
  }
  home();
}

// --- Home -------------------------------------------------------------------------
function home() {
  if (app.settingsPending) {
    app.settingsPending = false;
    return showSettings(app, { onClose: home });
  }
  if (celebrationWaiting()) return celebrateLevelUp(root).then(home, (e) => fatal("Level-up screen failed", e));
  const p = store.progress;
  const lowercase = lowercaseOn(p);
  const stageButtons = ORDER.map((k) => {
    const locked = !lowercase && LOWERCASE_STAGES.includes(k);
    return h("button", { class: `btn stage-btn${locked ? " locked" : ""}`, ...(locked ? { disabled: "" } : {}), onclick: () => launch(k) },
      spriteElement(STAGES[k].icon, 4), h("span", { kid: STAGES[k].label }));
  });
  root.replaceChildren(h("div", { class: "home" },
    h("div", { class: "hero" },
      spriteElement("hero", 8), h("h1", { kid: `${childPoss()} Mining Adventure` }), spriteElement("pig", 8, { p: "y", P: "Y" })),
    h("button", { class: "btn huge", kid: "Start today's adventure", onclick: () => runSequence(SMALLCAPS_ADVENTURE, "smallcaps") }),
    lowercase ? h("div", { class: "stage-row" },
      h("button", { class: "btn big", kid: "Lowercase track", onclick: () => runSequence(LOWERCASE_TRACK, "lowercase") }),
      h("button", { class: "btn big", kid: "Plain lowercase story", onclick: () => launch("story", { track: "lowercase" }) })) : null,
    h("div", { class: "stage-row" }, stageButtons),
    lowercase ? null : h("div", { class: "locked-note", kid: lockedNote() }),
    inventoryRow(p.inventory, ALL_INVENTORY),
    STATIC ? sendToDadButton(home) : null,
    h("div", { class: "dad-corner" },
      h("span", { class: "dad-corner-label", text: grownUp() }),
      h("span", { text: `Letters: ${p.active_letters.join(" ")}` }),
      app.note ? h("span", { text: app.note }) : null,
      mcStatusNode(),
      STATIC ? null : h("a", { class: "btn small", href: "dashboard.html", text: "Dashboard" }),
      fontToggleButton(home),
      soundToggleButton(),
      h("button", { class: "btn small settings-gear", text: "⚙ Settings", onclick: () => showSettings(app, { onClose: home }) }),
      // Always shown so Dad can find it; greyed out when no session is open (a finished adventure already ended it,
      // and on Dad's Mac that session_end already triggered the website update).
      store.sessionId ? h("button", { class: "btn small", text: "Finish session", onclick: async () => {
        await endSession();
        if (STATIC) {
          try { await sendToDadPrompt(root); } catch (e) { fatal(`Send to ${grownUp()} failed`, e); return; }
        }
        home();
      } }) : h("button", { class: "btn small", text: "No session open", disabled: true,
        title: "Nothing to finish: the last session already ended" }))));
}

async function boot() {
  installTextures();
  setSoundReporter(dadNote); // "sound could not start" goes to Dad, once; never to the child
  try {
    app.family = await loadFamily();
    STAGES.village.label = app.family.village_name;
    document.title = `${childPoss()} Mining Adventure`;
    await loadProgress();
    app.cues = await loadCues();
    app.words = await loadWords();
    app.swapOrder = await loadSwapOrder();
    app.levels = await loadLevels();
    await loadVillageRates();
    // Art mode (Dad's setting). "real" with missing/incomplete textures fails loudly here (never a silent hand-drawn
    // fallback); /?art=hand resets the saved mode so the game can still be opened.
    if (new URLSearchParams(location.search).get("art") === "hand") setArtMode("hand");
    await configureTextures(artToTextureMode(getArtMode()));
  } catch (e) {
    fatal("Could not start", e);
    return;
  }
  applyFont(store.progress.settings.font);
  home();
}

boot();
