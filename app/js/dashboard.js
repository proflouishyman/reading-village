// Dad dashboard: accuracy per letter, confusions, tricky words, stories, sessions, and controls.
import { loadProgress, store, saveProgress } from "./store.js";
import { getEvents, getMinecraft, getVillage, getTreasure, getHistory, HISTORY_CSV_URL } from "./api.js";
import { validateHistory, summary, describeLine } from "./historylogic.js";
import { judgeMinecraft } from "./mcstatus.js";
import { validateVillage, validateTreasure, standInsUsed, villagerSprite } from "./villagelogic.js";
import { installTextures, showFatal, h, applyFont, dadNote } from "./ui.js";
import { soundToggleButton } from "./soundui.js";
import { setSoundReporter } from "./sounds.js";
import { LETTERS, accuracy, LETTER_GROUPS, introductionStatus } from "./rules.js";
import { sessionsFrom, letterReport, confusions, trickyWords, smallcapsPasses, wordAccuracy, wordTrend, swapByPercent, craftStats } from "./stats.js";
import { formatClock } from "./util.js";
import { lowercaseOn } from "./constants.js";
import { loadIndex } from "./stories.js";
import { swappedLetters, nextSwapLetter, swapCount, percentForCount, MAX_SWAP_LETTERS } from "./swap.js";
import { loadSwapOrder } from "./data.js";
import { GAMES, GAME_TITLES, deriveLevels, levelNames, loadLevels } from "./levels.js";
import { loadFamily, fam, childName, grownUpPoss } from "./family.js";

const root = document.getElementById("app");
setSoundReporter(dadNote);

function fatal(title, err) {
  showFatal(title, err instanceof Error ? `${err.message}\n\n${err.stack ?? ""}` : String(err));
}
window.addEventListener("error", (e) => fatal("Something broke", e.error ?? e.message));
window.addEventListener("unhandledrejection", (e) => fatal("Something broke", e.reason));

const pct = (x) => (x === null ? "—" : `${Math.round(x * 100)}%`);

/** Inline SVG sparkline of per-session accuracy (0..1). */
function spark(values) {
  if (values.length === 0) return h("span", { class: "muted", text: "no data" });
  const w = 120, hh = 28;
  const pts = values.map((v, i) => `${values.length === 1 ? w / 2 : (i * (w - 8)) / (values.length - 1) + 4},${hh - 3 - v * (hh - 6)}`);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${hh}`);
  svg.setAttribute("class", "spark");
  svg.innerHTML = `<polyline fill="none" stroke="#2f7d32" stroke-width="2" points="${pts.join(" ")}"/>` +
    pts.map((p) => `<circle r="4" fill="#2f7d32" cx="${p.split(",")[0]}" cy="${p.split(",")[1]}"/>`).join("");
  return svg;
}

const table = (head, rows) => h("table", {}, h("thead", {}, h("tr", {}, head.map((t) => h("th", { text: t })))),
  h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))));
const section = (title, ...kids) => h("section", { class: "panel" }, h("h2", { text: title }), ...kids);

/** One fetch whose failure becomes a value (shown LOUDLY in the Minecraft panel), not a dead dashboard. */
const attempt = (fn) => fn().then((value) => ({ value }), (error) => ({ error }));

/**
 * Dad-only calls for the import and website panels (they never run in the static web copy, so they use fetch
 * directly). Any failure throws an Error carrying the server's message, never a silent default.
 */
async function dadApi(method, path, body) {
  let r;
  try {
    r = await fetch(path, { method, ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) });
  } catch (e) {
    throw new Error(`server not reachable (${e.message})`);
  }
  let payload;
  try { payload = await r.json(); } catch { throw new Error(`server said HTTP ${r.status} with a reply that is not JSON`); }
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${payload.error ?? "no details"}`);
  return payload;
}

/**
 * "Import from Mom's house": pick the export file Mom emailed; it is posted whole to /api/import. The counts are
 * shown big on success; ANY error is a red banner with the server's message (and nothing was changed).
 */
