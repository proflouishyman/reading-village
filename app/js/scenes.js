// Story scenes: each key composes sprites over a simple procedural background on a
// 192x108 logical canvas (scaled up with image-rendering: pixelated).
import { drawSprite, spriteSize, spriteCanvas, SPRITE_NAMES, SPRITES, PALETTE } from "./sprites.js";

export const SCENE_W = 192;
export const SCENE_H = 108;

// --- tiny drawing helpers ---------------------------------------------------
const rect = (ctx, c, x, y, w, h) => { ctx.fillStyle = c; ctx.fillRect(x, y, w, h); };

/** Banded sky (cheap pixel-art gradient). */
function sky(ctx, colours, h = SCENE_H) {
  const band = Math.ceil(h / colours.length);
  colours.forEach((c, i) => rect(ctx, c, 0, i * band, SCENE_W, band));
}

/** Ground strip with a grass top at y. */
function ground(ctx, y, top = "#5fb04a", dirt = "#8b5a2b") {
  rect(ctx, top, 0, y, SCENE_W, 5);
  rect(ctx, "#3f8a33", 0, y + 5, SCENE_W, 2);
  rect(ctx, dirt, 0, y + 7, SCENE_W, SCENE_H - y - 7);
  for (let x = 3; x < SCENE_W; x += 11) rect(ctx, "#5f3b1a", x, y + 10 + ((x * 7) % 14), 3, 2);
}

/** Stone cave wall filling the canvas, with deterministic speckles. */
function caveWall(ctx, base = "#6e6e6e", speck = "#5c5c5c") {
  rect(ctx, base, 0, 0, SCENE_W, SCENE_H);
  for (let i = 0; i < 160; i++) rect(ctx, i % 3 ? speck : "#7e7e7e", (i * 37) % SCENE_W, (i * 53) % SCENE_H, 3, 2);
}

function caveFloor(ctx, y) {
  rect(ctx, "#4a4a4a", 0, y, SCENE_W, SCENE_H - y);
  rect(ctx, "#5c5c5c", 0, y, SCENE_W, 2);
}

/** Draw a sprite standing with its feet at (cx, footY). */
function stand(ctx, name, cx, footY, scale = 4, swap) {
  const { w, h } = spriteSize(name);
  drawSprite(ctx, name, cx - (w * scale) / 2, footY - h * scale, scale, swap);
}

/** Soft glow: concentric translucent discs. */
function glow(ctx, cx, cy, r, colour = "255,200,80") {
  for (let i = 4; i >= 1; i--) {
    ctx.fillStyle = `rgba(${colour},${0.1 * (5 - i)})`;
    const rr = (r * i) / 4;
    ctx.fillRect(Math.round(cx - rr), Math.round(cy - rr / 2), Math.round(rr * 2), Math.round(rr));
    ctx.fillRect(Math.round(cx - rr / 2), Math.round(cy - rr), Math.round(rr), Math.round(rr * 2));
  }
}

function stars(ctx, n = 40, maxY = 70) {
  for (let i = 0; i < n; i++) rect(ctx, i % 4 ? "#cfd8ff" : "#ffffff", (i * 71) % SCENE_W, (i * 29) % maxY, 1, 1);
}

function darkness(ctx, alpha) {
  ctx.fillStyle = `rgba(5,5,15,${alpha})`;
  ctx.fillRect(0, 0, SCENE_W, SCENE_H);
}

function sparkles(ctx, cx, cy, spread = 26) {
  [[-1, -1], [1, -1], [-1, 1], [1, 1], [0, -2], [2, 0], [-2, 0]].forEach(([dx, dy], i) => {
    const x = cx + dx * (spread / 2), y = cy + dy * (spread / 3);
    rect(ctx, i % 2 ? "#ffffff" : "#f5d33a", x, y - 2, 1, 5);
    rect(ctx, i % 2 ? "#ffffff" : "#f5d33a", x - 2, y, 5, 1);
  });
}

function line(ctx, c, x0, y0, x1, y1) {
  const n = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
  for (let i = 0; i <= n; i++) rect(ctx, c, Math.round(x0 + ((x1 - x0) * i) / n), Math.round(y0 + ((y1 - y0) * i) / n), 1, 1);
}

function water(ctx, y, h) {
  rect(ctx, "#3d8be0", 0, y, SCENE_W, h);
  for (let yy = y + 3; yy < y + h; yy += 7)
    for (let x = (yy * 5) % 17; x < SCENE_W; x += 17) rect(ctx, "#8fc4f5", x, yy, 6, 1);
}

function hill(ctx, cx, topY, halfW) {
  for (let y = topY; y < SCENE_H; y++) {
    const half = Math.min(halfW, Math.round(halfW * Math.sqrt(Math.max(0, (y - topY) / 40))));
    rect(ctx, y - topY < 3 ? "#7ad063" : "#5fb04a", cx - half, y, half * 2, 1);
  }
}

// --- scenes -----------------------------------------------------------------
const DAY = ["#7ec8f0", "#8fd0f4", "#a2d8f6", "#b6e0f8"];

