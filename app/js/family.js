// The family config: the ONE place a parent personalizes the game (canonical file: config/family.json). The server
// serves it at data/family.json and the website build copies it there. Contract (docs/personalizing.md):
//   {"v":1, "child":{"name"}, "village_name", "home_grown_up", "away_label"}  all required, all non-empty strings.
// Anything else (unknown key, wrong type, missing key) throws naming the field; nothing is ever defaulted.

const TOP = ["v", "child", "village_name", "home_grown_up", "away_label"];
const CHILD = ["name"];
const TEXT_FIELDS = ["village_name", "home_grown_up", "away_label"];

let current = null;

/** Validate a parsed family.json object and return it. `file` is only used in error messages. */
export function validateFamily(obj, file = "data/family.json") {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) throw new Error(`${file}: must be a JSON object`);
  for (const k of Object.keys(obj)) if (!TOP.includes(k)) throw new Error(`${file}: unknown key "${k}"`);
  if (obj.v !== 1) throw new Error(`${file}: "v" must be 1 (got ${JSON.stringify(obj.v)})`);
  const child = obj.child;
  if (child === undefined) throw new Error(`${file}: missing required key "child"`);
  if (!child || typeof child !== "object" || Array.isArray(child)) throw new Error(`${file}: "child" must be an object`);
  for (const k of Object.keys(child)) if (!CHILD.includes(k)) throw new Error(`${file}: unknown key "child.${k}"`);
  if (child.name === undefined) throw new Error(`${file}: missing required key "child.name"`);
  if (typeof child.name !== "string" || !child.name.trim()) throw new Error(`${file}: "child.name" must be a non-empty string`);
  for (const k of TEXT_FIELDS) {
    if (obj[k] === undefined) throw new Error(`${file}: missing required key "${k}"`);
    if (typeof obj[k] !== "string" || !obj[k].trim()) throw new Error(`${file}: "${k}" must be a non-empty string`);
  }
  return obj;
}

/** Fetch data/family.json relative to the page, validate it, and make it the app-wide family. */
export async function loadFamily() {
  const file = "data/family.json";
  let res;
  try {
    res = await fetch(file, { cache: "no-store" });
  } catch (e) {
    throw new Error(`${file}: could not fetch (${e.message})`);
  }
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`);
  let obj;
  try {
    obj = await res.json();
  } catch (e) {
    throw new Error(`${file}: not valid JSON (${e.message})`);
  }
  return setFamily(obj);
}

/** Validate and install `obj` as the app-wide family (tests call this directly). */
export function setFamily(obj) {
  current = validateFamily(obj);
  return current;
}

/** The loaded family. Throws if boot has not loaded it: user-visible text must never be built without it. */
export function fam() {
  if (!current) throw new Error("family.json has not been loaded yet (call loadFamily() at boot)");
  return current;
}

/** Child's first name. */
export const childName = () => fam().child.name;
/** Possessive form: "Sam's", "Jess'" (names ending in s). */
export const childPoss = () => { const n = childName(); return /s$/i.test(n) ? `${n}'` : `${n}'s`; };
/** Label of the grown-up corner ("Dad"). */
export const grownUp = () => fam().home_grown_up;
/** Possessive of the grown-up label. */
export const grownUpPoss = () => { const n = grownUp(); return /s$/i.test(n) ? `${n}'` : `${n}'s`; };
