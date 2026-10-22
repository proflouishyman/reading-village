// Letter swap-in: which lowercase letters replace small caps at a given percent. Pure; no randomness.
import { LETTERS, PARTNER } from "./rules.js";

/** Validate swap_order.json ({v:1, order:[26 unique a-z letters]}); throws naming the problem. */
export function validateSwapOrder(obj, file = "swap_order.json") {
  if (!obj || obj.v !== 1 || !Array.isArray(obj.order)) throw new Error(`${file}: must be {"v":1,"order":[...]}`);
  const { order } = obj;
  if (order.length !== 26) throw new Error(`${file}: order must have exactly 26 letters (has ${order.length})`);
  for (const l of order) if (typeof l !== "string" || !/^[a-z]$/.test(l)) throw new Error(`${file}: "${l}" is not a single letter a-z`);
  if (new Set(order).size !== 26) throw new Error(`${file}: order has duplicate letters`);
  return order;
}

/** The slider works in whole letters (0..26); the stored setting is a percent: round(n * 100 / 26). */
export const MAX_SWAP_LETTERS = 26;
export function percentForCount(n) {
  if (!Number.isInteger(n) || n < 0 || n > MAX_SWAP_LETTERS) throw new Error(`swap letter count must be an integer 0..26, got ${n}`);
  return Math.round((n * 100) / MAX_SWAP_LETTERS);
}

/** Letters in lowercase at a stored percent: round(26 * percent / 100). Inverse of percentForCount. */
export function swapCount(order, percent) {
  if (!Number.isInteger(percent) || percent < 0 || percent > 100) throw new Error(`lowercase_percent must be an integer 0..100, got ${percent}`);
  return Math.round((order.length * percent) / 100);
}

/** Letters currently shown as plain lowercase, in swap order. */
export function swappedLetters(order, percent) {
  return order.slice(0, swapCount(order, percent));
}

/** The next letter to come, or null at 100%. */
export function nextSwapLetter(order, percent) {
  return order[swapCount(order, percent)] ?? null;
}

/**
 * Mirror letters Bridge Match / Letter Mine may drill: an active letter is drilled only when BOTH it and
 * its partner (b/d, p/q, n/u, m/w) are swapped in, since each round offers the pair side by side.
 * Empty means those stages are skipped with a calm "Not yet" (a deliberate rule, docs/design.md).
 */
export function drillLetters(active, order, percent) {
  const swapped = new Set(swappedLetters(order, percent));
  return active.filter((l) => LETTERS.includes(l) && swapped.has(l) && swapped.has(PARTNER[l]));
}