export const SCENES = {
  title(ctx) {
    sky(ctx, DAY, 70);
    drawSprite(ctx, "sun", 150, 10, 3);
    drawSprite(ctx, "cloud", 20, 14, 2);
    drawSprite(ctx, "cloud", 90, 30, 2);
    ground(ctx, 72);
    stand(ctx, "tree", 20, 74, 4);
    stand(ctx, "hero", 70, 92, 4);
    stand(ctx, "dad", 110, 92, 4);
    stand(ctx, "pig", 152, 94, 3, { p: "y", P: "Y" });
  },
  map(ctx) {
    rect(ctx, "#8b5a2b", 0, 0, SCENE_W, SCENE_H);
    rect(ctx, "#e8d3a0", 10, 8, 172, 92);
    rect(ctx, "#d6bd84", 10, 8, 172, 3);
    rect(ctx, "#d6bd84", 10, 97, 172, 3);
    for (const [x, y] of [[26, 70], [38, 74], [150, 28]]) drawSprite(ctx, "tree", x, y - 28, 2);
    for (let i = 0; i < 12; i++) rect(ctx, "#8f2420", 34 + i * 10, 74 - Math.round(Math.sin(i / 2) * 14) - i * 2, 4, 4);
    line(ctx, "#d8403a", 140, 24, 156, 40);
    line(ctx, "#d8403a", 156, 24, 140, 40);
    line(ctx, "#d8403a", 141, 24, 157, 40);
    line(ctx, "#d8403a", 157, 24, 141, 40);
    stand(ctx, "hero", 30, 96, 2);
  },
  hill(ctx) {
    sky(ctx, DAY);
    drawSprite(ctx, "sun", 20, 10, 2);
    hill(ctx, 100, 40, 120);
    stand(ctx, "tree", 40, 78, 3);
    stand(ctx, "hero", 100, 52, 3);
    drawSprite(ctx, "cloud", 120, 14, 2);
  },
  cave(ctx) {
    sky(ctx, DAY, 60);
    caveWall(ctx);
    rect(ctx, "#0e0e12", 62, 22, 68, 86);
    rect(ctx, "#0e0e12", 70, 14, 52, 8);
    ground(ctx, 96);
    stand(ctx, "hero", 30, 98, 4);
    drawSprite(ctx, "coal", 150, 60, 2);
    drawSprite(ctx, "iron", 170, 76, 2);
    stand(ctx, "torch", 56, 70, 3);
  },
  dark(ctx) {
    rect(ctx, "#05050a", 0, 0, SCENE_W, SCENE_H);
    stand(ctx, "hero", 96, 100, 4);
    darkness(ctx, 0.55);
    for (const [x, y] of [[30, 30], [150, 40], [40, 80], [160, 76]]) {
      rect(ctx, "#f4f4f4", x, y, 3, 3);
      rect(ctx, "#f4f4f4", x + 8, y, 3, 3);
    }
  },
  torch(ctx) {
    caveWall(ctx, "#4a4a4a", "#3c3c3c");
    caveFloor(ctx, 92);
    glow(ctx, 126, 50, 70);
    stand(ctx, "torch", 126, 80, 6);
    stand(ctx, "hero", 70, 98, 4);
    drawSprite(ctx, "diamond", 20, 20, 2);
  },
  bat(ctx) {
    caveWall(ctx);
    caveFloor(ctx, 92);
    stand(ctx, "hero", 60, 98, 4);
    stand(ctx, "dad", 108, 98, 4);
    drawSprite(ctx, "bat", 22, 6, 4);
    drawSprite(ctx, "bat", 150, 30, 3);
    stand(ctx, "torch", 20, 70, 3);
  },
  creeper(ctx) {
    caveWall(ctx);
    caveFloor(ctx, 92);
    stand(ctx, "creeper", 130, 98, 5);
    stand(ctx, "hero", 36, 98, 4);
    stand(ctx, "dad", 72, 98, 4);
  },
  run(ctx) {
    caveWall(ctx);
    caveFloor(ctx, 92);
    for (let i = 0; i < 5; i++) rect(ctx, "#8a8a8a", 10 + i * 14, 40 + i * 9, 20, 1);
    stand(ctx, "creeper", 28, 96, 3);
    stand(ctx, "hero", 98, 94, 4);
    stand(ctx, "dad", 144, 98, 4);
  },
  boom(ctx) {
    caveWall(ctx, "#3a3a3a", "#2c2c2c");
    caveFloor(ctx, 92);
    glow(ctx, 96, 56, 90, "255,180,60");
    const rays = [[0, -30], [30, -20], [34, 8], [0, 30], [-34, 8], [-30, -20], [18, -34], [-18, 34], [-40, -4], [40, -4]];
    rays.forEach(([dx, dy], i) => rect(ctx, i % 2 ? "#ffd23a" : "#ff8c1a", 96 + dx - 6, 56 + dy - 6, 12, 12));
    rect(ctx, "#ffffff", 84, 44, 24, 24);
    rect(ctx, "#ffd23a", 90, 50, 12, 12);
    [[30, 20], [150, 24], [164, 70], [24, 66]].forEach(([x, y]) => drawSprite(ctx, "stone", x, y, 1));
    stand(ctx, "hero", 30, 100, 3);
    stand(ctx, "dad", 162, 100, 3);
  },
  pool(ctx) {
    caveWall(ctx);
    caveFloor(ctx, 94);
    water(ctx, 66, 28);
    stand(ctx, "hero", 36, 94, 4);
    drawSprite(ctx, "gold", 150, 30, 2);
    stand(ctx, "torch", 92, 40, 3);
  },
  wall(ctx) {
    caveFloor(ctx, 94);
    for (let y = 0; y < 94; y += 12) for (let x = 0; x < SCENE_W; x += 12) drawSprite(ctx, "stone", x, y, 1);
    darkness(ctx, 0.25);
    stand(ctx, "hero", 60, 100, 4);
    stand(ctx, "dad", 110, 100, 4);
    stand(ctx, "torch", 150, 80, 3);
  },
  chest(ctx) {
    caveWall(ctx, "#4a4a4a", "#3c3c3c");
    caveFloor(ctx, 88);
    glow(ctx, 120, 70, 60);
    stand(ctx, "chest", 120, 92, 6);
    sparkles(ctx, 120, 44);
    stand(ctx, "hero", 50, 98, 4);
  },
  hat(ctx) {
    caveWall(ctx, "#4a4a4a", "#3c3c3c");
    caveFloor(ctx, 92);
    glow(ctx, 96, 40, 60);
    drawSprite(ctx, "crown", 66, 22, 6);
    sparkles(ctx, 96, 36, 60);
    stand(ctx, "hero", 50, 100, 4);
    stand(ctx, "chest", 146, 96, 4);
  },
  king(ctx) {
    sky(ctx, ["#2b2250", "#3a2e66", "#4b3b7a", "#5a4890"], 68);
    ground(ctx, 70, "#6a6a6a", "#4a4a4a");
    for (let i = 0; i < 4; i++) drawSprite(ctx, "gold", 78 + (i % 2) * 24, 58 - Math.floor(i / 2) * 12, 2);
    stand(ctx, "pig", 102, 52, 4, { p: "y", P: "Y" });
    drawSprite(ctx, "crown", 92, 14, 3);
    stand(ctx, "hero", 36, 100, 4);
    stand(ctx, "dad", 160, 100, 4);
  },
  rock(ctx) {
    sky(ctx, DAY, 70);
    ground(ctx, 72);
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4 - i; j++) drawSprite(ctx, "stone", 108 + j * 12 + i * 6, 60 - i * 12, 1);
    for (let j = 0; j < 4; j++) drawSprite(ctx, "stone", 108 + j * 12, 60, 1);
    stand(ctx, "hero", 76, 94, 4);
    stand(ctx, "dad", 30, 94, 4);
  },
  bed(ctx) {
    rect(ctx, "#8b5a2b", 0, 0, SCENE_W, 90);
    for (let x = 0; x < SCENE_W; x += 16) rect(ctx, "#7a4d24", x, 0, 1, 90);
    rect(ctx, "#2b2250", 130, 14, 44, 36);
    rect(ctx, "#4a3a2a", 126, 10, 52, 4);
    rect(ctx, "#4a3a2a", 126, 50, 52, 4);
    rect(ctx, "#4a3a2a", 126, 10, 4, 44);
    rect(ctx, "#4a3a2a", 174, 10, 4, 44);
    rect(ctx, "#4a3a2a", 150, 10, 3, 44);
    drawSprite(ctx, "moon", 134, 18, 2);
    rect(ctx, "#fff", 160, 24, 2, 2);
    rect(ctx, "#6a4a2a", 0, 90, SCENE_W, 18);
    drawSprite(ctx, "bed", 30, 54, 6);
    stand(ctx, "hero", 164, 100, 3);
  },
  dig(ctx) {
    sky(ctx, DAY, 40);
    ground(ctx, 40);
    for (let y = 47; y < 108; y += 12) for (let x = 0; x < SCENE_W; x += 12) drawSprite(ctx, (x + y) % 5 ? "dirt" : "stone", x, y, 1);
    rect(ctx, "#2a1c10", 88, 47, 36, 61);
    stand(ctx, "hero", 60, 47, 4);
    drawSprite(ctx, "pickaxe", 74, 22, 3);
    drawSprite(ctx, "gold", 140, 78, 1);
  },
  pup(ctx) {
    sky(ctx, DAY, 70);
    ground(ctx, 72);
    stand(ctx, "tree", 24, 74, 4);
    stand(ctx, "hero", 70, 94, 4);
    stand(ctx, "pup", 130, 96, 5);
    rect(ctx, "#f5a3b8", 120, 52, 3, 3); // a small heart for the pup
    rect(ctx, "#f5a3b8", 124, 52, 3, 3);
    rect(ctx, "#f5a3b8", 120, 55, 7, 2);
  },
  web(ctx) {
    caveWall(ctx);
    caveFloor(ctx, 92);
    for (const a of [0, 18, 36, 54, 72, 90]) line(ctx, "#f4f4f4", 192, 0, Math.round(192 - 100 * Math.sin((a * Math.PI) / 180)), Math.round(100 * Math.cos((a * Math.PI) / 180)));
    for (const r of [24, 46, 68, 90]) for (let a = 0; a <= 90; a += 4) rect(ctx, "#cfcfcf", Math.round(192 - r * Math.sin((a * Math.PI) / 180)), Math.round(r * Math.cos((a * Math.PI) / 180)), 1, 1);
    stand(ctx, "hero", 60, 100, 4);
    stand(ctx, "dad", 100, 100, 4);
    stand(ctx, "torch", 20, 74, 3);
  },
  sun(ctx) {
    sky(ctx, ["#ffd9a0", "#ffe3b0", "#ffeec4", "#fff6d8"], 70);
    drawSprite(ctx, "sun", 140, 22, 3);
    hill(ctx, 40, 54, 70);
    hill(ctx, 160, 60, 70);
    ground(ctx, 82);
    stand(ctx, "hero", 80, 100, 4);
    stand(ctx, "dad", 116, 100, 4);
  },
  night(ctx) {
    sky(ctx, ["#0b0d2a", "#10143a", "#161c4a", "#1c2458"], 78);
    stars(ctx);
    drawSprite(ctx, "moon", 150, 12, 3);
    ground(ctx, 78, "#2f6a2a", "#4a3015");
    glow(ctx, 96, 90, 40);
    stand(ctx, "torch", 96, 98, 4);
    stand(ctx, "hero", 56, 104, 4);
    stand(ctx, "dad", 136, 104, 4);
  },
  boat(ctx) {
    sky(ctx, DAY, 50);
    water(ctx, 50, 58);
    drawSprite(ctx, "cloud", 120, 12, 2);
    drawSprite(ctx, "boat", 52, 44, 5);
    stand(ctx, "hero", 76, 68, 3);
    stand(ctx, "dad", 100, 68, 3);
  },
  river(ctx) {
    sky(ctx, DAY, 40);
    ground(ctx, 40);
    water(ctx, 56, 24);
    ground(ctx, 82);
    stand(ctx, "hero", 40, 54, 3);
    stand(ctx, "dad", 80, 54, 3);
    stand(ctx, "tree", 160, 52, 3);
    stand(ctx, "pig", 140, 100, 3);
  },
  house(ctx) {
    sky(ctx, DAY, 72);
    ground(ctx, 72);
    for (let r = 0; r < 4; r++) for (let c = 0; c < 6; c++) drawSprite(ctx, (r + c) % 3 ? "wood" : "stone", 60 + c * 12, 28 + r * 12, 1);
    for (let i = 0; i < 4; i++) rect(ctx, "#8f2420", 54 + i * 6, 22 + i * 0, 84 - i * 12, 6); // roof band
    rect(ctx, "#8f2420", 54, 22, 84, 6);
    rect(ctx, "#8f2420", 66, 16, 60, 6);
    rect(ctx, "#8f2420", 78, 10, 36, 6);
    drawSprite(ctx, "door", 90, 52, 1);
    stand(ctx, "torch", 82, 62, 2);
    stand(ctx, "torch", 112, 62, 2);
    stand(ctx, "hero", 30, 96, 4);
    stand(ctx, "dad", 166, 96, 4);
    stand(ctx, "pig", 100, 98, 2);
  },
  hen(ctx) {
    sky(ctx, DAY, 70);
    drawSprite(ctx, "cloud", 20, 12, 2);
    ground(ctx, 72);
    for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) drawSprite(ctx, (r + c) % 3 ? "wood" : "stone", 120 + c * 12, 40 + r * 12, 1);
    rect(ctx, "#8f2420", 114, 34, 72, 6); // hut roof
    rect(ctx, "#8f2420", 126, 28, 48, 6);
    drawSprite(ctx, "door", 144, 60, 1);
    stand(ctx, "hero", 24, 94, 4);
    stand(ctx, "hen", 80, 96, 4);
  },
  fox(ctx) {
    sky(ctx, DAY);
    drawSprite(ctx, "sun", 20, 10, 2);
    hill(ctx, 100, 40, 120);
    rect(ctx, "#5f3b1a", 84, 62, 52, 14); // log, with an end ring on the left
    rect(ctx, "#8b5a2b", 86, 64, 48, 10);
    rect(ctx, "#c89a5a", 80, 62, 8, 14);
    rect(ctx, "#9a6b33", 82, 65, 4, 8);
    stand(ctx, "fox", 112, 62, 4);
    rect(ctx, "#c89a5a", 147, 31, 9, 7); // the bun, held in the fox's mouth
    rect(ctx, "#9a6b33", 147, 31, 9, 2);
    stand(ctx, "dad", 40, 100, 4);
    for (let d = 0; d < 3; d++) line(ctx, "#f1c27d", 60, 78 + d, 84, 62 + d); // Dad's arm, pointing at the fox
  },
  duck(ctx) {
    sky(ctx, DAY);
    drawSprite(ctx, "sun", 150, 8, 2);
    drawSprite(ctx, "cloud", 20, 14, 2);
    hill(ctx, 96, 50, 130);
    rect(ctx, "#6e6e6e", 62, 62, 68, 4); // bathtub rim
    stand(ctx, "duck", 98, 80, 4);
    rect(ctx, "#f4f4f4", 64, 66, 64, 20); // tub front hides the duck's feet
    rect(ctx, "#cfcfcf", 64, 82, 64, 4);
    rect(ctx, "#3d8be0", 64, 66, 64, 3); // bath water
    rect(ctx, "#6e6e6e", 70, 86, 6, 6);
    rect(ctx, "#6e6e6e", 116, 86, 6, 6);
  },
  fish(ctx) {
    sky(ctx, DAY, 50);
    water(ctx, 50, 58);
    drawSprite(ctx, "boat", 28, 44, 5);
    stand(ctx, "hero", 52, 68, 3);
    stand(ctx, "dad", 76, 68, 3);
    for (let d = 0; d < 2; d++) line(ctx, "#5f3b1a", 88 + d, 50, 120 + d, 8); // Dad's rod
    line(ctx, "#f4f4f4", 120, 8, 176, 34); // the line, ending at the fish's mouth
    drawSprite(ctx, "fish", 124, 22, 3);
    drawSprite(ctx, "stink", 132, 0, 3);
    drawSprite(ctx, "stink", 160, 2, 3);
  },
  end(ctx) {
    sky(ctx, ["#ffb27a", "#ffc58a", "#ffd79c", "#ffe6b4"], 76);
    drawSprite(ctx, "sun", 90, 44, 2);
    ground(ctx, 76);
    sparkles(ctx, 96, 30, 120);
    stand(ctx, "hero", 60, 100, 4);
    stand(ctx, "dad", 96, 100, 4);
    stand(ctx, "pig", 132, 100, 3, { p: "y", P: "Y" });
    stand(ctx, "pup", 160, 100, 3);
  },
};

/** Every scene key a story page may use. */
export const SCENE_KEYS = Object.keys(SCENES);

// =============================================================================
// Composable page art (docs/design.md "Stories"). A page's `art` is either a scene key (string, above)
// or an object { bg, actors?, props?, fx? } composed here. All coordinates are logical (192x108); an
// "x" of 0-100 is a percentage of the width, so it means the same thing at any canvas size.
// =============================================================================

/** Error for a bad art object; the message starts with the field path (e.g. `pages[2].art.fx ...`). */
export class ArtError extends Error {}

/**
 * Backgrounds. `ground` is the y where standing things put their feet; `water` (optional) is the water
 * surface y, needed by props with y "water". Each draw reuses the helpers above.
 */
