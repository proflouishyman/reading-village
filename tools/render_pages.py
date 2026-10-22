#!/usr/bin/env python3
"""Render every page's art of one story to PNG (800x450) for review.

    python3 tools/render_pages.py STORY_ID [--out DIR]

Starts server.py (--no-browser, a free port, a temp --data-dir), opens the dev-only /render.html?story=ID
in Playwright, and screenshots each page to DIR/<story>_<page:02d>.png. Also writes DIR/<story>_pages.json:
[{"page": int, "text": str, "png": str}]. Consecutive pages with identical art are reported (a warning, not a
failure). Any other problem prints a FAILED banner and exits non-zero.

Guards (all run after rendering; the PNGs and pages.json are still written, then every offender is listed as
story/page/element, a per-story count is printed, and the tool exits non-zero):
  CLIP: every actor, prop AND effect/text of every composable (object) art is measured with `artBoxes`
    (app/js/scenes.js) at 800x450. If the frame edge cuts off more than 5% of any of them (a mid-fall actor
    and a boom cloud count), it fails.
  OVERLAP: `artOverlaps` (app/js/scenes.js). Two actors, or an actor and a prop that is not held, whose boxes
    overlap by more than 20% of the smaller box fail, unless the art declares the relation (held, worn/head,
    on, in, sit_on, lying in a bed, hide, hug). The limit is OVERLAP_LIMIT; do not raise it to pass a story.
  HEADCOVER: `artBubbleHeadHits` (app/js/scenes.js). A speech bubble or text burst whose body overlaps an actor's head
    box (head plus worn hat, the speaker's own included) by more than 0.5 logical px fails. The engine places text clear
    of every head (above, the free side, then smaller), so this only fires when it found no clear place.
Scene-key (string) art has no actor list and is not checked; the run never hides that: a COVERAGE line (OK and
FAILED output) gives the checked count and lists the unchecked pages.
"""
import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CLIP_LIMIT = 0.05  # fail when the frame edge cuts off more than this fraction of an element's area
OVERLAP_LIMIT = 0.20  # fail when undeclared boxes share more than this fraction of the smaller box
CANVAS = (800, 450)  # the render size; boxes are measured at this size


