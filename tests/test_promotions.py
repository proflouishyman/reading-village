"""Villager promotions (docs/design.md "Villager promotions"): the threshold ladder, the server-owned spent counter,
POST /api/village/promote, per-villager trade gating, reset consistency, the history line and the config check.
Real server on a temp data dir; the delivery worker never runs."""
import copy
import json
import sys
import threading
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import minecraft_bridge as mcb  # noqa: E402
import server  # noqa: E402
import test_minecraft_api as base  # noqa: E402  (module import: its TestCase classes must not run twice)

CFG = base.CFG
PROMO = CFG["village"]["promotions"]


class LadderMath(unittest.TestCase):
    """promotions_earned / next_promotion_at with the shipped ladder [10,25,45,70,100] then every 40."""

    def test_thresholds_then_every(self):
        got = {n: mcb.promotions_earned(CFG, n) for n in (0, 9, 10, 24, 25, 44, 45, 69, 70, 99, 100, 139, 140, 179, 180)}
        self.assertEqual(got, {0: 0, 9: 0, 10: 1, 24: 1, 25: 2, 44: 2, 45: 3, 69: 3, 70: 4, 99: 4, 100: 5, 139: 5,
                               140: 6, 179: 6, 180: 7})

    def test_next_at(self):
        got = {n: mcb.next_promotion_at(CFG, n) for n in (0, 9, 10, 24, 54, 99, 100, 139, 140, 150)}
        self.assertEqual(got, {0: 10, 9: 10, 10: 25, 24: 25, 54: 70, 99: 100, 100: 140, 139: 140, 140: 180, 150: 180})

    def test_next_at_is_always_the_point_where_earned_goes_up(self):
        for n in range(0, 400):
            nxt = mcb.next_promotion_at(CFG, n)
            self.assertGreater(nxt, n)
            self.assertEqual(mcb.promotions_earned(CFG, nxt), mcb.promotions_earned(CFG, n) + 1, n)
            self.assertEqual(mcb.promotions_earned(CFG, nxt - 1), mcb.promotions_earned(CFG, n), n)


class ConfigCheck(unittest.TestCase):
    def bad(self, edit, needle):
        cfg = copy.deepcopy(CFG)
        edit(cfg)
        with self.assertRaises(mcb.ConfigError) as cm:
            mcb.validate_config(cfg, craft_words=set(server.load_craft_words()))
        self.assertIn(needle, str(cm.exception))

    def test_shipped_values(self):
        self.assertEqual(PROMO, {"spent_thresholds": [10, 25, 45, 70, 100], "then_every": 40})

    def test_bad_promotions_are_loud(self):
        self.bad(lambda c: c["village"].pop("promotions"), "promotions")
        self.bad(lambda c: c["village"]["promotions"].update(spent_thresholds=[10, 10]), "spent_thresholds")
        self.bad(lambda c: c["village"]["promotions"].update(spent_thresholds=[20, 10]), "spent_thresholds")
        self.bad(lambda c: c["village"]["promotions"].update(spent_thresholds=[]), "spent_thresholds")
        self.bad(lambda c: c["village"]["promotions"].update(spent_thresholds=[0, 5]), "spent_thresholds")
        self.bad(lambda c: c["village"]["promotions"].update(then_every=0), "then_every")
        self.bad(lambda c: c["village"]["promotions"].update(then_every="40"), "then_every")
        self.bad(lambda c: c["village"]["promotions"].update(extra=1), "extra")