function importPanel() {
  const out = h("div", { id: "import-result" });
  const input = h("input", { type: "file", accept: ".json,application/json", id: "import-file" });
  const btn = h("button", { class: "btn small", id: "import-btn", text: "Import this file", onclick: async () => {
    out.replaceChildren();
    const file = input.files[0];
    if (!file) { out.append(h("div", { class: "mc-banner", role: "alert", text: "IMPORT NOT DONE: choose the export file first." })); return; }
    btn.disabled = true;
    try {
      let json;
      try { json = JSON.parse(await file.text()); } catch (e) { throw new Error(`${file.name} is not a JSON file (${e.message})`); }
      const r = await dadApi("POST", "/api/import", json);
      const treasure = r.treasure.map((t) => t.label).join(", ") || "none";
      const lv = r.game_level_ups.map((g) => `${g.game} level ${g.level}`).join(", ") || "none";
      out.append(h("div", { class: "import-ok", role: "status" },
        h("p", { text: r.already_imported ? `ALREADY IMPORTED earlier (${r.events_new} new, ${r.duplicates} duplicate events then). Nothing changed.`
                                          : `IMPORTED: ${r.events_new} new events, ${r.duplicates} already there, ${r.emeralds_added} emeralds added.` }),
        r.already_imported ? null : h("p", { text: `Surprises: ${treasure}. Level-ups: ${lv}.` })));
      if (r.house_conflicts.length) {
        const cells = r.house_conflicts.map((c) => `(${c.x},${c.y}): kept ${c.dads}, ${fam().away_label} had ${c.moms}`).join("; ");
        out.append(h("div", { class: "mc-banner", role: "alert", text: `HOUSE CELLS SKIPPED (${r.house_conflicts.length}), ${grownUpPoss()} blocks were kept: ${cells}` }));
      }
      if (!r.already_imported) setTimeout(load, 2500);  // show the new numbers; the website update starts by itself
    } catch (e) {
      out.append(h("div", { class: "mc-banner", role: "alert", text: `IMPORT FAILED, NOTHING WAS CHANGED: ${e.message}` }));
    } finally {
      btn.disabled = false;
    }
  } });
  const el = section(`Import from ${fam().away_label}`, h("p", { class: "muted", text: `Choose the reading-village-....json file emailed from ${fam().away_label}, then import it. It can be imported twice safely.` }),
    h("div", {}, input, " ", btn), out);
  el.id = "import-panel";
  return el;
}

/**
 * "Mom's-house website": the publish status (GET /api/web) and the Update button (POST /api/web/publish). A failed
 * publish, a missing or broken config/web.json is a red box. While a publish runs the status is polled.
 */
function webPanel(res) {
  const el = section(`${fam().away_label} website`);
  el.id = "web-panel";
  const paint = (r) => {
    const kids = [];
    if (r.error && !r.value) {
      el.classList.add("mc-panel-loud");
      kids.push(h("div", { class: "mc-banner", role: "alert", text: `WEBSITE STATUS UNAVAILABLE: ${r.error.message}` }));
    } else {
      const w = r.value;
      el.classList.toggle("mc-panel-loud", w.state === "failed" || (w.state === "disabled" && w.error !== null));
      if (w.state === "failed") kids.push(h("div", { class: "mc-banner", role: "alert", text: `WEBSITE UPDATE FAILED: ${w.error}` }));
      else if (w.state === "disabled" && w.error) kids.push(h("div", { class: "mc-banner", role: "alert", text: `WEBSITE PUBLISHING IS OFF: ${w.error}` }));
      const when = w.at ? ` at ${w.at.replace("T", " ").slice(0, 16)}` : "";
      const line = { idle: "Not published since the server started.", running: "Updating the website now...", ok: `Website updated${when} (snapshot ${w.snapshot_id}).`,
        failed: `Last update failed${when}.`, disabled: "Publishing is switched off." }[w.state];
      kids.push(h("p", { id: "web-state", text: `${line}${w.enabled ? (w.auto ? " Updates by itself after each session and each import." : " Automatic updates are off.") : ""}` }));
      const btn = h("button", { class: "btn small", id: "web-update", text: `Update ${fam().away_label} website`, onclick: async () => {
        btn.disabled = true;
        try { paint({ value: await dadApi("POST", "/api/web/publish") }); poll(); } catch (e) { paint({ error: e }); }
      } });
      btn.disabled = w.state === "running" || w.state === "disabled";
      kids.push(btn);
      if (w.state === "running") poll();
    }
    el.replaceChildren(h("h2", { text: `${fam().away_label} website` }), ...kids);
  };
  let timer = null;
  const poll = () => {
    if (timer) return;
    timer = setTimeout(async () => {
      timer = null;
      try { paint({ value: await dadApi("GET", "/api/web") }); } catch (e) { paint({ error: e }); }
    }, 1500);
  };
  paint(res);
  return el;
}

