"""POST /api/import (docs/away-from-home.md section 5): replay an export file into the real record, all or nothing."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import server  # noqa: E402
import test_server  # noqa: E402  (module import, so its test classes are not collected twice)

CLIENT_KEYS = server.CLIENT_OWNED_KEYS


def client_part(p):
    return {k: copy.deepcopy(p[k]) for k in CLIENT_KEYS if k in p}


def base_progress():
    p = client_part(copy.deepcopy(server.DEFAULT_PROGRESS))
    p["crafted"] = {}
    return p


def ev(t, i=0, **over):
    e = test_server.event_of(t)
    e["ts"] = f"2026-10-20T10:{i:02d}:00-04:00"
    e["session_id"] = "mom-1"
    e.update(over)
    return e


def make_export(events, progress, base=None, export_id="exp-1", device="dev-1", snap="snap-A"):
    return {"format": "reading-village-export", "v": 1, "export_id": export_id, "device_id": device,
            "created": "2026-10-20T11:00:00-04:00",
            "base": {"snapshot_id": snap, "progress": base if base is not None else base_progress()},
            "progress": progress, "events": events}


class ImportCase(test_server.ServerCase):
    def files(self):
        names = ("progress.json", "events.jsonl", "imports.jsonl", "rewards_history.jsonl", "treasure_counter.json")
        return {n: (self.data / n).read_bytes() if (self.data / n).exists() else None for n in names}

    def events_on_file(self):
        f = self.data / "events.jsonl"
        return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []

    def played(self):
        """A small bit of Mom's-house play: an adventure (earns a surprise), a word, +5 emeralds, +1 wood."""
        events = [ev("session_start", 0), ev("word", 1), ev("adventure_done", 2), ev("session_end", 3)]
        prog = base_progress()
        prog["inventory"]["emerald"] = 5
        prog["inventory"]["wood"] = 1
        return events, prog

    def assert_rejected_untouched(self, export, fragment):
        before = self.files()
        status, body = self.req("POST", "/api/import", export)
        self.assertEqual(status, 400, body)
        self.assertIn(fragment, body["error"])
        self.assertEqual(self.files(), before)  # byte for byte: nothing changed


class HappyPath(ImportCase):
    def test_import_replays_events_rolls_treasure_adds_emeralds_and_writes_receipt(self):
        events, prog = self.played()
        status, body = self.req("POST", "/api/import", make_export(events, prog))
        self.assertEqual(status, 200, body)
        self.assertEqual((body["ok"], body["already_imported"], body["events_new"], body["duplicates"]), (True, False, 4, 0))
        self.assertEqual(body["emeralds_added"], 5)
        self.assertEqual(len(body["treasure"]), 1)  # adventure_done surprise, rolled here at Dad's
        self.assertEqual(self.events_on_file(), events)  # in file order, ts unchanged
        p = self.req("GET", "/api/progress")[1]
        self.assertEqual(p["inventory"]["emerald"], 5)
        self.assertEqual(p["inventory"]["wood"], 1)
        self.assertEqual(len(p["treasure"]), 1)
        self.assertEqual(body["rev"], p["rev"])
        earn = self.req("GET", "/api/history?kind=earn")[1]["lines"]
        self.assertEqual(len(earn), 1)
        self.assertEqual(earn[0]["what"]["resources"], {"wood": 1, "emerald": 5})
        receipts = [json.loads(l) for l in (self.data / "imports.jsonl").read_text().splitlines()]
        self.assertEqual(len(receipts), 1)
        r = receipts[0]
        self.assertEqual((r["export_id"], r["device_id"], r["base_snapshot_id"], r["events_total"], r["events_new"],
                          r["duplicates"], r["v"]), ("exp-1", "dev-1", "snap-A", 4, 4, 0, 1))
        self.assertEqual(r["progress"], prog)

    def test_dad_settings_win_and_active_letters_union(self):
        events, prog = self.played()
        prog["settings"]["font"] = "opendyslexic"
        prog["active_letters"] = ["b", "d", "p"]
        self.assertEqual(self.req("POST", "/api/import", make_export(events, prog))[0], 200)
        p = self.req("GET", "/api/progress")[1]
        self.assertEqual(p["settings"]["font"], "system")
        self.assertEqual(p["active_letters"], ["b", "d", "p"])


