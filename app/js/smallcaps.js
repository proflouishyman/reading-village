// Small-caps rendering. Browsers synthesize font-variant: small-caps inconsistently,
// so every lowercase letter becomes an explicit capital span (.sc is 0.72em in CSS).

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape text for safe insertion as HTML. */
export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

/**
 * Convert plain text to an HTML string: a-z become <span class="sc">UPPER</span>;
 * capitals, digits and punctuation are unchanged (but HTML-escaped).
 */
export function toSmallCaps(text) {
  let out = "";
  for (const ch of String(text)) {
    out += ch >= "a" && ch <= "z" ? `<span class="sc">${ch.toUpperCase()}</span>` : escapeHtml(ch);
  }
  return out;
}

/**
 * Mixed text for the letter swap-in: letters in `lowercaseSet` (a Set of a-z) stay plain lowercase, every
 * other lowercase letter is small caps. Deterministic: a letter looks the same everywhere. Capitals stay.
 */
export function toMixedCase(text, lowercaseSet) {
  let out = "";
  for (const ch of String(text)) {
    out += ch >= "a" && ch <= "z" && !lowercaseSet.has(ch) ? `<span class="sc">${ch.toUpperCase()}</span>` : escapeHtml(ch);
  }
  return out;
}

/** Render one piece of text for a track: small caps, ordinary lowercase, or "mixed" (needs lowercaseSet). */
export function renderText(text, track, lowercaseSet) {
  if (track === "smallcaps") return toSmallCaps(text);
  if (track === "mixed") {
    if (!(lowercaseSet instanceof Set)) throw new Error("renderText: mixed needs a lowercaseSet");
    return toMixedCase(text, lowercaseSet);
  }
  if (track === "lowercase") return escapeHtml(text);
  throw new Error(`renderText: unknown track "${track}"`);
}

/** The word a token stands for: lowercased, punctuation stripped; the curly apostrophe counts as ' . */
export function cleanWord(token) {
  return token.toLowerCase().replace(/\u2019/g, "'").replace(/[^a-z']/g, "");
}

/**
 * Split a sentence into clickable word spans (for the "tricky word" tap).
 * Returns HTML; each word span (class "w") carries data-word with the cleaned word. A token with no
 * letter in it (a dash, "...", a lone quote) is shown but is not a word: class "t", not tappable.
 */
export function renderWords(text, track, lowercaseSet) {
  return text
    .split(/\s+/)
    .filter(Boolean)
    .map((tok) => {
      const word = cleanWord(tok);
      const html = renderText(tok, track, lowercaseSet);
      return /[a-z]/.test(word) ? `<span class="w" data-word="${escapeHtml(word)}">${html}</span>` : `<span class="t">${html}</span>`;
    })
    .join(" ");
}
