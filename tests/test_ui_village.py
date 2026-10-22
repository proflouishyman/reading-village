"""Browser tests for Sam's Village, the shop, the Treasure Pile and the Send scene (Playwright, real server on a
temp data dir; the real Minecraft server is never involved: the delivery worker is not started, so deliveries stay
"pending" and the pile shows "on the way").

* Everything the child sees stays small caps (same DOM walk as test_ui_smallcaps).
* The flows: first free unlock, bell unlock, emerald unlock, buy, sell, send a subset, level locks, level-up screen.
* Earning: word / craft / story emeralds reach progress.json.
* Loud failure: a refused send shows SEND FAILED and never "Sent to your Magic Chest!"; Dad's bar and the dashboard
  show pending sends with no worker, loudly.
Playwright is required: if it is missing these tests ERROR (a skipped check would look like a pass).
"""
import base64
import json
import os
import struct
import sys
import tempfile
import zlib
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import server  # noqa: E402
import test_ui_smallcaps as base  # noqa: E402  (module import: its TestCase classes must not run twice)

CFG = json.loads((ROOT / "config" / "minecraft.json").read_text())
EARN = CFG["earn"]
TS = "2026-10-18T09:00:00-04:00"


def word_event(i=0):
    return {"v": 1, "ts": TS, "session_id": "old", "type": "word", "track": "smallcaps", "item": "pig", "result": "correct"}


class VillageCase(base.UiCase):
    @staticmethod
    def delivery_on_config(tmpdir):
        """The shipped config/minecraft.json has delivery OFF (template default); these tests exercise the Send flow,
        so point the server at a temp copy with it ON."""
        path = Path(tmpdir) / "minecraft.json"
        path.write_text(json.dumps({**CFG, "enabled": True}))
        return path

    def start_village(self, points=0, village=None, **inventory):
        """Fresh server + page with `points` independent correct words already in events.jsonl (points = level) and
        the given inventory (emerald=..., wood=...) and, optionally, a `village` dict (the server-owned unlocked /
        emeralds_spent / levels). The data dir is a temp dir: the child's real data is never used."""
        progress = json.loads(json.dumps(server.DEFAULT_PROGRESS))
        if village is not None:
            progress["village"] = {**progress["village"], **village}
        progress["inventory"].update(inventory)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "data"
        data.mkdir()
        (data / "progress.json").write_text(json.dumps(progress))
        (data / "events.jsonl").write_text("".join(json.dumps(word_event()) + "\n" for _ in range(points)))
        srv = server.make_server(data, 0, mc_config=self.delivery_on_config(tmp.name))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.data = data
        self.url = f"http://127.0.0.1:{srv.server_address[1]}"
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.url + "/")
        page.wait_for_selector(".home")
        return page

    def start_village_routed(self, route, art=None):
        """Like start_village, but `route(page)` installs page.route fakes BEFORE the app loads and `art` (optional)
        pre-saves the art mode. Waits for Home or a loud error."""
        progress = json.loads(json.dumps(server.DEFAULT_PROGRESS))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "data"
        data.mkdir()
        (data / "progress.json").write_text(json.dumps(progress))
        (data / "events.jsonl").write_text("")
        srv = server.make_server(data, 0, mc_config=self.delivery_on_config(tmp.name))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.data = data
        self.url = f"http://127.0.0.1:{srv.server_address[1]}"
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        route(page)
        if art:
            page.add_init_script(f"if (!localStorage.getItem('reading_village_art_mode')) localStorage.setItem('reading_village_art_mode', '{art}')")
        page.goto(self.url + "/")
        page.wait_for_selector(".home, .loud")
        return page

    def api(self, path):
        with urllib.request.urlopen(self.url + path) as r:
            return json.loads(r.read())

    def saved(self):
        return json.loads((self.data / "progress.json").read_text())

    def read_story(self, page):
        """Tap Next until the story-done interlude appears. Waits for either, so the interlude replacing the
        button between a check and a click cannot make this flaky."""
        while True:
            page.wait_for_selector(".interlude, button.nav.primary:not([disabled])")
            if page.query_selector(".interlude"):
                return
            try:
                page.click("button.nav.primary:not([disabled])", timeout=1500)
            except Exception:  # the page moved on (interlude replaced the button): the loop re-checks
                pass

    def open_village(self, page):
        page.click("button.stage-btn:has-text(\"Sam's Village\")")
        page.wait_for_selector(".village-plots")

    def unlock(self, page, prof, how=None):
        page.click(f".plot.open[data-prof={prof}]")
        page.wait_for_selector(".picker")
        page.click({None: "#pick-free", "bell": "#pick-bell", "emeralds": "#pick-emeralds"}[how])
        page.wait_for_selector(".picker.meet")
        page.click("#meet-hub")
        page.wait_for_selector(f".plot.have[data-prof={prof}]")