/**
 * The Minecraft panel (Dad only, plain text): delivery status, pending and failed sends, any problem, the village
 * (level, points, bells, villagers) and the pile by state. Anything wrong is a red banner at the top.
 */
function minecraftPanel({ mc, village, pile }) {
  const banners = [];
  const body = [];
  let loud = false;
  const fail = (what, r) => { loud = true; banners.push(`${what} UNAVAILABLE: ${r.error.message}`); };
  if (mc.error) fail("MINECRAFT STATUS", mc);
  else {
    let j;
    try { j = judgeMinecraft(mc.value); } catch (e) { j = { loud: true, lines: [`MINECRAFT STATUS MALFORMED: ${e.message}`] }; }
    if (j.loud) loud = true;
    for (const line of j.lines) if (j.loud && /FAILED|PROBLEM|MALFORMED|worker is NOT|OFF/.test(line)) banners.push(line);
      else body.push(h("p", { text: line }));
    const m = mc.value;
    if (Array.isArray(m.pending) && m.pending.length) body.push(table(["Waiting", "What", "Tries", "Last error"], m.pending.map((d) => [d.id, d.label, String(d.attempts), d.last_error ?? ""])));
    if (Array.isArray(m.failed) && m.failed.length) body.push(table(["FAILED", "What", "Tries", "Error"], m.failed.map((d) => [d.id, d.label, String(d.attempts), d.last_error ?? ""])));
    if (Array.isArray(m.recent) && m.recent.length) body.push(h("p", { class: "muted", text: `Last arrived: ${m.recent.map((d) => d.label).join(", ")} (${m.chests} chest${m.chests === 1 ? "" : "s"} placed)` }));
  }
  if (village.error) fail("VILLAGE", village);
  else {
    const v = village.value;
    const have = v.professions.filter((p) => p.unlocked).map((p) => p.name);
    body.push(h("p", { text: `Village: ${v.points} reading points; bells ${v.bells.available} available (${v.bells.earned} earned, ${v.bells.spent} spent); ${v.wallet.emerald} emeralds.` }));
    const pr = v.promotions;
    body.push(h("p", { text: `Promotions: ${pr.earned} earned from ${pr.spent} emeralds spent (next at ${pr.next_at}), ${pr.used} used, ${pr.available} waiting for ${childName()} to choose. Villager levels: ${v.professions.filter((p) => p.unlocked).map((p) => `${p.name} ${p.level_name}`).join(", ") || "none yet"}.` }));
    body.push(h("p", { text: `Villagers (${have.length} of ${v.professions.length}): ${have.join(", ") || "none yet"}.` }));
    const names = v.professions.flatMap((p) => [p.job_block_sprite, villagerSprite(p), ...p.offers.map((o) => o.sprite)]);
    const stand = standInsUsed(names);
    if (stand.length) body.push(h("p", { class: "muted", text: `Art gap: ${stand.length} item pictures are stand-ins until real sprites are drawn: ${stand.join(", ")}.` }));
  }
  if (pile.error) fail("TREASURE PILE", pile);
  else {
    const counts = { kept: 0, on_the_way: 0, in_chest: 0, failed: 0 };
    for (const t of pile.value.treasure) counts[t.state] += 1;
    body.push(h("p", { text: `Treasure Pile: ${counts.kept} kept, ${counts.on_the_way} on the way, ${counts.in_chest} in the chest, ${counts.failed} failed.` }));
    if (pile.value.problem) { loud = true; banners.push(`PROBLEM: ${pile.value.problem}`); }
  }
  const el = section("Minecraft", ...banners.map((b) => h("div", { class: "mc-banner", role: "alert", text: b })), ...body);
  if (loud) el.classList.add("mc-panel-loud");
  el.id = "mc-panel";
  return el;
}