export const BGS = {
  grass: { ground: 94, draw(ctx) { sky(ctx, DAY, 70); drawSprite(ctx, "cloud", 20, 14, 2); ground(ctx, 72); } },
  hill: { ground: 98, draw(ctx) { sky(ctx, DAY); drawSprite(ctx, "sun", 20, 10, 2); hill(ctx, 100, 40, 120); } },
  cave: { ground: 98, draw(ctx) { caveWall(ctx); caveFloor(ctx, 92); } },
  dark_cave: { ground: 98, draw(ctx) { caveWall(ctx, "#2c2c2c", "#222222"); caveFloor(ctx, 92); darkness(ctx, 0.55); } },
  night: { ground: 104, draw(ctx) {
    sky(ctx, ["#0b0d2a", "#10143a", "#161c4a", "#1c2458"], 78); stars(ctx);
    drawSprite(ctx, "moon", 150, 12, 3); ground(ctx, 78, "#2f6a2a", "#4a3015"); } },
  river: { ground: 100, water: 68, draw(ctx) { sky(ctx, DAY, 40); ground(ctx, 40); water(ctx, 56, 24); ground(ctx, 82); } },
  sea: { ground: 70, water: 56, draw(ctx) { sky(ctx, DAY, 50); water(ctx, 50, 58); drawSprite(ctx, "cloud", 120, 12, 2); } },
  inside_house: { ground: 100, draw(ctx) {
    rect(ctx, "#8b5a2b", 0, 0, SCENE_W, 90);
    for (let x = 0; x < SCENE_W; x += 16) rect(ctx, "#7a4d24", x, 0, 1, 90);
    rect(ctx, "#6a4a2a", 0, 90, SCENE_W, 18); rect(ctx, "#4a3320", 0, 90, SCENE_W, 2); } },
  sandpit: { ground: 98, draw(ctx) {
    sky(ctx, DAY, 70); ground(ctx, 72);
    rect(ctx, "#e2c98a", 20, 76, 152, 30); rect(ctx, "#c8ad6c", 20, 76, 152, 2);
    for (let x = 26; x < 170; x += 13) rect(ctx, "#c8ad6c", x, 84 + ((x * 3) % 16), 3, 1); } },
  hilltop: { ground: 66, draw(ctx) {
    sky(ctx, DAY, 56); drawSprite(ctx, "cloud", 130, 12, 2); hill(ctx, 30, 44, 50); hill(ctx, 170, 48, 50); ground(ctx, 60); } },
  sunset: { ground: 100, draw(ctx) {
    sky(ctx, ["#ff9a62", "#ffb27a", "#ffc58a", "#ffd79c"], 76); drawSprite(ctx, "sun", 90, 46, 2); ground(ctx, 76, "#5a8a3a", "#6a4020"); } },
  pond: { ground: 100, water: 72, draw(ctx) {
    sky(ctx, DAY, 60); ground(ctx, 60); rect(ctx, "#e2c98a", 32, 66, 128, 22); water(ctx, 68, 18);
    ground(ctx, 88); } },
  // open sky for flying scenes: no ground band, ground level at the very bottom so riders can be drawn big
  sky: { ground: 106, draw(ctx) {
    sky(ctx, ["#5fb4ee", "#7ec8f0", "#9ad4f4", "#b6e0f8", "#d2ecfa"]);
    drawSprite(ctx, "cloud", 14, 10, 2); drawSprite(ctx, "cloud", 128, 22, 2); drawSprite(ctx, "cloud", 96, 80, 2); } },
  wall: { ground: 100, draw(ctx) {
    caveFloor(ctx, 94);
    for (let y = 0; y < 94; y += 12) for (let x = 0; x < SCENE_W; x += 12) drawSprite(ctx, "stone", x, y, 1);
    darkness(ctx, 0.25); } },
};
export const BG_NAMES = Object.keys(BGS);

export const POSES = ["stand", "run", "jump", "sit", "fall", "upside_down", "hug", "hide", "sleep",
  "lying", "up", "in", "sit_on", "dig"];
export const FX_NAMES = ["boom", "splash", "sneeze", "hiss", "sparkle", "mud_splat", "zzz", "stink", "tap", "text"];
export const PROP_YS = ["ground", "air", "water", "held", "head", "on"];
export const TEXT_STYLES = ["burst", "say"];
export const TEXT_SIDES = ["above", "left", "right"];
// Poses in which an actor's head is upright enough for a "head" prop to sit on it.
const HEAD_POSES = ["stand", "run", "jump", "sit", "hug", "hide", "dig", "up", "in", "sit_on"];
// Where the head is on a sprite whose head is not centred at the top: dx = head centre as a fraction of the
// width right of centre (mirrored by flip), row = sprite row of the top of the head. Default {0, 0}.
const HEAD = { pig: { dx: 0.32, row: 3 }, pup: { dx: 0.25, row: 0 }, hen: { dx: 0.31, row: 0 },
  fox: { dx: 0.32, row: 0 }, duck: { dx: 0.22, row: 0 } };
// The hand at the end of the arm that faces the viewer (sprite column/row, actor facing right) and its skin
// colour. Animals have no hands: they hold things at the front edge at 45% height (no skin patch).
const HANDS = { hero: { col: 9, row: 10, skin: "#f6d3b8" }, dad: { col: 9, row: 13, skin: "#f6d3b8" },
  mama: { col: 9, row: 11, skin: "#f6d3b8" }, pirate: { col: 9, row: 12, skin: "#f6d3b8" },
  witch: { col: 9, row: 13, skin: "#f6d3b8" } };

const ART_KEYS = ["bg", "actors", "props", "fx"];
const ACTOR_KEYS = ["who", "x", "pose", "flip", "scale", "id", "in", "on"];
const PROP_KEYS = ["what", "x", "y", "id", "by", "on", "angle", "scale", "line_to"];
const FX_KEYS = ["fx", "near", "text", "style", "side", "size"];

const AIR_BOTTOM = 36; // props with y "air" hang with their bottom edge here
const UP_TOP = 6; // pose "up": the top of the actor, in logical px from the top of the frame
export const HI_RES = 4; // canvas pixels per logical pixel when a page has text (crisp Arial); 1 otherwise

/** Pixel scale of a sprite when the art does not say otherwise (a multiplier of this is `scale`). */
const DEFAULT_SCALE = {
  hero: 4, dad: 4, mama: 4, lighthouse: 5, crab: 4, pig: 4, creeper: 5, bat: 4, hen: 4, fox: 4, duck: 4, pup: 5, fish: 3,
  boat: 5, tree: 4, chest: 4, bed: 6, torch: 4, door: 4,
  hut: 5, raft: 5, log: 4, mud: 4, rod: 4, bow: 4, web: 4, bell: 4, pot: 4, map: 4, gold_pig: 4,
  pirate: 4, witch: 4, berry_bush: 4, tent: 4, campfire: 4, pine: 4, plank: 4, flag: 4, pirate_flag: 4,
};
const defaultScale = (name) => DEFAULT_SCALE[name] ?? 3;

// How tools sit in a hand. `size` is the sprite size this table was written for (a change is a loud error, not a
// mis-drawn tool); `grip` is the sprite pixel the hand closes on; `angle` is the held angle in degrees (clockwise,
// for an actor facing right; 0 = as drawn); `dig` the angle in pose "dig"; `tip` the pixel a line leaves from.
const TOOLS = {
  pickaxe: { size: [10, 10], grip: [2.8, 8.6], angle: 35, dig: 100, tip: [5, 1.5] },
  rod: { size: [12, 14], grip: [0.6, 13], angle: 0, tip: [11.5, 2.5] },
  torch: { size: [4, 10], grip: [2, 8], angle: 15 },
  pan: { size: [16, 7], grip: [14.5, 3.5], angle: -15, mirror: true },
  sock: { size: [12, 11], grip: [1.5, 1.5], angle: 0 },
  // broom held upright like a walking stick (handle up, bristles down); spyglass raised to the eye
  broom: { size: [16, 6], grip: [10.5, 2.5], angle: 100 },
  spyglass: { size: [12, 5], grip: [4, 2], angle: -25 },
  // flags are held by the pole, flag up
  flag: { size: [12, 12], grip: [0.5, 9], angle: 0 },
  pirate_flag: { size: [12, 12], grip: [0.5, 9], angle: 0 },
};
// The rod sprite has its own short line hanging from the tip. When art gives `line_to`, that line is left out and
// the engine draws a line to the target instead. These are the sprite cells of that baked line (col, row).
const ROD_BAKED = (c, r) => (c === 11 && r >= 3) || (c === 9 && r === 10) || (c === 10 && r === 11);
// Bed: where the blanket starts (sprite col) and its rows, and where the pillow/headboard end (the head rests there).
const BED = { blanketCol: 4, rowTop: 2, rowBottom: 6, headCol: 1.5, footCols: 2 };
// Sprite rows from the top of a lying actor's head to its shoulders (the blanket starts after them).
const HEAD_ROWS = { hero: 7, dad: 9, mama: 7, pirate: 9, witch: 11 };
// The head box a speech bubble must never cover (sprite rows from the top of the head, and its width as a fraction
// of the sprite). Humans default to the full sprite width and HEAD_ROWS (6 rows when unlisted); the off-centre
// heads of animals are placed by HEAD (dx, row), or by dx/row here when HEAD has no entry (gold_pig). A worn hat or a prop "on" the head is added to the box.
const HEAD_BOX = { pig: { w: 0.4, rows: 5 }, gold_pig: { w: 0.4, rows: 5, dx: 0.32, row: 3 }, pup: { w: 0.5, rows: 5 }, hen: { w: 0.3, rows: 4 },
  fox: { w: 0.3, rows: 6 }, duck: { w: 0.3, rows: 5 }, bat: { w: 0.4, rows: 4 }, creeper: { w: 0.8, rows: 8 }, mama: { w: 0.9, rows: 7 },
  hero: { w: 0.9, rows: 7 }, dad: { w: 0.8, rows: 9 }, pirate: { w: 0.9, rows: 9 }, witch: { w: 1, rows: 11 } };

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const isPlain = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const ID_RE = /^[a-z][a-z0-9_]*$/;

// --- 2D affine matrices [a, b, c, d, e, f] exactly as canvas transform(a, b, c, d, e, f) ---
const mul = (m, n) => [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3],
  m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
const mT = (x, y) => [1, 0, 0, 1, x, y];
const mR = (t) => [Math.cos(t), Math.sin(t), -Math.sin(t), Math.cos(t), 0, 0];
const mS = (x, y) => [x, 0, 0, y, 0, 0];
const mApply = (m, x, y) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
const mBox = (m, w, h) => {
  const pts = [[0, 0], [w, 0], [0, h], [w, h]].map(([x, y]) => mApply(m, x, y));
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
};

// --- references: an `id`, else a sprite name that is unique among the actors and props ---
/**
 * Resolve `ref` (a string) to {kind: "actor"|"prop", index}, or {error} saying why not. Ids win; a sprite name
 * must match exactly one actor or prop (two clouds need ids).
 */
function lookup(art, ref) {
  const actors = art.actors ?? [], props = art.props ?? [];
  if (typeof ref !== "string") return { error: "must be a string (an id or a sprite name)" };
  const byId = [];
  actors.forEach((a, i) => { if (a.id === ref) byId.push({ kind: "actor", index: i }); });
  props.forEach((p, i) => { if (p.id === ref) byId.push({ kind: "prop", index: i }); });
  if (byId.length === 1) return byId[0];
  const byName = [];
  actors.forEach((a, i) => { if (a.who === ref) byName.push({ kind: "actor", index: i }); });
  props.forEach((p, i) => { if (p.what === ref) byName.push({ kind: "prop", index: i }); });
  if (byName.length === 1) return byName[0];
  if (byName.length > 1) return { error: `${JSON.stringify(ref)} matches ${byName.length} things; give them ids and use the id` };
  return { error: `${JSON.stringify(ref)} is not an id or a sprite name used in this art` };
}

/** Index of the actor whose x (percent) is nearest `x`; the first wins a tie. Used by "head"/"held" props with no `by`. */
function nearestActor(actors, x) {
  let best = 0;
  actors.forEach((a, i) => { if (Math.abs(a.x - x) < Math.abs(actors[best].x - x)) best = i; });
  return best;
}

/** The actor index that wears/holds prop `p` (its `by`, else the nearest actor by x). Art must be validated. */
function holderIndex(art, p) {
  if (p.by !== undefined) return lookup(art, p.by).index;
  return nearestActor(art.actors, p.x);
}

