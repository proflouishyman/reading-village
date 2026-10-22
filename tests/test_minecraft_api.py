"""Village / shop / treasure API tests against a real server thread with a temp data dir and the shipped config.
The delivery worker is never started here (that is test_minecraft.py); these tests check what the API writes."""
import copy
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import minecraft_bridge as mcb  # noqa: E402
import server  # noqa: E402

CFG = json.loads((ROOT / "config" / "minecraft.json").read_text())
PROFS = [p["id"] for p in CFG["village"]["professions"]]
BASE_PROFS = PROFS[:13]
TS = "2026-10-18T09:00:00-04:00"


def ev(t, **kw):
    return {"v": 1, "ts": TS, "session_id": "s1", "type": t, **kw}


class Api(unittest.TestCase):
    config_path = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        config_path = self.config_path
        if config_path is None:
            # The shipped config has delivery OFF (template default); these tests exercise delivery, so use a copy
            # with it ON.
            config_path = Path(self.tmp.name) / "minecraft.json"
            config_path.write_text(json.dumps({**CFG, "enabled": True}))
        self.srv = server.make_server(self.data, 0, mc_config=config_path)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self._stderr = mock.patch("sys.stderr")
        self._stderr.start()

    def tearDown(self):
        self._stderr.stop()
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def req(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        r = urllib.request.Request(self.base + path, data=data, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def get(self, path):
        return self.req("GET", path)

    def post(self, path, body):
        return self.req("POST", path, body)

    # -- state helpers
    def progress(self):
        return self.get("/api/progress")[1]

    def set_inventory(self, **inv):
        """What the game client does: save progress with a changed inventory (client-owned)."""
        p = self.progress()
        p["inventory"].update(inv)
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 200)

    def add_events(self, *events):
        """Append already-valid events straight to events.jsonl (as if they had been posted earlier)."""
        with open(self.data / "events.jsonl", "a", encoding="utf-8") as f:
            for e in events:
                server.validate_event(e)
                f.write(json.dumps(e) + "\n")

    def words(self, n, session="old"):
        self.add_events(*[ev("word", track="smallcaps", item="pig", result="correct", session_id=session)] * n)

    def set_village(self, **keys):
        """Test seam for the SERVER-owned village keys (a client save cannot change them): rewrite progress.json
        with `keys` merged into progress.village and rev + 1."""
        pf = self.data / "progress.json"
        p = json.loads(pf.read_text())
        p["village"] = {**p.get("village", {"unlocked": [], "bells_spent": 0}), **keys}
        p["rev"] += 1
        server.validate_progress(p)
        pf.write_text(json.dumps(p))

    def unlock(self, pid, pay="emeralds"):
        return self.post("/api/village/unlock", {"profession": pid, "pay": pay})

    def unlock_all_base(self):
        self.set_inventory(emerald=10000)
        for pid in BASE_PROFS:
            self.assertEqual(self.unlock(pid)[0], 200, pid)

    def treasure(self):
        return self.get("/api/treasure")[1]["treasure"]

    def ledger(self):
        return self.srv.mc.ledger.deliveries()

    def history(self, kind=None):
        return self.get("/api/history" + (f"?kind={kind}" if kind else ""))[1]["lines"]


class VillageView(Api):
    def test_shape_at_the_start(self):
        s, v = self.get("/api/village")
        self.assertEqual(s, 200)
        self.assertEqual(v["level"], {"index": 0, "name": "Novice", "next_at": 30})
        self.assertEqual(v["points"], 0)
        self.assertEqual(v["bells"], {"earned": 0, "spent": 0, "available": 0})
        self.assertTrue(v["first_free"])
        self.assertEqual([p["id"] for p in v["professions"]], PROFS)
        lib = v["professions"][0]
        self.assertEqual((lib["unlocked"], lib["can_unlock"], lib["unlock_emeralds"]), (False, True, 20))
        self.assertFalse(v["professions"][13]["can_unlock"])  # the trader waits for everyone
        offers = {o["id"]: o for o in lib["offers"]}
        self.assertFalse(offers["lib_nametag"]["locked"])
        self.assertTrue(offers["lib_mending"]["locked"])  # Master only
        self.assertEqual(v["earn"], CFG["earn"])
        self.assertEqual(len(v["trades"]), 6)

    def test_points_level_and_bells_are_derived_from_events(self):
        self.words(35)
        self.add_events(ev("story_done", track="smallcaps", story_id="a"),
                        ev("story_done", track="smallcaps", story_id="a"))
        v = self.get("/api/village")[1]
        self.assertEqual(v["points"], 35 + 10)
        self.assertEqual(v["level"]["name"], "Apprentice")
        self.assertEqual(v["bells"]["earned"], 1 + 1)  # one first pass + 45 // 40

    def test_letters_mastered_count_beyond_the_starting_two(self):
        p = self.progress()
        p["active_letters"] = ["b", "d", "p", "q"]
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 200)
        self.assertEqual(self.get("/api/village")[1]["points"], 10)  # 2 mastered x 5

    def test_unchanged_by_reading_progress_json_edits_to_inventory(self):
        self.set_inventory(emerald=500)
        self.assertEqual(self.get("/api/village")[1]["points"], 0)  # emeralds are not reading points


