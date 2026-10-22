// DEV-ONLY page script for app/render.html (used by tools/render_pages.py). Exposes window.__render so the
// tool can draw any page of a story and screenshot #scene. Any failure sets __render.error (the tool fails loudly).
import { loadStory, findRepeatedArt } from "./stories.js";
import { drawScene, SCENE_W, SCENE_H } from "./scenes.js";

window.__render = { ready: false, error: null, pages: 0, texts: [], repeats: [], draw: null };
try {
  const id = new URLSearchParams(location.search).get("story");
  if (!id) throw new Error("render.html needs ?story=ID");
  const story = await loadStory(id);
  const canvas = document.getElementById("scene");
  canvas.width = SCENE_W;
  canvas.height = SCENE_H;
  const ctx = canvas.getContext("2d");
  Object.assign(window.__render, {
    pages: story.pages.length, texts: story.pages.map((p) => p.text), repeats: findRepeatedArt(story),
    draw(i) {
      ctx.clearRect(0, 0, SCENE_W, SCENE_H);
      drawScene(ctx, story.pages[i].art, `${id} page ${i} art`);
    },
  });
  window.__render.ready = true;
} catch (e) {
  window.__render.error = String(e && e.message ? e.message : e);
  window.__render.ready = true;
}
