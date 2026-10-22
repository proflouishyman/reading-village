// Build: spend earned blocks by placing them in the child and Dad's house grid.
import { stageLayout } from "../layout.js";
import { commitUntilSaved, SKIP } from "../store.js";
import { playThunk } from "../sounds.js";
import { spriteElement, drawSprite, drawSpriteFit } from "../sprites.js";
import { GRID_W, GRID_H, BUILD_BLOCKS, unlockedDecorations } from "../rules.js";
import { h, setKid } from "../ui.js";

const CELL = 64; // canvas pixels per grid cell

/** Draw the sky/grass scene plus every placed block. */
export function drawHouse(ctx, house) {
  ctx.imageSmoothingEnabled = false;
  const w = GRID_W * CELL, hgt = GRID_H * CELL;
  ctx.fillStyle = "#a8dcf6";
  ctx.fillRect(0, 0, w, hgt);
  ctx.fillStyle = "#c4e8fa";
  ctx.fillRect(0, 0, w, hgt * 0.45);
  ctx.fillStyle = "#5fb04a";
  ctx.fillRect(0, (GRID_H - 1) * CELL, w, CELL);
  ctx.fillStyle = "#3f8a33";
  ctx.fillRect(0, (GRID_H - 1) * CELL, w, 6);
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= GRID_W; x++) { ctx.beginPath(); ctx.moveTo(x * CELL + 0.5, 0); ctx.lineTo(x * CELL + 0.5, hgt); ctx.stroke(); }
  for (let y = 0; y <= GRID_H; y++) { ctx.beginPath(); ctx.moveTo(0, y * CELL + 0.5); ctx.lineTo(w, y * CELL + 0.5); ctx.stroke(); }
  for (const b of house) drawSpriteFit(ctx, b.block, b.x * CELL + 2, b.y * CELL + 2, CELL - 4, CELL - 4);
}

export async function run(app) {
  const L = stageLayout(app.root, { title: "Build our house", dadHint: "Pick a block, then tap a square. Blocks are only ever added." });
  L.disableButtons();
  const decorations = unlockedDecorations(app.store.progress);
  const kinds = [...BUILD_BLOCKS, ...decorations];
  let selected = kinds[0];

  const canvas = h("canvas", { class: "house-grid", width: GRID_W * CELL, height: GRID_H * CELL });
  const ctx = canvas.getContext("2d");
  const palette = h("div", { class: "palette" });
  const note = h("div", { class: "build-note" });

  /** Inventory item a block kind costs: wood/stone cost themselves, decorations cost an emerald. */
  const costOf = (k) => (BUILD_BLOCKS.includes(k) ? k : "emerald");
  const countOf = (k) => app.store.progress.inventory[costOf(k)];

  function renderPalette() {
    palette.replaceChildren(
      ...kinds.map((k) => h("button", {
        class: `btn pal${k === selected ? " sel" : ""}`,
        onclick: () => { selected = k; renderPalette(); },
      }, spriteElement(k, 3), h("span", { class: "pal-n", text: `× ${countOf(k)}` }))),
      h("div", { class: "pal-people" }, spriteElement("hero", 4), spriteElement("dad", 4)),
    );
    setKid(note, countOf(selected) > 0 ? "" : "Mine and read to earn more blocks!");
  }

  const redraw = () => drawHouse(ctx, app.store.progress.house);

  return new Promise((resolve) => {
    L.quitted.then(() => resolve("quit"));
    canvas.addEventListener("click", async (ev) => {
      const r = canvas.getBoundingClientRect();
      const x = Math.floor(((ev.clientX - r.left) / r.width) * GRID_W);
      const y = Math.floor(((ev.clientY - r.top) / r.height) * GRID_H);
      if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H) return; // a click exactly on the canvas edge
      const block = selected;
      // The occupied-cell / no-blocks checks run INSIDE the mutation, against the state it is applied to:
      // saves are queued, so a quick second click sees the first block and is ignored before anything is
      // logged or saved (a double-click can never place two blocks or log two block_placed events).
      const placed = await commitUntilSaved({ type: "block_placed", cell: [x, y], block }, (p) => {
        if (p.house.some((b) => b.x === x && b.y === y)) return SKIP;
        if (p.inventory[costOf(block)] < 1) return SKIP;
        p.inventory[costOf(block)] -= 1;
        p.house.push({ x, y, block });
      });
      if (placed) playThunk();
      redraw();
      renderPalette();
    });
    const done = h("button", { class: "btn big", kid: "All done building", onclick: () => resolve("done") });
    L.play.replaceChildren(h("div", { class: "build" }, h("div", { class: "build-side" }, palette, note), canvas), h("div", { class: "build-done" }, done));
    renderPalette();
    redraw();
  });
}
