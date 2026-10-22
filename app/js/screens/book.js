// Treasure Book: everything the child has ever earned and sent, newest first, small caps, with pictures. It reads the
// server's append-only rewards history (GET /api/history); the bookkeeping kinds (spend, trade, failures) are Dad's
// and appear only on his dashboard. A long history is shown a page at a time.
import { spriteElement } from "../sprites.js";
import { h, showFatal } from "../ui.js";
import { getHistory, getTreasure } from "../api.js";
import { validateTreasure } from "../villagelogic.js";
import { validateHistory, newestFirst, bookRow, bookDate, BOOK_KINDS } from "../historylogic.js";
import { grownUp } from "../family.js";

export const PAGE = 60;

/** Render the book into L.play. `onBack` returns to the pile. Failures are shown loudly, never as an empty book. */
export async function renderBook(L, onBack) {
  const hist = validateHistory(await getHistory());
  // treasure lines carry no picture: take them from the pile by tid (the pile is archived by a reset: see pictureFor)
  const pile = new Map(validateTreasure(await getTreasure()).treasure.map((t) => [t.tid, { sprite: t.sprite, label: t.label }]));
  const lines = newestFirst(hist.lines).filter((l) => BOOK_KINDS.includes(l.kind));
  const rowsData = lines.map((l) => ({ l, r: bookRow(l, pile) }));
  const placeholders = rowsData.reduce((n, x) => n + x.r.placeholders, 0);
  let shown = PAGE;

  function row({ l, r }) {
    return h("div", { class: `book-row book-${l.kind}`, "data-kind": l.kind },
      h("div", { class: "book-date", kid: bookDate(l.ts) }),
      h("div", { class: "book-pics" }, r.sprites.map((s) => h("span", { class: "book-pic" }, spriteElement(s.name, 4), s.n ? h("span", { class: "offer-n", text: `× ${s.n}` }) : null))),
      h("div", { class: "book-text", kid: r.text }));
  }

  function render() {
    const rows = rowsData.slice(0, shown);
    L.play.replaceChildren(h("div", { class: "book" },
      h("div", { class: "pile-head" }, h("button", { class: "btn small back-btn", id: "book-back", kid: "◀ Back", onclick: onBack }),
        spriteElement("enchanted_book", 5), h("div", { class: "shop-title", kid: "Treasure Book" })),
      rows.length ? h("div", { class: "book-list", id: "book-list" }, rows.map(row))
        : h("div", { class: "pile-empty", id: "book-empty", kid: "Your book is empty. Read to find treasure!" }),
      placeholders ? h("div", { class: "dad-only book-note", id: "book-note", text: `${grownUp()}: ${placeholders} picture(s) here are a chest placeholder (their treasure is no longer in the pile, e.g. after a reset, and has no sprite of its own).` }) : null,
      rowsData.length > shown ? h("button", { class: "btn big", id: "book-more", kid: "Show more", onclick: () => { shown += PAGE; render(); } }) : null));
  }
  render();
}

/** Open the book on `L`; any failure is shown loudly and the pile stays reachable via `onBack`. */
export async function openBook(L, onBack) {
  try { await renderBook(L, onBack); } catch (e) { showFatal("Treasure Book failed", e instanceof Error ? e.message : String(e)); }
}
