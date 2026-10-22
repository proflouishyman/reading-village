// Pure statistics for the Dad dashboard, computed from events.jsonl contents.

/** Sessions in start order: {id, start, end|null, seconds, ended, events}. */
export function sessionsFrom(events) {
  const by = new Map();
  for (const e of events) {
    if (!by.has(e.session_id)) by.set(e.session_id, { id: e.session_id, start: e.ts, end: null, last: e.ts, events: 0 });
    const s = by.get(e.session_id);
    s.events += 1;
    s.last = e.ts;
    if (e.type === "session_end") s.end = e.ts;
  }
  return [...by.values()].map((s) => {
    const endTs = s.end ?? s.last;
    return { id: s.id, start: s.start, end: s.end, ended: s.end !== null, events: s.events,
      seconds: Math.max(0, Math.round((Date.parse(endTs) - Date.parse(s.start)) / 1000)) };
  });
}

/** Per-letter numbers from card+match events: independent/assisted/miss counts and per-session accuracy. */
export function letterReport(events, letter) {
  const mine = events.filter((e) => (e.type === "card" || e.type === "match") && e.item === letter);
  const count = (r) => mine.filter((e) => e.result === r).length;
  const sessions = new Map();
  for (const e of mine) {
    const s = sessions.get(e.session_id) ?? { tries: 0, correct: 0 };
    s.tries += 1;
    s.correct += e.result === "correct" ? 1 : 0;
    sessions.set(e.session_id, s);
  }
  return {
    independent: count("correct"), assisted: count("assisted"), miss: count("miss"),
    trend: [...sessions.values()].map((s) => s.correct / s.tries),
  };
}

/** Confusion pairs from match misses: [{target, chosen, n}] most frequent first. */
export function confusions(events) {
  const m = new Map();
  for (const e of events) {
    if (e.type !== "match" || e.result !== "miss") continue;
    const k = `${e.item}|${e.chosen}`;
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  return [...m.entries()].map(([k, n]) => ({ target: k.split("|")[0], chosen: k.split("|")[1], n })).sort((a, b) => b.n - a.n);
}

/** Tricky words with counts, most frequent first. */
export function trickyWords(events) {
  const m = new Map();
  for (const e of events) if (e.type === "tricky_word") m.set(e.item, (m.get(e.item) ?? 0) + 1);
  return [...m.entries()].map(([word, n]) => ({ word, n })).sort((a, b) => b.n - a.n || a.word.localeCompare(b.word));
}

/**
 * Small-caps story passes for the fluency panel, oldest first. One row per (session, story): pages =
 * story_page events, seconds = first to last story_page timestamp, secPerPage = seconds / (pages - 1)
 * (the time before the first tap is not logged; null for a single page), taps = small-caps tricky_word
 * events for that story in that session, tapsPer10 = taps / pages * 10.
 */
export function smallcapsPasses(events) {
  const by = new Map();
  for (const e of events) {
    if (e.track !== "smallcaps" || (e.type !== "story_page" && e.type !== "tricky_word")) continue;
    const k = `${e.session_id}|${e.story_id}`;
    if (!by.has(k)) by.set(k, { start: e.ts, last: e.ts, story: e.story_id, pages: 0, taps: 0, firstPage: null, lastPage: null });
    const r = by.get(k);
    if (e.type === "tricky_word") { r.taps += 1; continue; }
    r.pages += 1;
    r.firstPage ??= e.ts;
    r.lastPage = e.ts;
  }
  return [...by.values()].filter((r) => r.pages > 0).map((r) => {
    const seconds = Math.round((Date.parse(r.lastPage) - Date.parse(r.firstPage)) / 1000);
    return { date: r.start.slice(0, 10), story: r.story, pages: r.pages, seconds,
      secPerPage: r.pages > 1 ? seconds / (r.pages - 1) : null, taps: r.taps, tapsPer10: (r.taps / r.pages) * 10 };
  });
}

/** Small-caps Word Blocks: independent-correct share of the last n words ({n, correct, share}); null if none. */
export function wordAccuracy(events, n = 20) {
  const last = events.filter((e) => e.type === "word" && e.track === "smallcaps").slice(-n);
  if (last.length === 0) return null;
  const correct = last.filter((e) => e.result === "correct").length;
  return { n: last.length, correct, share: correct / last.length };
}

/** Per-session small-caps word accuracy (independent-correct share), in session order, for a trend line. */
export function wordTrend(events) {
  const by = new Map();
  for (const e of events) {
    if (e.type !== "word" || e.track !== "smallcaps") continue;
    const s = by.get(e.session_id) ?? { n: 0, c: 0 };
    s.n += 1;
    s.c += e.result === "correct" ? 1 : 0;
    by.set(e.session_id, s);
  }
  return [...by.values()].map((s) => s.c / s.n);
}

/**
 * Swap-in fluency per percent, ascending: pages, seconds per page (sum of first-to-last tap seconds over
 * sum of (pages - 1), per session+story pass) and tricky taps per 10 pages (taps / pages * 10).
 */
export function swapByPercent(events) {
  const passes = new Map();
  for (const e of events) {
    if (e.type !== "swap_page" && !(e.type === "tricky_word" && e.percent !== undefined)) continue;
    const k = `${e.session_id}|${e.story_id}|${e.percent}`;
    const r = passes.get(k) ?? { percent: e.percent, pages: 0, taps: 0, first: null, last: null };
    passes.set(k, r);
    if (e.type === "tricky_word") { r.taps += 1; continue; }
    r.pages += 1;
    r.first ??= e.ts;
    r.last = e.ts;
  }
  const by = new Map();
  for (const r of passes.values()) {
    if (r.pages === 0) continue;
    const a = by.get(r.percent) ?? { percent: r.percent, pages: 0, taps: 0, seconds: 0, gaps: 0 };
    a.pages += r.pages;
    a.taps += r.taps;
    a.seconds += (Date.parse(r.last) - Date.parse(r.first)) / 1000;
    a.gaps += r.pages - 1;
    by.set(r.percent, a);
  }
  return [...by.values()].sort((x, y) => x.percent - y.percent).map((a) => ({
    percent: a.percent, pages: a.pages, secPerPage: a.gaps > 0 ? a.seconds / a.gaps : null, tapsPer10: (a.taps / a.pages) * 10 }));
}

/**
 * Crafting Table numbers for the dashboard's "Crafting" line: total crafts, how many needed help (a wrong block
 * first), and per-word counts, most crafted first. Returns null when there are no craft events.
 */
export function craftStats(events) {
  const crafts = events.filter((e) => e.type === "craft");
  if (crafts.length === 0) return null;
  const by = new Map();
  for (const e of crafts) {
    const w = by.get(e.item) ?? { word: e.item, n: 0, assisted: 0 };
    w.n += 1;
    w.assisted += e.result === "assisted" ? 1 : 0;
    by.set(e.item, w);
  }
  const assisted = crafts.filter((e) => e.result === "assisted").length;
  return { total: crafts.length, assisted, independentShare: (crafts.length - assisted) / crafts.length,
    words: [...by.values()].sort((a, b) => b.n - a.n || a.word.localeCompare(b.word)) };
}