/**
 * "Rewards history": totals (ever earned per resource, ever delivered per item, villagers, levels), the full
 * chronological list (oldest first) and the CSV download. A history that cannot be read or fails validation is a red
 * banner, never an empty or partial list.
 */
function historyPanel(hist) {
  const el = section("Rewards history");
  el.id = "history-panel";
  if (hist.error) {
    el.classList.add("mc-panel-loud");
    el.append(h("div", { class: "mc-banner", role: "alert", text: `REWARDS HISTORY UNAVAILABLE: ${hist.error.message}` }));
    return el;
  }
  const lines = hist.value.lines;
  const t = summary(hist.value);
  const kv = (m) => Object.entries(m).map(([k, n]) => `${n} ${k}`).join(", ") || "none yet";
  el.append(
    h("p", { id: "history-totals", text: `Ever earned: ${kv(t.earned)}. Ever spent: ${kv(t.spent)}.` }),
    h("p", { id: "history-sent", text: `Ever sent to Minecraft: ${kv(t.sent)}. Confirmed delivered: ${kv(t.delivered)}.` }),
    h("p", { text: `Villagers unlocked (${t.villagers.length}): ${t.villagers.join(", ") || "none yet"}. Levels reached: ${t.levels.join(", ") || "none yet"}.` }),
    t.failed ? h("div", { class: "mc-banner", role: "alert", text: `${t.failed} DELIVERY FAILED line(s) in the history.` }) : null,
    h("p", {}, h("a", { class: "btn small", id: "history-csv", href: HISTORY_CSV_URL, download: "rewards_history.csv", text: "Download CSV" }), ` ${lines.length} lines, oldest first.`),
    lines.length ? h("div", { class: "history-scroll" }, table(["When", "What", "Wallet after"], lines.map((l) => [
      l.ts.replace("T", " ").slice(0, 19), h("span", { class: `hist-${l.kind}`, text: describeLine(l) }),
      l.wallet_after ? Object.entries(l.wallet_after).filter(([, n]) => n).map(([k, n]) => `${n} ${k}`).join(", ") : "—"])))
      : h("p", { class: "muted", text: "Nothing earned yet." }));
  return el;
}

/**
 * "Levels" panel: per game the level in force, what that level is, and the last-10 independent count toward the next
 * (derived from events, docs/design.md "Levels"); a Dad override is named, and is changed in Settings.
 */
function levelsPanel(events, cfg, progress) {
  const derived = deriveLevels(events, cfg);
  const override = progress.settings.level_override ?? {};
  const row = (g) => {
    const d = derived[g];
    const o = override[g];
    const level = o ?? d.level;
    const toNext = d.level >= d.max ? "top level" : `${d.independent} of ${d.need} right (${d.attempts} tries at level ${d.level}; needs ${d.window})`;
    return [GAME_TITLES[g], o === undefined ? `${level} of ${d.max}` : `${level} of ${d.max} (${grownUpPoss()} override; earned ${d.level})`, levelNames(g)[level - 1], toNext];
  };
  const el = section("Levels", table(["Game", "Level", "What it is", "Last 10 independent"], GAMES.map(row)),
    h("p", { class: "muted", text: "A level rises after at least 10 tries at it with 8 of the last 10 right on his own. Change it in Settings." }));
  el.id = "levels-panel";
  return el;
}

