"""Minigame levels (docs/design.md "Levels"): the derivation rule, the event `level` field, Dad's override, and the
once-only rare level-up surprise. Real server on a temp data dir; the delivery worker never runs."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import server  # noqa: E402
import test_minecraft_api as base  # noqa: E402  (module import: its TestCase classes must not run twice)

ev = base.ev
LEVELS = json.loads((ROOT / "app" / "data" / "levels.json").read_text())["games"]


def attempts(type_, results, level=None, **kw):
    """Valid events of one game; `kw` fills the type's other required fields."""
    fields = {"craft": {"track": "smallcaps", "item": "PIG"}, "word": {"track": "smallcaps", "item": "pig"},
              "card": {"track": "lowercase", "item": "b"}, "match": {"item": "b", "chosen": "b"}}[type_]
    return [ev(type_, **fields, result=r, **({} if level is None else {"level": level}), **kw) for r in results]


def run(n, result="correct"):
    return [result] * n


class Derivation(unittest.TestCase):
    def derive(self, events):
        return server.derive_levels(events, LEVELS)

    def test_promotion_at_exactly_eight_of_ten_with_ten_attempts(self):
        self.assertEqual(self.derive(attempts("craft", run(7) + run(3, "assisted")))["craft"]["level"], 1)
        d = self.derive(attempts("craft", run(2, "assisted") + run(8)))["craft"]
        self.assertEqual((d["level"], d["attempts"], d["independent"]), (2, 0, 0))

    def test_fewer_than_ten_attempts_never_promote(self):
        self.assertEqual(self.derive(attempts("word", run(9)))["blocks"]["level"], 1)
        self.assertEqual(self.derive(attempts("word", run(10)))["blocks"]["level"], 2)

    def test_assisted_and_miss_do_not_count(self):
        self.assertEqual(self.derive(attempts("match", run(10, "assisted")))["match"]["level"], 1)
        self.assertEqual(self.derive(attempts("match", run(5, "miss") + run(5, "assisted")))["match"]["level"], 1)

    def test_only_the_last_ten_count(self):
        self.assertEqual(self.derive(attempts("card", run(5, "miss") + run(8)))["mine"]["level"], 2)

    def test_events_without_level_are_level_one_and_other_levels_are_ignored(self):
        self.assertEqual(self.derive(attempts("craft", run(10)))["craft"]["level"], 2)
        self.assertEqual(self.derive(attempts("craft", run(10), level=2))["craft"]["level"], 1)
        both = attempts("craft", run(10)) + attempts("craft", run(10), level=2)
        self.assertEqual(self.derive(both)["craft"]["level"], 3)
        self.assertEqual(self.derive(attempts("craft", run(10)) + attempts("craft", run(10), level=1))["craft"]["level"], 2)

    def test_never_demotes_and_stops_at_max(self):
        d = self.derive(attempts("craft", run(10)) + attempts("craft", run(30, "assisted"), level=2))
        self.assertEqual(d["craft"]["level"], 2)
        evs = [e for lv in range(1, 9) for e in attempts("card", run(10), level=lv)]
        d = self.derive(evs)
        self.assertEqual((d["mine"]["level"], d["craft"]["level"]), (LEVELS["mine"]["max"], 1))

    def test_each_event_type_feeds_only_its_game(self):
        d = self.derive(attempts("word", run(10)))
        self.assertEqual([d[g]["level"] for g in ("craft", "blocks", "mine", "match")], [1, 2, 1, 1])


class LevelsFile(unittest.TestCase):
    def load(self, obj):
        with mock.patch.object(server, "LEVELS_FILE", Path(self.id() + ".json")):
            with mock.patch("pathlib.Path.read_text", return_value=json.dumps(obj)):
                return server.load_levels()

    def test_shipped_file_loads(self):
        self.assertEqual(set(server.load_levels()), set(server.LEVEL_GAMES))

    def test_bad_files_are_loud(self):
        good = {"v": 1, "games": {g: dict(c) for g, c in LEVELS.items()}}
        self.assertEqual(self.load(good)["craft"]["max"], 6)
        for mutate in (lambda o: o.update(v=2), lambda o: o["games"].pop("mine"), lambda o: o["games"]["craft"].update(need=11),
                       lambda o: o["games"]["craft"].update(extra=1), lambda o: o["games"]["craft"].update(max="6")):
            bad = json.loads(json.dumps(good))
            mutate(bad)
            with self.assertRaises(ValueError):
                self.load(bad)