class Unlock(Api):
    def test_first_unlock_is_free_whatever_pay_says_and_creates_treasure_not_a_delivery(self):
        s, r = self.unlock("armorer", "bell")
        self.assertEqual(s, 200)
        self.assertEqual(r["wallet"]["emerald"], 0)
        self.assertEqual(r["treasure"]["status"], "kept")
        self.assertEqual([i["item"] for i in r["treasure"]["items"]], ["minecraft:villager_spawn_egg", "minecraft:blast_furnace"])
        self.assertEqual(r["treasure"]["source"], {"kind": "unlock", "ref": "unlock:armorer"})
        self.assertTrue(r["village"]["professions"][1]["unlocked"])
        self.assertFalse(r["village"]["first_free"])
        self.assertEqual(self.ledger(), [])  # nothing goes to Minecraft by itself
        self.assertEqual(self.progress()["village"], {"unlocked": ["armorer"], "bells_spent": 0, "emeralds_spent": 0, "levels": {}})

    def test_second_unlock_by_emeralds(self):
        self.unlock("armorer")
        self.assertEqual(self.unlock("farmer")[0], 409)  # 0 emeralds
        self.set_inventory(emerald=14)
        self.assertEqual(self.unlock("farmer")[0], 409)  # farmer costs 15
        self.set_inventory(emerald=16)
        s, r = self.unlock("farmer", "emeralds")
        self.assertEqual((s, r["wallet"]["emerald"]), (200, 1))
        self.assertEqual(self.progress()["village"]["bells_spent"], 0)

    def test_second_unlock_by_bell(self):
        self.unlock("armorer")
        s, r = self.unlock("farmer", "bell")
        self.assertEqual(s, 409)
        self.assertIn("Bell", r["error"])
        self.add_events(ev("story_done", track="smallcaps", story_id="a"))  # one bell
        self.set_inventory(emerald=100)
        s, r = self.unlock("farmer", "bell")
        self.assertEqual(s, 200)
        self.assertEqual(r["wallet"]["emerald"], 100)  # emeralds untouched
        self.assertEqual(r["village"]["bells"], {"earned": 1, "spent": 1, "available": 0})
        self.assertEqual(self.unlock("shepherd", "bell")[0], 409)  # the bell is spent

    def test_bad_requests(self):
        self.assertEqual(self.unlock("nobody")[0], 400)
        self.assertEqual(self.post("/api/village/unlock", {"profession": "farmer", "pay": "gold"})[0], 400)
        self.assertEqual(self.post("/api/village/unlock", {"profession": "farmer"})[0], 400)
        self.assertEqual(self.post("/api/village/unlock", {"profession": "farmer", "pay": "bell", "x": 1})[0], 400)
        self.assertEqual(self.unlock("farmer")[0], 200)
        s, r = self.unlock("farmer")
        self.assertEqual(s, 400)
        self.assertIn("already unlocked", r["error"])
        self.assertEqual(len(self.treasure()), 1)  # the failed ones changed nothing

    def test_wandering_trader_needs_all_thirteen(self):
        self.set_inventory(emerald=10000)
        for pid in BASE_PROFS[:-1]:
            self.assertEqual(self.unlock(pid)[0], 200)
        s, r = self.unlock("wandering_trader")
        self.assertEqual(s, 409)
        self.assertIn("Leatherworker", r["error"])
        self.assertEqual(self.unlock("leatherworker")[0], 200)
        v = self.get("/api/village")[1]
        self.assertTrue(v["professions"][13]["can_unlock"])
        s, r = self.unlock("wandering_trader", "emeralds")
        self.assertEqual(s, 200)
        self.assertEqual([i["item"] for i in r["treasure"]["items"]],
                         ["minecraft:wandering_trader_spawn_egg", "minecraft:trader_llama_spawn_egg"])
        self.assertEqual(r["treasure"]["items"][1]["count"], 2)
        paid = sum(p["unlock_emeralds"] for p in CFG["village"]["professions"][1:])  # first one is free
        self.assertEqual(r["wallet"]["emerald"], 10000 - paid)


class Shop(Api):
    def test_buy_needs_unlock_level_and_emeralds(self):
        self.set_inventory(emerald=100)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "lib_nametag"})[0], 409)  # librarian locked
        self.unlock("librarian")
        s, r = self.post("/api/shop/buy", {"offer_id": "lib_mending"})
        self.assertEqual(s, 409)  # Master only
        self.assertIn("Master", r["error"])
        self.assertEqual(self.progress()["inventory"]["emerald"], 100)
        self.set_inventory(emerald=1)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "lib_nametag"})[0], 409)  # costs 2
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "nope"})[0], 400)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "lib_nametag", "price": 0})[0], 400)  # client never prices

    def test_buy_is_atomic_and_creates_treasure_only(self):
        self.unlock("librarian")
        self.set_inventory(emerald=10)
        s, r = self.post("/api/shop/buy", {"offer_id": "lib_nametag"})
        self.assertEqual(s, 200)
        self.assertEqual(r["wallet"]["emerald"], 8)
        t = r["treasure"]
        self.assertEqual((t["label"], t["sprite"], t["status"]), ("Name Tags", "name_tag", "kept"))
        self.assertEqual(t["items"], [{"item": "minecraft:name_tag", "count": 2}])
        self.assertEqual(self.ledger(), [])
        p = self.progress()
        self.assertEqual(p["inventory"]["emerald"], 8)
        self.assertEqual([x["tid"] for x in p["treasure"]], ["t000001", t["tid"]])  # the unlock, then the purchase

    def test_enchanted_book_and_spawn_egg_at_the_right_level(self):
        self.unlock("librarian")
        self.set_inventory(emerald=1000)
        self.unlock("leatherworker")
        # Master librarian (4 promotions) and Expert leatherworker (3): villager levels, not reading points, gate trades
        self.set_village(emeralds_spent=1000, levels={"librarian": 4, "leatherworker": 3})
        s, r = self.post("/api/shop/buy", {"offer_id": "lib_mending"})
        self.assertEqual(s, 200)
        self.assertEqual(r["treasure"]["items"], [{"item": "minecraft:enchanted_book", "count": 1,
                                                    "stored_enchantments": {"minecraft:mending": 1}}])
        s, r = self.post("/api/shop/buy", {"offer_id": "lea_horse_egg"})
        self.assertEqual((s, r["treasure"]["items"][0]["item"]), (200, "minecraft:horse_spawn_egg"))

    def test_trade_still_works(self):
        self.set_inventory(wood=25)
        s, r = self.post("/api/shop/trade", {"trade_id": "wood10"})
        self.assertEqual((s, r["wallet"]["wood"], r["wallet"]["emerald"]), (200, 15, 1))
        self.set_inventory(wood=3)
        self.assertEqual(self.post("/api/shop/trade", {"trade_id": "wood10"})[0], 409)
        self.assertEqual(self.post("/api/shop/trade", {"trade_id": "nope"})[0], 400)


