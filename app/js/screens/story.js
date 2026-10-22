// Story: one sentence per page with a scene, in small caps or lowercase; resumes where left.
import { renderWords } from "../smallcaps.js";
import { loadIndex, loadStory } from "../stories.js";
import { drawScene, SCENE_W, SCENE_H } from "../scenes.js";
import { commitUntilSaved, earnRates } from "../store.js";
import { spriteElement, itemSprite } from "../sprites.js";
import { stageLayout, interlude } from "../layout.js";
import { playFanfare, playSparkle } from "../sounds.js";
import { h, popReward, setKid } from "../ui.js";
import { swappedLetters } from "../swap.js";
import { childName } from "../family.js";

/** Stories whose small-caps pass is done (the only ones offered in lowercase or swap-in); may be empty. */
function progressEligible(ids, progress) {
  return ids.filter((i) => progress.stories[i]?.smallcaps_done);
}

/** Lowercase pass: the first eligible story whose lowercase is not done (else re-read the first eligible one). */
function lowercasePass(eligible, progress) {
  return eligible.find((i) => !progress.stories[i].lowercase_done) ?? eligible[0];
}

/**
 * The lowercase track with no finished small-caps story is a legitimate state, not an error: the child sees a
 * calm small-caps message and goes Home; Dad's bar says why. Resolves "quit" (the stage was not run).
 */
async function nothingToReadYet(app) {
  await interlude(app.root, {
    title: "Read a story in small caps first!", buttonText: "OK", sprite: "pig",
    dadNote: `The lowercase track only offers stories ${childName()} has already finished in small caps. Finish one in Story (small caps), then come back.`,
  });
  return "quit";
}

/** Let Dad/the child pick any story to read or re-read; resolves to a story id, or "quit". */
async function pickStory(app, ids, swap) {
  const stories = await Promise.all(ids.map(loadStory));
  const L = stageLayout(app.root, { title: "Pick a story", dadHint: "Re-reading a story in small caps is good practice." });
  L.disableButtons();
  return new Promise((resolve) => {
    L.quitted.then(() => resolve("quit"));
    const firstNew = stories.find((s) => !app.store.progress.stories[s.id]?.smallcaps_done)?.id;
    L.play.replaceChildren(h("div", { class: "story-pick" }, stories.map((s) => {
      const done = app.store.progress.stories[s.id]?.smallcaps_done;
      return h("button", { class: "btn big", onclick: () => resolve(s.id),
        kid: `${s.title}${swap ? "" : done ? " (read again)" : s.id === firstNew ? " (next)" : ""}` });
    })));
  });
}

/**
 * opts.track "smallcaps" (with opts.pick: choose any story), "lowercase" (only stories whose small-caps
 * pass is done) or "swap" (letter swap-in: pick any story whose small-caps pass is done; rendered at
 * settings.lowercase_percent; always a replay-style read that pays earn.story_replay_emerald, logs swap_page per page and swap_done at the end, which earns a replay surprise). A track already finished for the story is a
 * replay: re-read from page 0, pays earn.story_replay_emerald instead of earn.story_first_emerald, and leaves progress untouched.
 */