// --- text metrics: Arial Bold advance widths per 1000 em (the browser draws Arial; this keeps boxes pure) ---
const ARIAL_BOLD = { A: 722, B: 722, C: 722, D: 722, E: 667, F: 611, G: 778, H: 722, I: 278, J: 556, K: 722, L: 611,
  M: 833, N: 722, O: 778, P: 667, Q: 778, R: 722, S: 667, T: 611, U: 722, V: 667, W: 944, X: 667, Y: 667, Z: 611,
  " ": 278, "!": 333, "?": 611, ".": 278, ",": 278, "'": 238, "’": 278, "-": 333 };
const TEXT_RE = /^[A-Za-z0-9 !?.,'’-]+$/;
/** Small caps like the rest of the game: a-z are drawn as capitals at 0.72 of the size; capitals are full size. */
function glyphs(text, size) {
  return [...text].map((ch) => {
    const lower = ch >= "a" && ch <= "z";
    const up = lower ? ch.toUpperCase() : ch;
    const sz = lower ? size * 0.72 : size;
    const unit = /[0-9]/.test(up) ? 556 : ARIAL_BOLD[up];
    return { ch: up, size: sz, w: (unit * sz) / 1000 };
  });
}
/** Width (logical px) of `text` in bold Arial small caps at `size`. */
export function estimateTextWidth(text, size) {
  return glyphs(text, size).reduce((s, g) => s + g.w, 0);
}
/** Greedy word wrap to `maxW`; a single word wider than that stays on its own line (checkArt rejects it later). */
function wrapText(text, size, maxW) {
  const lines = [];
  let cur = "";
  for (const word of text.split(" ")) {
    const next = cur ? `${cur} ${word}` : word;
    if (cur && estimateTextWidth(next, size) > maxW) { lines.push(cur); cur = word; } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Normalise `art.fx` (a name, an object, or a list of either) to a list of {fx, ...fields}. */
function fxSpecs(art) {
  if (art.fx === undefined) return [];
  return (Array.isArray(art.fx) ? art.fx : [art.fx]).map((f) => (typeof f === "string" ? { fx: f } : f));
}
const textStyle = (s) => s.style ?? "burst";
const hasText = (art) => fxSpecs(art).some((s) => s.fx === "text" || s.fx === "sneeze" || s.fx === "hiss");

/**
 * Validate a composable art object. `path` is the field path used in every message (e.g.
 * `pages[3].art`). Throws ArtError naming the exact field and, for an unknown name, the allowed list. Also
 * lays the art out once, so a placement that cannot work (an actor outside its pit, a bed too short) is loud
 * here, when the story loads, not only when the page is drawn.
 */
export function checkArt(art, path = "art") {
  const fail = (m) => { throw new ArtError(`${path}${m}`); };
  const oneOf = (field, v, list, what) => {
    if (!list.includes(v)) fail(`${field} ${JSON.stringify(v)} is not a known ${what} (known: ${list.join(", ")})`);
  };
  const only = (f, obj, keys) => {
    for (const k of Object.keys(obj)) if (!keys.includes(k)) fail(`${f}.${k} is an unknown field (allowed: ${keys.join(", ")})`);
  };
  const ref = (f, v, kinds) => {
    const r = lookup(art, v);
    if (r.error) fail(`${f} ${r.error}`);
    if (!kinds.includes(r.kind)) fail(`${f} ${JSON.stringify(v)} is ${r.kind === "actor" ? "an actor" : "a prop"}, needs ${kinds.length === 2 ? "an actor or a prop" : `a ${kinds[0]}`}`);
    return r;
  };
  if (!isPlain(art)) fail(" must be a scene key string or an object { bg, actors?, props?, fx? }");
  only("", art, ART_KEYS);
  if (!("bg" in art)) fail(".bg is required");
  oneOf(".bg", art.bg, BG_NAMES, "background");
  const actors = art.actors ?? [], props = art.props ?? [];
  if (!Array.isArray(actors)) fail(".actors must be a list");
  if (!Array.isArray(props)) fail(".props must be a list");
  // First pass: shapes, names and ids (references are checked after every id is known).
  const ids = new Set();
  const checkId = (f, e) => {
    if (!("id" in e)) return;
    if (typeof e.id !== "string" || !ID_RE.test(e.id)) fail(`${f}.id must be lowercase letters, digits and _, starting with a letter`);
    if (ids.has(e.id)) fail(`${f}.id ${JSON.stringify(e.id)} is used twice`);
    ids.add(e.id);
  };
  actors.forEach((a, i) => {
    const f = `.actors[${i}]`;
    if (!isPlain(a)) fail(`${f} must be an object`);
    only(f, a, ACTOR_KEYS);
    if (!("who" in a)) fail(`${f}.who is required`);
    oneOf(`${f}.who`, a.who, SPRITE_NAMES, "sprite");
    if (!isNum(a.x) || a.x < 0 || a.x > 100) fail(`${f}.x must be a number 0-100, got ${JSON.stringify(a.x)}`);
    if ("pose" in a) oneOf(`${f}.pose`, a.pose, POSES, "pose");
    if ("flip" in a && typeof a.flip !== "boolean") fail(`${f}.flip must be true or false`);
    if ("scale" in a && (!isNum(a.scale) || a.scale <= 0 || a.scale > 4)) fail(`${f}.scale must be a number above 0 and at most 4`);
    checkId(f, a);
  });
  props.forEach((p, i) => {
    const f = `.props[${i}]`;
    if (!isPlain(p)) fail(`${f} must be an object`);
    only(f, p, PROP_KEYS);
    if (!("what" in p)) fail(`${f}.what is required`);
    oneOf(`${f}.what`, p.what, SPRITE_NAMES, "sprite");
    if (!isNum(p.x) || p.x < 0 || p.x > 100) fail(`${f}.x must be a number 0-100, got ${JSON.stringify(p.x)}`);
    if ("y" in p) oneOf(`${f}.y`, p.y, PROP_YS, "prop y");
    if ("scale" in p && (!isNum(p.scale) || p.scale <= 0 || p.scale > 4)) fail(`${f}.scale must be a number above 0 and at most 4`);
    if ("angle" in p && (!isNum(p.angle) || p.angle < -180 || p.angle > 180)) fail(`${f}.angle must be a number -180 to 180 (degrees)`);
    checkId(f, p);
  });
  // Second pass: relations.
  const held = new Map();
  actors.forEach((a, i) => {
    const f = `.actors[${i}]`, pose = a.pose ?? "stand";
    if (pose === "in") {
      if (!("in" in a)) fail(`${f}.pose "in" needs ${f}.in (the id or sprite name of the prop he stands in: pit, bathtub ...)`);
    } else if (pose === "lying") {
      if ("in" in a && props[ref(`${f}.in`, a.in, ["prop"]).index].what !== "bed")
        fail(`${f}.in: a lying actor can only lie in a "bed" prop`);
    } else if ("in" in a) fail(`${f}.in is only for pose "in" or "lying" (this actor is "${pose}")`);
    if ("in" in a) {
      const q = props[ref(`${f}.in`, a.in, ["prop"]).index];
      if (!["ground", "water"].includes(q.y ?? "ground")) fail(`${f}.in: the container must stand on the ground or float on water (its y is "${q.y}")`);
    }
    if (pose === "sit_on") {
      if (!("on" in a)) fail(`${f}.pose "sit_on" needs ${f}.on (the id or sprite name of what he sits on)`);
      const r = ref(`${f}.on`, a.on, ["actor", "prop"]);
      if (r.kind === "actor" && r.index === i) fail(`${f}.on cannot be the actor itself`);
    } else if ("on" in a) fail(`${f}.on is only for pose "sit_on" (this actor is "${pose}")`);
  });
  props.forEach((p, i) => {
    const f = `.props[${i}]`, y = p.y ?? "ground";
    if (y === "water" && BGS[art.bg].water === undefined) fail(`${f}.y "water" needs a bg with water (river, sea, pond), not "${art.bg}"`);
    if ("by" in p && y !== "held" && y !== "head") fail(`${f}.by is only for y "held" or "head"`);
    if ("angle" in p && y !== "held") fail(`${f}.angle is only for y "held"`);
    if ("on" in p && y !== "on") fail(`${f}.on is only for y "on"`);
    if ("line_to" in p && y !== "held") fail(`${f}.line_to is only for a held prop`);
    if (y === "on") {
      if (!("on" in p)) fail(`${f}.y "on" needs ${f}.on (the id or sprite name of what it sits on)`);
      const r = ref(`${f}.on`, p.on, ["actor", "prop"]);
      if (r.kind === "prop" && r.index === i) fail(`${f}.on cannot be the prop itself`);
    }
    if (y === "held" || y === "head") {
      if (actors.length === 0) fail(`${f}.y "${y}" needs at least one actor to ${y === "held" ? "hold" : "wear"} it`);
      if ("by" in p) ref(`${f}.by`, p.by, ["actor"]);
      const hi = holderIndex(art, p), who = actors[hi];
      if (y === "held") {
        if (held.has(hi)) fail(`${f}: ${who.who} (actors[${hi}]) already holds props[${held.get(hi)}]; one held prop per actor (\`by\` picks the actor)`);
        held.set(hi, i);
      }
      if (y === "head" && !HEAD_POSES.includes(who.pose ?? "stand"))
        fail(`${f}.y "head" needs the actor (${who.who}) upright; its pose "${who.pose}" is not (allowed: ${HEAD_POSES.join(", ")})`);
      if ("line_to" in p) {
        if (!TOOLS[p.what]?.tip) fail(`${f}.line_to: only a tool with a tip can draw a line (${Object.keys(TOOLS).filter((n) => TOOLS[n].tip).join(", ")}), not "${p.what}"`);
        if (p.what !== "rod") fail(`${f}.line_to is supported for "rod" only`);
        ref(`${f}.line_to`, p.line_to, ["actor", "prop"]);
      }
    }
  });
  actors.forEach((a, i) => {
    if (a.pose === "dig" && !held.has(i)) throw new ArtError(`${path}.actors[${i}].pose "dig" needs a prop with y "held" held by this actor (a pickaxe), with \`by\` if another actor is nearer`);
  });
  const fxs = fxSpecs(art);
  if ("fx" in art) {
    if (Array.isArray(art.fx) && art.fx.length === 0) fail(".fx list must not be empty");
    if (actors.length + props.length === 0) fail(".fx needs at least one actor or prop to appear at");
  }
  fxs.forEach((s, i) => {
    const f = Array.isArray(art.fx) ? `.fx[${i}]` : ".fx";
    const fo = typeof (Array.isArray(art.fx) ? art.fx[i] : art.fx) === "string" ? f : `${f}.fx`;
    if (!isPlain(s)) fail(`${f} must be a name or an object { fx, ... }`);
    only(f, s, FX_KEYS);
    if (!("fx" in s)) fail(`${f}.fx is required`);
    oneOf(fo, s.fx, FX_NAMES, "fx");
    if ("near" in s) ref(`${f}.near`, s.near, ["actor", "prop"]);
    if (s.fx === "text") {
      if (typeof art.fx === "string" || (Array.isArray(art.fx) && typeof art.fx[i] === "string"))
        fail(`${f} "text" needs the object form {"fx":"text","text":"QUACK!","near":"duck"}`);
      if (!("near" in s)) fail(`${f}.near is required for text (the actor or prop it comes from)`);
      if (typeof s.text !== "string" || !TEXT_RE.test(s.text))
        fail(`${f}.text must be letters, digits, space and ! ? . , ' - only, got ${JSON.stringify(s.text)}`);
      if (s.text.length > 40) fail(`${f}.text is longer than 40 characters`);
    } else for (const k of ["text", "style", "side", "size"]) if (k in s) fail(`${f}.${k} is only for fx "text"`);
    if ("style" in s) oneOf(`${f}.style`, s.style, TEXT_STYLES, "text style");
    if ("side" in s) oneOf(`${f}.side`, s.side, TEXT_SIDES, "text side");
    if ("size" in s && (!isNum(s.size) || s.size < 5 || s.size > 24)) fail(`${f}.size must be a number 5-24 (logical px)`);
    if (s.fx === "text") {
      const sz = s.size ?? (textStyle(s) === "say" ? 7 : 11);
      const wMax = textStyle(s) === "say" ? Math.max(...wrapText(s.text, sz, 100).map((l) => estimateTextWidth(l, sz))) + 8
        : estimateTextWidth(s.text, sz) + sz * 1.6;
      if (wMax > SCENE_W - 4) fail(`${f}.text is too wide for the frame at size ${sz} (${Math.round(wMax)} of ${SCENE_W}); shorten it or lower size`);
    }
  });
  if (fxs.filter((s) => s.fx === "boom").length > 1) fail(".fx has more than one boom");
  const hugs = actors.filter((a) => a.pose === "hug").length;
  if (hugs % 2) fail(`.actors has ${hugs} with pose "hug"; hugging needs pairs (exactly two actors)`);
  if (actors.some((a) => a.pose === "hide") && !props.some((p) => (p.y ?? "ground") === "ground"))
    fail('.actors pose "hide" needs a prop with y "ground" (the default) to hide behind');
  layout(art, BGS[art.bg], path);
  return art;
}

// --- tiny 3x5 pixel font (only the letters the zzz effect spells) ---
const FONT = {
  A: [".#.", "#.#", "###", "#.#", "#.#"], C: ["###", "#..", "#..", "#..", "###"],
  H: ["#.#", "#.#", "###", "#.#", "#.#"], O: ["###", "#.#", "#.#", "#.#", "###"],
  I: ["###", ".#.", ".#.", ".#.", "###"], S: ["###", "#..", "###", "..#", "###"],
  Z: ["###", "..#", ".#.", "#..", "###"],
};

/** Draw `str` (letters in FONT only) with its top-left at (x, y), dark outline then fill. */
function pixelText(ctx, str, x, y, scale, fill = "#ffffff", outline = "#1b1b1b") {
  const cells = [];
  [...str].forEach((ch, n) => {
    const g = FONT[ch];
    if (!g) throw new Error(`pixelText: no glyph for "${ch}"`);
    g.forEach((row, r) => [...row].forEach((c, k) => { if (c === "#") cells.push([x + (n * 4 + k) * scale, y + r * scale]); }));
  });
  for (const [cx, cy] of cells) for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [1, 1], [-1, -1]]) rect(ctx, outline, cx + dx, cy + dy, scale, scale);
  for (const [cx, cy] of cells) rect(ctx, fill, cx, cy, scale, scale);
}

/** Draw bold Arial small-caps `text` with its left at x and baseline at y; dark outline under the fill. */
function drawSmallCaps(ctx, text, x, y, size, fill, outline = "#1b1b1b") {
  let cx = x;
  ctx.lineJoin = "round";
  for (const g of glyphs(text, size)) {
    ctx.font = `bold ${g.size}px Arial, Helvetica, sans-serif`;
    if (outline) { ctx.lineWidth = Math.max(0.6, size * 0.17); ctx.strokeStyle = outline; ctx.strokeText(g.ch, cx, y); }
    ctx.fillStyle = fill;
    ctx.fillText(g.ch, cx, y);
    cx += g.w;
  }
}

// --- actors: pose frames ---
/**
 * The transform of an actor and its sprite frame. `full` maps sprite-local px (origin = top-left of the sprite
 * as drawn at 1:1 scaled by r.k, i.e. the frame the drawing code uses) to the canvas; `rigid` is the same
 * without the "sit" squash (props held by a sitting actor are not squashed). `ox, oy`: where the sprite's
 * top-left is in that frame; `widen`: extra half-width (run spreads its legs).
 */
function poseFrame(r) {
  const pose = r.a.pose ?? "stand", W = r.w, H = r.h, k = r.k;
  const base = mul(mul(mT(Math.round(r.cx), Math.round(r.foot)), mR(r.lean)), mS(r.a.flip ? -1 : 1, 1));
  let P = mT(0, 0), squash = false, ox = -W / 2, oy = -H, widen = 0;
  switch (pose) {
    case "stand": case "hug": case "hide": case "up": case "in": break;
    case "run": P = mR(0.2); widen = 1.5 * k; break;
    case "jump": P = mT(0, -16); break;
    case "sit": case "sit_on": squash = true; break;
    case "fall": P = mR(1.1); break;
    case "upside_down": P = mul(mT(0, -H / 2 - 6), mR(Math.PI)); oy = -H / 2; break;
    case "sleep": P = mul(mT(0, -W / 2), mR(-Math.PI / 2)); break;
    case "lying": P = mul(mT(H / 2, -W / 2), mR(-Math.PI / 2)); break;
    case "dig": P = mR(0.2); break;
    default: throw new Error(`poseFrame: unknown pose "${pose}"`);
  }
  const full = mul(base, squash ? mul(P, mS(1, 0.72)) : P), rigid = mul(base, P);
  return { full, rigid, ox, oy, widen };
}

/** Draw `cv` rows [sy, sy+sh) of columns [sx, sx+sw) with scale, top-left at (dx, dy) in the current transform. */
function slice(ctx, cv, sx, sy, sw, sh, dx, dy, k) {
  ctx.drawImage(cv, sx, sy, sw, sh, Math.round(dx), Math.round(dy), sw * k, sh * k);
}

/** Draw an actor in its pose frame (poses are plain canvas transforms of the one sprite, no new art). */
function drawActor(ctx, r) {
  const { w, h } = spriteSize(r.a.who);
  const cv = spriteCanvas(r.a.who);
  const pose = r.a.pose ?? "stand", W = r.w, H = r.h, k = r.k;
  const f = poseFrame(r);
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.transform(...f.full);
  if (pose === "run") {
    const cut = Math.floor(h * 0.72), half = Math.floor(w / 2), spread = 1.5 * k;
    slice(ctx, cv, 0, 0, w, cut, -W / 2, -H, k);
    slice(ctx, cv, 0, cut, half, h - cut, -W / 2 - spread, -(h - cut) * k, k);
    slice(ctx, cv, half, cut, w - half, h - cut, -W / 2 + half * k + spread, -(h - cut) * k, k);
  } else slice(ctx, cv, 0, 0, w, h, f.ox, f.oy, k);
  ctx.restore();
}

/** The bounding box [x0, y0, x1, y1] (logical px) of an actor after its pose transform. */
function actorBox(r) {
  const f = poseFrame(r);
  const pts = [[f.ox - f.widen, f.oy], [f.ox + r.w + f.widen, f.oy], [f.ox - f.widen, f.oy + r.h], [f.ox + r.w + f.widen, f.oy + r.h]]
    .map(([x, y]) => mApply(f.full, x, y));
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
const boxOf = (r) => (r.kind === "actor" ? actorBox(r) : r.box);

/** Where the held hand is, canvas px: the hand pixel of the sprite through the pose frame. */
function handPoint(r) {
  const f = poseFrame(r), hd = HANDS[r.a.who] ?? { col: spriteSize(r.a.who).w - 1, row: Math.round(spriteSize(r.a.who).h * 0.45) };
  return mApply(f.full, f.ox + (hd.col + 0.5) * r.k, f.oy + (hd.row + 0.5) * r.k);
}

/** The top-centre of an actor's head, canvas px (through the pose frame; off-centre heads per HEAD, mirrored by flip). */
function headPoint(r) {
  const f = poseFrame(r), hd = HEAD[r.a.who] ?? { dx: 0, row: 0 };
  return mApply(f.full, hd.dx * r.w, f.oy + hd.row * r.k);
}

/**
 * Resolve every actor and prop to canvas positions, in dependency order (a thing is placed after what it holds,
 * wears, sits on or stands in). Throws ArtError (naming `path`) for placements that cannot work.
 * Returns { actors, props } records; each has `box`, a draw `order`, and (props) the matrix `mat` to draw with.
 */
function layout(art, bg, path = "art") {
  const fail = (m) => { throw new ArtError(`${path}${m}`); };
  const xOf = (x) => (x * SCENE_W) / 100;
  const actors = (art.actors ?? []).map((a, i) => {
    const k = defaultScale(a.who) * (a.scale ?? 1), { w, h } = spriteSize(a.who);
    return { kind: "actor", i, a, k, w: w * k, h: h * k, cx: xOf(a.x), foot: bg.ground, lean: 0, order: -1, state: 0, decor: [], ground: bg.ground };
  });
  const props = (art.props ?? []).map((p, i) => {
    const k = defaultScale(p.what) * (p.scale ?? 1), { w, h } = spriteSize(p.what);
    return { kind: "prop", i, p, k, w: w * k, h: h * k, cx: xOf(p.x), y: p.y ?? "ground", foot: 0, front: false, order: -1, state: 0, box: null, mat: null, extra: [] };
  });
  const find = (refStr) => { const r = lookup(art, refStr); return r.kind === "actor" ? actors[r.index] : props[r.index]; };
  // Hug: pair actors left to right (0-1, 2-3 ...); each pair meets at its midpoint with 2px overlap, leaning in.
  const huggers = actors.filter((r) => r.a.pose === "hug").sort((l, r) => l.cx - r.cx);
  for (let i = 0; i + 1 < huggers.length; i += 2) {
    const L = huggers[i], R = huggers[i + 1], mid = (L.cx + R.cx) / 2;
    L.cx = mid - L.w / 2 + 2; R.cx = mid + R.w / 2 - 2;
    L.lean = 0.04; R.lean = -0.04;
    L.hugWith = R; R.hugWith = L;
  }
  let counter = 0;
  const place = (r) => {
    if (r.state === 2) return;
    if (r.state === 1) fail(`: ${r.kind}s[${r.i}] depends on itself (a circle of in / on / sit_on / by relations)`);
    r.state = 1;
    if (r.kind === "actor") placeActor(r); else placeProp(r);
    r.state = 2;
    r.order = counter++;
  };
  const placeActor = (r) => {
    const a = r.a, pose = a.pose ?? "stand", f = `.actors[${r.i}]`;
    if (pose === "hide") {
      const cands = props.filter((q) => q.y === "ground");
      const t = cands.reduce((best, q) => (Math.abs(q.cx - r.cx) < Math.abs(best.cx - r.cx) ? q : best));
      place(t);
      r.cx = t.cx + (r.cx >= t.cx ? 1 : -1) * (t.w / 2);
      t.front = true;
      r.hidesBehind = t;
    } else if (pose === "up") {
      r.foot = UP_TOP + r.h;
      r.decor.push("up");
    } else if (pose === "in") {
      const q = find(a.in);
      place(q);
      const reach = q.w / 2 - r.w / 2 + 3;
      if (reach < 0) fail(`${f}: the ${a.who} (${Math.round(r.w)}px wide) is wider than the ${q.p.what} (${Math.round(q.w)}px); scale the actor down (scale <= ${(q.w / (r.w / (a.scale ?? 1))).toFixed(2)})`);
      if (Math.abs(r.cx - q.cx) > reach)
        fail(`${f}.x ${a.x} puts the ${a.who} outside the ${q.p.what}; use x ${(100 * (q.cx - reach) / SCENE_W).toFixed(0)}-${(100 * (q.cx + reach) / SCENE_W).toFixed(0)} (the ${q.p.what}'s x is ${q.p.x})`);
      // The container covers the lower part of the actor: up to 80% of its own height, at most half the actor.
      r.foot = q.foot - q.h + Math.min(q.h * 0.8, r.h * 0.5);
      q.front = true;
      r.container = q;
    } else if (pose === "lying") {
      if ("in" in a) {
        const q = find(a.in);
        place(q);
        const len = r.h, room = q.w - BED.headCol * q.k - q.k * 0.5;
        if (len > room) fail(`${f}: lying in the bed needs ${Math.round(len)}px of bed, the bed has ${Math.round(room)}; scale the actor down or the bed up`);
        r.cx = (a.flip ? q.cx + q.w / 2 - BED.headCol * q.k - len / 2 : q.cx - q.w / 2 + BED.headCol * q.k + len / 2);
        r.foot = q.foot - q.h + BED.rowTop * q.k + r.w / 2 + q.k * 0.4;
        r.bed = q;
        const startCol = Math.max(BED.blanketCol, Math.ceil((BED.headCol * q.k + (HEAD_ROWS[a.who] ?? 6) * r.k + 2) / q.k));
        r.bedCover = { startCol, top: r.foot - r.w / 2 - 0.2 * r.w };
      }
    } else if (pose === "sit_on") {
      const t = find(a.on);
      place(t);
      const tb = boxOf(t);
      if (Math.abs(r.cx - (tb[0] + tb[2]) / 2) > (tb[2] - tb[0]) / 2)
        fail(`${f}.x ${a.x} is not over the thing it sits on (${a.on}); use x ${(100 * ((tb[0] + tb[2]) / 2) / SCENE_W).toFixed(0)} +/- ${(100 * ((tb[2] - tb[0]) / 2) / SCENE_W).toFixed(0)}`);
      r.foot = tb[1] + 5;
      r.sitsOn = t;
    }
    if (pose === "run") r.decor.push("run");
    if (pose === "dig") r.decor.push("dig");
  };
  const placeProp = (q) => {
    const p = q.p, f = `.props[${q.i}]`;
    if (q.y === "ground") q.foot = bg.ground;
    else if (q.y === "air") q.foot = AIR_BOTTOM;
    else if (q.y === "water") q.foot = bg.water + 6;
    else if (q.y === "head") {
      // Worn: on the head of its actor, overlapping the head by a third of its own height.
      const r = actors[holderIndex(art, p)];
      place(r);
      const hp = headPoint(r);
      q.cx = hp[0];
      q.foot = hp[1] + q.h / 3;
      q.front = true;
    } else if (q.y === "on") {
      const t = find(p.on);
      place(t);
      if (t.kind === "actor") {
        const hp = headPoint(t);
        q.cx = hp[0];
        q.foot = hp[1] + q.h / 3;
      } else {
        q.cx = t.cx;
        q.foot = t.box[1] + q.h / 4;
      }
      q.front = true;
    } else if (q.y === "held") {
      const r = actors[holderIndex(art, p)];
      place(r);
      const T = TOOLS[p.what];
      if (T && (T.size[0] * 1 !== spriteSize(p.what).w || T.size[1] !== spriteSize(p.what).h))
        fail(`${f}: the "${p.what}" sprite is ${spriteSize(p.what).w}x${spriteSize(p.what).h} but TOOLS in scenes.js expects ${T.size.join("x")}; update TOOLS`);
      const grip = T ? T.grip : [spriteSize(p.what).w / 2, spriteSize(p.what).h / 2];
      const dig = r.a.pose === "dig";
      const deg = p.angle ?? (dig && T?.dig !== undefined ? T.dig : T?.angle ?? 0);
      const hand = handPoint(r), fr = poseFrame(r);
      const lin = [fr.rigid[0], fr.rigid[1], fr.rigid[2], fr.rigid[3], 0, 0];
      q.mat = mul(mul(mul(mul(mul(mT(hand[0], hand[1]), lin), mR((deg * Math.PI) / 180)), mS(T?.mirror ? -1 : 1, 1)), mS(q.k, q.k)), mT(-grip[0], -grip[1]));
      q.box = mBox(q.mat, spriteSize(p.what).w, spriteSize(p.what).h);
      q.cx = (q.box[0] + q.box[2]) / 2;
      q.foot = q.box[3];
      q.front = true;
      q.hand = { x: hand[0], y: hand[1], skin: HANDS[r.a.who]?.skin, k: r.k };
      q.holder = r;
      if (T?.tip) q.tipPx = mApply(q.mat, T.tip[0], T.tip[1]);
      if (p.line_to !== undefined) {
        const target = find(p.line_to);
        place(target);
        q.lineTarget = target;
      }
    }
    if (q.y === "held") return; // box and mat were set from the hand
    q.box = [q.cx - q.w / 2, q.foot - q.h, q.cx + q.w / 2, q.foot];
    q.mat = mul(mT(Math.round(q.box[0]), Math.round(q.box[1])), mS(q.k, q.k));
  };
  // dependencies first: containers, hosts, then everything
  for (const q of props) if (q.y === "ground" || q.y === "air" || q.y === "water") place(q);
  for (const r of actors) place(r);
  for (const q of props) place(q);
  return { actors, props, art, byRef: find };
}

/** The anchor of an effect: where it appears. `near` (an id or name) overrides the legacy default. */
function fxAnchor(spec, L, art) {
  const near = spec.near !== undefined ? lookup(art, spec.near) : null;
  const actor = L.actors[0], prop = L.props[0];
  const headFx = spec.fx === "sneeze" || spec.fx === "zzz";
  const t = near ? (near.kind === "actor" ? L.actors[near.index] : L.props[near.index]) : headFx ? actor ?? prop : prop ?? actor;
  const isActor = t.kind === "actor";
  const b = boxOf(t);
  const lying = isActor && ["sleep", "fall", "lying"].includes(t.a.pose);
  // Where a speech tail points: the speaker's head box (a prop speaks from the top fifth of its box).
  const head = isActor ? headRect(t, L) : [b[0], b[1], b[2], b[1] + Math.max(2, (b[3] - b[1]) * 0.2)];
  return { target: t, head, cx: (b[0] + b[2]) / 2, top: b[1], bottom: b[3], w: b[2] - b[0], dir: isActor && t.a.flip ? -1 : 1, lying,
    sleepHead: isActor && t.a.pose === "sleep" ? t.cx : null };
}

/** True when two boxes [x0, y0, x1, y1] share more than `eps` px of both width and height. */
const boxesTouch = (a, b, eps = 0) => Math.min(a[2], b[2]) - Math.max(a[0], b[0]) > eps && Math.min(a[3], b[3]) - Math.max(a[1], b[1]) > eps;
const overlapArea = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));