class VillageFlows(VillageCase):
    def test_home_has_village_and_pile_tiles_and_no_build_tile(self):
        page = self.start_village()
        tiles = page.inner_text(".stage-row").upper()
        self.assertIn("SAM'S VILLAGE", tiles)
        self.assertIn("TREASURE PILE", tiles)
        self.assertNotIn("BUILD", tiles)
        self.assert_small_caps(page, "home with village tiles")

    def test_the_village_screen_and_its_home_tile_are_called_the_village_name(self):
        page = self.start_village()
        self.assertEqual(page.inner_text("button.stage-btn:has-text(\"Sam's Village\")").upper(), "SAM'S VILLAGE")
        self.open_village(page)
        self.assertEqual(page.inner_text(".stage-title").upper(), "SAM'S VILLAGE")

    def test_unlock_buy_sell_send_flow_and_small_caps_everywhere(self):
        page = self.start_village(points=100, emerald=200, wood=25, diamond=2)  # Journeyman, 2 bells (100 // 40)
        self.open_village(page)
        self.assertEqual(len(page.query_selector_all(".plot")), 14)
        self.assertEqual(len(page.query_selector_all(".plot.open")), 13, "13 villagers to pick from; the trader waits")
        self.assertIn("EVERY VILLAGER", page.inner_text(".plot.locked").upper())
        self.assert_small_caps(page, "village, nothing unlocked")

        # 1. the first villager is free, and he chooses which
        page.click(".plot.open[data-prof=librarian]")
        page.wait_for_selector(".picker")
        self.assertIsNone(page.query_selector("#pick-bell"), "the first one has no payment choice")
        self.assert_small_caps(page, "unlock picker (free)")
        page.click("#pick-free")
        page.wait_for_selector(".picker.meet")
        self.assert_small_caps(page, "villager moved in")
        self.assertEqual(self.saved()["village"]["unlocked"], ["librarian"])
        self.assertEqual(self.saved()["inventory"]["emerald"], 200, "free means free")
        page.click("#meet-shop")
        page.wait_for_selector(".offers")

        # 2. level locks: a Novice villager's higher offers are greyed with "Reach Apprentice!" etc., not hidden or scolded
        locked = page.query_selector_all(".offer.locked")
        self.assertGreater(len(locked), 0)
        self.assertRegex(locked[0].inner_text().upper(), r"REACH (APPRENTICE|JOURNEYMAN|EXPERT|MASTER)!")
        self.assertIsNone(page.query_selector(".offer.locked[onclick]"))
        self.assert_small_caps(page, "librarian shop")
        page.click(".offer.locked >> nth=0", force=True)  # tapping a locked card does nothing
        self.assertIsNotNone(page.query_selector(".offers"))

        # 3. buy: the server debits, the treasure lands in the pile (not in Minecraft)
        page.click(".offer[data-offer=lib_nametag]")
        page.wait_for_selector(".confirm")
        self.assert_small_caps(page, "confirm purchase")
        page.click("#buy-yes")
        page.wait_for_selector("#bought")
        self.assertIn("TREASURE PILE", page.inner_text("#bought").upper())
        self.assertEqual(self.saved()["inventory"]["emerald"], 198)
        self.assertEqual([t["label"] for t in self.saved()["treasure"]][-1], "Name Tags")
        self.assertEqual(self.api("/api/minecraft")["pending"], [], "buying sends nothing")

        # 4. a bell unlock and an emerald unlock
        page.click(".back-btn")
        page.wait_for_selector(".village-plots")
        self.unlock(page, "armorer", "bell")
        self.assertEqual(self.saved()["village"]["bells_spent"], 1)
        self.unlock(page, "farmer", "emeralds")
        self.assertEqual(self.saved()["inventory"]["emerald"], 198 - 15)
        self.assert_small_caps(page, "village with three villagers")

        # 5. sell to the village
        page.click("#sell-btn")
        page.wait_for_selector(".trades")
        self.assert_small_caps(page, "sell stall")
        page.click(".trade[data-trade=diamond1]")
        page.wait_for_function("document.querySelector('.trade[data-trade=diamond1]').classList.contains('dim') === false")
        page.wait_for_timeout(400)
        self.assertEqual((self.saved()["inventory"]["diamond"], self.saved()["inventory"]["emerald"]), (1, 183 + 2))
        page.click(".back-btn")

        # 6. the pile: choose a subset and send
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        kept = page.query_selector_all(".treasure.kept")
        self.assertEqual(len(kept), 4, "three villager kits + name tags")
        self.assertTrue(page.is_disabled("#send-btn"), "nothing chosen, nothing to send")
        self.assert_small_caps(page, "treasure pile")
        page.click(".treasure.kept >> nth=0")
        page.click(".treasure.kept >> nth=3")
        self.assertIn("2", page.inner_text("#chosen-count"))
        self.assert_small_caps(page, "pile with a choice")
        page.click("#send-btn")
        page.wait_for_selector("#sent-done", timeout=20000)
        self.assertIn("SENT TO YOUR MAGIC CHEST!", page.inner_text("#portal-msg").upper())
        self.assert_small_caps(page, "send scene end")
        page.click("#sent-done")
        page.wait_for_selector(".pile")
        states = self.api("/api/treasure")["treasure"]
        self.assertEqual(sorted(t["state"] for t in states), ["kept", "kept", "on_the_way", "on_the_way"])
        self.assertEqual(len(page.query_selector_all(".treasure.kept")), 2, "unsent treasure stays in the pile")
        self.assertIn("ON THE WAY", page.inner_text("#sent-list").upper())
        self.assert_small_caps(page, "pile after send")
        # Dad's bar says so loudly: sends are waiting and nothing will deliver them
        self.assertIsNotNone(page.query_selector(".dad-bar .mc-loud"))
        self.assertEqual(len(self.api("/api/minecraft")["pending"]), 2)
        self.assertIsNone(page.query_selector(".loud"))

    def test_emeralds_not_enough_is_dim_not_an_error(self):
        page = self.start_village(emerald=3)
        self.open_village(page)
        self.unlock(page, "farmer")  # first villager: free
        page.click(".plot.open[data-prof=librarian]")
        page.wait_for_selector(".picker")
        self.assertTrue(page.is_disabled("#pick-bell"), "no bells yet")
        self.assertTrue(page.is_disabled("#pick-emeralds"), "3 emeralds is not 20")
        self.assertIsNone(page.query_selector(".loud"))

    def test_expensive_offer_is_dimmed_and_does_not_open(self):
        page = self.start_village(emerald=2)
        self.open_village(page)
        self.unlock(page, "librarian")
        page.click(".plot.have")
        page.wait_for_selector(".offers")
        self.assertGreater(len(page.query_selector_all(".offer.poor")), 0)
        page.click(".offer[data-offer=lib_shelves]", force=True)  # costs 3
        page.wait_for_timeout(200)
        self.assertIsNone(page.query_selector(".confirm"))

    def test_trader_plot_opens_after_every_villager(self):
        page = self.start_village(emerald=5000)
        self.open_village(page)
        for p in CFG["village"]["professions"][:13]:
            self.unlock(page, p["id"], None if p is CFG["village"]["professions"][0] else "emeralds")
        page.wait_for_selector(".plot.open[data-prof=wandering_trader]")
        self.assert_small_caps(page, "all villagers, trader waiting")


