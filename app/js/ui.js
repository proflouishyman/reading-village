// DOM helpers, generated textures, rewards animation, and the loud banners.
import { spriteElement, itemSprite } from "./sprites.js";
import { escapeHtml, toSmallCaps } from "./smallcaps.js";
import { STATIC } from "./runmode.js";

/**
 * THE one helper for text the child sees: replaces el's content with `text` in Arial small caps.
 * Everything child-facing goes through this (h's `kid` prop, or setKid for text that changes later);
 * Dad-only areas (.dad-bar, .dad-only, .dad-corner, banners, dashboard) use plain `text` instead.
 * tests/test_ui_smallcaps.py walks the DOM and fails on any a-z text outside those areas.
 */
export function setKid(el, text) {
  // One wrapper span: buttons are flex containers, and without it every letter span would become its own
  // flex item (spread out by the button's gap).
  el.innerHTML = `<span class="kid">${toSmallCaps(text)}</span>`;
  return el;
}

/** Create an element: h("div", {class:"x", html:"..", onclick:fn, text:"..", kid:".."}, ...children). */
export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "html") el.innerHTML = v;
    else if (k === "kid") setKid(el, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid);
  return el;
}

// --- Textures (generated, so the app needs no image files) -------------------
function texture(base, shades, seed) {
  const cv = document.createElement("canvas");
  cv.width = cv.height = 16;
  const ctx = cv.getContext("2d");
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, 16, 16);
  let s = seed;
  for (let i = 0; i < 46; i++) {
    s = (s * 1664525 + 1013904223) % 4294967296;
    ctx.fillStyle = shades[s % shades.length];
    ctx.fillRect((s >> 8) % 16, (s >> 16) % 16, 1 + (s % 2), 1);
  }
  return `url(${cv.toDataURL()})`;
}

/** Install dirt/stone/planks/grass textures as CSS variables on :root. */
export function installTextures() {
  const r = document.documentElement.style;
  r.setProperty("--tex-dirt", texture("#86582c", ["#6f4720", "#93632f", "#7a4d24"], 11));
  r.setProperty("--tex-stone", texture("#8a8a8a", ["#7a7a7a", "#999999", "#707070"], 23));
  r.setProperty("--tex-planks", texture("#c49a5c", ["#b08848", "#d2a96a", "#a47c3e"], 37));
  r.setProperty("--tex-grass", texture("#5fb04a", ["#4f9a3c", "#6dc058", "#438a32"], 41));
}

// --- Loud failure ----------------------------------------------------------
function overlayRoot() {
  return document.getElementById("overlay");
}

/** Full-screen unmissable banner; blocks the UI so nothing can be awarded. */
export function showSaveBanner(reason, onRetry) {
  const o = overlayRoot();
  o.replaceChildren(
    h("div", { class: "loud", role: "alert" },
      h("div", { class: "loud-title", text: `PROGRESS NOT SAVED — ${reason}` }),
      h("p", { text: STATIC
        ? "Nothing more will be awarded until this is fixed. Ask a grown-up to reload the page."
        : "Nothing more will be awarded until this is fixed. Is the server still running (python3 server.py)?" }),
      h("button", { class: "btn big", text: "Try saving again", onclick: onRetry })),
  );
  o.classList.add("show");
}

export function hideSaveBanner() {
  const o = overlayRoot();
  o.replaceChildren();
  o.classList.remove("show");
}

/**
 * One-off note for Dad (e.g. "sound could not start"): appended to the visible Dad bar / Dad corner, or the
 * Dad-only toast when neither is on screen. Never shown in the child's area.
 */
export function dadNote(text) {
  const note = h("span", { class: "dad-note", text });
  const host = document.querySelector(".dad-bar, .dad-corner");
  if (host) host.append(note);
  else document.getElementById("toast").replaceChildren(note);
}

/** Show a fatal, non-recoverable error loudly (story load failures, bugs). */
export function showFatal(title, detail) {
  const o = overlayRoot();
  o.replaceChildren(
    h("div", { class: "loud", role: "alert" },
      h("div", { class: "loud-title", text: title }),
      h("pre", { text: detail }),
      h("button", { class: "btn big", text: "Back to home", onclick: () => { location.href = "./"; } })),
  );
  o.classList.add("show");
}

// --- Cues and rewards ------------------------------------------------------
/** Cue markup: **x** -> bold, *x* -> italic (text is escaped first). */
export function cueHtml(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>");
}

/** Cue block for Dad to read aloud; letters b/d also get the bed picture. */
export function cueBox(letterCue) {
  const box = h("div", { class: "cue" }, h("div", { class: "cue-text", html: cueHtml(letterCue.cue) }));
  if (letterCue.picture === "bed") {
    box.append(h("div", { class: "cue-bed" },
      spriteElement("bed", 5),
      h("div", { class: "bed-word", html: "<b class='hb'>b</b>e<b class='hd'>d</b>" }),
      h("div", { class: "cue-note", html: cueHtml(letterCue.bedNote) })));
  }
  return box;
}

/** Gentle success animation: the ore sprite pops up out of `anchor` and settles. */
export function popReward(anchor, kind) {
  const pop = h("div", { class: "pop" }, spriteElement(kind, 6));
  anchor.append(pop);
  pop.addEventListener("animationend", () => pop.remove());
}

/** Row of inventory icons with counts. Coal/iron/gold/diamond/emerald show the ITEM icon (see itemSprite). */
export function inventoryRow(inv, kinds) {
  return h("div", { class: "inv" }, kinds.map((k) =>
    h("span", { class: "inv-item", title: k.toUpperCase() }, spriteElement(itemSprite(k), 3), h("span", { class: "inv-n", text: String(inv[k]) }))));
}

/** Switch the whole app between OpenDyslexic and the plain system font. */
export function applyFont(font) {
  document.documentElement.dataset.font = font;
}