/**
 * The head box of an actor, canvas px [x0, y0, x1, y1], through its pose frame (so a lying or fallen actor's head is
 * where its head really is). Per HEAD_BOX / HEAD / HEAD_ROWS; a head prop (hat, crown, sock on the hat) worn by the
 * actor is united with it, because a bubble must not hide those either.
 */
function headRect(r, L) {
  const f = poseFrame(r), hb = HEAD_BOX[r.a.who] ?? {}, hd = HEAD[r.a.who] ?? {};
  const dx = hb.dx ?? hd.dx ?? 0, row = hb.row ?? hd.row ?? 0, rows = hb.rows ?? HEAD_ROWS[r.a.who] ?? 6;
  const hw = (hb.w ?? 0.8) * r.w, cx = dx * r.w;
  const pts = [[cx - hw / 2, f.oy + row * r.k], [cx + hw / 2, f.oy + row * r.k], [cx - hw / 2, f.oy + (row + rows) * r.k], [cx + hw / 2, f.oy + (row + rows) * r.k]]
    .map(([x, y]) => mApply(f.full, x, y));
  const box = [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))];
  for (const q of L.props) {
    const worn = q.y === "head" ? L.actors[holderIndex(L.art, q.p)] : q.y === "on" ? L.byRef(q.p.on) : null;
    if (worn !== r) continue;
    box[0] = Math.min(box[0], q.box[0]); box[1] = Math.min(box[1], q.box[1]); box[2] = Math.max(box[2], q.box[2]); box[3] = Math.max(box[3], q.box[3]);
  }
  return box;
}