class Earning(VillageCase):
    def test_word_gives_wood_and_the_configured_emeralds(self):
        page = self.start_village()
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        page.click("button.good:not([disabled])")
        page.wait_for_function("document.querySelector('.inv-n') && [...document.querySelectorAll('.inv-n')].some(e => e.textContent === '1')")
        inv = self.saved()["inventory"]
        self.assertEqual((inv["wood"], inv["emerald"]), (1, EARN["word_emerald"]))

    def test_craft_gives_an_emerald_and_a_treasure_toast(self):
        page = self.start_village()
        page.click("button.stage-btn:has-text('Crafting Table')")
        page.wait_for_selector(".craft-tile")
        for letter in "PIG":  # the first word of a fresh round (file order); small caps has no confusable gate
            page.click(f".craft-tile[data-letter='{letter}']:not([disabled])")
        page.click(".craft-btn.ready")
        page.wait_for_selector("#surprise.show")
        self.assertIn("SURPRISE", page.inner_text("#surprise").upper())
        self.assert_small_caps(page, "surprise toast")
        self.assertEqual(self.saved()["inventory"]["emerald"], EARN["craft_emerald"])
        self.assertEqual(len(self.saved()["treasure"]), 1)

    def test_first_story_pass_pays_the_configured_emeralds(self):
        page = self.start_village()
        page.click("button.stage-btn:has-text('Story')")
        page.wait_for_selector(".story-pick")
        page.click(".story-pick button >> nth=0")
        page.wait_for_selector(".story-text .w")
        self.read_story(page)
        self.assertEqual(self.saved()["inventory"]["emerald"], EARN["story_first_emerald"])
        self.assertIn(str(EARN["story_first_emerald"]), page.inner_text(".interlude"))
        self.assert_small_caps(page, "story done")
        types = [t["source"]["kind"] for t in self.saved()["treasure"]]
        self.assertIn("surprise", types, "a first story pass gives a surprise for the pile")

    def test_swap_in_read_logs_swap_done_and_gives_a_replay_surprise(self):
        page = self.start_village()
        p = self.saved()
        p["settings"].update(lowercase_track="on", lowercase_percent=50)
        p["stories"]["gold-pig"] = {"smallcaps_done": True, "lowercase_done": False, "resume_page": 0}
        (self.data / "progress.json").write_text(json.dumps(p))
        page.reload()
        page.wait_for_selector(".home")
        page.click("text=Lowercase track")
        page.wait_for_selector(".story-pick")
        page.click(".story-pick button >> nth=0")
        page.wait_for_selector(".story-text .w")
        self.read_story(page)
        events = [json.loads(l) for l in (self.data / "events.jsonl").read_text().splitlines()]
        done = [e for e in events if e["type"] == "swap_done"]
        self.assertEqual(len(done), 1)
        self.assertEqual((done[0]["track"], done[0]["story_id"], done[0]["percent"]), ("lowercase", "gold-pig", 50))
        self.assertFalse([e for e in events if e["type"] == "story_done"])
        refs = [t["source"]["ref"] for t in self.saved()["treasure"]]
        self.assertEqual(refs, ["story_replay:swap:gold-pig:replay1:epic"])
        self.assertEqual(self.saved()["inventory"]["emerald"], EARN["story_replay_emerald"])

    def test_adventure_done_event_is_sent_when_the_adventure_finishes(self):
        page = self.start_village()
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
        self.read_story(page)
        page.click(".interlude .btn")  # story done
        page.wait_for_selector(".interlude")  # next: Build
        page.click(".interlude .btn")
        page.wait_for_selector(".build")
        page.click("text=All done building")
        page.wait_for_selector(".interlude")
        done = [e for e in self.events() if e["type"] == "adventure_done"]
        self.assertEqual([e["adventure"] for e in done], ["smallcaps"])
        page.click(".interlude .btn")
        page.wait_for_selector(".home")