class Dedupe(ImportCase):
    def test_events_already_on_file_are_skipped(self):
        events, prog = self.played()
        for e in events[:2]:  # two of them already reached Dad's some other way
            self.assertEqual(self.req("POST", "/api/event", e)[0], 200)
        status, body = self.req("POST", "/api/import", make_export(events, prog))
        self.assertEqual(status, 200, body)
        self.assertEqual((body["events_new"], body["duplicates"]), (2, 2))
        self.assertEqual(self.events_on_file(), events)

    def test_two_identical_events_are_deduped_by_count_not_collapsed(self):
        # Two identical word events in the export; one of them already reached Dad's side: only ONE is new.
        events, prog = self.played()
        twin = ev("word", 7)
        export_events = events + [twin, copy.deepcopy(twin)]
        self.assertEqual(self.req("POST", "/api/event", twin)[0], 200)
        status, body = self.req("POST", "/api/import", make_export(export_events, prog))
        self.assertEqual(status, 200, body)
        self.assertEqual((body["events_new"], body["duplicates"]), (len(events) + 1, 1))
        self.assertEqual(sum(1 for e in self.events_on_file() if e == twin), 2)

    def test_same_export_id_again_changes_nothing(self):
        events, prog = self.played()
        export = make_export(events, prog)
        first = self.req("POST", "/api/import", export)[1]
        before = self.files()
        status, body = self.req("POST", "/api/import", export)
        self.assertEqual(status, 200)
        self.assertTrue(body["already_imported"])
        self.assertEqual((body["events_new"], body["duplicates"]), (first["events_new"], first["duplicates"]))
        self.assertEqual(self.files(), before)

    def test_cumulative_second_export_adds_only_the_difference(self):
        events, prog = self.played()
        self.assertEqual(self.req("POST", "/api/import", make_export(events, prog))[0], 200)
        events2 = events + [ev("word", 4), ev("word", 5, item="stone")]
        prog2 = copy.deepcopy(prog)
        prog2["inventory"]["emerald"] = 7  # +2 since the first export
        prog2["crafted"] = {"PIG": 1}
        status, body = self.req("POST", "/api/import", make_export(events2, prog2, export_id="exp-2"))
        self.assertEqual(status, 200, body)
        self.assertEqual((body["events_new"], body["duplicates"], body["emeralds_added"]), (2, 4, 2))
        self.assertEqual(len(self.events_on_file()), 6)
        p = self.req("GET", "/api/progress")[1]
        self.assertEqual((p["inventory"]["emerald"], p["inventory"]["wood"], p["crafted"]), (7, 1, {"PIG": 1}))

    def test_other_device_with_same_base_starts_from_the_base(self):
        events, prog = self.played()
        self.assertEqual(self.req("POST", "/api/import", make_export(events, prog))[0], 200)
        status, body = self.req("POST", "/api/import", make_export([], prog, export_id="exp-9", device="dev-2"))
        self.assertEqual(status, 200, body)
        self.assertEqual(self.req("GET", "/api/progress")[1]["inventory"]["emerald"], 10)  # both devices' +5


