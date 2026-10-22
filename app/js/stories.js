// Story loading and validation. Any problem throws StoryError naming the file and the problem.
import { SCENE_KEYS, checkArt, ArtError } from "./scenes.js";
import { LETTERS } from "./rules.js";

export class StoryError extends Error {}

const STORY_FIELDS = ["v", "id", "title", "subtitle", "focus_letters", "pages"];
const PAGE_FIELDS = ["text", "art"];

const isStr = (x) => typeof x === "string" && x.trim() !== "";

/** Validate a parsed story object; returns it unchanged or throws StoryError. */
export function validateStory(story, file = "story", sceneKeys = SCENE_KEYS) {
  const fail = (msg) => {
    throw new StoryError(`${file}: ${msg}`);
  };
  if (story === null || typeof story !== "object" || Array.isArray(story)) fail("must be a JSON object");
  for (const k of STORY_FIELDS) if (!(k in story)) fail(`missing field "${k}"`);
  for (const k of Object.keys(story)) if (!STORY_FIELDS.includes(k)) fail(`unknown field "${k}"`);
  if (story.v !== 1) fail('"v" must be 1');
  for (const k of ["id", "title", "subtitle"]) if (!isStr(story[k])) fail(`"${k}" must be a non-empty string`);
  if (!/^[a-z0-9-]+$/.test(story.id)) fail('"id" must be lowercase letters, digits and dashes');
  if (!Array.isArray(story.focus_letters) || !story.focus_letters.every((l) => LETTERS.includes(l)))
    fail(`"focus_letters" must be a list of letters from ${LETTERS.join("")}`);
  if (!Array.isArray(story.pages) || story.pages.length === 0) fail('"pages" must be a non-empty list');
  story.pages.forEach((p, i) => {
    if (p === null || typeof p !== "object") fail(`pages[${i}] must be an object`);
    for (const k of PAGE_FIELDS) if (!(k in p)) fail(`pages[${i}] missing field "${k}"`);
    for (const k of Object.keys(p)) if (!PAGE_FIELDS.includes(k)) fail(`pages[${i}] unknown field "${k}"`);
    if (!isStr(p.text)) fail(`pages[${i}].text must be a non-empty string`);
    // Only LETTERS must be ASCII. Curly quotes/apostrophes (\u2018 \u2019 \u201c \u201d), dashes and
    // ellipses are not letters, so they are allowed exactly as written (not normalised); cleanWord maps
    // \u2019 to ' for the tricky-word tap.
    const bad = [...p.text].find((ch) => /\p{L}/u.test(ch) && !/[A-Za-z]/.test(ch));
    if (bad) fail(`pages[${i}].text has the non-ASCII letter "${bad}" (small caps only knows a-z; fix the text)`);
    if (typeof p.art === "string") {
      if (!sceneKeys.includes(p.art)) fail(`pages[${i}].art "${p.art}" is not a known scene key`);
    } else {
      // Composable object art: names are validated against the real backgrounds/sprites/poses/fx.
      try {
        checkArt(p.art, `pages[${i}].art`);
      } catch (e) {
        if (e instanceof ArtError) fail(e.message);
        throw e;
      }
    }
  });
  return story;
}

/**
 * Optional story-level check for the authoring tools (not run by the app): consecutive pages whose art is
 * identical (a string key or an object, compared by value). Returns [{ page, same_as }] (0-based; `page`
 * repeats the art of `same_as = page - 1`). A repeat is not invalid; the tools report it for review.
 */
export function findRepeatedArt(story) {
  const out = [];
  story.pages.forEach((p, i) => {
    if (i > 0 && JSON.stringify(p.art) === JSON.stringify(story.pages[i - 1].art)) out.push({ page: i, same_as: i - 1 });
  });
  return out;
}

/** Validate stories/index.json: exactly { "v":1, "stories":[ids] } (docs/design.md). */
export function validateIndex(index, file = "stories/index.json") {
  if (index === null || typeof index !== "object" || Array.isArray(index) || index.v !== 1)
    throw new StoryError(`${file}: must be an object with "v": 1`);
  const ids = index.stories;
  if (!Array.isArray(ids) || ids.length === 0 || !ids.every(isStr))
    throw new StoryError(`${file}: must list story ids (a non-empty array of strings)`);
  return ids;
}

async function fetchJson(url) {
  let res;
  try {
    res = await fetch(url, { cache: "no-store" });
  } catch (e) {
    throw new StoryError(`${url}: could not fetch (${e.message})`);
  }
  if (!res.ok) throw new StoryError(`${url}: HTTP ${res.status}`);
  try {
    return await res.json();
  } catch (e) {
    throw new StoryError(`${url}: not valid JSON (${e.message})`);
  }
}

/** Load the ordered list of story ids. */
export async function loadIndex() {
  return validateIndex(await fetchJson("stories/index.json"));
}

/** Load and validate one story; its id must match the file name. */
export async function loadStory(id) {
  const file = `stories/${id}.json`;
  const story = validateStory(await fetchJson(file), file);
  if (story.id !== id) throw new StoryError(`${file}: "id" is "${story.id}" but the file is named "${id}"`);
  return story;
}