class LevelUp(VillageCase):
    def test_reading_points_no_longer_celebrate_a_village_level(self):
        """170 reading points used to be "Your village is now Expert!". Now only the minigame level (Word Blocks 2,
        earned by the 170 word events on file) is celebrated, and no village level treasure is made."""
        page = self.start_village(points=170)
        page.click("button.stage-btn:has-text('Word Blocks')")
        page.wait_for_selector(".big-word")
        page.click("button.good:not([disabled])")
        page.wait_for_timeout(500)
        page.click(".stage-top button")  # Home
        page.wait_for_selector(".interlude")
        self.assertNotIn("VILLAGE", page.inner_text(".interlude h1").upper())
        self.assertIn("LEVEL", page.inner_text(".interlude h1").upper())
        self.skip_celebrations(page)
        page.wait_for_selector(".home")
        levels = [t["source"]["ref"] for t in self.saved()["treasure"] if t["source"]["ref"].startswith("level:")]
        self.assertEqual(levels, [])
        self.assertIsNone(page.query_selector(".loud"))


class Promotions(VillageCase):
    """The promotion banner, the picker (the child chooses who), the celebration and the per-villager badges."""
    SHOTS = os.environ.get("VILLAGE_SHOTS")  # a directory: also save screenshots of the screens

    def shot(self, page, name):
        if self.SHOTS:
            page.screenshot(path=str(Path(self.SHOTS) / name))

    def test_banner_picker_confirm_celebration_and_per_villager_gating(self):
        page = self.start_village(emerald=20, village={"unlocked": ["armorer", "farmer"], "emeralds_spent": 30})
        self.open_village(page)
        self.assertIn("15 MORE EMERALDS", page.inner_text("#promo-hint").upper())  # 30 spent, next promotion at 45
        self.assertIn("PROMOTION READY!", page.inner_text("#promo-banner").upper())  # 2 earned (10, 25)
        for prof in ("armorer", "farmer"):
            self.assertIn("NOVICE", page.inner_text(f".plot.have[data-prof={prof}]").upper())
        self.assert_small_caps(page, "village with a promotion ready")
        self.shot(page, "village.png")

        page.click("#promo-banner")
        page.wait_for_selector(".promo-picker")
        self.assertEqual(sorted(e.get_attribute("data-prof") for e in page.query_selector_all(".promo-pick")), ["armorer", "farmer"])
        self.assert_small_caps(page, "promotion picker")
        self.shot(page, "picker.png")
        page.click(".promo-pick[data-prof=armorer]")
        page.wait_for_selector("#promo-yes")
        self.assertIn("MAKE THE ARMORER APPRENTICE?", page.inner_text(".confirm").upper())
        self.assert_small_caps(page, "promotion confirm")
        page.click("#promo-no")
        page.wait_for_selector(".promo-picker")
        self.assertEqual(self.saved()["village"]["levels"], {}, "Not now changes nothing")
        page.click(".promo-pick[data-prof=armorer]")
        page.wait_for_selector("#promo-yes")
        page.dblclick("#promo-yes")  # a double tap is one promotion
        page.wait_for_selector(".promoted")
        self.assertIn("THE ARMORER IS NOW APPRENTICE!", page.inner_text(".promoted").upper())
        self.assertIn("NEW TRADES!", page.inner_text("#new-trades").upper())
        self.assert_small_caps(page, "promotion celebration")
        self.shot(page, "celebration.png")
        self.assertEqual(self.saved()["village"]["levels"], {"armorer": 1})
        self.assertEqual(len([l for l in self.api("/api/history?kind=promote")["lines"]]), 1)

        page.click("#promoted-shop")  # the promoted Armorer sells its Apprentice goods; the Farmer's stay locked
        page.wait_for_selector(".offers")
        self.assertIsNone(page.query_selector(".offer.locked[data-offer=arm_iron_legs]"))
        self.assertIsNotNone(page.query_selector(".offer.locked[data-offer=arm_diamond_boots]"))
        self.assertRegex(page.inner_text(".offer.locked[data-offer=arm_diamond_boots]").upper(), r"REACH JOURNEYMAN!")
        self.assert_small_caps(page, "promoted villager's shop")
        page.click(".back-btn")
        page.wait_for_selector(".village-plots")
        self.assertIn("APPRENTICE", page.inner_text(".plot.have[data-prof=armorer]").upper())
        self.assertIn("NOVICE", page.inner_text(".plot.have[data-prof=farmer]").upper())
        self.assertIn("PROMOTION READY!", page.inner_text("#promo-banner").upper(), "one more is waiting")
        page.click("#promo-banner")
        page.wait_for_selector(".promo-picker")
        page.click(".promo-pick[data-prof=farmer]")
        page.click("#promo-yes")
        page.wait_for_selector(".promoted")
        page.click("#promoted-hub")
        page.wait_for_selector(".village-plots")
        self.assertIsNone(page.query_selector("#promo-banner"), "nothing left to choose")
        self.assertEqual(self.saved()["village"]["levels"], {"armorer": 1, "farmer": 1})
        self.assertIsNone(page.query_selector(".loud"))

    def test_no_banner_without_a_promotion_and_the_hint_counts_down(self):
        page = self.start_village(village={"unlocked": ["armorer"], "emeralds_spent": 4})
        self.open_village(page)
        self.assertIsNone(page.query_selector("#promo-banner"))
        self.assertIn("6 MORE EMERALDS FOR A PROMOTION", page.inner_text("#promo-hint").upper())
        self.assert_small_caps(page, "village, no promotion yet")

    def test_masters_are_not_offered_for_promotion(self):
        page = self.start_village(village={"unlocked": ["armorer", "farmer"], "emeralds_spent": 1000, "levels": {"armorer": 4}})
        self.open_village(page)
        page.click("#promo-banner")
        page.wait_for_selector(".promo-picker")
        self.assertEqual([e.get_attribute("data-prof") for e in page.query_selector_all(".promo-pick")], ["farmer"])