class Promotions(base.Api):
    def spend(self, n):
        """Spend exactly n emeralds through real shop buys (armorer arm_iron_boots costs 3, farm_bread 1)."""
        self.set_inventory(emerald=n)
        for _ in range(n):
            self.assertEqual(self.post("/api/shop/buy", {"offer_id": "farm_bread"})[0], 200)

    def promo(self):
        return self.get("/api/village")[1]["promotions"]

    def promote(self, pid):
        return self.post("/api/village/promote", {"profession": pid})

    def start(self, *pids):
        """Unlock the villagers (emeralds), then zero the spent counter so tests count only their own spending."""
        self.set_inventory(emerald=1000)
        for pid in pids:
            self.assertEqual(self.unlock(pid)[0], 200, pid)
        self.set_village(emeralds_spent=0)  # seam: start the ladder at 0 (the unlock fees above would count)
        self.set_inventory(emerald=0)

    # -- the spent total ------------------------------------------------------------------------------------
    def test_spent_counts_buys_and_emerald_unlocks_not_bells_or_trades(self):
        self.assertEqual(self.promo(), {"earned": 0, "used": 0, "available": 0, "spent": 0, "next_at": 10})
        self.set_inventory(emerald=100, wood=10)
        self.unlock("farmer")  # the first one is free: 0 spent
        self.assertEqual(self.promo()["spent"], 0)
        self.assertEqual(self.unlock("shepherd", "emeralds")[0], 200)  # 15
        self.assertEqual(self.promo()["spent"], 15)
        self.add_events(base.ev("story_done", track="smallcaps", story_id="a"))
        self.assertEqual(self.unlock("butcher", "bell")[0], 200)  # a bell: not emeralds
        self.assertEqual(self.post("/api/shop/trade", {"trade_id": "wood10"})[0], 200)  # earns, never spends
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "farm_pie"})[0], 200)  # 2
        self.assertEqual(self.promo()["spent"], 17)
        self.assertEqual(self.progress()["village"]["emeralds_spent"], 17)

    def test_a_refused_buy_does_not_count(self):
        self.unlock("farmer")
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "farm_bread"})[0], 409)  # no emeralds
        self.assertEqual(self.promo()["spent"], 0)

    def test_client_cannot_write_the_counter_or_levels(self):
        self.unlock("farmer")
        for change in ({"emeralds_spent": 500}, {"levels": {"farmer": 1}}):
            p = self.progress()
            p["village"] = {**p["village"], **change}
            s, r = self.req("PUT", "/api/progress", p)
            self.assertEqual(s, 400, change)
            self.assertIn("owned by the server", r["error"])

    # -- promoting -------------------------------------------------------------------------------------------
    def test_promote_happy_path(self):
        self.start("farmer", "armorer")
        self.spend(10)
        self.assertEqual(self.promo(), {"earned": 1, "used": 0, "available": 1, "spent": 10, "next_at": 25})
        v = self.get("/api/village")[1]
        self.assertTrue(all(p["level"] == 0 and p["level_name"] == "Novice" for p in v["professions"]))
        self.assertEqual([p["id"] for p in v["professions"] if p["can_promote"]], ["armorer", "farmer"])
        s, r = self.promote("armorer")
        self.assertEqual(s, 200)
        self.assertEqual(r["profession"], {"id": "armorer", "name": "Armorer", "level": 1, "level_name": "Apprentice"})
        self.assertEqual(r["village"]["promotions"],
                         {"earned": 1, "used": 1, "available": 0, "spent": 10, "next_at": 25})
        prof = {p["id"]: p for p in r["village"]["professions"]}
        self.assertEqual((prof["armorer"]["level"], prof["armorer"]["level_name"]), (1, "Apprentice"))
        self.assertEqual(prof["farmer"]["level"], 0)  # never every villager
        self.assertEqual(self.progress()["village"]["levels"], {"armorer": 1})
        self.assertFalse(any(p["can_promote"] for p in r["village"]["professions"]))
        self.assertEqual(r["wallet"], self.progress()["inventory"])

    def test_two_promotions_can_go_to_one_villager_or_two(self):
        self.start("farmer", "armorer")
        self.spend(25)
        self.assertEqual(self.promo()["available"], 2)
        self.assertEqual(self.promote("farmer")[0], 200)
        self.assertEqual(self.promote("farmer")[1]["profession"]["level_name"], "Journeyman")
        self.assertEqual(self.promote("armorer")[0], 409)

    def test_409_when_none_available(self):
        self.start("farmer")
        s, r = self.promote("farmer")
        self.assertEqual(s, 409)
        self.assertIn("10 more emeralds", r["error"])
        self.assertEqual(self.progress()["village"].get("levels", {}), {})

    def test_409_when_not_unlocked(self):
        self.start("farmer")
        self.spend(10)
        s, r = self.promote("armorer")
        self.assertEqual(s, 409)
        self.assertIn("not unlocked", r["error"])
        self.assertEqual(self.promo()["available"], 1)

    def test_409_when_already_master(self):
        self.start("farmer")
        self.set_village(emeralds_spent=1000, levels={"farmer": 4})
        s, r = self.promote("farmer")
        self.assertEqual(s, 409)
        self.assertIn("Master", r["error"])
        self.assertFalse(next(p for p in self.get("/api/village")[1]["professions"] if p["id"] == "farmer")["can_promote"])

    def test_400_bad_bodies(self):
        self.assertEqual(self.promote("nobody")[0], 400)
        self.assertEqual(self.post("/api/village/promote", {})[0], 400)
        self.assertEqual(self.post("/api/village/promote", {"profession": "farmer", "x": 1})[0], 400)
        self.assertEqual(self.post("/api/village/promote", {"profession": 3})[0], 400)
        self.assertEqual(self.post("/api/village/promote", ["farmer"])[0], 400)

    def test_double_tap_gives_exactly_one_promotion(self):
        self.start("farmer", "armorer")
        self.spend(10)
        results = []

        def tap(pid):
            results.append(self.promote(pid)[0])
        ts = [threading.Thread(target=tap, args=(pid,)) for pid in ("farmer", "farmer", "armorer", "armorer")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(results), [200, 409, 409, 409])
        self.assertEqual(sum(self.progress()["village"]["levels"].values()), 1)
        self.assertEqual(len(self.history("promote")), 1)

    # -- per-villager gating -----------------------------------------------------------------------------------
    def test_min_level_compares_against_that_villagers_own_level(self):
        self.start("farmer", "armorer")
        self.spend(10)
        self.assertEqual(self.promote("armorer")[0], 200)
        self.set_inventory(emerald=50)
        # arm_iron_legs needs Apprentice: the promoted Armorer sells it, an unpromoted Farmer's Apprentice goods stay locked
        s, r = self.post("/api/shop/buy", {"offer_id": "farm_cookies"})
        self.assertEqual(s, 409)
        self.assertIn("Farmer", r["error"])
        self.assertIn("Apprentice", r["error"])
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "arm_iron_legs"})[0], 200)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "arm_diamond_boots"})[0], 409)  # Journeyman
        offers = {p["id"]: {o["id"]: o["locked"] for o in p["offers"]} for p in self.get("/api/village")[1]["professions"]}
        self.assertFalse(offers["armorer"]["arm_iron_legs"])
        self.assertTrue(offers["armorer"]["arm_diamond_boots"])
        self.assertTrue(offers["farmer"]["farm_cookies"])

    def test_reading_points_no_longer_gate_anything(self):
        self.unlock("farmer")
        self.set_inventory(emerald=50)
        self.words(400)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "farm_cookies"})[0], 409)

    # -- reset, history, legacy ----------------------------------------------------------------------------------
    def test_reset_zeroes_the_ladder_and_levels(self):
        self.start("farmer")
        self.spend(10)
        self.assertEqual(self.promote("farmer")[0], 200)
        self.assertEqual(self.post("/api/reset", {"confirm": "RESET"})[0], 200)  # same second as the spends above
        v = self.get("/api/village")[1]
        self.assertEqual(v["promotions"], {"earned": 0, "used": 0, "available": 0, "spent": 0, "next_at": 10})
        self.assertEqual(self.progress()["village"], {"unlocked": [], "bells_spent": 0, "emeralds_spent": 0, "levels": {}})
        self.assertTrue(all(p["level"] == 0 for p in v["professions"]))

    def test_history_line_csv_and_filter(self):
        self.start("farmer")
        self.spend(10)
        self.promote("farmer")
        lines = self.history("promote")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["what"], {"profession": "farmer", "name": "Farmer", "from_level": 0, "level": 1,
                                            "level_name": "Apprentice", "spent": 10})
        self.assertEqual((lines[0]["ref"], lines[0]["wallet_after"]["emerald"]), ("farmer", 0))
        import urllib.request
        with urllib.request.urlopen(self.base + "/api/history.csv?kind=promote") as r:
            text = r.read().decode()
        self.assertEqual(len(text.strip().splitlines()), 2)
        self.assertIn("promote", text)
        self.assertEqual(self.get("/api/history?kind=nonsense")[0], 400)

    def test_legacy_progress_derives_spent_from_history_since_the_last_reset(self):
        """A progress.json from before the counter has no emeralds_spent: derive it once from the emerald spend lines
        at or after the newest data/archive stamp, and persist it with the next write."""
        now = datetime.now().astimezone()
        reset_at = now - timedelta(days=2)
        (self.data / "archive" / reset_at.strftime("%Y%m%d-%H%M%S")).mkdir(parents=True)
        (self.data / "archive" / "20200101-000000").mkdir()  # an older reset is irrelevant
        (self.data / "archive" / "notes").mkdir()  # not ours: ignored
        wallet = {k: 0 for k in server.INVENTORY_KEYS}

        def line(ts, resource, amount):
            return json.dumps({"v": 1, "ts": ts.isoformat(timespec="seconds"), "kind": "spend",
                               "what": {"resource": resource, "amount": amount, "on": "x"}, "wallet_after": wallet,
                               "ref": "x"})
        with open(self.data / "rewards_history.jsonl", "w") as f:
            f.write("\n".join([line(reset_at - timedelta(hours=1), "emerald", 100),  # the old era: not counted
                               line(reset_at + timedelta(hours=1), "emerald", 4),
                               line(reset_at + timedelta(hours=2), "bell", 1),  # not emeralds
                               line(reset_at + timedelta(hours=3), "emerald", 20)]) + "\n")
        pf = self.data / "progress.json"
        p = json.loads(pf.read_text())
        p["village"] = {"unlocked": ["farmer"], "bells_spent": 0}  # the pre-counter shape
        pf.write_text(json.dumps(p))
        self.assertEqual(self.promo(), {"earned": 1, "used": 0, "available": 1, "spent": 24, "next_at": 25})
        self.assertEqual(self.promote("farmer")[0], 200)
        self.assertEqual(self.progress()["village"], {"unlocked": ["farmer"], "bells_spent": 0, "emeralds_spent": 24,
                                                      "levels": {"farmer": 1}})

    def test_corrupt_levels_fail_loudly(self):
        self.start("farmer")
        pf = self.data / "progress.json"
        p = json.loads(pf.read_text())
        p["village"]["levels"] = {"farmer": 2}  # two levels but nothing spent: no such promotions were earned
        pf.write_text(json.dumps(p))
        s, r = self.get("/api/village")
        self.assertEqual(s, 500)
        self.assertIn("promotions", r["error"])
        p["village"]["levels"] = {"armorer": 1}  # not unlocked
        pf.write_text(json.dumps(p))
        self.assertEqual(self.get("/api/village")[0], 500)


if __name__ == "__main__":
    unittest.main()


class LegacyFirstBuy(base.Api):
    """Regression: on an old progress.json without village.emeralds_spent, the first buy
    summed the history AFTER writing its own spend line, so its price was counted twice."""

    promo = Promotions.promo

    def test_first_buy_on_old_progress_counts_its_price_once(self):
        self.unlock("farmer")
        pf = self.data / "progress.json"
        p = json.loads(pf.read_text())
        p["village"] = {"unlocked": ["farmer"], "bells_spent": 0}
        pf.write_text(json.dumps(p))
        self.set_inventory(emerald=5)
        self.assertEqual(self.post("/api/shop/buy", {"offer_id": "farm_bread"})[0], 200)
        self.assertEqual(self.progress()["village"]["emeralds_spent"], 1)
        self.assertEqual(self.promo()["spent"], 1)