export async function run(app, opts) {
  if (!opts || !["smallcaps", "lowercase", "swap"].includes(opts.track)) throw new Error(`story: bad track ${opts?.track}`);
  const ids = await loadIndex();
  const progress = app.store.progress;
  const swap = opts.track === "swap";
  const percent = progress.settings.lowercase_percent ?? 0; // missing reads as 0 (documented default)
  const lowerSet = swap ? new Set(swappedLetters(app.swapOrder, percent)) : null;
  const eligible = progressEligible(ids, progress);
  if (opts.track !== "smallcaps" && eligible.length === 0) return nothingToReadYet(app);
  const id = swap ? await pickStory(app, eligible, true) : opts.track === "lowercase" ? lowercasePass(eligible, progress) : opts.pick ? await pickStory(app, ids) : ids.find((i) => !progress.stories[i]?.smallcaps_done) ?? ids[0];
  if (id === "quit") return "quit";
  const replay = swap || Boolean(progress.stories[id]?.[`${opts.track}_done`]);
  const pass = { id, track: opts.track };
  const story = await loadStory(pass.id);
  const { track } = pass;
  const eventTrack = swap ? "lowercase" : track; // swap-in is part of the lowercase track in the log

  // Create the progress entry the first time this story is opened (explicit, matches the contract).
  if (!app.store.progress.stories[story.id]) {
    await commitUntilSaved(null, (p) => {
      p.stories[story.id] = { smallcaps_done: false, lowercase_done: false, resume_page: 0 };
    });
  }

  const L = stageLayout(app.root, {
    title: `${story.title} — ${swap ? `Swap-in ${percent}%` : track === "smallcaps" ? "Pass 1: small caps" : "Pass 2: lowercase"}`,
    dadHint: `Tap a word ${childName()} finds tricky: a tiny pickaxe marks it for you.`,
  });
  L.disableButtons();
  let page = replay ? 0 : Math.min(app.store.progress.stories[story.id].resume_page, story.pages.length - 1);

  return new Promise((resolve) => {
    // Once Dad taps Home the stage is over: a save still in flight must not pop up the story-done screen.
    let active = true;
    L.quitted.then(() => { active = false; resolve("quit"); });
    const canvas = h("canvas", { class: "scene", width: SCENE_W, height: SCENE_H });
    const textEl = h("div", { class: `story-text ${swap ? "mixed" : track}` });
    const counter = h("div", { class: "page-count dad-only", text: "" });
    const back = h("button", { class: "btn nav", kid: "◀ Back", onclick: () => go(page - 1) });
    const next = h("button", { class: "btn nav primary", onclick: () => advance() });
    L.play.replaceChildren(canvas, textEl, h("div", { class: "nav-row" }, back, counter, next));

    textEl.addEventListener("click", (ev) => {
      const w = ev.target.closest(".w");
      if (!w || w.classList.contains("tricky")) return;
      w.classList.add("tricky");
      w.prepend(h("span", { class: "pick" }, spriteElement("pickaxe", 2)));
      commitUntilSaved({ type: "tricky_word", item: w.dataset.word, story_id: story.id, track: eventTrack, ...(swap ? { percent } : {}) }, null);
    });

    function draw() {
      const p = story.pages[page];
      drawScene(canvas.getContext("2d"), p.art); // throws loudly on a bad key
      textEl.innerHTML = renderWords(p.text, swap ? "mixed" : track, lowerSet);
      counter.textContent = `page ${page + 1} / ${story.pages.length}`;
      back.style.visibility = page === 0 ? "hidden" : "visible";
      setKid(next, page === story.pages.length - 1 ? "The end ▶" : "Next ▶");
    }

    function go(i) {
      page = i;
      draw();
    }

    async function advance() {
      next.disabled = true;
      const last = page === story.pages.length - 1;
      const pageEvent = swap ? { type: "swap_page", track: eventTrack, story_id: story.id, page, percent } : { type: "story_page", track, story_id: story.id, page };
      await commitUntilSaved(pageEvent, (p) => {
        if (!last && !replay) p.stories[story.id].resume_page = page + 1;
      });
      if (!active) return;
      if (!last) {
        go(page + 1);
        next.disabled = false;
        return;
      }
      const firstTime = !replay;
      const rates = earnRates();
      const emeralds = firstTime ? rates.story_first_emerald : rates.story_replay_emerald;
      await commitUntilSaved(swap ? { type: "swap_done", track: eventTrack, story_id: story.id, percent } : { type: "story_done", track, story_id: story.id }, (p) => {
        p.inventory.emerald += emeralds; // first pass and replay both pay emeralds now (config earn.*)
        if (!firstTime) return; // replay: reward only, progress untouched
        const s = p.stories[story.id];
        s[`${track}_done`] = true;
        s.resume_page = 0;
      });
      if (!active) return;
      playFanfare();
      if (firstTime) playSparkle(1.0); // the emerald, sparkling over the end of the fanfare
      const done = interlude(app.root, {
        title: firstTime ? "You finished the story!" : "Great reading!",
        body: `${emeralds} emeralds for your village!`,
        buttonText: "Continue",
        sprite: itemSprite("emerald"),
      });
      popReward(app.root.querySelector(".interlude"), itemSprite("emerald"));
      await done;
      resolve("done");
    }

    draw();
  });
}