class LoudFailures(VillageCase):
    def test_refused_send_is_loud_and_never_says_sent(self):
        page = self.start_village(emerald=50)
        self.open_village(page)
        self.unlock(page, "farmer")
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        page.route("**/api/treasure/send", lambda r: r.fulfill(status=409, content_type="application/json", body='{"error":"already sent"}'))
        page.click(".treasure.kept >> nth=0")
        page.click("#send-btn")
        page.wait_for_selector("#overlay .loud")
        self.assertIn("SEND FAILED", page.inner_text("#overlay .loud-title"))
        self.assertIn("already sent", page.inner_text("#overlay"))
        self.assertNotIn("SENT TO YOUR MAGIC CHEST", page.inner_text("body").upper())

    def test_dashboard_shows_minecraft_panel_loud_when_sends_wait_with_no_worker(self):
        page = self.start_village(emerald=50)
        self.open_village(page)
        self.unlock(page, "farmer")
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        page.click("#choose-all")
        page.click("#send-btn")
        page.wait_for_selector("#sent-done", timeout=20000)
        page.goto(self.url + "/dashboard.html")
        page.wait_for_selector("#mc-panel")
        self.assertIn("mc-panel-loud", page.get_attribute("#mc-panel", "class"))
        self.assertIn("Delivery worker is NOT running", page.inner_text("#mc-panel .mc-banner >> nth=0"))
        self.assertIn("1 waiting", page.inner_text("#mc-panel"))
        self.assertFalse(self.errors, self.errors)


if __name__ == "__main__":
    unittest.main()