// --- effects: each plan gives its box (for the guards) and the drawing ---
const cyOf = (t) => Math.round((t.top + t.bottom) / 2);

/**
 * A bold text burst (or speech bubble) for `text`, anchored to `t`. `opts.avoid` is the list of head boxes (see
 * headRect) the text must never cover, the speaker's own included. Placement is deterministic: the requested side
 * (default above the head), then above, then the other sides (the one with more room first), then the same sides
 * below the head level; if none is clear, the text shrinks one size step (down to 5 for a bubble, 6 for a burst)
 * and every place is tried again. When nothing is clear at any size the least-covering place is used and the
 * render guard (artBubbleHeadHits) fails it. Returns { box (with the tail), bubble (the text body alone), draw }.
 */
function textPlan(spec, t, opts = {}) {
  const style = textStyle(spec), want = spec.side ?? "above", text = spec.text, avoid = opts.avoid ?? [];
  const clampX = (x, w) => Math.max(1, Math.min(SCENE_W - w - 1, x));
  const clampY = (y, h) => Math.max(1, Math.min(SCENE_H - h - 1, y));
  const topRef = Math.min(t.top, t.head[1]); // a worn hat extends above the actor's own box
  const roomR = SCENE_W - 1 - (t.cx + t.w / 2), roomL = t.cx - t.w / 2 - 1;
  const others = (roomR >= roomL ? ["right", "left"] : ["left", "right"]);
  const sides = [...new Set([want, "above", ...others])];
  // Variants in order: the sides as listed, but "above" is followed by "up" (still above, raised over the head of a
  // neighbour that the plain spot would touch), then the other sides at the head level, then below the head level.
  const variants = [...sides.flatMap((s) => (s === "above" ? [["above", false], ["up", false]] : [[s, false]])), ...others.map((s) => [s, true])];
  const S0 = spec.size ?? opts.size ?? (style === "say" ? 7 : 11), minS = Math.min(S0, style === "say" ? 5 : 6);
  // The y a bubble above must stay over: the highest head top among the heads its x range spans (and `top`).
  const raisedTop = (bx, bw, top) => avoid.reduce((y, h) => (h[0] < bx + bw && h[2] > bx ? Math.min(y, h[1]) : y), top);
  // One candidate of a style: its geometry for (side, size, below-the-head).
  const build = (side, S, low) => {
    if (style === "burst") {
      const tw = estimateTextWidth(text, S), padX = S * 0.8, padY = S * 0.6, bw = tw + 2 * padX, bh = S * 0.75 + 2 * padY;
      let bx = t.cx - bw / 2 + t.dir * t.w * 0.15, by = topRef - bh - 1;
      if (side === "up") by = raisedTop(bx, bw, topRef) - bh - 1;
      if (side === "right") { bx = t.cx + t.w / 2 + 1; by = low ? t.head[3] + 1 : t.top + (t.bottom - t.top) * 0.2 - bh / 2; }
      if (side === "left") { bx = t.cx - t.w / 2 - bw - 1; by = low ? t.head[3] + 1 : t.top + (t.bottom - t.top) * 0.2 - bh / 2; }
      bx = clampX(bx, bw); by = clampY(by, bh);
      return { S, bx, by, bw, bh, padX, padY };
    }
    const room = side === "right" ? roomR - 7 : side === "left" ? roomL - 7 : SCENE_W - 2; // "above"/"up": the frame
    const lines = wrapText(text, S, Math.min(100, room - 8)), lh = S * 1.25;
    const tw = Math.max(...lines.map((l) => estimateTextWidth(l, S))), bw = tw + 8, bh = lines.length * lh + 5;
    let bx = t.cx - bw / 2, by = topRef - bh - 7;
    if (side === "up") by = raisedTop(bx, bw, topRef) - bh - 7;
    if (side === "right") { bx = t.cx + t.w / 2 + 7; by = low ? t.head[3] + 2 : t.top - bh * 0.4; }
    if (side === "left") { bx = t.cx - t.w / 2 - 7 - bw; by = low ? t.head[3] + 2 : t.top - bh * 0.4; }
    bx = clampX(bx, bw); by = clampY(by, bh);
    return { S, bx, by, bw, bh, lines, lh, tw };
  };
  // Cover score of a candidate: 0 when it touches no head box, else the covered area (plus 1 so a graze still counts).
  const cover = (c) => avoid.reduce((n, h) => n + (boxesTouch([c.bx, c.by, c.bx + c.bw, c.by + c.bh], h) ? overlapArea([c.bx, c.by, c.bx + c.bw, c.by + c.bh], h) + 1 : 0), 0);
  let pick = null;
  for (let S = S0; S >= minS && !(pick && pick.score === 0); S--) {
    for (const [side, low] of variants) {
      const c = build(side, S, low);
      c.score = cover(c);
      if (!pick || c.score < pick.score) pick = c;
      if (c.score === 0) break;
    }
  }
  const { bx, by, bw, bh, S } = pick;
  const bubble = [bx, by, bx + bw, by + bh];
  if (style === "burst") {
    const { padX, padY } = pick;
    return { box: bubble, bubble, draw(ctx) {
      const cx = bx + bw / 2, cy = by + bh / 2, n = 14;
      ctx.beginPath();
      for (let i = 0; i < n * 2; i++) {
        const a = (Math.PI * i) / n - Math.PI / 2, f = i % 2 ? 0.8 : 1;
        const x = cx + Math.cos(a) * (bw / 2) * f, y = cy + Math.sin(a) * (bh / 2) * f;
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = opts.burst ?? "#ffd23a";
      ctx.fill();
      ctx.lineJoin = "round";
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#1b1b1b";
      ctx.stroke();
      drawSmallCaps(ctx, text, bx + padX, by + padY + S * 0.72 + 0.4, S, opts.text ?? "#8f2420", "#ffffff");
    } };
  }
  // speech bubble: white box, dark border, a tail that points at the speaker's head box (never into the face)
  const { lines, lh, tw } = pick, hr = t.head, hx = (hr[0] + hr[2]) / 2;
  let tail = null;
  if (by + bh <= hr[1]) { // above the head
    const px = Math.max(bx + 6, Math.min(bx + bw - 6, hx)), py = by + bh;
    tail = { pts: [[px - 3, py], [px + 3, py], [Math.max(bx, Math.min(bx + bw, hx)), hr[1] - 1]] };
  } else if (by >= hr[3]) { // below the head
    const px = Math.max(bx + 6, Math.min(bx + bw - 6, hx));
    tail = { pts: [[px - 3, by], [px + 3, by], [Math.max(bx, Math.min(bx + bw, hx)), hr[3] + 1]] };
  } else if (hx < bx || hx > bx + bw) { // beside it
    const ty = (hr[1] + hr[3]) / 2, py = Math.max(by + 4, Math.min(by + bh - 4, ty)), px = hx > bx + bw ? bx + bw : bx;
    tail = { pts: [[px, py - 3], [px, py + 3], [hx > bx + bw ? hr[0] - 1 : hr[2] + 1, ty]] };
  }
  const box = [...bubble];
  if (tail) { const p = tail.pts[2]; box[0] = Math.min(box[0], p[0]); box[1] = Math.min(box[1], p[1]); box[2] = Math.max(box[2], p[0]); box[3] = Math.max(box[3], p[1]); }
  return { box, bubble, draw(ctx) {
    const poly = (pts, c) => { ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.fillStyle = c; ctx.fill(); };
    if (tail) poly(tail.pts.map(([x, y], i) => (i === 2 ? [x, y] : [x + (i ? 1 : -1), y])), "#1b1b1b");
    rect(ctx, "#1b1b1b", bx - 1, by - 1, bw + 2, bh + 2);
    rect(ctx, "#ffffff", bx, by, bw, bh);
    if (tail) poly(tail.pts, "#ffffff");
    lines.forEach((l, i) => drawSmallCaps(ctx, l, bx + 4 + (tw - estimateTextWidth(l, S)) / 2, by + 2.5 + lh * i + S * 0.8, S, "#1b1b1b", null));
  } };
}

const RAYS = [[0, -30], [30, -20], [34, 8], [0, 30], [-34, 8], [-30, -20], [18, -34], [-18, 34], [-40, -4], [40, -4]];
/** Plan one effect: { box, draw(ctx) } for `spec` anchored at `t` (see fxAnchor). */
function fxPlan(spec, t, avoid = []) {
  const name = spec.fx, cx = t.cx;
  switch (name) {
    case "boom": { const cy = cyOf(t); return { box: [cx - 46, cy - 40, cx + 46, cy + 40], draw(ctx) {
      glow(ctx, cx, cy, 64, "255,180,60");
      RAYS.forEach(([dx, dy], i) => rect(ctx, i % 2 ? "#ffd23a" : "#ff8c1a", cx + dx - 6, cy + dy - 6, 12, 12));
      rect(ctx, "#ffffff", cx - 12, cy - 12, 24, 24);
      rect(ctx, "#ffd23a", cx - 6, cy - 6, 12, 12);
    } }; }
    case "splash": { const y = t.bottom - 2; return { box: [cx - 24, y - 31, cx + 24, y + 3], draw(ctx) {
      rect(ctx, "#8fc4f5", cx - 24, y, 48, 3);
      rect(ctx, "#ffffff", cx - 16, y - 1, 32, 2);
      for (let i = -4; i <= 4; i++) {
        const up = 26 - Math.abs(i) * 4;
        rect(ctx, "#8fc4f5", cx + i * 5, y - up, 4, 4);
        rect(ctx, "#ffffff", cx + i * 5 + 1, y - up - 5, 2, 3);
      }
    } }; }
    case "sneeze": {
      const x = cx + t.dir * (t.w * 0.6), y = t.top + 8;
      const tp = textPlan({ fx: "text", text: "ACHOO!", style: "burst", side: "above" }, t, { burst: "#cfe8ff", text: "#2646a0", avoid });
      const px0 = x + t.dir * 6, px1 = x + t.dir * 10;
      const box = [Math.min(tp.box[0], px0, px1), Math.min(tp.box[1], y - 10), Math.max(tp.box[2], px0 + 3, px1 + 3), Math.max(tp.box[3], y + 13)];
      return { box, draw(ctx) {
        for (let i = -2; i <= 2; i++) rect(ctx, i % 2 ? "#cfe8ff" : "#ffffff", x + t.dir * (6 + Math.abs(i) * 2), y + i * 5, 3, 3);
        tp.draw(ctx);
      } };
    }
    case "hiss": {
      const tp = textPlan({ fx: "text", text: "HISS", style: "burst", side: "above" }, t, { burst: "#7ad063", text: "#17803d", avoid });
      return tp;
    }
    case "sparkle": {
      // The glints are decoration: clamp them into the frame instead of letting them run off it.
      const s = Math.min(84, Math.max(30, t.w * 1.4)); // at most 84 so the clamp range below is never empty
      const sx = Math.max(s + 3, Math.min(SCENE_W - s - 4, cx)), sy = Math.max((2 * s) / 3 + 3, Math.min(SCENE_H - s / 3 - 4, cyOf(t)));
      return { box: [sx - s - 2, sy - (2 * s) / 3 - 2, sx + s + 3, sy + s / 3 + 3], draw(ctx) { sparkles(ctx, sx, sy, s); } };
    }
    case "mud_splat": { const cy = cyOf(t); return { box: [cx - 28, cy - 18, cx + 28, cy + 18], draw(ctx) {
      const blobs = [[0, -14, 7], [-16, -4, 5], [16, -6, 6], [-8, 10, 4], [10, 12, 5], [-24, 8, 3], [26, 6, 3], [0, 2, 8]];
      blobs.forEach(([dx, dy, r], i) => {
        rect(ctx, i % 2 ? "#5f3b1a" : "#8b5a2b", cx + dx - r / 2, cy + dy - r / 2, r, r);
        rect(ctx, "#3a2410", cx + dx - r / 2, cy + dy + r / 2 - 1, r, 1);
      });
    } }; }
    case "zzz": {
      const x = t.sleepHead !== null ? t.cx - t.w / 2 + 3 : cx + (t.lying ? -t.w * 0.2 : t.dir * t.w * 0.3), y = t.top - 2;
      const zs = [[0, 0, 1], [7, -9, 2], [16, -22, 3]].map(([dx, dy, s]) => [x + dx * t.dir, Math.max(2, y + dy), s]);
      const box = [Math.min(...zs.map((z) => z[0])) - 1, Math.min(...zs.map((z) => z[1])) - 1, Math.max(...zs.map((z) => z[0] + 3 * z[2])) + 1, Math.max(...zs.map((z) => z[1] + 5 * z[2])) + 1];
      return { box, draw(ctx) { zs.forEach(([zx, zy, s]) => pixelText(ctx, "Z", zx, zy, s, "#ffffff")); } };
    }
    case "stink": return { box: [cx - 12, t.top - 30, cx + 29, t.top - 3], draw(ctx) {
      drawSprite(ctx, "stink", cx - 12, t.top - 24, 3);
      drawSprite(ctx, "stink", cx + 8, t.top - 30, 3);
    } };
    case "tap": { const cy = cyOf(t); return { box: [cx - 23, cy - 23, cx + 23, cy + 1], draw(ctx) {
      for (const [dx, dy] of [[-1, 0], [-0.7, -0.7], [0, -1], [0.7, -0.7], [1, 0]]) {
        line(ctx, "#ffffff", cx + dx * 10, cy + dy * 10, cx + dx * 22, cy + dy * 22);
        line(ctx, "#ffd23a", cx + dx * 10 + 1, cy + dy * 10, cx + dx * 20 + 1, cy + dy * 20);
      }
    } }; }
    case "text": return textPlan(spec, t, { avoid });
    default: throw new Error(`fxPlan: unknown fx "${name}"`);
  }
}

/** Every effect of the art as { spec, t, plan }. The boom's target is `t.target`. */
function fxPlans(art, L) {
  const anchors = fxSpecs(art).map((spec) => ({ spec, t: fxAnchor(spec, L, art) }));
  const blast = anchors.find((f) => f.spec.fx === "boom")?.t.target ?? null;
  // Text never covers a head: the head boxes of every drawn actor (not the one a boom replaces).
  const avoid = L.actors.filter((r) => r !== blast).map((r) => headRect(r, L));
  return anchors.map(({ spec, t }) => ({ spec, t, plan: fxPlan(spec, t, avoid) }));
}

/**
 * Pure. The bounding box of every drawn actor, prop and effect of a composable art object, scaled to a canvas of
 * `width` x `height` (default: the logical 192x108), with how much of it the frame cuts off.
 * Returns [{kind: "actor"|"prop"|"fx", index, name, x0, y0, x1, y1, clip}] (actors, then props, then effects) where
 * `clip` is the fraction (0-1) of the box's area outside the canvas, so it is 0 when fully visible. An effect's
 * `name` is "fx:<name>" and covers its solid parts (a glow is not counted); text is clamped into the frame by the
 * engine, so it clips only when it cannot fit. Validates the art first (throws ArtError). A boom replaces its
 * target, which therefore is not drawn and is not listed.
 */
export function artBoxes(art, width = SCENE_W, height = SCENE_H, path = "art") {
  checkArt(art, path);
  const L = layout(art, BGS[art.bg], path);
  const fx = fxPlans(art, L);
  const blast = fx.find((f) => f.spec.fx === "boom")?.t.target ?? null;
  const kx = width / SCENE_W, ky = height / SCENE_H, out = [];
  const add = (kind, index, name, b) => {
    const [x0, y0, x1, y1] = [b[0] * kx, b[1] * ky, b[2] * kx, b[3] * ky];
    const area = (x1 - x0) * (y1 - y0);
    const seen = Math.max(0, Math.min(x1, width) - Math.max(x0, 0)) * Math.max(0, Math.min(y1, height) - Math.max(y0, 0));
    out.push({ kind, index, name, x0, y0, x1, y1, clip: Math.max(0, 1 - seen / area) });
  };
  L.actors.forEach((r, i) => { if (r !== blast) add("actor", i, r.a.who, actorBox(r)); });
  L.props.forEach((q, i) => { if (q !== blast) add("prop", i, q.p.what, q.box); });
  fx.forEach((f, i) => add("fx", i, `fx:${f.spec.fx}${f.spec.text ? ` ${JSON.stringify(f.spec.text)}` : ""}`, f.plan.box));
  return out;
}

/**
 * Pure. Pairs of things that overlap without the art saying why. Two actors, or an actor and a prop that is not
 * held, overlap when their boxes share more than `limit` (default 20%) of the smaller box. Declared relations are
 * exempt: held, worn (head), on, in, sit_on, lying in a bed, hide, hug. Returns
 * [{ a: {kind, index, name}, b: {kind, index, name}, frac }] (frac = shared area / smaller area). Validates first.
 */
export function artOverlaps(art, limit = 0.2, path = "art") {
  checkArt(art, path);
  const L = layout(art, BGS[art.bg], path);
  const blast = fxPlans(art, L).find((f) => f.spec.fx === "boom")?.t.target ?? null;
  const exempt = new Set();
  const key = (x, y) => `${x.kind}${x.i}|${y.kind}${y.i}`;
  const pair = (x, y) => { exempt.add(key(x, y)); exempt.add(key(y, x)); };
  for (const r of L.actors) {
    if (r.hugWith) pair(r, r.hugWith);
    if (r.hidesBehind) pair(r, r.hidesBehind);
    if (r.container) pair(r, r.container);
    if (r.bed) pair(r, r.bed);
    if (r.sitsOn) pair(r, r.sitsOn);
  }
  for (const q of L.props) {
    if (q.y === "head") pair(q, L.actors[holderIndex(art, q.p)]);
    if (q.y === "on") { const t = lookup(art, q.p.on); pair(q, t.kind === "actor" ? L.actors[t.index] : L.props[t.index]); }
  }
  const things = [...L.actors, ...L.props.filter((q) => q.y !== "held")].filter((r) => r !== blast);
  const nm = (r) => ({ kind: r.kind, index: r.i, name: r.kind === "actor" ? r.a.who : r.p.what });
  const out = [];
  for (let i = 0; i < things.length; i++) for (let j = i + 1; j < things.length; j++) {
    const A = things[i], B = things[j];
    if (A.kind === "prop" && B.kind === "prop") continue;
    if (exempt.has(key(A, B))) continue;
    const a = boxOf(A), b = boxOf(B);
    const w = Math.min(a[2], b[2]) - Math.max(a[0], b[0]), h = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
    if (w <= 0 || h <= 0) continue;
    const small = Math.min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]));
    const frac = (w * h) / small;
    if (frac > limit) out.push({ a: nm(A), b: nm(B), frac });
  }
  return out;
}