class DeliveryDisabled(Api):
    """enabled: false in the config: treasure still accumulates, but nothing can be sent."""

    @classmethod
    def setUpClass(cls):
        cls._cfgdir = tempfile.TemporaryDirectory()
        cfg = copy.deepcopy(CFG)
        cfg["enabled"] = False
        cls.config_path = Path(cls._cfgdir.name) / "off.json"
        cls.config_path.write_text(json.dumps(cfg))

    @classmethod
    def tearDownClass(cls):
        cls._cfgdir.cleanup()

    def test_buying_works_but_sending_is_refused(self):
        self.unlock("librarian")
        self.set_inventory(emerald=10)
        s, r = self.post("/api/shop/buy", {"offer_id": "lib_nametag"})
        self.assertEqual(s, 200)
        s, r2 = self.post("/api/treasure/send", {"tids": [r["treasure"]["tid"]]})
        self.assertEqual(s, 409)
        self.assertIn("disabled", r2["error"])
        self.assertEqual(self.ledger(), [])


class EventTreasure(Api):
    def test_craft_creates_treasure_with_the_word_sprite(self):
        s, r = self.post("/api/event", ev("craft", track="smallcaps", item="SUN", result="correct"))
        self.assertEqual(s, 200)
        self.assertEqual(r["treasure"], [{"label": "Glowstone x4 + Sunflower", "sprite": "sun"}])
        self.assertNotIn("level_up", r)
        t = self.treasure()[0]
        self.assertEqual((t["state"], t["source"]), ("kept", {"kind": "craft", "ref": "SUN"}))
        self.assertEqual(self.ledger(), [])

    def test_craft_every_word_has_a_real_item(self):
        for w in server.load_craft_words():
            self.assertEqual(self.post("/api/event", ev("craft", track="smallcaps", item=w, result="assisted"))[0], 200)
        self.assertEqual(len(self.treasure()), len(server.load_craft_words()))

    def test_unconfigured_craft_word_is_400_and_writes_nothing(self):
        s, r = self.post("/api/event", ev("craft", track="smallcaps", item="ZAP", result="correct"))
        self.assertEqual(s, 400)
        self.assertFalse((self.data / "events.jsonl").exists())

    def test_story_first_then_replay(self):
        s, r = self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))
        self.assertEqual(len(r["treasure"]), 1)
        self.assertEqual(self.treasure()[0]["source"]["ref"], "story_first:smallcaps:a")
        s, r = self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))
        self.assertEqual(self.treasure()[1]["source"]["ref"], "story_replay:smallcaps:a:replay1:epic")

    def labels(self, tier):
        return [x["label"] for x in CFG["tiers"][tier]]

    def replay_entries(self):
        return [t for t in self.treasure() if t["source"]["ref"].startswith("story_replay:")]

    def test_replays_escalate_epic_then_legendary(self):
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))  # first pass: epic as before
        self.assertIn(self.treasure()[0]["label"], self.labels("epic"))
        for _ in range(3):
            self.assertEqual(self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))[0], 200)
        refs_labels = [(t["source"]["ref"], t["label"]) for t in self.replay_entries()]
        self.assertEqual([r for r, _ in refs_labels], ["story_replay:smallcaps:a:replay1:epic",
                                                        "story_replay:smallcaps:a:replay2:legendary",
                                                        "story_replay:smallcaps:a:replay3:legendary"])
        self.assertIn(refs_labels[0][1], self.labels("epic"))
        self.assertIn(refs_labels[1][1], self.labels("legendary"))
        self.assertIn(refs_labels[2][1], self.labels("legendary"))

    def test_replay_count_is_per_story_and_a_new_track_is_not_a_replay(self):
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))
        self.post("/api/event", ev("story_done", track="lowercase", story_id="a"))  # first pass of its own track
        self.assertEqual(self.replay_entries(), [])
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="b"))
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="b"))
        self.assertEqual([t["source"]["ref"] for t in self.replay_entries()], ["story_replay:smallcaps:b:replay1:epic"])

    def test_swap_in_read_gives_a_replay_surprise(self):
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))
        s, r = self.post("/api/event", ev("swap_done", track="lowercase", story_id="a", percent=30))
        self.assertEqual((s, len(r["treasure"])), (200, 1))
        self.assertEqual(self.replay_entries()[0]["source"]["ref"], "story_replay:swap:a:replay1:epic")
        self.post("/api/event", ev("swap_done", track="lowercase", story_id="a", percent=30))  # a second, later read
        self.assertEqual(self.replay_entries()[1]["source"]["ref"], "story_replay:swap:a:replay2:legendary")
        self.assertIn(self.replay_entries()[1]["label"], self.labels("legendary"))
        self.assertEqual(len(self.history("treasure")), 3)  # the history line carries the ref: number and tier
        self.assertIn("replay2:legendary", self.history("treasure")[-1]["ref"] + self.history("treasure")[-1]["what"]["source"]["ref"])

    def test_swap_page_alone_gives_no_surprise(self):
        self.post("/api/event", ev("swap_page", track="lowercase", story_id="a", page=0, percent=30))
        self.assertEqual(self.treasure(), [])

    def test_retry_of_a_swap_done_gives_one_surprise(self):
        e = ev("swap_done", track="lowercase", story_id="a", percent=30)
        real_open = open

        def failing_open(path, mode="r", *a, **kw):
            if str(path).endswith("events.jsonl") and "a" in mode:
                raise OSError("disk full")
            return real_open(path, mode, *a, **kw)
        with mock.patch("server.open", failing_open, create=True):
            self.assertEqual(self.post("/api/event", e)[0], 500)
        first = [t["label"] for t in self.treasure()]
        self.assertEqual(len(first), 1)
        self.assertEqual(self.post("/api/event", e)[0], 200)
        self.assertEqual([t["label"] for t in self.treasure()], first)
        self.assertEqual(len(self.history("treasure")), 1)

    def test_surprise_comes_from_the_configured_tier(self):
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))
        t = self.treasure()[0]
        epic = [x["label"] for x in CFG["tiers"]["epic"]]
        self.assertIn(t["label"], epic)

    def test_streak_of_ten_independent_correct_in_one_session(self):
        for i in range(9):
            s, r = self.post("/api/event", ev("word", track="smallcaps", item="pig", result="correct"))
            self.assertNotIn("treasure", r)
        s, r = self.post("/api/event", ev("card", track="lowercase", item="b", result="correct"))
        self.assertEqual(len(r["treasure"]), 1)
        self.assertEqual(self.treasure()[0]["source"]["kind"], "surprise")
        # a miss breaks the run; another session does not continue it
        self.post("/api/event", ev("word", track="smallcaps", item="pig", result="miss"))
        for i in range(9):
            s, r = self.post("/api/event", ev("word", track="smallcaps", item="pig", result="correct"))
            self.assertNotIn("treasure", r)
        for i in range(9):
            s, r = self.post("/api/event", ev("word", track="smallcaps", item="pig", result="correct", session_id="s2"))
            self.assertNotIn("treasure", r)

    def test_assisted_answers_do_not_build_a_streak(self):
        for i in range(12):
            s, r = self.post("/api/event", ev("word", track="smallcaps", item="pig", result="assisted"))
            self.assertNotIn("treasure", r)

    def test_adventure_done_once_per_session_and_adventure(self):
        s, r = self.post("/api/event", ev("adventure_done", adventure="smallcaps"))
        self.assertEqual(len(r["treasure"]), 1)
        s, r = self.post("/api/event", ev("adventure_done", adventure="smallcaps"))
        self.assertNotIn("treasure", r)
        s, r = self.post("/api/event", ev("adventure_done", adventure="lowercase"))
        self.assertEqual(len(r["treasure"]), 1)
        self.assertEqual(self.post("/api/event", ev("adventure_done", adventure="x"))[0], 400)

    def test_reading_points_no_longer_earn_a_village_level_up(self):
        """The shared reading-points village level is gone as a reward: 300 points make no `level_up` and no
        level:<n> treasure (old ones stay in existing piles; the minigame level surprises are separate)."""
        self.words(29)
        s, r = self.post("/api/event", ev("word", track="smallcaps", item="pig", result="correct", session_id="s9"))
        self.assertNotIn("level_up", r)
        self.words(300)
        s, r = self.post("/api/event", ev("word", track="smallcaps", item="pig", result="correct", session_id="s9"))
        self.assertNotIn("level_up", r)
        self.assertEqual([t for t in self.treasure() if t["source"]["ref"].startswith("level:")], [])
        self.assertEqual(self.history("level"), [])

    def test_event_that_is_not_a_reward_leaves_progress_alone(self):
        rev = self.progress()["rev"]
        self.post("/api/event", ev("block_placed", cell=[0, 0], block="wood"))
        self.assertEqual(self.progress()["rev"], rev)

    def test_tids_are_unique_and_survive_a_reset(self):
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        self.post("/api/event", ev("craft", track="smallcaps", item="HEN", result="correct"))
        first = [t["tid"] for t in self.treasure()]
        self.assertEqual(first, ["t000001", "t000002"])
        self.post("/api/treasure/send", {"tids": ["t000002"]})
        self.assertEqual(self.post("/api/reset", {"confirm": "RESET"})[0], 200)
        self.assertEqual(self.treasure(), [])
        self.post("/api/event", ev("craft", track="smallcaps", item="FOX", result="correct"))
        self.assertEqual(self.treasure()[0]["tid"], "t000003")  # the ledger still knows t000002


