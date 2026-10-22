"""Browser tests (Playwright, real server on a temp data dir).

* Everything the child sees is Arial small caps: walk the DOM at every screen and fail on any a-z text node
  outside the Dad areas (and, in the lowercase track, outside the lowercase reading material).
* Word Blocks shows no letter cue; the victory card cannot record a miss; a Build double-click places one block;
  the lowercase track with no finished story shows a calm message, not an error.
Playwright is required: if it is missing these tests ERROR (a skipped check would look like a pass).
"""
import copy
import json
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server  # noqa: E402

# Visible text nodes containing a-z (or accented lowercase) outside Dad areas. Text inside <span class="sc"> is
# already uppercase, so only real lowercase shows up. `extra` lists selectors that are intended reading material.
LEAK_JS = r"""(extra) => {
  const out = [];
  const skip = ['.dad-bar', '.dad-only', '.dad-corner', '#overlay', ...extra].join(', ');
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.textContent;
    if (!/[a-zß-ÿ]/.test(t)) continue;
    const el = n.parentElement;
    if (el.closest(skip)) continue;
    const cs = getComputedStyle(el);
    if (el.getBoundingClientRect().width === 0 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    out.push(t.trim());
  }
  return out;
}"""

PROGRESS_OVER = {"inventory": {"coal": 0, "iron": 0, "gold": 0, "diamond": 0, "wood": 0, "stone": 0, "emerald": 0}}


class UiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def start(self, progress=None):
        """Fresh server + page. `progress` (dict) overrides the default progress.json."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "data"
        data.mkdir()
        if progress is not None:
            (data / "progress.json").write_text(json.dumps(progress))
        srv = server.make_server(data, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.data = data
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/")
        page.wait_for_selector(".home")
        return page

    def skip_celebrations(self, page):
        """Click through level-up screens (a village level or a minigame level, docs/design.md "Levels") that may come
        before the next screen. A plain interlude ("Nice work!") is left alone."""
        for _ in range(6):
            h1 = page.query_selector(".interlude h1")
            if not h1 or not re.search(r"\blevel\b|\bvillage\b", h1.inner_text(), re.I):
                return
            page.click(".interlude .btn")
            page.wait_for_timeout(300)

    def saved_progress(self):
        return json.loads((self.data / "progress.json").read_text())

    def events(self):
        f = self.data / "events.jsonl"
        return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []

    def assert_small_caps(self, page, label, extra=()):
        page.wait_for_timeout(250)
        self.assertEqual(page.evaluate(LEAK_JS, list(extra)), [], f"lowercase text the child can see at: {label}")
        self.assertFalse(self.errors, self.errors)


def progress_with(**settings):
    p = copy.deepcopy(server.DEFAULT_PROGRESS)
    p["settings"].update(settings)
    return p


class SmallCapsEverywhere(UiCase):
    def test_small_caps_adventure_has_no_lowercase_outside_dad_areas(self):
        page = self.start()
        self.assert_small_caps(page, "home")
        page.click("text=Start today's adventure")
        page.wait_for_selector(".big-word")
        self.assert_small_caps(page, "word blocks")
        # H1: "try again" shows NO letter cue; Dad's bar says what to do instead.
        page.click("text=Let's try again")
        page.wait_for_timeout(300)
        self.assertEqual(page.query_selector_all(".cue .cue-text, .cue-bed"), [], "Word Blocks must not show a letter cue")
        self.assertIn("Sound it out together, then tap.", page.inner_text(".dad-hint"))
        self.assert_small_caps(page, "word blocks, try again")
        page.click("text=Got it!")
        while True:
            page.wait_for_timeout(1300)
            if page.query_selector(".interlude"):
                break
            page.click("button.good:not([disabled])")
        self.skip_celebrations(page)  # ten independent words also earn Word Blocks level 2
        self.assert_small_caps(page, "interlude")
        page.click(".interlude .btn")
        page.wait_for_selector(".story-pick")
        self.assert_small_caps(page, "story picker")
        page.click(".story-pick button >> nth=0")
        page.wait_for_selector(".story-text .w")
        self.assert_small_caps(page, "story page")
        while not page.query_selector(".interlude"):
            page.click("button.nav.primary:not([disabled])")
            page.wait_for_timeout(150)
        self.assert_small_caps(page, "story done")
        page.click(".interlude .btn")
        page.wait_for_selector(".interlude")  # "Nice work! Next: Build"
        self.assert_small_caps(page, "interlude before build")
        page.click(".interlude .btn")
        page.wait_for_selector(".build")
        self.assert_small_caps(page, "build")

    def test_lowercase_track_chrome_stays_small_caps(self):
        p = progress_with(lowercase_track="on", lowercase_percent=100)
        p["stories"]["gold-pig"] = {"smallcaps_done": True, "lowercase_done": False, "resume_page": 0}
        p["inventory"]["wood"] = 1
        page = self.start(p)
        # Reading material (letters, cues, story text) is lowercase on purpose; everything else is not.
        material = [".big-letter", ".choice", ".cue", ".story-text"]
        self.assert_small_caps(page, "home, lowercase track on")
        page.click("button.stage-btn:has-text('Bridge Match')")
        page.wait_for_selector(".choices")
        self.assert_small_caps(page, "bridge match", material)
        page.click("text=Home")
        page.wait_for_selector(".home")
        page.click("button.stage-btn:has-text('Letter Mine')")
        page.wait_for_selector(".big-letter")
        page.click("text=Let's try again")
        page.wait_for_selector(".cue .cue-text")  # the cue and the bed picture belong here
        self.assert_small_caps(page, "letter mine", material)

    def test_lowercase_track_without_a_finished_story_is_a_calm_message(self):
        page = self.start(progress_with(lowercase_track="on"))
        page.click("text=Lowercase track")
        page.wait_for_selector(".interlude")
        self.assertIsNone(page.query_selector(".loud"), "this is a legitimate state, not an error screen")
        self.assertEqual(page.inner_text(".interlude h1").lower(), "read a story in small caps first!")
        self.assertIn("small caps", page.inner_text(".dad-bar"))
        self.assert_small_caps(page, "no story yet")
        page.click(".interlude .btn")
        page.wait_for_selector(".home")


class SettingsAndProgress(UiCase):
    def test_gear_opens_settings_and_it_is_not_child_text(self):
        page = self.start()
        page.click(".dad-corner .settings-gear")
        page.wait_for_selector(".settings")
        self.assertIn("Reset progress", page.inner_text(".settings"))
        self.assertTrue(page.query_selector(".settings a[href='dashboard.html']"))
        self.assert_small_caps(page, "settings")
        page.click("#settings-back")
        page.wait_for_selector(".home")

    def test_gear_in_a_stage_leaves_the_stage_for_settings(self):
        page = self.start()
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        page.click(".dad-bar .settings-gear")
        page.wait_for_selector(".settings")
        page.wait_for_timeout(300)
        self.assertIsNotNone(page.query_selector(".settings"), "Home must not replace Settings after the stage quits")
        self.assertIsNone(page.query_selector(".big-word"))

    def test_reset_needs_typed_phrase_and_archives(self):
        p = progress_with()
        p["inventory"]["wood"] = 3
        page = self.start(p)
        page.click(".dad-corner .settings-gear")
        page.wait_for_selector(".settings")
        self.assertTrue(page.is_disabled("#reset-go"))
        page.fill("#reset-confirm", "reset")
        self.assertTrue(page.is_disabled("#reset-go"))
        page.fill("#reset-confirm", "RESET")
        page.click("#reset-go")
        page.wait_for_selector(".settings-archived")
        self.assertIn("data/archive/", page.inner_text(".settings-archived"))
        archives = list((self.data / "archive").iterdir())
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads((archives[0] / "progress.json").read_text())["inventory"]["wood"], 3)
        self.assertEqual(json.loads((self.data / "progress.json").read_text())["inventory"]["wood"], 0)
        # Client state was reloaded through the store: the next save carries the new rev and is accepted.
        page.click("#settings-back")
        page.wait_for_selector(".home")
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        page.click("button.good:not([disabled])")
        page.wait_for_timeout(500)
        self.assertIsNone(page.query_selector(".loud"))
        self.assertEqual(self.events()[0]["type"], "session_start", "a fresh session starts after a reset")

    def test_progress_row_advances_and_never_shows_a_miss(self):
        page = self.start()
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        total = len(page.query_selector_all(".stage-progress .pip"))
        self.assertGreater(total, 1)
        self.assertEqual(len(page.query_selector_all(".pip.cur")), 1)
        self.assertEqual(len(page.query_selector_all(".pip.done")), 0)
        self.assertEqual(page.inner_text(".pip-count").replace(" ", "").lower(), f"1/{total}")
        self.assert_small_caps(page, "word blocks with progress row")
        # Miss the first card (try again twice): it is filled like any other and the row grows by one.
        page.click("button.again:not([disabled])")
        page.click("button.again:not([disabled])")
        page.wait_for_function("document.querySelectorAll('.pip.done').length === 1")
        page.wait_for_function("document.querySelectorAll('.pip').length === %d" % (total + 1))
        self.assertEqual(page.eval_on_selector(".pip.done", "e => e.className"), "pip done")
        self.assertEqual(page.inner_text(".pip-count").replace(" ", "").lower(), f"2/{total + 1}")


class CraftingTable(UiCase):
    """Crafting Table: one full craft, a wrong block (assisted, silent), the chest, and the small-caps walk."""

    def open_craft(self, progress=None):
        # Crafting honours the confusable-letter gate (only words whose b/d/p/q/m/w/n/u are all active), so these tests
        # activate every letter to get the original first words (PIG, BAT, BED, PUP, HEN).
        progress = progress or progress_with()
        progress["active_letters"] = list("bdpqmwnu")
        page = self.start(progress)
        self.assert_small_caps(page, "home with the Crafting Table tile")
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-grid")
        return page

    def tap(self, page, letter):
        page.click(f".craft-tile[data-letter='{letter}']:not([disabled])")

    def test_full_craft_logs_correct_and_fills_the_chest(self):
        page = self.open_craft()
        self.assert_small_caps(page, "crafting table")
        self.assertTrue(page.is_disabled(".craft-btn"))
        self.assertEqual(len(page.query_selector_all(".craft-tile")), 5, "3 letters + 2 distractors")
        self.assertEqual(len(page.query_selector_all(".stage-progress .pip")), 5)
        for letter in "PIG":  # the first word of craft_words.json
            self.tap(page, letter)
        page.wait_for_selector(".craft-btn.ready")
        self.assertFalse(page.is_disabled(".craft-btn"))
        self.assert_small_caps(page, "crafting table, word complete")
        page.click(".craft-btn")
        page.wait_for_function("document.querySelectorAll('.pip.done').length === 1")
        crafts = [e for e in self.events() if e["type"] == "craft"]
        self.assertEqual(len(crafts), 1)
        self.assertEqual({k: crafts[0][k] for k in ("item", "result", "track")}, {"item": "PIG", "result": "correct", "track": "smallcaps"})
        self.assertEqual(json.loads((self.data / "progress.json").read_text())["crafted"], {"PIG": 1})
        page.click(".chest-btn")
        page.wait_for_selector(".chest-item:not(.empty) canvas")
        self.assertEqual(len(page.query_selector_all(".chest-item:not(.empty)")), 1)
        self.assert_small_caps(page, "collection chest")
        self.assertIsNone(page.query_selector(".loud"))

    def test_wrong_block_wiggles_silently_and_the_craft_is_assisted(self):
        page = self.open_craft()
        wrong = page.eval_on_selector_all(".craft-tile", "els => els.map(e => e.dataset.letter).find(l => !'PIG'.includes(l))")
        # Every sound is built from oscillators, so counting OscillatorNode.start calls detects any sound at all.
        page.evaluate("""() => {
            window.__oscStarts = 0;
            const orig = OscillatorNode.prototype.start;
            OscillatorNode.prototype.start = function (...a) { window.__oscStarts += 1; return orig.apply(this, a); };
        }""")
        page.click(f".craft-tile[data-letter='{wrong}']")
        page.wait_for_selector(f".craft-tile[data-letter='{wrong}'].wiggle")  # the tap handler has run (sync)
        self.assertEqual(page.evaluate("window.__oscStarts"), 0, "a wrong tap must play no sound")
        self.assertEqual(page.query_selector_all(".craft-slot.full"), [], "a wrong block is not placed")
        self.assertFalse(page.is_disabled(f".craft-tile[data-letter='{wrong}']"), "it stays in the tray")
        self.assertIsNone(page.query_selector(".miss, .wrong, .loud"))
        self.assertEqual([e for e in self.events() if e["type"] == "craft"], [], "nothing is logged until Craft!")
        self.tap(page, "I")  # out of order: the slot wants P first, so this is also a wiggle
        self.assertEqual(page.query_selector_all(".craft-slot.full"), [])
        for letter in "PIG":
            self.tap(page, letter)
        page.click(".craft-btn")
        page.wait_for_function("document.querySelectorAll('.pip.done').length === 1")
        self.assertGreater(page.evaluate("window.__oscStarts"), 0, "the spy works: Craft! plays the jingle")
        crafts = [e for e in self.events() if e["type"] == "craft"]
        self.assertEqual([(e["item"], e["result"]) for e in crafts], [("PIG", "assisted")])

    def test_round_of_five_ends_on_a_success_screen(self):
        page = self.open_craft()
        for word in ("PIG", "BAT", "BED", "PUP", "HEN"):
            for letter in word:
                self.tap(page, letter)
            page.click(".craft-btn.ready")
            page.wait_for_timeout(1700)
        page.wait_for_selector(".interlude")
        self.assert_small_caps(page, "craft round done")
        self.assertEqual([e["item"] for e in self.events() if e["type"] == "craft"], ["PIG", "BAT", "BED", "PUP", "HEN"])
        page.click(".interlude .btn")
        self.skip_celebrations(page)  # the all-letters-active setup also earned a village level
        page.wait_for_selector(".home")


class StageBehaviour(UiCase):
    def test_victory_card_cannot_record_a_miss(self):
        page = self.start()
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        victory_buttons = None
        # Judge every card "try again" twice (a miss). The only card that then offers just "Got it!" is the victory card.
        while not page.query_selector(".home"):
            again = page.query_selector("button.again:not([disabled])")
            good = page.query_selector("button.good:not([disabled])")
            if again and good:
                if again.is_visible():
                    again.click()
                else:
                    victory_buttons = "got-only"
                    good.click()
            page.wait_for_timeout(120)
        words = [e for e in self.events() if e["type"] == "word"]
        self.assertEqual(victory_buttons, "got-only", "the final card must offer only Got it!")
        self.assertNotEqual(words[-1]["result"], "miss", "the stage must end on a success")

    def test_build_double_click_places_one_block(self):
        p = progress_with()
        p["inventory"]["wood"] = 1
        page = self.start(p)
        # Build is no longer a Home tile (Sam's Village replaced it); it is the last stage of the adventure.
        page.click("text=Start today's adventure")
        page.wait_for_selector(".big-word")
        while not page.query_selector(".interlude"):
            page.wait_for_timeout(1300)
            if page.query_selector("button.good:not([disabled])") and not page.query_selector(".interlude"):
                page.click("button.good:not([disabled])")
        self.skip_celebrations(page)
        page.click(".interlude .btn")
        page.wait_for_selector(".story-pick")
        page.click(".story-pick button >> nth=0")
        page.wait_for_selector(".story-text .w")
        while not page.query_selector(".interlude"):
            page.click("button.nav.primary:not([disabled])")
            page.wait_for_timeout(120)
        page.click(".interlude .btn")
        page.wait_for_selector(".interlude")
        page.click(".interlude .btn")
        page.wait_for_selector("canvas.house-grid")
        wood_before = self.saved_progress()["inventory"]["wood"]  # the adventure's words earned some wood on the way
        page.dblclick("canvas.house-grid", position={"x": 30, "y": 30})
        page.wait_for_timeout(1200)
        self.assertEqual(sum(e["type"] == "block_placed" for e in self.events()), 1)
        saved = json.loads((self.data / "progress.json").read_text())
        self.assertEqual((saved["inventory"]["wood"], len(saved["house"])), (wood_before - 1, 1))
        self.assertIsNone(page.query_selector(".loud"))


if __name__ == "__main__":
    unittest.main()