class DoubleTap(VillageCase):
    """A double-tap on any POSTing button sends exactly one request (review finding 1: Buy / sell / Unlock used to
    stay live until the reply re-rendered the screen, so the second tap bought or unlocked twice)."""

    def count_posts(self, page, suffix):
        seen = []
        page.on("request", lambda r: seen.append(r.url) if r.method == "POST" and r.url.endswith(suffix) else None)
        return seen

    @staticmethod
    def double_tap(page, selector):
        # Two clicks in the same tick: the strictest double-tap (no reply can arrive between them).
        page.eval_on_selector(selector, "el => { el.click(); el.click(); }")

    def test_double_tap_buy_sends_one_request_and_buys_once(self):
        page = self.start_village(emerald=50)
        self.open_village(page)
        self.unlock(page, "librarian")
        page.click(".plot.have")
        page.wait_for_selector(".offers")
        page.click(".offer[data-offer=lib_nametag]")
        page.wait_for_selector("#buy-yes")
        posts = self.count_posts(page, "/api/shop/buy")
        self.double_tap(page, "#buy-yes")
        page.wait_for_selector("#bought")
        page.wait_for_timeout(300)
        self.assertEqual(len(posts), 1, "one tap pair = one purchase request")
        self.assertEqual(len([t for t in self.saved()["treasure"] if t["label"] == "Name Tags"]), 1)
        self.assertIsNone(page.query_selector(".loud"))

    def test_double_tap_sell_sends_one_request(self):
        page = self.start_village(wood=40)
        self.open_village(page)
        page.click("#sell-btn")
        page.wait_for_selector(".trades")
        posts = self.count_posts(page, "/api/shop/trade")
        self.double_tap(page, ".trade[data-trade=wood10]")
        page.wait_for_timeout(600)
        self.assertEqual(len(posts), 1)
        self.assertEqual(self.saved()["inventory"]["wood"], 30, "sold once, not twice")
        self.assertIsNone(page.query_selector(".loud"))

    def test_double_tap_unlock_sends_one_request_and_no_error_overlay(self):
        page = self.start_village()
        self.open_village(page)
        page.click(".plot.open[data-prof=librarian]")
        page.wait_for_selector("#pick-free")
        posts = self.count_posts(page, "/api/village/unlock")
        self.double_tap(page, "#pick-free")
        page.wait_for_selector(".picker.meet")
        page.wait_for_timeout(300)
        self.assertEqual(len(posts), 1)
        self.assertIsNone(page.query_selector(".loud"), "a second unlock would have shown the 400 overlay")
        self.assertEqual(self.saved()["village"]["unlocked"], ["librarian"])


def red_png(size=16):
    """A solid red PNG (so real-mode tests need no Mojang files)."""
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * size for _ in range(size))

    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


MAPPING = json.loads((ROOT / "app" / "js" / "mctextures_map.json").read_text())