class Rejections(ImportCase):
    def test_every_invalid_event_is_400_and_nothing_changes(self):
        events, prog = self.played()
        for i, mutate, frag in [
            (0, lambda e: e.update(type="nope"), "events[0]"),
            (1, lambda e: e.update(result="great"), "events[1]: result"),
            (2, lambda e: e.update(extra=1), "events[2]: extra"),
            (3, lambda e: e.pop("session_id"), "events[3]: session_id"),
            (1, lambda e: e.update(level=999), "events[1]: level"),
        ]:
            bad = copy.deepcopy(events)
            mutate(bad[i])
            with self.subTest(frag=frag):
                self.assert_rejected_untouched(make_export(bad, prog), frag)

    def test_bad_event_late_in_the_file_leaves_earlier_events_unwritten(self):
        events, prog = self.played()
        events[3]["ts"] = "yesterday"
        self.assert_rejected_untouched(make_export(events, prog), "events[3]: ts")
        self.assertEqual(self.events_on_file(), [])

    def test_bad_shape_fields(self):
        events, prog = self.played()
        good = make_export(events, prog)
        cases = []
        for key, val, frag in [("format", "other", "format"), ("v", 2, "v"), ("export_id", "", "export_id"),
                               ("device_id", 5, "device_id"), ("created", "2026-10-20T11:00:00", "created"),
                               ("events", {}, "events")]:
            cases.append((dict(good, **{key: val}), frag))
        extra = dict(good, surprise=1)
        cases.append((extra, "surprise"))
        missing = {k: v for k, v in good.items() if k != "base"}
        cases.append((missing, "base"))
        noprog = copy.deepcopy(good)
        del noprog["progress"]["house"]
        cases.append((noprog, "progress"))
        owned = copy.deepcopy(good)
        owned["progress"]["treasure"] = []  # server-owned keys are not part of an export
        cases.append((owned, "treasure"))
        badinv = copy.deepcopy(good)
        badinv["base"]["progress"]["inventory"]["emerald"] = -1
        cases.append((badinv, "base.progress.inventory.emerald"))
        for export, frag in cases:
            with self.subTest(frag=frag):
                self.assert_rejected_untouched(export, frag)
        status, body = self.req("POST", "/api/import", [1, 2])
        self.assertEqual(status, 400)

    def test_negative_inventory_result_is_400_and_nothing_changes(self):
        # Dad spent 3 emeralds at the shop; Mom's house spent 4 of the base's 5 (-4). 3 + ... would go below 0.
        base = base_progress()
        base["inventory"]["emerald"] = 5
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["inventory"]["emerald"] = 3
        self.assertEqual(self.put(p)[0], 200)
        mine = copy.deepcopy(base)
        mine["inventory"]["emerald"] = 1
        events = [ev("session_start", 0)]
        self.assert_rejected_untouched(make_export(events, mine, base=base), "inventory.emerald")

    def test_failure_midway_rolls_everything_back(self):
        """A craft word with no configured item passes validate_event but fails inside accept_event, after the
        earlier events were already appended: every file is restored."""
        events, prog = self.played()
        events.append(ev("craft", 4, item="ZZZZZZ"))
        before = self.files()
        status, body = self.req("POST", "/api/import", make_export(events, prog))
        self.assertEqual(status, 400, body)
        self.assertIn("item", body["error"])
        self.assertEqual(self.files(), before)


class OlderExportAndConflicts(ImportCase):
    def test_older_export_after_newer_from_same_device_and_base_is_400(self):
        events, prog = self.played()
        newer_events = events + [ev("word", 4)]
        newer = copy.deepcopy(prog)
        newer["inventory"]["emerald"] = 9
        self.assertEqual(self.req("POST", "/api/import", make_export(newer_events, newer, export_id="exp-2"))[0], 200)
        self.assert_rejected_untouched(make_export(events, prog, export_id="exp-1"),
                                       "older than an export already imported; nothing changed")
        self.assertEqual(self.req("GET", "/api/progress")[1]["inventory"]["emerald"], 9)

    def test_house_cell_conflict_keeps_dads_block_and_still_imports(self):
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["house"] = [{"x": 3, "y": 2, "block": "stone"}]
        p["inventory"]["stone"] = 1
        self.assertEqual(self.put(p)[0], 200)
        events, prog = self.played()
        prog["house"] = [{"x": 3, "y": 2, "block": "wood"}]
        status, body = self.req("POST", "/api/import", make_export(events, prog))
        self.assertEqual(status, 200, body)
        self.assertEqual(body["house_conflicts"], [{"x": 3, "y": 2, "dads": "stone", "moms": "wood"}])
        self.assertEqual(body["events_new"], 4)
        got = self.req("GET", "/api/progress")[1]
        self.assertEqual(got["house"], [{"x": 3, "y": 2, "block": "stone"}])
        self.assertEqual(got["inventory"]["emerald"], 5)

    def test_rollback_keeps_history_lines_the_worker_appended(self):
        from unittest import mock
        events, prog = self.played()
        real = server.accept_event
        calls = []

        def flaky(srv, e):
            calls.append(e)
            if len(calls) == 3:  # stands in for the delivery worker writing during the import, then a disk error
                srv.mc.history.append("delivery_failed", {"delivery": "d1", "tid": "t1", "error": "x"}, "d1")
                raise OSError("disk full")
            return real(srv, e)
        with mock.patch.object(server, "accept_event", flaky):
            status, _ = self.req("POST", "/api/import", make_export(events, prog))
        self.assertEqual(status, 500)
        lines = [json.loads(l) for l in (self.data / "rewards_history.jsonl").read_text().splitlines()]
        self.assertEqual([l["kind"] for l in lines], ["delivery_failed"])
        self.assertEqual(self.events_on_file(), [])


if __name__ == "__main__":
    unittest.main()
