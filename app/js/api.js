// Thin fetch wrappers for the server API. Every failure throws ApiError with a reason
// suitable for the "PROGRESS NOT SAVED" banner; nothing is swallowed or defaulted.
// In STATIC mode (runmode.js) the same calls are answered by offline.js instead of fetch.

import { ApiError } from "./apierror.js";
import { STATIC } from "./runmode.js";
import { offlineBackend } from "./offline.js";

export { ApiError };

async function call(method, path, body) {
  // Static website copy (docs/away-from-home.md §1): nothing reaches the network; the in-browser backend answers with
  // the same reply shapes and throws ApiError just like a failed server call.
  if (STATIC) return (await offlineBackend()).request(method, path, body);
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (e) {
    throw new ApiError(`server not reachable (${e.message})`);
  }
  let payload = null;
  try {
    payload = await res.json();
  } catch {
    // Non-JSON body: reported below using the HTTP status.
  }
  if (!res.ok) {
    const detail = payload && payload.error ? payload.error : "no details";
    throw new ApiError(`server said HTTP ${res.status}: ${detail}`, res.status);
  }
  if (payload === null) throw new ApiError(`${method} ${path}: server returned a non-JSON response`);
  return payload;
}

export const getProgress = () => call("GET", "/api/progress");
/** `cause` (optional) = the full event this save belongs to; the server records it as the provenance of the earn/spend
 *  history lines (progress is saved BEFORE its event is posted, so it cannot infer it). It is never stored in progress. */
export const putProgress = (p, cause) => call("PUT", "/api/progress", cause ? { ...p, cause } : p);
export const postEvent = (e) => call("POST", "/api/event", e);
export const getEvents = () => call("GET", "/api/events");

// Village, shop, treasure and Minecraft status (docs/design.md "Villager shop and Magic Chest").
export const getVillage = () => call("GET", "/api/village");
export const postUnlock = (profession, pay) => call("POST", "/api/village/unlock", { profession, pay });
export const postPromote = (profession) => call("POST", "/api/village/promote", { profession });
export const postBuy = (offer_id) => call("POST", "/api/shop/buy", { offer_id });
export const postTrade = (trade_id) => call("POST", "/api/shop/trade", { trade_id });
export const getTreasure = () => call("GET", "/api/treasure");
export const postSend = (tids) => call("POST", "/api/treasure/send", { tids });
export const getMinecraft = () => call("GET", "/api/minecraft");

// Rewards history (append-only data/rewards_history.jsonl, oldest first). `kind` optionally filters on the server.
export const getHistory = (kind) => call("GET", kind ? `/api/history?kind=${encodeURIComponent(kind)}` : "/api/history");
export const HISTORY_CSV_URL = "/api/history.csv";
