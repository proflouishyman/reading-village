// Dad-only Minecraft delivery status (plain text; Dad bar, Dad corner, dashboard). Failures and problems are LOUD:
// a red banner, never a quiet line. the child never sees this.
import { getMinecraft } from "./api.js";
import { h } from "./ui.js";
import { STATIC } from "./runmode.js";

/**
 * Judge a GET /api/minecraft body. Returns {loud: bool, lines: [string]}: `loud` when something needs Dad
 * (a failed delivery, a problem, sends waiting with no worker running, or a worker/config that is off).
 */
export function judgeMinecraft(m) {
  const lines = [];
  let loud = false;
  const must = (k, t) => { if (typeof m[k] !== t) throw new Error(`/api/minecraft.${k} must be a ${t}`); };
  must("enabled", "boolean"); must("worker_running", "boolean"); must("server_running", "boolean");
  for (const k of ["pending", "failed", "recent"]) if (!Array.isArray(m[k])) throw new Error(`/api/minecraft.${k} must be an array`);
  if (!m.enabled) {
    // Static website copy: the offline backend says why in `problem` (there is no config/minecraft.json to point at).
    lines.push(STATIC && m.problem ? m.problem : "Minecraft delivery is OFF (config/minecraft.json enabled:false): nothing can be sent.");
    return { loud: m.pending.length > 0 || m.failed.length > 0, lines };
  }
  lines.push(m.server_running ? "Server: running" : "Server: NOT running (sends wait until it is up)");
  lines.push(`${m.pending.length} waiting to arrive, ${m.failed.length} failed`);
  if (m.failed.length) { loud = true; lines.unshift(`${m.failed.length} DELIVERY FAILED: ${m.failed.map((d) => `${d.id} "${d.label}": ${d.last_error}`).join(" | ")}`); }
  if (m.problem) { loud = true; lines.unshift(`PROBLEM: ${m.problem}`); }
  if (!m.worker_running) {
    lines.push("Delivery worker is NOT running (temp data dir or --minecraft-worker off).");
    if (m.pending.length) loud = true;
  }
  return { loud, lines };
}

/** A small element showing the status; `el.refresh()` re-fetches. A failed fetch is itself shown loudly. */
export function mcStatusNode() {
  const el = h("div", { class: "mc-status", "data-state": "loading" }, h("span", { text: "Minecraft: checking..." }));
  el.refresh = async () => {
    try {
      const { loud, lines } = judgeMinecraft(await getMinecraft());
      el.className = `mc-status${loud ? " mc-loud" : ""}`;
      el.dataset.state = loud ? "loud" : "ok";
      el.replaceChildren(h("b", { text: "Minecraft: " }), h("span", { text: lines.join(" · ") }));
    } catch (e) {
      el.className = "mc-status mc-loud";
      el.dataset.state = "loud";
      el.replaceChildren(h("b", { text: "MINECRAFT STATUS UNAVAILABLE: " }), h("span", { text: e.message }));
    }
  };
  el.refresh();
  return el;
}
