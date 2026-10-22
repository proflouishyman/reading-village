"""Browser tests for minigame levels (Playwright, real server on a temp data dir, small fixture word lists).

* Crafting levels up: ten independent crafts at level 1 show "Crafting level 2!" with a rare surprise in the pile, then the
  next round uses level 2 words mixed with easier ones, and every craft event carries its level.
* The level line (title and "n of 8 right at level L") shows on all four screens, in small caps.
* Dad's override in Settings: sets progress.settings.level_override, drives the screen, and "Automatic" clears it.
* The dashboard "Levels" panel shows the derived level, what it is and the last-10 independent count.
Playwright is required: if it is missing these tests ERROR (a skipped check would look like a pass).
Set LEVEL_SHOTS=<dir> to also save screenshots (level-up celebration, dashboard panel, settings).
"""
import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import server  # noqa: E402
import test_ui_smallcaps as base  # noqa: E402  (module import: its TestCase classes must not run twice)

TS = "2026-10-18T09:00:00-04:00"
ALL_LETTERS = list("bdpqmwnu")
SHOTS = os.environ.get("LEVEL_SHOTS")

# Fixture craft words (v2 contract). Level 1: the eight original CVC words. Level 2 ("blend") reuses words the shipped
# config has real items for; the sprite is any existing one, since only the contract is under test here.
L1 = ["PIG", "BAT", "BED", "PUP", "HEN", "FOX", "SUN", "DAD"]
L2 = ["COW", "BEE", "GOAT", "WOOL", "MILK"]
FIXTURE = {"v": 2, "words": (
    [{"word": w, "level": 1, "pattern": "cvc", "sprite": w.lower()} for w in L1]
    + [{"word": w, "level": 2, "pattern": "blend", "sprite": "pig"} for w in L2])}


def craft_event(i, level=1, result="correct"):
    return {"v": 1, "ts": TS, "session_id": "old", "type": "craft", "track": "smallcaps", "item": L1[i % len(L1)],
            "result": result, "level": level}


class LevelsCase(base.UiCase):
    def start_levels(self, events=(), progress=None, craft_fixture=True, active=None):
        """Fresh server (fixture craft words, all letters active) + page. `events` are on file before the page loads."""
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["active_letters"] = active if active is not None else ALL_LETTERS
        if progress:
            p["settings"].update(progress)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "data"
        data.mkdir()
        (data / "progress.json").write_text(json.dumps(p))
        (data / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        fixture = Path(tmp.name) / "craft_words.json"
        fixture.write_text(json.dumps(FIXTURE))
        patch = mock.patch.object(server, "CRAFT_WORDS_FILE", fixture)
        patch.start()
        self.addCleanup(patch.stop)
        srv = server.make_server(data, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.data = data
        self.url = f"http://127.0.0.1:{srv.server_address[1]}"
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        if craft_fixture:  # the client reads the same fixture the server loaded
            page.route("**/data/craft_words.json", lambda r: r.fulfill(json=FIXTURE))
        page.goto(self.url + "/")
        page.wait_for_selector(".home")
        return page

    def craft_word(self, page, word):
        for letter in word:
            page.click(f".craft-tile[data-letter='{letter}']:not([disabled])")
        page.click(".craft-btn.ready")
        page.wait_for_timeout(1550)  # the 1.4 s reward beat, then the next word

    def to_home(self, page, seen=None):
        """Click through celebrations (a village level or a minigame level may be waiting) until Home; returns their titles."""
        titles = []
        for _ in range(8):
            page.wait_for_selector(".home, .interlude")
            if page.query_selector(".home"):
                return titles
            titles.append(page.inner_text(".interlude h1").lower())
            page.click(".interlude .btn")
        self.fail(f"never reached Home: {titles}")

    def level_text(self, page):
        return page.inner_text(".level-line").lower().replace("\n", " | ")

    def shot(self, page, name):
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / name))