class EventField(base.Api):
    def test_level_is_accepted_on_the_four_game_events_only(self):
        for t in ("craft", "word", "card", "match"):
            self.assertEqual(self.post("/api/event", attempts(t, ["correct"], level=1)[0])[0], 200, t)
        bad = ev("session_start", level=1)
        s, r = self.post("/api/event", bad)
        self.assertEqual(s, 400)
        self.assertIn("level", r["error"])

    def test_bad_levels_are_400_naming_the_field(self):
        for v in (0, -1, "2", 2.5, True, 100, None):
            e = attempts("craft", ["correct"])[0]
            e["level"] = v
            s, r = self.post("/api/event", e)
            self.assertEqual(s, 400, v)
            self.assertIn("level", r["error"])
        self.assertEqual(self.get("/api/events")[1], [])

    def test_level_above_the_games_max_is_400(self):
        for t, game in (("craft", "craft"), ("word", "blocks"), ("card", "mine"), ("match", "match")):
            top = LEVELS[game]["max"]
            self.assertEqual(self.post("/api/event", attempts(t, ["correct"], level=top)[0])[0], 200)
            s, r = self.post("/api/event", attempts(t, ["correct"], level=top + 1)[0])
            self.assertEqual(s, 400, t)
            self.assertIn(f"at most {top}", r["error"])

    def test_old_events_without_level_still_read(self):
        self.add_events(*attempts("craft", run(3)))
        self.assertEqual(len(self.get("/api/events")[1]), 3)


class Override(base.Api):
    def put(self, override):
        p = self.progress()
        if override is None:
            p["settings"].pop("level_override", None)
        else:
            p["settings"]["level_override"] = override
        return self.req("PUT", "/api/progress", p)

    def test_valid_override_round_trips_and_clearing_removes_it(self):
        self.assertEqual(self.put({"craft": 3, "mine": 1})[0], 200)
        self.assertEqual(self.progress()["settings"]["level_override"], {"craft": 3, "mine": 1})
        self.assertEqual(self.put(None)[0], 200)
        self.assertNotIn("level_override", self.progress()["settings"])

    def test_bad_overrides_are_400_naming_the_field(self):
        for bad, field in (({"dance": 1}, "dance"), ({"craft": 0}, "craft"), ({"craft": 7}, "craft"), ({"mine": 5}, "mine"),
                           ({"craft": "3"}, "craft"), ({"craft": True}, "craft"), ([], "level_override")):
            s, r = self.put(bad)
            self.assertEqual(s, 400, bad)
            self.assertIn(field, r["error"])

    def test_override_does_not_change_the_derived_level_or_the_surprise(self):
        self.assertEqual(self.put({"craft": 4})[0], 200)
        self.add_events(*attempts("craft", run(9), level=4))
        s, r = self.post("/api/event", attempts("craft", ["correct"], level=4)[0])
        self.assertEqual(s, 200)
        self.assertNotIn("game_level_ups", r)