/** A bubble body may graze a head box by this many logical px before the guard calls it covering. */
const HEAD_HIT_TOLERANCE = 0.5;

/**
 * Pure. Text bubbles (say / burst text, sneeze and hiss text) that cover an actor's head box (the head plus any
 * worn hat; see headRect). The engine places text clear of every head, so this finds only what it could not place
 * (no free spot at the smallest size). Returns [{ fx: {index, name}, actor: {index, name}, w, h }] (w, h = the shared
 * width and height in logical px). The speaker's own head counts. A boom's target is not drawn and not checked.
 * Validates first.
 */
export function artBubbleHeadHits(art, path = "art") {
  checkArt(art, path);
  const L = layout(art, BGS[art.bg], path);
  const plans = fxPlans(art, L);
  const blast = plans.find((f) => f.spec.fx === "boom")?.t.target ?? null;
  const out = [];
  plans.forEach((f, i) => {
    if (!f.plan.bubble) return;
    L.actors.forEach((r, j) => {
      if (r === blast) return;
      const h = headRect(r, L), b = f.plan.bubble;
      if (!boxesTouch(b, h, HEAD_HIT_TOLERANCE)) return;
      out.push({ fx: { index: i, name: `fx:${f.spec.fx}${f.spec.text ? ` ${JSON.stringify(f.spec.text)}` : ""}` }, actor: { index: j, name: r.a.who },
        w: Math.min(b[2], h[2]) - Math.max(b[0], h[0]), h: Math.min(b[3], h[3]) - Math.max(b[1], h[1]) });
    });
  });
  return out;
}