class CraftLevelUp(LevelsCase):
    def test_ten_independent_crafts_level_up_with_a_celebration_and_one_rare_surprise(self):
        page = self.start_levels(events=[craft_event(i) for i in range(5)])  # five earlier independent crafts on file
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        self.assertIn("level 1: short vowel words", self.level_text(page))
        self.assertIn("5 of 8 right at level 1", self.level_text(page))
        self.assert_small_caps(page, "craft level line")
        for word in L1[:5]:  # a fresh round, least-crafted first, file order
            self.craft_word(page, word)
        page.wait_for_selector(".interlude")  # "You crafted five things!"
        page.click(".interlude .btn")
        # The celebrations come at the calm moment after the stage: the village level the crafts also earned (if any),
        # then "Crafting level 2!".
        titles = []
        for _ in range(4):
            page.wait_for_selector(".interlude")
            titles.append(page.inner_text(".interlude h1").lower())
            if titles[-1] == "crafting level 2!":
                self.assert_small_caps(page, "level-up celebration")
                self.shot(page, "levelup-celebration.png")
            page.click(".interlude .btn")
            page.wait_for_timeout(200)
            if page.query_selector(".home"):
                break
        self.assertEqual(titles.count("crafting level 2!"), 1, titles)
        page.wait_for_selector(".home")
        refs = [t["source"]["ref"] for t in json.loads((self.data / "progress.json").read_text())["treasure"]]
        self.assertEqual(refs.count("minigame_level:craft:2"), 1)
        mine = [e for e in self.events() if e["type"] == "craft" and e["session_id"] != "old"]
        self.assertEqual([e["level"] for e in mine], [1] * 5)
        self.assertEqual([e["item"] for e in mine], L1[:5])

        # The next round is level 2: the screen says so, 0 of 8, and the words are four at level 2 plus one easier review word.
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        self.assertIn("level 2: blends", self.level_text(page))
        self.assertIn("0 of 8 right at level 2", self.level_text(page))
        self.shot(page, "craft-level2.png")
        order = [L1[5], L2[0], L2[1], L2[2], L2[3]]  # one review word first, then four at level 2 (least crafted, file order)
        self.craft_word(page, order[0])
        self.craft_word(page, order[1])
        later = [e for e in self.events() if e["type"] == "craft" and e["session_id"] != "old"][5:]
        # the event's level is the WORD's own rung: the mixed-in easier word is level 1 and does not count at level 2
        self.assertEqual([(e["item"], e["level"]) for e in later], [(order[0], 1), (order[1], 2)])
        self.assertIn("1 of 8 right at level 2", self.level_text(page))
        self.assertFalse(self.errors, self.errors)

    def test_small_caps_craft_uses_words_with_letters_not_yet_introduced(self):
        # Only b and d are active, but small caps does not mirror: PIG and PUP (p) are in the round, in file order.
        page = self.start_levels(active=["b", "d"])
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        for word in ["PIG", "BAT", "BED", "PUP", "HEN"]:
            self.craft_word(page, word)
        page.wait_for_selector(".interlude")
        self.assertFalse(self.errors, self.errors)

    def test_mid_round_level_up_does_not_credit_the_rest_of_the_round_to_the_new_level(self):
        page = self.start_levels(events=[craft_event(i) for i in range(9)])  # nine on file: the first craft levels up
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        for word in L1[:3]:
            self.craft_word(page, word)
        mine = [e for e in self.events() if e["type"] == "craft" and e["session_id"] != "old"]
        self.assertEqual([e["level"] for e in mine], [1, 1, 1], "the round started at level 1 and every event says so")
        self.assertIn("level 2: blends", self.level_text(page))
        self.assertIn("0 of 8 right at level 2", self.level_text(page))
        self.assertFalse(self.errors, self.errors)

    def test_assisted_crafts_do_not_count_toward_the_level(self):
        page = self.start_levels(events=[craft_event(i, result="assisted") for i in range(9)])
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        self.assertIn("0 of 8 right at level 1", self.level_text(page))
        for word in L1[:5]:
            self.craft_word(page, word)
        page.wait_for_selector(".interlude")
        page.click(".interlude .btn")
        self.assertFalse([t for t in self.to_home(page) if "level" in t and "village" not in t], "no minigame celebration: nothing earned")
        refs = [t["source"]["ref"] for t in json.loads((self.data / "progress.json").read_text()).get("treasure", [])]
        self.assertFalse([r for r in refs if r.startswith("minigame_level:")])


