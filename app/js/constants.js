import { grownUp } from "./family.js";
// UI-level constants shared by screens.
export const ORES_ROW = ["coal", "iron", "gold", "diamond"];
export const ALL_INVENTORY = ["coal", "iron", "gold", "diamond", "wood", "stone", "emerald"];

// Session sequences. `track` is passed to the story screen; `label` is shown on interludes.
// The small-caps adventure is "Start today's adventure" and never includes lowercase.
export const SMALLCAPS_ADVENTURE = [
  { stage: "blocks", label: "Word Blocks" },
  { stage: "story", track: "smallcaps", pick: true, label: "Story (small caps)" },
  { stage: "build", label: "Build" },
];
// The separate lowercase track (only when settings.lowercase_track is "on"). Easy to change later.
export const LOWERCASE_TRACK = [
  { stage: "story", track: "swap", pick: true, label: "Swap-in story" },
  { stage: "match", label: "Bridge Match" },
  { stage: "mine", label: "Letter Mine" },
  { stage: "build", label: "Build" },
];
/** Stages that belong to the lowercase track: locked on Home while it is off. */
export const LOWERCASE_STAGES = ["match", "mine"];
/** Home note while lowercase is locked; the grown-up label comes from family.json. */
export const lockedNote = () => `Lowercase comes later — ${grownUp()} will open it.`;

/** settings.lowercase_track; a progress file without it reads as "off". */
export function lowercaseOn(progress) {
  return progress.settings.lowercase_track === "on";
}

// Crafting Table (docs/design.md "Crafting Table"). Not part of the adventure sequences: Home tile only.
export const CRAFT_WORDS_PER_ROUND = 5;
export const CRAFT_DISTRACTORS = 2; // extra letter blocks in the tray
