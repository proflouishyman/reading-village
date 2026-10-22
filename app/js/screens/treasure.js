// Treasure Pile: everything the child owns, with pictures and counts. He taps what to send; Send! plays the magical
// portal scene and only then says "Sent to your Magic Chest!" (after the server accepted the send). Unsent
// treasure stays in the pile forever; sent treasure shows "on the way" until the chest confirms, then "in your chest".
import { stageLayout } from "../layout.js";
import { spriteElement } from "../sprites.js";
import { h, setKid, showFatal } from "../ui.js";
import { getTreasure, postSend } from "../api.js";
import { loadProgress } from "../store.js";
import { playFanfare, playSparkle } from "../sounds.js";
import { mcStatusNode } from "../mcstatus.js";
import { STATIC } from "../runmode.js";
import { openBook } from "./book.js";
import { resolveSprite, validateTreasure, treasureCount, toggleSelection, pileSections, pileSignature } from "../villagelogic.js";
import { grownUp, grownUpPoss, childName } from "../family.js";

const POLL_MS = 4000;
const spr = (name, scale) => spriteElement(resolveSprite(name), scale);
const stateText = () => ({ on_the_way: "on the way", in_chest: "in your chest", failed: `${grownUp()} is checking` });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const countPiece = (t) => { const n = treasureCount(t); return n > 1 ? h("span", { class: "offer-n", text: `× ${n}` }) : null; };

/** A burst of little squares around `anchor` (decoration only: Math.random is fine here). */
function sparkles(anchor, n = 12) {
  const colors = ["#ffd23a", "#b6f0ff", "#e7b8ff", "#fff"];
  for (let i = 0; i < n; i++) {
    const s = h("span", { class: "sparkle" });
    s.style.background = colors[i % colors.length];
    anchor.append(s);
    const a = Math.random() * Math.PI * 2, d = 60 + Math.random() * 110;
    s.animate([{ transform: "translate(0,0) scale(1)", opacity: 1 }, { transform: `translate(${Math.cos(a) * d}px,${Math.sin(a) * d}px) scale(.2)`, opacity: 0 }],
      { duration: 700 + Math.random() * 400, easing: "ease-out" }).finished.then(() => s.remove());
  }
}

/**
 * Render the pile into L.play. `onBack` (optional) adds a Back button; `mc` (optional) is the Dad status node to
 * refresh after a send. Resolves once the first render is done; polling keeps states fresh while the pile is shown.
 */