class Treasure(Api):
    def make(self, n=3):
        for w in ["PIG", "HEN", "FOX", "BAT"][:n]:
            self.post("/api/event", ev("craft", track="smallcaps", item=w, result="correct"))
        return [t["tid"] for t in self.treasure()]

    def test_send_a_subset_creates_one_delivery_per_tid(self):
        a, b, c = self.make()
        s, r = self.post("/api/treasure/send", {"tids": [a, c]})
        self.assertEqual(s, 200)
        self.assertEqual([t["tid"] for t in r["treasure"]], [a, c])
        self.assertEqual({t["state"] for t in r["treasure"]}, {"on_the_way"})
        ds = self.ledger()
        self.assertEqual([(d["source"]["ref"], d["status"]) for d in ds], [(a, "pending"), (c, "pending")])
        self.assertEqual(ds[0]["items"], [{"item": "minecraft:pig_spawn_egg", "count": 1}])
        states = {t["tid"]: t["state"] for t in self.treasure()}
        self.assertEqual(states, {a: "on_the_way", b: "kept", c: "on_the_way"})
        self.assertEqual({t["tid"]: t["status"] for t in self.progress()["treasure"]}, {a: "sent", b: "kept", c: "sent"})

    def test_a_tid_can_never_be_sent_twice(self):
        a, b, c = self.make()
        self.assertEqual(self.post("/api/treasure/send", {"tids": [a]})[0], 200)
        s, r = self.post("/api/treasure/send", {"tids": [a]})
        self.assertEqual(s, 409)
        self.assertIn(a, r["error"])
        s, r = self.post("/api/treasure/send", {"tids": [b, a]})  # one bad tid: nothing at all happens
        self.assertEqual(s, 409)
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(self.treasure()[1]["state"], "kept")

    def test_bad_requests(self):
        a, *_ = self.make(1)
        for body in ({}, {"tids": []}, {"tids": "t000001"}, {"tids": [a, a]}, {"tids": [1]}, {"tids": [a], "x": 1}):
            self.assertEqual(self.post("/api/treasure/send", body)[0], 400, body)
        s, r = self.post("/api/treasure/send", {"tids": [a, "t999999"]})
        self.assertEqual(s, 400)
        self.assertEqual(self.ledger(), [])
        self.assertEqual(self.treasure()[0]["state"], "kept")

    def test_states_follow_the_delivery(self):
        a, b, c = self.make()
        self.post("/api/treasure/send", {"tids": [a, b, c]})
        led = self.srv.mc.ledger
        d = led.deliveries()
        led.update(d[0]["id"], status="delivered", delivered_ts=TS, chest={"x": 1, "y": 2, "z": 3})
        led.update(d[1]["id"], status="failed", last_error="boom")
        by = {t["tid"]: t for t in self.treasure()}
        self.assertEqual([by[x]["state"] for x in (a, b, c)], ["in_chest", "failed", "on_the_way"])
        self.assertEqual(by[b]["delivery"]["last_error"], "boom")
        self.assertEqual(by[a]["delivery"]["chest"], {"x": 1, "y": 2, "z": 3})

    def test_failed_delivery_creation_rolls_the_sent_marks_back(self):
        a, b, c = self.make()
        real = self.srv.mc.ledger.create
        calls = []

        def flaky(*args):
            calls.append(args)
            if len(calls) == 2:
                raise mcb.LedgerError("disk full")
            return real(*args)
        with mock.patch.object(self.srv.mc.ledger, "create", flaky):
            s, r = self.post("/api/treasure/send", {"tids": [a, b]})
        self.assertEqual(s, 500)
        self.assertIn("disk full", r["error"])
        self.assertEqual({t["status"] for t in self.progress()["treasure"]}, {"kept"})
        # Review finding 5: the send was undone, so the history must not say "You sent" (no line before durability)
        self.assertEqual(self.get("/api/history?kind=send")[1]["lines"], [])

    def test_a_history_failure_after_a_durable_send_is_loud_and_says_the_send_happened(self):
        a, *_ = self.make(1)
        with mock.patch.object(self.srv.mc.history, "append", side_effect=mcb.HistoryError("disk full")):
            s, r = self.post("/api/treasure/send", {"tids": [a]})
        self.assertEqual(s, 500)
        self.assertIn("DID happen", r["error"])
        self.assertEqual(len(self.ledger()), 1)  # no silent rollback of a send that already has its delivery

    def test_startup_repairs_a_sent_treasure_without_a_delivery(self):
        a, b, c = self.make()
        p = self.progress()
        p_sent = copy.deepcopy(p)
        p_sent["treasure"][0]["status"] = "sent"
        server.write_json_atomic(self.data / "progress.json", p_sent)  # the crash window: marked, no delivery
        self.assertEqual(self.treasure()[0]["state"], "failed")  # visible, not "kept"
        server.reconcile_sent_treasure(self.srv)
        server.reconcile_sent_treasure(self.srv)  # idempotent
        self.assertEqual([d["source"]["ref"] for d in self.ledger()], [a])
        self.assertEqual(self.treasure()[0]["state"], "on_the_way")

    def test_unlock_treasure_can_be_sent(self):
        r = self.unlock("librarian")[1]
        tid = r["treasure"]["tid"]
        self.assertEqual(self.post("/api/treasure/send", {"tids": [tid]})[0], 200)
        d = self.ledger()[0]
        self.assertEqual((d["source"]["kind"], d["source"]["ref"]), ("unlock", tid))
        self.assertEqual([i["item"] for i in d["items"]], ["minecraft:villager_spawn_egg", "minecraft:lectern"])

    def test_minecraft_view(self):
        a, *_ = self.make(1)
        self.post("/api/treasure/send", {"tids": [a]})
        m = self.get("/api/minecraft")[1]
        self.assertEqual((m["enabled"], m["worker_running"], m["server_running"]), (True, False, False))
        self.assertEqual([d["source"]["ref"] for d in m["pending"]], [a])
        self.assertEqual((m["failed"], m["recent"], m["chests"], m["problem"]), ([], [], 0, None))