class LevelUpSurprise(base.Api):
    def refs(self):
        return [t["source"]["ref"] for t in self.treasure()]

    def test_the_tenth_good_attempt_gives_one_rare_surprise_and_the_reply_names_it(self):
        self.add_events(*attempts("card", run(9), session_id="old"))
        s, r = self.post("/api/event", attempts("card", ["correct"])[0])
        self.assertEqual(s, 200)
        self.assertEqual(r["game_level_ups"], [{"game": "mine", "level": 2}])
        self.assertEqual(len(r["treasure"]), 1)
        self.assertIn("minigame_level:mine:2", self.refs())
        t = next(t for t in self.treasure() if t["source"]["ref"] == "minigame_level:mine:2")
        self.assertEqual(t["source"]["kind"], "surprise")
        rare = {(e["label"], e["sprite"]) for e in self.srv.mc.cfg["tiers"]["rare"]}
        self.assertIn((t["label"], t["sprite"]), rare)  # rolled from the rare tier
        self.assertEqual(len(self.history("treasure")), 1)  # the history line for it

    def test_below_the_threshold_gives_nothing(self):
        self.add_events(*attempts("match", run(2, "assisted") + run(7)))
        s, r = self.post("/api/event", attempts("match", ["correct"])[0])  # the 10th attempt: 8 of 10 correct exactly
        self.assertEqual(r.get("game_level_ups"), [{"game": "match", "level": 2}])
        s, r = self.post("/api/event", attempts("match", ["correct"], level=2)[0])  # 1 attempt at level 2
        self.assertNotIn("game_level_ups", r)
        self.assertNotIn("treasure", r)

    def test_once_only_per_game_and_level(self):
        self.add_events(*attempts("craft", run(9), session_id="old"))
        self.post("/api/event", attempts("craft", ["correct"])[0])
        n = len(self.treasure())
        # more level-1 attempts after the level was reached change nothing, and level 2 attempts that stay short too
        for _ in range(12):
            s, r = self.post("/api/event", attempts("craft", ["correct"], level=1)[0])
            self.assertNotIn("game_level_ups", r)
        self.assertEqual(self.refs().count("minigame_level:craft:2"), 1)
        self.assertEqual(len([x for x in self.refs() if x.startswith("minigame_level:")]), 1)
        self.assertEqual(len(self.treasure()), n + 12)  # only the 12 crafts' own items

    def test_every_level_reached_has_its_own_surprise_and_an_existing_one_is_not_repeated(self):
        # Levels 2 and 3 are both earned on file and neither has a surprise yet: the event adds both, once.
        self.add_events(*attempts("word", run(10), session_id="old"), *attempts("word", run(9), level=2, session_id="old"))
        s, r = self.post("/api/event", attempts("word", ["correct"], level=2)[0])
        self.assertEqual(r["game_level_ups"], [{"game": "blocks", "level": 2}, {"game": "blocks", "level": 3}])
        s, r = self.post("/api/event", attempts("word", ["correct"], level=3)[0])
        self.assertNotIn("game_level_ups", r)
        self.assertEqual(sorted(x for x in self.refs() if x.startswith("minigame_level:")),
                         ["minigame_level:blocks:2", "minigame_level:blocks:3"])

    def test_a_game_at_a_level_does_not_trigger_other_games(self):
        self.add_events(*attempts("card", run(10)))
        s, r = self.post("/api/event", attempts("word", ["correct"])[0])
        self.assertNotIn("game_level_ups", r)

    def test_a_retried_event_returns_the_same_level_up_and_makes_no_second_treasure(self):
        self.add_events(*attempts("card", run(9), session_id="old"))
        e = attempts("card", ["correct"])[0]
        real_open = open

        def failing_open(path, mode="r", *a, **kw):
            if str(path).endswith("events.jsonl") and "a" in mode:
                raise OSError("disk full")
            return real_open(path, mode, *a, **kw)
        with mock.patch("server.open", failing_open, create=True):
            self.assertEqual(self.post("/api/event", e)[0], 500)
        self.assertEqual(len(self.treasure()), 1)
        s, r = self.post("/api/event", e)
        self.assertEqual(s, 200)
        self.assertEqual(r["game_level_ups"], [{"game": "mine", "level": 2}])
        self.assertEqual(len(self.treasure()), 1)

    def test_old_data_reaching_a_level_gets_its_surprise_on_the_next_event(self):
        # Ten level-less craft events on file (made before levels existed) already earned level 2.
        self.add_events(*attempts("craft", run(10)))
        s, r = self.post("/api/event", attempts("craft", ["correct"], level=1)[0])
        self.assertEqual(r["game_level_ups"], [{"game": "craft", "level": 2}])


if __name__ == "__main__":
    unittest.main()