class LevelLineOnEveryScreen(LevelsCase):
    def test_word_blocks_shows_the_level(self):
        page = self.start_levels()
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        self.assertIn("level 1: short vowel words | 0 of 8 right at level 1", self.level_text(page))
        page.click("button.good:not([disabled])")
        page.wait_for_function("document.querySelector('.level-sub').textContent.toLowerCase().includes('1 of 8')")
        self.assertEqual([e["level"] for e in self.events() if e["type"] == "word"], [1])
        self.assert_small_caps(page, "word blocks level line")

    def test_letter_mine_and_bridge_match_show_their_levels_and_log_them(self):
        page = self.start_levels(progress={"lowercase_track": "on", "lowercase_percent": 100})
        page.click("button.stage-btn:has-text('Letter Mine')")
        page.wait_for_selector(".big-letter")
        self.assertIn("level 1: one letter at a time", self.level_text(page))
        letters = []
        for _ in range(3):  # level 1 is runs of three of the same letter
            letters.append(page.inner_text(".big-letter"))
            page.click("button.good:not([disabled])")
            page.wait_for_timeout(1250)
        self.assertEqual(len(set(letters)), 1, letters)
        self.assertEqual([e["level"] for e in self.events() if e["type"] == "card"], [1, 1, 1])
        page.click("text=Home")
        self.to_home(page)
        page.click("button.stage-btn:has-text('Bridge Match')")
        page.wait_for_selector(".choices")
        self.assertIn("level 1: two choices, one letter at a time", self.level_text(page))
        self.assertEqual(len(page.query_selector_all(".choices .choice")), 2)
        target = page.inner_text(".sc-letter").lower()
        page.click(f".choice[data-letter='{target}']")
        page.wait_for_timeout(300)
        self.assertEqual([e["level"] for e in self.events() if e["type"] == "match"], [1])
        self.assertFalse(self.errors, self.errors)

    def test_bridge_match_at_level_four_offers_four_choices(self):
        page = self.start_levels(progress={"lowercase_track": "on", "lowercase_percent": 100, "level_override": {"match": 4}})
        page.click("button.stage-btn:has-text('Bridge Match')")
        page.wait_for_selector(".choices")
        self.assertIn("level 4: four choices", self.level_text(page))
        self.assertIn("level chosen by dad", self.level_text(page))
        self.assertEqual(len(page.query_selector_all(".choices .choice")), 4)
        page.click(f".choice[data-letter='{page.inner_text('.sc-letter').lower()}']")
        page.wait_for_timeout(300)
        self.assertEqual([e["level"] for e in self.events() if e["type"] == "match"], [4])


class DadControls(LevelsCase):
    def test_settings_override_sets_drives_and_clears(self):
        page = self.start_levels()
        page.click(".dad-corner .settings-gear")
        page.wait_for_selector("#level-craft")
        self.assertEqual(page.input_value("#level-craft"), "")
        page.select_option("#level-craft", "3")
        page.wait_for_function("(document.querySelector('#level-craft') || {}).value === '3'")
        self.assertEqual(json.loads((self.data / "progress.json").read_text())["settings"]["level_override"], {"craft": 3})
        self.shot(page, "settings-levels.png")
        page.click("#settings-back")
        page.wait_for_selector(".home")
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        self.assertIn("level 3: digraphs", self.level_text(page))
        page.click("text=Home")
        self.to_home(page)  # the all-letters-active setup also earns a village level, celebrated on the way
        page.click(".dad-corner .settings-gear")
        page.wait_for_selector("#level-craft")
        page.select_option("#level-craft", "")
        page.wait_for_function("(document.querySelector('#level-craft') || {}).value === ''")
        page.wait_for_timeout(300)
        self.assertNotIn("level_override", json.loads((self.data / "progress.json").read_text())["settings"])

    def test_dashboard_levels_panel(self):
        evs = [craft_event(i) for i in range(10)] + [craft_event(i, level=2, result="assisted" if i < 2 else "correct") for i in range(5)]
        page = self.start_levels(events=evs, progress={"level_override": {"mine": 3}})
        page.goto(self.url + "/dashboard.html")
        page.wait_for_selector("#levels-panel")
        text = page.inner_text("#levels-panel")
        self.assertIn("Crafting", text)
        self.assertIn("2 of 6", text)  # derived level 2 (ten correct at level 1)
        self.assertIn("blends", text)
        self.assertIn("3 of 8 right (5 tries at level 2; needs 10)", text)
        self.assertIn("3 of 4 (Dad's override; earned 1)", text)  # Letter Mine override
        self.assertIn("mirror pairs", text)
        self.shot(page, "dashboard-levels.png")
        self.assertFalse(self.errors, self.errors)


if __name__ == "__main__":
    unittest.main()