class ProgressGuards(Api):
    def test_save_cannot_change_village_or_treasure(self):
        self.unlock("librarian")
        p = self.progress()
        p["village"]["unlocked"] = []
        s, r = self.req("PUT", "/api/progress", p)
        self.assertEqual(s, 400)
        self.assertIn("village", r["error"])
        p = self.progress()
        p["treasure"][0]["status"] = "sent"
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 400)
        p = self.progress()
        del p["treasure"]  # dropping the pile is a change too
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 400)
        self.assertEqual(len(self.progress()["treasure"]), 1)

    def test_a_stale_save_is_a_409_not_a_400(self):
        stale = self.progress()
        self.unlock("librarian")  # bumps rev and changes village/treasure
        s, r = self.req("PUT", "/api/progress", stale)
        self.assertEqual(s, 409)

    def test_unchanged_village_and_treasure_save_fine(self):
        self.unlock("librarian")
        p = self.progress()
        p["inventory"]["coal"] = 3
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 200)

    def test_shape_validation_names_the_field(self):
        base = server.DEFAULT_PROGRESS
        cases = [
            (lambda p: p.update(village={"unlocked": [], "bells_spent": -1}), "village.bells_spent"),
            (lambda p: p.update(village={"unlocked": ["a", "a"], "bells_spent": 0}), "village.unlocked"),
            (lambda p: p.update(village={"unlocked": []}), "village.bells_spent"),
            (lambda p: p.update(treasure=[{"tid": "x"}]), "treasure[0]"),
            (lambda p: p.update(treasure="no"), "treasure"),
        ]
        for mut, field in cases:
            p = copy.deepcopy(base)
            mut(p)
            with self.assertRaises(server.ValidationError) as cm:
                server.validate_progress(p)
            self.assertIn(field, str(cm.exception))
        good = copy.deepcopy(base)
        good["treasure"] = [{"tid": "t000001", "label": "x", "sprite": "diamond",
                             "items": [{"item": "minecraft:diamond", "count": 1}],
                             "source": {"kind": "shop", "ref": "diamond"}, "status": "kept"}]
        good["village"] = {"unlocked": ["librarian"], "bells_spent": 1}
        server.validate_progress(good)
        good["treasure"][0]["status"] = "lost"
        with self.assertRaises(server.ValidationError):
            server.validate_progress(good)