function render(events, storyIds, swapOrder, mcData, hist, levelsCfg, webStatus) {
  const p = store.progress;
  const status = introductionStatus(p.active_letters, p.letter_stats);

  // Letters table
  const rows = LETTERS.map((l) => {
    const st = p.letter_stats[l];
    const rep = letterReport(events, l);
    return [
      h("b", { class: "letter-cell", text: l }),
      p.active_letters.includes(l) ? "active" : "",
      pct(accuracy(st)),
      st ? `${pct(st.total_correct / st.total_tries)} (${st.total_correct}/${st.total_tries})` : "—",
      spark(rep.trend),
      `${rep.independent} / ${rep.assisted} / ${rep.miss}`,
    ];
  });

  // Controls
  const boxes = LETTERS.map((l) => {
    const cb = h("input", { type: "checkbox", id: `act-${l}` });
    cb.checked = p.active_letters.includes(l);
    return h("label", { class: "chk" }, cb, h("span", { text: l }));
  });
  const applyBtn = h("button", { class: "btn small", text: "Apply active letters", onclick: async () => {
    const chosen = LETTERS.filter((l, i) => boxes[i].querySelector("input").checked);
    if (chosen.length === 0) { alert("Pick at least one letter."); return; }
    await saveProgress((q) => { q.active_letters = chosen; });
    load();
  } });
  const fontBtn = h("button", { class: "btn small", text: p.settings.font === "opendyslexic" ? "Font: OpenDyslexic (click for plain)" : "Font: plain (click for OpenDyslexic)", onclick: async () => {
    await saveProgress((q) => { q.settings.font = q.settings.font === "opendyslexic" ? "system" : "opendyslexic"; });
    applyFont(store.progress.settings.font);
    load();
  } });

  const lcOn = lowercaseOn(p);
  const lcBtn = h("button", { class: "btn small", text: lcOn ? "Turn lowercase track off" : "Start lowercase track", onclick: async () => {
    if (!lcOn && !confirm("Turn the lowercase track on? Home will show a Lowercase track button (Bridge Match, Letter Mine, lowercase story).")) return;
    await saveProgress((q) => { q.settings.lowercase_track = lcOn ? "off" : "on"; });
    load();
  } });
  // Swap-in controls: the slider counts whole letters (0..26, one step = one letter); the saved setting is
  // the percent round(n*100/26). Nothing advances automatically.
  const pctNow = p.settings.lowercase_percent ?? 0;
  const nNow = swapCount(swapOrder, pctNow);
  const letterInfo = h("span", {});
  const showLetters = (n) => {
    const pc = percentForCount(n);
    letterInfo.replaceChildren(
      `${n} of ${MAX_SWAP_LETTERS} letters (${pc}%): lowercase = ${swappedLetters(swapOrder, pc).join(" ") || "(none)"}; next letter: ${nextSwapLetter(swapOrder, pc) ?? "(none, all swapped in)"}`);
  };
  showLetters(nNow);
  const slider = h("input", { type: "range", min: "0", max: String(MAX_SWAP_LETTERS), step: "1", value: String(nNow) });
  slider.addEventListener("input", () => showLetters(Number(slider.value)));
  const saveBtn = h("button", { class: "btn small", text: "Save letters", onclick: async () => {
    const percent = percentForCount(Number(slider.value));
    await saveProgress((q) => { q.settings.lowercase_percent = percent; });
    load();
  } });
  const swapRows = swapByPercent(events);
  const passes = smallcapsPasses(events);
  const wa = wordAccuracy(events, 20);
  const cs = craftStats(events);
  const f1 = (x) => (x === null ? "—" : x.toFixed(1));

  const doneCount = (track) => events.filter((e) => e.type === "story_done" && e.track === track).length;
  const sessions = sessionsFrom(events);

  root.replaceChildren(
    h("header", { class: "dash-head" }, h("h1", { text: `${grownUpPoss()} Dashboard` }), h("a", { class: "btn small", href: "./", text: "Back to the game" })),
    h("div", { class: "dash-grid" },
      importPanel(),
      webPanel(webStatus),
      minecraftPanel(mcData),
      levelsPanel(events, levelsCfg, p),
      historyPanel(hist),
      section("Small-caps fluency",
        passes.length ? table(["Date", "Story", "Pages", "Minutes", "Sec / page", "Tricky taps", "Taps / 10 pages"],
          passes.map((r) => [r.date, r.story, String(r.pages), (r.seconds / 60).toFixed(1), f1(r.secPerPage), String(r.taps), f1(r.tapsPer10)]))
          : h("p", { class: "muted", text: "No small-caps story passes yet." }),
        h("p", { text: wa ? `Word Blocks (small caps), last ${wa.n}: ${wa.correct} read without help (${pct(wa.share)}).` : "No Word Blocks small-caps words yet." }),
        h("div", {}, "Word accuracy per session: ", spark(wordTrend(events))),
        h("p", { text: cs ? `Crafting: ${cs.total} crafted, ${cs.total - cs.assisted} without help (${pct(cs.independentShare)}); most crafted: ${cs.words.slice(0, 3).map((w) => `${w.word} x${w.n}`).join(", ")}.` : "No crafting yet." }),
        h("div", { class: "spacer" }), lcBtn, " ", soundToggleButton()),
      section("Letter swap-in (lowercase track)",
        h("div", {}, slider, " ", saveBtn), h("p", {}, letterInfo),
        h("p", { class: "muted", text: `Saved: ${nNow} letters (${pctNow}%).` }),
        swapRows.length ? table(["Percent", "Pages", "Sec / page", "Tricky taps / 10 pages"],
          swapRows.map((r) => [`${r.percent}%`, String(r.pages), f1(r.secPerPage), f1(r.tapsPer10)]))
          : h("p", { class: "muted", text: "No swap-in reading yet." })),
      section("Letters",
        table(["", "", "Last 10", "All time", "Per-session trend", "Independent / assisted / miss"], rows)),
      section("Active letters and the rule",
        h("p", { text: `Order: ${LETTER_GROUPS.map((g) => g.join("")).join(" → ")}. Next group is added when every active letter is at 80% or better over its last 10 tries.` }),
        h("p", { text: status.next ? `Next to add: ${status.next.join(", ")}. ${status.waitingOn.length ? `Still waiting on: ${status.waitingOn.join(", ")}.` : "All active letters are mastered; it is added at the next session start."}` : "All letters are active." }),
        h("div", { class: "chk-row" }, boxes), applyBtn, h("div", { class: "spacer" }), fontBtn),
      section("Letters he mixes up (Bridge Match)",
        confusions(events).length ? table(["Target", "Clicked instead", "Times"], confusions(events).map((c) => [c.target, c.chosen, String(c.n)]))
          : h("p", { class: "muted", text: "No mix-ups recorded yet." })),
      section("Tricky words",
        trickyWords(events).length ? table(["Word", "Times tapped"], trickyWords(events).map((w) => [w.word, String(w.n)]))
          : h("p", { class: "muted", text: "None tapped yet." })),
      section("Stories",
        h("p", { text: `Passes finished — small caps: ${doneCount("smallcaps")}, lowercase: ${doneCount("lowercase")}.` }),
        table(["Story", "Small caps", "Lowercase", "Resume page"], storyIds.map((id) => {
          const s = p.stories[id];
          return [id, s?.smallcaps_done ? "done" : "—", s?.lowercase_done ? "done" : "—", s ? String(s.resume_page + 1) : "—"];
        }))),
      section("Sessions",
        sessions.length ? table(["Started", "Length", "Events"], sessions.slice().reverse().map((s) =>
          [s.start.replace("T", " ").slice(0, 16), `${formatClock(s.seconds)}${s.ended ? "" : " (not closed)"}`, String(s.events)]))
          : h("p", { class: "muted", text: "No sessions yet." }))));
}

async function load() {
  try {
    installTextures();
    await loadFamily();
    document.title = `${grownUpPoss()} Dashboard`;
    await loadProgress();
    applyFont(store.progress.settings.font);
    const [events, storyIds, swapOrder, levelsCfg, mc, village, pile, hist, webStatus] = await Promise.all([getEvents(), loadIndex(), loadSwapOrder(), loadLevels(),
      attempt(getMinecraft), attempt(() => getVillage().then((v) => validateVillage(v))), attempt(() => getTreasure().then((t) => validateTreasure(t))),
      attempt(() => getHistory().then((b) => validateHistory(b))), attempt(() => dadApi("GET", "/api/web"))]);
    render(events, storyIds, swapOrder, { mc, village, pile }, hist, levelsCfg, webStatus);
  } catch (e) {
    fatal("Dashboard could not load", e);
  }
}

load();