class ArtMode(VillageCase):
    """Dad's art-mode setting. The texture files are faked with page.route, so these tests behave the same with or
    without Dad's extracted Mojang textures on the machine (those are gitignored and never needed for tests)."""

    def fake_textures(self, page, drop=()):
        sprites = {i: "f/red.png" for i in MAPPING["entries"] if i not in drop}
        manifest = {"v": 1, "source_jar": "x", "jar_sha256": "x", "minecraft_version": "test", "files": {"f/red.png": {"w": 16, "h": 16, "sha256": "x"}}, "sprites": sprites}
        page.route("**/assets/mc/manifest.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(manifest)))
        page.route("**/assets/mc/f/red.png", lambda r: r.fulfill(status=200, content_type="image/png", body=red_png()))

    def no_textures(self, page):
        page.route("**/assets/mc/manifest.json", lambda r: r.fulfill(status=404, content_type="application/json", body='{"error":"nf"}'))

    def open_settings(self, page):
        page.click(".dad-corner .settings-gear")
        page.wait_for_selector("#settings-art")

    def test_real_is_not_offered_without_the_extracted_textures(self):
        page = self.start_village_routed(self.no_textures)
        self.open_settings(page)
        page.wait_for_selector("#art-state")
        self.assertIsNone(page.query_selector("#art-toggle"))
        self.assertIn("not installed", page.inner_text("#art-state"))

    def test_default_is_hand_drawn_and_real_can_be_switched_on_and_off(self):
        page = self.start_village_routed(self.fake_textures)
        self.assertEqual(page.evaluate("localStorage.getItem('reading_village_art_mode')"), None, "default: nothing saved = hand")
        self.open_settings(page)
        page.wait_for_selector("#art-toggle")
        self.assertIn("hand-drawn", page.inner_text("#art-toggle"))
        self.assertIsNone(page.query_selector("#art-unmapped"))
        page.click("#art-toggle")
        page.wait_for_selector("#art-unmapped")  # Settings re-renders in real mode with the hand-drawn list
        self.assertEqual(page.evaluate("localStorage.getItem('reading_village_art_mode')"), "real")
        ids = page.eval_on_selector_all("#art-unmapped li", "els => els.map(e => e.dataset.id)")
        self.assertIn("hero", ids)
        self.assertIn("villager_locked", ids)
        self.assertNotIn("villager_librarian", ids)
        self.assertIn("character, hand-drawn", page.inner_text("#art-unmapped li[data-id=hero]"))
        # the real texture is what gets drawn: the fake villager is solid red, a hand-drawn one is not
        red = """async () => { const m = await import('/js/sprites.js'); const px = (n) => { const c = m.spriteImage(n); const d = c.getContext('2d').getImageData(c.width/2, c.height-8, 1, 1).data; return [...d]; }; return [px('villager_librarian'), px('hero')]; }"""
        villager, hero = page.evaluate(red)
        self.assertEqual(villager, [255, 0, 0, 255])
        self.assertNotEqual(hero, [255, 0, 0, 255], "unmapped ids stay hand-drawn")
        page.click("#art-toggle")
        page.wait_for_function("document.querySelector('#art-toggle') && document.querySelector('#art-toggle').textContent.includes('hand-drawn (click')")
        self.assertEqual(page.evaluate("localStorage.getItem('reading_village_art_mode')"), "hand")
        self.assertEqual(self.errors, [])

    def test_village_screens_render_in_real_mode(self):
        page = self.start_village_routed(self.fake_textures, art="real")
        self.open_village(page)
        self.unlock(page, "librarian")
        page.click(".plot.have")
        page.wait_for_selector(".offers")
        self.assert_small_caps(page, "librarian shop, real art")
        page.click(".back-btn")
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        self.assertEqual(self.errors, [])
        self.assertIsNone(page.query_selector(".loud"))

    def test_a_mapped_sprite_without_a_texture_is_a_loud_boot_failure_and_art_hand_resets_it(self):
        page = self.start_village_routed(lambda p: self.fake_textures(p, drop=("villager_librarian",)), art="real")
        # start_village_routed waited for .home or .loud: the missing texture must be loud, not a silent hand-drawn villager
        self.assertIsNotNone(page.query_selector(".loud"))
        self.assertIn("villager_librarian", page.inner_text(".loud"))
        page.goto(self.url + "/?art=hand")
        page.wait_for_selector(".home")
        self.assertEqual(page.evaluate("localStorage.getItem('reading_village_art_mode')"), "hand")


def hist_line(kind, what, i=0, wallet=None):
    return {"v": 1, "ts": f"2026-10-18T09:{i // 60:02d}:{i % 60:02d}-04:00", "kind": kind, "what": what, "wallet_after": wallet, "ref": f"r{i}"}


TAG = [{"item": "minecraft:name_tag", "count": 2}]
HISTORY = [
    hist_line("earn", {"resources": {"wood": 1, "emerald": 1}, "last_event": {"type": "word", "item": "pig"}}, 0, {"emerald": 1}),
    hist_line("trade", {"trade_id": "wood10", "give": {"wood": 10}, "get": {"emerald": 1}}, 1, {"emerald": 2}),
    hist_line("treasure", {"tid": "t000001", "label": "Name Tags", "items": TAG, "source": {"kind": "shop", "ref": "lib_nametag"}}, 2),
    hist_line("unlock", {"profession": "librarian", "name": "Librarian", "paid": "free"}, 3),
    hist_line("level", {"index": 1, "name": "Apprentice", "points": 30}, 4),
    hist_line("send", {"tids": ["t000001"], "items": TAG}, 5),
    hist_line("delivered", {"delivery": "d000001", "tid": "t000001", "label": "Name Tags", "items": TAG, "chest": {"x": 1, "y": 2, "z": 3}, "log": ["Dropped 2 [Name Tag]"]}, 6),
]
TOTALS = {"earned": {"wood": 1, "emerald": 1}, "spent": {}, "sent": {"minecraft:name_tag": 2}, "delivered": {"minecraft:name_tag": 2}, "unlocked": ["librarian"], "levels": [1]}


def hist_body(lines, totals=TOTALS, kind=None):
    """A GET /api/history reply: {v, kind, count, lines, totals} (docs/design.md "Rewards history")."""
    return {"v": 1, "kind": kind, "count": len(lines), "lines": lines, "totals": totals}


class RewardsHistory(VillageCase):
    """The Treasure Book (the child) and the dashboard's Rewards history (Dad), reading GET /api/history. The response
    is faked with page.route so these tests pin the FRONTEND contract (docs/design.md "Rewards history")."""

    def serve_history(self, page, body, status=200):
        page.route("**/api/history", lambda r: r.fulfill(status=status, content_type="application/json", body=json.dumps(body)))

    def open_book(self, page):
        self.open_village(page)
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        page.click("#book-btn")
        page.wait_for_selector(".book")

    def test_treasure_book_is_newest_first_small_caps_with_pictures_and_hides_bookkeeping(self):
        page = self.start_village()
        self.serve_history(page, hist_body(HISTORY))
        self.open_book(page)
        kinds = page.eval_on_selector_all(".book-row", "els => els.map(e => e.dataset.kind)")
        self.assertEqual(kinds, ["delivered", "send", "level", "unlock", "treasure", "earn"], "newest first; the trade is Dad's")
        self.assertGreaterEqual(len(page.query_selector_all(".book-row canvas")), 6, "every row has a picture")
        self.assertIn("IS IN YOUR MAGIC CHEST", page.inner_text(".book-row >> nth=0").upper())
        self.assert_small_caps(page, "treasure book")
        page.click("#book-back")
        page.wait_for_selector(".pile")
        self.assertEqual(self.errors, [])

    def test_treasure_book_pages_a_long_history(self):
        page = self.start_village()
        self.serve_history(page, hist_body([hist_line("earn", {"resources": {"wood": 1}, "last_event": None}, i) for i in range(150)]))
        self.open_book(page)
        self.assertEqual(len(page.query_selector_all(".book-row")), 60)
        page.click("#book-more")
        self.assertEqual(len(page.query_selector_all(".book-row")), 120)

    def test_empty_history_is_a_calm_empty_book_not_an_error(self):
        page = self.start_village()
        self.serve_history(page, hist_body([], totals={**TOTALS, "earned": {}, "sent": {}, "delivered": {}, "unlocked": [], "levels": []}))
        self.open_book(page)
        self.assertIn("EMPTY", page.inner_text("#book-empty").upper())
        self.assertIsNone(page.query_selector(".loud"))

    def test_malformed_history_is_loud_never_an_empty_book(self):
        page = self.start_village()
        self.serve_history(page, hist_body([{"v": 1, "kind": "earn"}]))
        self.open_village(page)
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        page.click("#book-btn")
        page.wait_for_selector(".loud")
        self.assertIn("Treasure Book failed", page.inner_text(".loud"))
        self.assertIsNone(page.query_selector("#book-empty"))

    def test_dashboard_shows_totals_the_full_list_and_the_csv_link(self):
        page = self.start_village()
        self.serve_history(page, hist_body(HISTORY))
        page.goto(self.url + "/dashboard.html")
        page.wait_for_selector("#history-panel")
        self.assertIn("Ever earned: 1 wood, 1 emerald", page.inner_text("#history-totals"))
        panel = page.inner_text("#history-panel")
        self.assertIn("Confirmed delivered: 2 minecraft:name_tag", panel)
        self.assertIn("Villagers unlocked (1): Librarian", panel)
        self.assertEqual(len(page.query_selector_all("#history-panel tbody tr")), len(HISTORY), "the full list, oldest first")
        self.assertEqual(page.get_attribute("#history-csv", "href"), "/api/history.csv")
        self.assertIsNone(page.query_selector("#history-panel .mc-banner"))

    def test_dashboard_history_failure_is_a_red_banner(self):
        page = self.start_village()
        self.serve_history(page, {"error": "boom"}, status=500)
        page.goto(self.url + "/dashboard.html")
        page.wait_for_selector("#history-panel .mc-banner")
        self.assertIn("REWARDS HISTORY UNAVAILABLE", page.inner_text("#history-panel .mc-banner"))

    def test_real_server_history_flows_into_the_book_and_the_dashboard(self):
        """No fakes: unlock + buy through the real UI/server, then the real /api/history feeds both screens."""
        page = self.start_village(emerald=50)
        self.open_village(page)
        self.unlock(page, "librarian")
        page.click(".plot.have")
        page.wait_for_selector(".offers")
        page.click(".offer[data-offer=lib_nametag]")
        page.click("#buy-yes")
        page.wait_for_selector("#bought")
        body = self.api("/api/history")
        self.assertEqual(body["count"], len(body["lines"]))
        page.click(".back-btn")
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        page.click("#book-btn")
        page.wait_for_selector(".book-row")
        kinds = page.eval_on_selector_all(".book-row", "els => els.map(e => e.dataset.kind)")
        self.assertIn("treasure", kinds)
        self.assertIn("unlock", kinds)
        self.assertIsNone(page.query_selector(".loud"))
        self.assert_small_caps(page, "treasure book from the real server")
        page.goto(self.url + "/dashboard.html")
        page.wait_for_selector("#history-panel")
        self.assertIsNone(page.query_selector("#history-panel .mc-banner"))
        self.assertIn("Librarian", page.inner_text("#history-panel"))
        self.assertEqual(len(page.query_selector_all("#history-panel tbody tr")), body["count"])