class TidsAndEventRetries(Api):
    def test_a_kept_treasure_archived_by_a_reset_does_not_give_its_tid_away(self):
        # Review finding 5: next_tid looked only at the pile and the ledger; a never-sent treasure archived by a reset
        # left no trace, so its id was issued again.
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        self.post("/api/event", ev("craft", track="smallcaps", item="HEN", result="correct"))
        self.assertEqual([t["tid"] for t in self.treasure()], ["t000001", "t000002"])  # nothing sent: no ledger entry
        self.assertEqual(self.post("/api/reset", {"confirm": "RESET"})[0], 200)
        self.post("/api/event", ev("craft", track="smallcaps", item="FOX", result="correct"))
        self.assertEqual(self.treasure()[0]["tid"], "t000003")
        self.post("/api/reset", {"confirm": "RESET"})
        self.post("/api/event", ev("craft", track="smallcaps", item="BAT", result="correct"))
        self.assertEqual(self.treasure()[0]["tid"], "t000004")

    def test_the_counter_is_seeded_from_archives_when_its_file_is_missing(self):
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        self.post("/api/reset", {"confirm": "RESET"})
        (self.data / server.TID_COUNTER_FILE).unlink()  # data from before the counter existed
        self.post("/api/event", ev("craft", track="smallcaps", item="HEN", result="correct"))
        self.assertEqual(self.treasure()[0]["tid"], "t000002")

    def test_a_corrupt_counter_is_a_loud_error_and_is_not_overwritten(self):
        (self.data / server.TID_COUNTER_FILE).write_text("{nope")
        s, r = self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        self.assertEqual(s, 500)
        self.assertIn(server.TID_COUNTER_FILE, r["error"])
        self.assertEqual((self.data / server.TID_COUNTER_FILE).read_text(), "{nope")

    def test_a_retried_event_does_not_grant_its_treasure_twice(self):
        # Review finding 5: the treasure is saved before the event line is appended; when the append failed the client
        # got a 500, retried, and received a second craft item.
        e = ev("craft", track="smallcaps", item="PIG", result="correct")
        real_open = open

        def failing_open(path, mode="r", *a, **kw):
            if str(path).endswith("events.jsonl") and "a" in mode:
                raise OSError("disk full")
            return real_open(path, mode, *a, **kw)
        with mock.patch("server.open", failing_open, create=True):
            s, r = self.post("/api/event", e)
        self.assertEqual(s, 500)
        self.assertEqual(len(self.treasure()), 1)  # saved before the failed append
        s, r = self.post("/api/event", e)  # the client's retry of the same event
        self.assertEqual(s, 200)
        self.assertEqual(len(self.treasure()), 1)  # still one
        self.assertEqual(r["treasure"][0]["label"], self.treasure()[0]["label"])  # and the toast data is returned
        self.assertEqual(len(self.get("/api/events")[1]), 1)  # the event line is written once
        self.assertEqual(len(self.history("treasure")), 1)

    def test_retry_of_a_story_surprise_keeps_the_same_roll(self):
        e = ev("story_done", track="smallcaps", story_id="a")
        real_open = open

        def failing_open(path, mode="r", *a, **kw):
            if str(path).endswith("events.jsonl") and "a" in mode:
                raise OSError("disk full")
            return real_open(path, mode, *a, **kw)
        with mock.patch("server.open", failing_open, create=True):
            self.assertEqual(self.post("/api/event", e)[0], 500)
        first = [t["label"] for t in self.treasure()]
        self.assertEqual(self.post("/api/event", e)[0], 200)
        self.assertEqual([t["label"] for t in self.treasure()], first)

    def test_two_identical_events_in_a_row_are_still_two_events(self):
        e = ev("craft", track="smallcaps", item="PIG", result="correct")
        self.post("/api/event", e)
        self.post("/api/event", e)  # a second craft of the same word (same second): a different event count
        self.assertEqual(len(self.treasure()), 2)