/** Make the canvas the right resolution for the page (HI_RES when it has text, else logical) and scale to it. */
function prepareCanvas(ctx, hi) {
  const s = hi ? HI_RES : 1, cv = ctx.canvas;
  if (cv && typeof cv.width === "number" && (cv.width !== SCENE_W * s || cv.height !== SCENE_H * s)) {
    cv.width = SCENE_W * s; // resizing clears the canvas and resets its state, which is what a new page needs
    cv.height = SCENE_H * s;
  }
  ctx.setTransform(s, 0, 0, s, 0, 0);
  ctx.imageSmoothingEnabled = false;
}

let rodCanvas = null;
/** The rod sprite without its baked-in hanging line (the engine draws a line to the target instead). */
function rodNoLine() {
  if (rodCanvas) return rodCanvas;
  const rows = SPRITES.rod.rows, cv = document.createElement("canvas");
  cv.width = rows[0].length; cv.height = rows.length;
  const c = cv.getContext("2d");
  rows.forEach((row, y) => [...row].forEach((ch, x) => {
    if (ch === "." || ROD_BAKED(x, y)) return;
    c.fillStyle = PALETTE[ch];
    c.fillRect(x, y, 1, 1);
  }));
  rodCanvas = cv;
  return cv;
}

/** Draw a prop through its matrix (held props are rotated into the hand). */
function drawProp(ctx, q) {
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.transform(...q.mat);
  const cv = q.p.what === "rod" && q.p.line_to !== undefined ? rodNoLine() : spriteCanvas(q.p.what);
  ctx.drawImage(cv, 0, 0);
  ctx.restore();
}

/** What goes on the ground behind/around an actor for its pose: shadow and streaks (up), motion lines (run). */
function drawDecor(ctx, r) {
  const b = actorBox(r);
  if (r.decor.includes("up")) {
    ctx.fillStyle = "rgba(0,0,0,0.22)";
    ctx.fillRect(Math.round(r.cx - r.w * 0.3), r.ground - 1, Math.round(r.w * 0.6), 2);
    for (const dx of [-0.2, 0, 0.2]) rect(ctx, "rgba(255,255,255,0.7)", Math.round(r.cx + dx * r.w), b[3] + 2, 1, 5);
  }
  if (r.decor.includes("run")) {
    const dir = r.a.flip ? -1 : 1, x0 = r.cx - dir * (r.w / 2 + 3);
    [0.3, 0.55, 0.8].forEach((f, i) => {
      const len = 10 + i * 3, y = Math.round(b[1] + (b[3] - b[1]) * f);
      const xa = dir > 0 ? x0 - len : x0, xb = xa + len;
      rect(ctx, "rgba(255,255,255,0.85)", Math.max(0, xa), y, Math.max(0, Math.min(SCENE_W, xb) - Math.max(0, xa)), 1);
    });
  }
}

/** Dirt flying where the pickaxe meets the ground (pose dig). */
function drawDirt(ctx, tip) {
  [[-6, -1], [-3, -6], [2, -8], [6, -3], [9, -7], [-9, -5]].forEach(([dx, dy], i) => {
    rect(ctx, i % 2 ? "#8b5a2b" : "#5f3b1a", Math.round(tip[0] + dx), Math.round(tip[1] + dy), 2, 2);
  });
}

/** Draw a composable art object (validated first; throws ArtError naming `path` + field). */
function drawArt(ctx, art, path) {
  const bg = BGS[art.bg];
  bg.draw(ctx);
  const L = layout(art, bg, path);
  const fx = fxPlans(art, L);
  const boom = fx.find((f) => f.spec.fx === "boom");
  const blast = boom ? boom.t.target : null;
  // A boom replaces the thing that blows up (the anchor): the blast is drawn in its place, behind everyone else,
  // and that thing is not drawn. Every other effect is drawn on top.
  for (const q of L.props) if (!q.front && q !== blast) drawProp(ctx, q);
  if (boom) boom.plan.draw(ctx);
  for (const r of L.actors) if (r !== blast) drawDecor(ctx, r);
  for (const r of L.actors) if (r !== blast) drawActor(ctx, r);
  // Everything that goes in front of the actors, in the order it was placed (hat before the sock on the hat).
  const front = L.props.filter((q) => q.front && q !== blast).map((q) => ({ order: q.order, q }));
  for (const r of L.actors) if (r.bed && r !== blast) front.push({ order: r.order + 0.5, bed: r });
  front.sort((x, y) => x.order - y.order);
  for (const it of front) {
    if (it.q) {
      drawProp(ctx, it.q);
      const h = it.q.hand;
      if (h && h.skin) rect(ctx, h.skin, Math.round(h.x - h.k * 0.6), Math.round(h.y - h.k * 0.6), Math.round(h.k * 1.2), Math.round(h.k * 1.2));
      if (it.q.lineTarget && it.q.tipPx) {
        const tb = boxOf(it.q.lineTarget);
        line(ctx, "#f4f4f4", Math.round(it.q.tipPx[0]), Math.round(it.q.tipPx[1]), Math.round((tb[0] + tb[2]) / 2), Math.round(tb[1] + (tb[3] - tb[1]) * 0.15));
      }
    } else {
      // the bed's blanket goes over the lying actor from the shoulders on, raised to cover most of his thickness
      const q = it.bed.bed, { startCol, top } = it.bed.bedCover, cv = spriteCanvas("bed"), { w } = spriteSize("bed");
      const x0 = Math.round(q.cx - q.w / 2 + startCol * q.k), y0 = Math.round(q.foot - q.h + BED.rowTop * q.k);
      ctx.save();
      ctx.imageSmoothingEnabled = false;
      if (top < y0) rect(ctx, PALETTE[SPRITES.bed.rows[BED.rowTop][startCol]], x0, Math.round(top), (w - BED.footCols - startCol) * q.k, y0 - Math.round(top));
      ctx.drawImage(cv, startCol, BED.rowTop, w - startCol, BED.rowBottom - BED.rowTop, x0, y0, (w - startCol) * q.k, (BED.rowBottom - BED.rowTop) * q.k);
      ctx.restore();
    }
  }
  for (const r of L.actors) if (r.decor.includes("dig") && r !== blast) {
    const q = L.props.find((p) => p.holder === r);
    if (q?.tipPx) drawDirt(ctx, [q.tipPx[0], Math.min(q.tipPx[1], bg.ground - 1)]);
  }
  for (const f of fx) if (f.spec.fx !== "boom") f.plan.draw(ctx);
}

/**
 * Draw a page's art onto ctx (logical 192x108): `art` is a scene key (string) or a composable object.
 * An unknown key or name throws (stories must fail loudly). `path` names the field in errors. A page with
 * text effects switches the canvas to HI_RES so the Arial text is crisp; other pages use 192x108.
 */
export function drawScene(ctx, art, path = "art") {
  if (typeof art === "string") {
    const fn = SCENES[art];
    if (!fn) throw new Error(`${path}: Unknown scene key "${art}". Known keys: ${SCENE_KEYS.join(", ")}`);
    prepareCanvas(ctx, false);
    fn(ctx);
    return;
  }
  checkArt(art, path);
  prepareCanvas(ctx, hasText(art));
  drawArt(ctx, art, path);
}