export async function renderPile(app, L, onBack = null, mc = null) {
  let data = validateTreasure(await getTreasure());
  let selected = new Set();
  let sending = false;
  const dadNode = mc ?? (() => { const n = mcStatusNode(); L.dad.append(n); return n; })();

  const refresh = async () => {
    const fresh = validateTreasure(await getTreasure());
    const changed = pileSignature(fresh.treasure) !== pileSignature(data.treasure);
    data = fresh;
    if (changed && !sending) render();
  };
  let timer = null;
  const stopPolling = () => { clearInterval(timer); timer = null; };
  /** Re-read the states every few seconds while the pile is on screen ("on the way" becomes "in your chest"). */
  const startPolling = () => {
    stopPolling();
    timer = setInterval(() => {
      if (!L.play.isConnected || !L.play.querySelector(".pile")) { stopPolling(); return; }
      refresh().catch((e) => showFatal("Treasure Pile: could not refresh", e.message));
    }, POLL_MS);
  };

  function card(t) {
    const kept = t.state === "kept";
    const on = selected.has(t.tid);
    const el = h("button", { class: `treasure ${t.state}${on ? " chosen" : ""}`, "data-tid": t.tid, "aria-pressed": String(on),
      ...(kept ? { onclick: () => { selected = toggleSelection(selected, t); render(); } } : { "aria-disabled": "true" }) },
      h("div", { class: "offer-pic" }, spr(t.sprite, 5), countPiece(t)),
      h("div", { class: "offer-label", kid: t.label }),
      kept ? (on ? h("div", { class: "tag chosen-tag", kid: "✓ Chosen" }) : null) : h("div", { class: `tag ${t.state}-tag`, kid: stateText()[t.state] }));
    return el;
  }

  function render() {
    const { kept, sent } = pileSections(data.treasure);
    const chosen = kept.filter((t) => selected.has(t.tid));
    selected = new Set(chosen.map((t) => t.tid)); // forget anything that is no longer sendable
    const canSend = !STATIC && data.enabled && chosen.length > 0;
    L.setHint(STATIC ? `Sending to Minecraft happens at ${grownUpPoss()} house.` : data.enabled ? `${childName()} chooses what to send to the Magic Chest. Nothing is sent without a tap.` : "Sending is disabled in config/minecraft.json (enabled:false).");
    const sendBtn = h("button", { class: "btn huge send-btn", id: "send-btn", ...(canSend ? { onclick: () => send(chosen) } : { disabled: "" }) },
      spr("magic_portal", 3), h("span", { kid: "Send!" }));
    L.play.replaceChildren(h("div", { class: "pile" },
      h("div", { class: "pile-head" }, onBack ? h("button", { class: "btn small back-btn", kid: "◀ Back", onclick: () => { stopPolling(); onBack(); } }) : null,
        spr("chest", 5), h("div", { class: "shop-title", kid: "Treasure Pile" }),
        h("div", { class: "pile-count", id: "chosen-count", kid: kept.length ? `${chosen.length} chosen of ${kept.length}` : "" }),
        h("button", { class: "btn small", id: "book-btn", kid: "Treasure Book", onclick: () => { stopPolling(); openBook(L, () => { render(); startPolling(); }); } }),
        h("button", { class: "btn small", id: "choose-all", kid: "Choose all", onclick: () => { selected = new Set(kept.map((t) => t.tid)); render(); }, ...(kept.length ? {} : { disabled: "" }) }),
        h("button", { class: "btn small", id: "choose-none", kid: "Choose none", onclick: () => { selected = new Set(); render(); }, ...(chosen.length ? {} : { disabled: "" }) })),
      kept.length ? h("div", { class: "treasures", id: "kept-list" }, kept.map(card))
        : h("div", { class: "pile-empty", kid: data.treasure.length ? "Everything is sent! Read more to find more treasure." : "Your pile is empty. Read, craft and trade to find treasure!" }),
      kept.length ? sendBtn : null,
      STATIC ? h("div", { class: "static-note", id: "static-send-note", kid: `Sending to Minecraft happens at ${grownUpPoss()} house.` }) : null,
      sent.length ? h("div", { class: "sent-block" }, h("h2", { class: "sent-title", kid: "Already sent" }), h("div", { class: "treasures sent-list", id: "sent-list" }, sent.map(card))) : null));
  }

  /** The portal scene. The send is made first; items only fly in after the server has accepted it. */
  async function send(chosen) {
    if (sending) return; // a double-tap on Send! must be one request
    sending = true;
    stopPolling();
    const portal = h("div", { class: "portal" }, spr("magic_portal", 14));
    const line = h("div", { class: "lineup" }, chosen.map((t) => h("div", { class: "fly", "data-tid": t.tid }, spr(t.sprite, 6))));
    const msg = h("div", { class: "portal-msg", id: "portal-msg" });
    L.play.replaceChildren(h("div", { class: "portal-scene", id: "portal-scene" }, portal, line, msg));
    const request = postSend(chosen.map((t) => t.tid)).then((r) => ({ r }), (e) => ({ e }));
    portal.animate([{ transform: "scale(.2)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], { duration: 800, easing: "ease-out", fill: "both" });
    sparkles(portal, 10);
    await sleep(900);
    const res = await request;
    if (res.e) { showFatal("SEND FAILED: nothing was sent", res.e.message); return; }
    const from = portal.getBoundingClientRect();
    for (const el of line.children) {
      const b = el.getBoundingClientRect();
      const dx = from.left + from.width / 2 - (b.left + b.width / 2), dy = from.top + from.height / 2 - (b.top + b.height / 2);
      playSparkle(0);
      await el.animate([{ transform: "translate(0,0) scale(1) rotate(0)", opacity: 1 }, { transform: `translate(${dx}px,${dy}px) scale(.1) rotate(300deg)`, opacity: 0 }],
        { duration: 650, easing: "ease-in", fill: "forwards" }).finished;
      sparkles(portal, 8);
      await sleep(120);
    }
    playFanfare();
    playSparkle(0.9);
    portal.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 700, fill: "forwards" });
    msg.replaceChildren(spr("chest_open", 12), h("div", { class: "sent-msg", kid: "Sent to your Magic Chest!" }),
      h("button", { class: "btn big", id: "sent-done", kid: "Back to my pile", onclick: async () => {
        sending = false;
        await loadProgress(); // the server changed progress.treasure; keep the client's copy current
        data = validateTreasure(await getTreasure());
        selected = new Set();
        render();
        await dadNode.refresh();
        startPolling();
      } }));
    sparkles(msg, 24);
    dadNode.refresh();
  }

  render();
  startPolling();
}

/** Standalone Home tile: the pile on its own stage. Resolves "quit" when Dad/the child taps Home. */
export async function run(app) {
  const L = stageLayout(app.root, { title: "Treasure Pile", dadHint: "" });
  L.disableButtons();
  await renderPile(app, L);
  return L.quitted;
}