class RewardsHistory(Api):
    def test_empty_history(self):
        s, r = self.get("/api/history")
        self.assertEqual((s, r["count"], r["lines"], r["kind"]), (200, 0, [], None))
        self.assertEqual(r["totals"]["earned"], {})

    def test_a_progress_save_that_raises_a_resource_writes_an_earn_line(self):
        self.post("/api/event", ev("word", track="smallcaps", item="pig", result="correct"))
        before = self.progress()
        self.set_inventory(wood=2, emerald=1)
        (line,) = self.history("earn")
        self.assertEqual(line["what"]["resources"], {"wood": 2, "emerald": 1})
        self.assertIsNone(line["what"]["last_event"])  # no `cause` sent: nothing is guessed from the events on file
        self.assertEqual(line["wallet_after"]["emerald"], 1)
        self.assertEqual(line["ref"], f"progress_rev:{before['rev'] + 1}")
        self.assertEqual(line["kind"], "earn")
        self.assertEqual(line["v"], 1)

    def put_with_cause(self, cause, **inv):
        p = self.progress()
        p["inventory"].update(inv)
        p["cause"] = cause
        return self.req("PUT", "/api/progress", p)

    def test_the_earn_line_names_the_event_that_earned_it_not_the_previous_one(self):
        # Review finding 2: the client PUTs progress BEFORE it posts the event, so the newest event on file is the
        # previous one. The client sends the event with the save as `cause`.
        self.post("/api/event", ev("story_done", track="smallcaps", story_id="a"))  # the PREVIOUS event
        s, _ = self.put_with_cause(ev("word", track="smallcaps", item="pig", result="correct"), emerald=1)
        self.assertEqual(s, 200)
        (line,) = self.history("earn")
        self.assertEqual((line["what"]["last_event"]["type"], line["what"]["last_event"]["item"]), ("word", "pig"))
        self.assertNotIn("cause", self.progress())  # provenance only: never stored in progress.json

    def test_a_malformed_cause_is_a_400_and_nothing_is_saved(self):
        before = self.progress()
        s, r = self.put_with_cause({"type": "nope"}, wood=3)
        self.assertEqual(s, 400)
        self.assertEqual(self.progress(), before)
        self.assertEqual(self.history(), [])

    def test_resources_the_client_spends_write_spend_lines(self):
        # Review finding 3: build.js spends an emerald per decoration (and wood/stone per block) on the client.
        self.set_inventory(emerald=3, wood=4, stone=2)
        n = len(self.history())
        s, _ = self.put_with_cause(ev("block_placed", cell=[1, 1], block="torch"), emerald=2, wood=1)
        self.assertEqual(s, 200)
        spends = self.history("spend")
        self.assertEqual(sorted((l["what"]["resource"], l["what"]["amount"]) for l in spends), [("emerald", 1), ("wood", 3)])
        self.assertTrue(all(l["what"]["on"] == "block_placed torch" for l in spends))
        self.assertEqual(spends[0]["wallet_after"]["emerald"], 2)
        r = self.get("/api/history")[1]
        self.assertEqual(r["totals"]["spent"], {"emerald": 1, "wood": 3})
        # earned minus spent is the wallet again
        self.assertEqual(r["totals"]["earned"]["emerald"] - r["totals"]["spent"]["emerald"], self.progress()["inventory"]["emerald"])
        self.assertEqual(len(self.history()), n + 2)

    def test_a_spend_without_a_cause_still_writes_a_line_that_says_so(self):
        self.set_inventory(wood=4)
        self.set_inventory(wood=1)
        (line,) = self.history("spend")
        self.assertEqual(line["what"], {"resource": "wood", "amount": 3, "on": "the game (no event named)"})

    def test_only_increases_are_earnings_and_a_save_without_any_writes_nothing(self):
        self.set_inventory(wood=5)
        p = self.progress()
        p["inventory"]["wood"] = 3  # the client used wood up: not an earning (it is a spend line)
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 200)
        p = self.progress()
        self.assertEqual(self.req("PUT", "/api/progress", p)[0], 200)  # nothing changed
        self.assertEqual(len(self.history("earn")), 1)

    def test_every_kind_is_written_by_the_request_that_makes_the_change(self):
        self.set_inventory(emerald=200, wood=10)
        self.assertEqual(self.post("/api/shop/trade", {"trade_id": "wood10"})[0], 200)
        self.assertEqual(self.unlock("librarian")[0], 200)  # free first unlock
        self.assertEqual(self.unlock("farmer", "emeralds")[0], 200)
        self.add_events(ev("story_done", track="smallcaps", story_id="b"))  # one bell
        self.assertEqual(self.unlock("shepherd", "bell")[0], 200)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": CFG["village"]["professions"][0]["offers"][0]["id"]})[0], 200)
        self.words(30)
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))  # level 1 + a craft
        tids = [t["tid"] for t in self.treasure()]
        self.assertEqual(self.post("/api/treasure/send", {"tids": tids[:2]})[0], 200)
        kinds = [l["kind"] for l in self.history()]
        for k in ("earn", "spend", "trade", "treasure", "unlock", "send"):
            self.assertIn(k, kinds, k)
        trade = self.history("trade")[0]
        self.assertEqual((trade["what"]["give"], trade["what"]["get"], trade["ref"]), ({"wood": 10}, {"emerald": 1}, "wood10"))
        unlocks = self.history("unlock")
        self.assertEqual([(u["what"]["profession"], u["what"]["paid"]) for u in unlocks],
                         [("librarian", "free"), ("farmer", "emeralds"), ("shepherd", "bell")])
        spends = self.history("spend")
        self.assertEqual({(sp["what"]["resource"], sp["what"]["amount"]) for sp in spends},
                         {("emerald", 15), ("bell", 1), ("emerald", CFG["village"]["professions"][0]["offers"][0]["price"])})
        send = self.history("send")[0]
        self.assertEqual(send["what"]["tids"], tids[:2])
        self.assertEqual(send["ref"], ",".join(tids[:2]))
        self.assertTrue(all(isinstance(it["item"], str) for it in send["what"]["items"]))
        # every spend/trade line carries the wallet after the change, and it matches the real one
        self.assertEqual(self.history("trade")[0]["wallet_after"]["emerald"], 201)
        self.assertEqual(self.history()[-1]["kind"], "send")
        stamps = [l["ts"] for l in self.history()]  # chronological: timestamps never go backwards
        self.assertEqual(stamps, sorted(stamps))

    def test_every_treasure_has_a_treasure_line(self):
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        (line,) = self.history("treasure")
        t = self.treasure()[0]
        self.assertEqual((line["what"]["tid"], line["ref"], line["what"]["source"]), (t["tid"], t["tid"], t["source"]))
        self.assertEqual(line["what"]["items"], t["items"])

    def test_filter_by_kind_and_bad_queries(self):
        self.set_inventory(wood=1)
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        s, r = self.get("/api/history?kind=treasure")
        self.assertEqual({l["kind"] for l in r["lines"]}, {"treasure"})
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["totals"]["earned"], {"wood": 1})  # totals always cover everything
        for q in ("?kind=nope", "?foo=1", "?kind=earn&kind=send", "?kind="):
            self.assertEqual(self.get("/api/history" + q)[0], 400, q)

    def test_csv(self):
        self.set_inventory(wood=3)
        r = urllib.request.urlopen(self.base + "/api/history.csv")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.headers["Content-Type"].startswith("text/csv"))
        self.assertIn("rewards_history.csv", r.headers["Content-Disposition"])
        rows = r.read().decode().splitlines()
        self.assertEqual(rows[0], "ts,kind,ref,what,wallet_after")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].split(",")[1], "earn")
        r = urllib.request.urlopen(self.base + "/api/history.csv?kind=send")
        self.assertEqual(len(r.read().decode().splitlines()), 1)  # header only
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.base + "/api/history.csv?kind=nope")
        self.assertEqual(cm.exception.code, 400)

    def test_history_survives_a_reset_and_is_not_archived(self):
        self.set_inventory(wood=3)
        before = (self.data / server.HISTORY_FILE).read_text()
        s, r = self.post("/api/reset", {"confirm": "RESET"})
        self.assertEqual(s, 200)
        self.assertEqual((self.data / server.HISTORY_FILE).read_text(), before)
        self.assertEqual([p.name for p in Path(r["archived_to"]).iterdir()], ["progress.json"])
        self.set_inventory(wood=1)
        self.assertEqual(len(self.history("earn")), 2)  # the new life continues the same file

    def test_the_file_is_append_only_each_request_only_adds_lines(self):
        self.set_inventory(wood=3)
        first = (self.data / server.HISTORY_FILE).read_text()
        self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))
        second = (self.data / server.HISTORY_FILE).read_text()
        self.assertTrue(second.startswith(first))
        self.assertGreater(len(second), len(first))

    def test_a_failed_history_write_fails_the_request_and_changes_nothing(self):
        self.set_inventory(emerald=50, wood=10)
        self.unlock("librarian")
        before = self.progress()
        with mock.patch.object(self.srv.mc.history, "append", side_effect=mcb.HistoryError("disk full")):
            for call in (lambda: self.post("/api/shop/trade", {"trade_id": "wood10"}),
                         lambda: self.unlock("farmer"),
                         lambda: self.post("/api/event", ev("craft", track="smallcaps", item="PIG", result="correct"))):
                # (send is the exception: its line is written after the send is durable, see the Treasure tests)
                s, r = call()
                self.assertIn(s, (400, 500, 409))
            p = self.progress()
            p["inventory"]["coal"] = 4
            s, r = self.req("PUT", "/api/progress", p)
            self.assertEqual(s, 500)
            self.assertIn("disk full", r["error"])
        after = self.progress()
        self.assertEqual(after["inventory"], before["inventory"])
        self.assertEqual(after["treasure"], before["treasure"])
        self.assertEqual(after["village"], before["village"])

    def test_corrupt_history_is_a_loud_500(self):
        (self.data / server.HISTORY_FILE).write_text("not json\n")
        s, r = self.get("/api/history")
        self.assertEqual(s, 500)
        self.assertIn("line 1", r["error"])


if __name__ == "__main__":
    unittest.main()