def fail(msg):
    print(f"\n*** FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story_id")
    ap.add_argument("--out", default="renders", help="output directory (default ./renders)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    with tempfile.TemporaryDirectory() as data_dir:
        srv = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py"), "--no-browser", "--port", str(port), "--data-dir", data_dir],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            base = f"http://localhost:{port}"
            for _ in range(50):
                if srv.poll() is not None:
                    fail(f"server exited early:\n{srv.stdout.read()}")
                try:
                    urllib.request.urlopen(f"{base}/render.html", timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                fail("server did not start within 5 s")
            entries, clipped, overlaps, headcover, pages_failing, checked, unchecked = render(base, args.story_id, out)
        finally:
            srv.terminate()
            srv.wait(timeout=5)
    (out / f"{args.story_id}_pages.json").write_text(json.dumps(entries, indent=2) + "\n")
    if clipped or overlaps or headcover:
        if clipped:
            print(f"\n*** FAILED: {len(clipped)} element(s) clipped by the frame edge by more than {CLIP_LIMIT:.0%}:",
                  file=sys.stderr)
            for c in clipped:
                print(f"  CLIP {c}", file=sys.stderr)
        if overlaps:
            print(f"\n*** FAILED: {len(overlaps)} undeclared overlap(s) above {OVERLAP_LIMIT:.0%} of the smaller box:",
                  file=sys.stderr)
            for o in overlaps:
                print(f"  OVERLAP {o}", file=sys.stderr)
        if headcover:
            print(f"\n*** FAILED: {len(headcover)} text bubble(s) cover an actor's head:", file=sys.stderr)
            for h in headcover:
                print(f"  HEADCOVER {h}", file=sys.stderr)
        print(f"\nSUMMARY {args.story_id}: {len(entries)} pages; pages failing: clip={pages_failing['clip']} "
              f"overlap={pages_failing['overlap']} headcover={pages_failing['headcover']} any={pages_failing['any']}", file=sys.stderr)
        print(coverage_line(args.story_id, checked, unchecked), file=sys.stderr)
        sys.exit(1)
    print(f"OK: {len(entries)} pages rendered to {out}, nothing clipped, no undeclared overlaps, "
          f"no bubble over a head among the checked pages")
    print(coverage_line(args.story_id, checked, unchecked))


def coverage_line(story_id, checked, unchecked):
    """How much of the story the guards actually covered. String-art pages are legitimately unchecked (no actor
    list) but are always counted and named, so a clean OK never reads as 'everything verified'."""
    line = f"COVERAGE {story_id}: {checked} composable pages checked, {len(unchecked)} string-art pages NOT checked"
    return line + (f" (pages: {', '.join(map(str, unchecked))})" if unchecked else "")


def find_problems(page, story_id):
    """(clip lines, overlap lines, headcover lines, pages failing {clip, overlap, headcover, any}, composable pages
    checked, string-art pages NOT checked) for the story.

    Lines read `story/page N/<kind>[i] name: ...` so a story fixer can find the element. Runs in the page, where
    app/js/scenes.js (the one source of the geometry) is importable."""
    rows = page.evaluate("""async ([id, w, h, limit]) => {
      const { artBoxes, artOverlaps, artBubbleHeadHits } = await import('/js/scenes.js');
      const story = await (await fetch(`/stories/${id}.json`)).json();
      const out = { boxes: [], overlaps: [], heads: [], checked: 0, unchecked: [] };
      story.pages.forEach((p, i) => {
        if (typeof p.art === 'string') { out.unchecked.push(i); return; }
        out.checked += 1;
        for (const b of artBoxes(p.art, w, h, `${id} page ${i} art`)) out.boxes.push({ page: i, ...b });
        for (const o of artOverlaps(p.art, limit, `${id} page ${i} art`)) out.overlaps.push({ page: i, ...o });
        for (const h of artBubbleHeadHits(p.art, `${id} page ${i} art`)) out.heads.push({ page: i, ...h });
      });
      return out;
    }""", [story_id, *CANVAS, OVERLAP_LIMIT])
    clip = [f"{story_id}/page {r['page']}/{r['kind']}[{r['index']}] {r['name']}: {r['clip']:.0%} outside the frame"
            for r in rows["boxes"] if r["clip"] > CLIP_LIMIT]
    over = [f"{story_id}/page {o['page']}/{o['a']['kind']}[{o['a']['index']}] {o['a']['name']} x "
            f"{o['b']['kind']}[{o['b']['index']}] {o['b']['name']}: {o['frac']:.0%} overlap, no relation declared"
            for o in rows["overlaps"]]
    heads = [f"{story_id}/page {h['page']}/fx[{h['fx']['index']}] {h['fx']['name']} covers the head of "
             f"actor[{h['actor']['index']}] {h['actor']['name']} ({h['w']:.1f}x{h['h']:.1f} px)" for h in rows["heads"]]
    pages_clip = {r["page"] for r in rows["boxes"] if r["clip"] > CLIP_LIMIT}
    pages_over = {o["page"] for o in rows["overlaps"]}
    pages_head = {h["page"] for h in rows["heads"]}
    return (clip, over, heads, {"clip": len(pages_clip), "overlap": len(pages_over), "headcover": len(pages_head),
            "any": len(pages_clip | pages_over | pages_head)}, rows["checked"], rows["unchecked"])


def render(base, story_id, out):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 800, "height": 450})
            problems = []
            page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
            page.on("console", lambda m: problems.append(f"console error: {m.text}") if m.type == "error" else None)
            page.goto(f"{base}/render.html?story={story_id}")
            page.wait_for_function("window.__render && window.__render.ready", timeout=15000)
            info = page.evaluate("({error: window.__render.error, pages: window.__render.pages, "
                                 "texts: window.__render.texts, repeats: window.__render.repeats})")
            if info["error"]:
                fail(f"story {story_id}: {info['error']}")
            for r in info["repeats"]:
                print(f"WARNING: page {r['page']} has the same art as page {r['same_as']}")
            entries = []
            for i in range(info["pages"]):
                err = page.evaluate(f"(() => {{ try {{ window.__render.draw({i}); return null; }} "
                                    f"catch (e) {{ return String(e.message || e); }} }})()")
                if err:
                    fail(f"story {story_id} page {i}: {err}")
                png = out / f"{story_id}_{i:02d}.png"
                page.locator("#scene").screenshot(path=str(png))
                if not png.exists() or png.stat().st_size == 0:
                    fail(f"story {story_id} page {i}: screenshot not written to {png}")
                entries.append({"page": i, "text": info["texts"][i], "png": str(png)})
            if problems:
                fail(f"story {story_id}: browser reported errors: {problems}")
            return (entries, *find_problems(page, story_id))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
