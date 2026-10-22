"""Server tests: validation, atomic writes, corrupt-file refusal, default creation."""
import copy
import json
import os
import subprocess
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
import server  # noqa: E402


def good_event(**over):
    ev = {"v": 1, "ts": "2026-10-18T09:00:00-04:00", "session_id": "s1", "type": "card",
          "track": "lowercase", "item": "b", "result": "correct"}
    ev.update(over)
    return ev


# One valid example per event type, used to test "omit each required field -> 400".
VALID_BY_TYPE = {
    "session_start": {},
    "session_end": {},
    "card": {"track": "lowercase", "item": "b", "result": "correct"},
    "match": {"item": "b", "result": "miss", "chosen": "d"},
    "word": {"track": "smallcaps", "item": "pig", "result": "assisted"},
    "story_page": {"track": "lowercase", "story_id": "gold-pig", "page": 0},
    "swap_page": {"track": "lowercase", "story_id": "gold-pig", "page": 0, "percent": 30},
    "swap_done": {"track": "lowercase", "story_id": "gold-pig", "percent": 30},
    "story_done": {"track": "smallcaps", "story_id": "gold-pig"},
    "tricky_word": {"item": "pig", "story_id": "gold-pig"},
    "block_placed": {"cell": [1, 2], "block": "wood"},
    "craft": {"track": "smallcaps", "item": "PIG", "result": "assisted"},
    "adventure_done": {"adventure": "smallcaps"},
}


def event_of(t):
    return {"v": 1, "ts": "2026-10-18T09:00:00-04:00", "session_id": "s1", "type": t, **VALID_BY_TYPE[t]}


class ServerCase(unittest.TestCase):
    """Runs a real server in a thread against a temp data dir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.srv = server.make_server(self.data, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self._stderr = mock.patch("sys.stderr")  # keep expected 4xx logs out of test output
        self._stderr.start()

    def tearDown(self):
        self._stderr.stop()
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def put(self, p):
        """PUT p carrying the server's current rev (what a client that just read would send)."""
        p = dict(p, rev=self.req("GET", "/api/progress")[1]["rev"])
        return self.req("PUT", "/api/progress", p)

    def req(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        r = urllib.request.Request(self.base + path, data=data, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class DefaultAndShape(ServerCase):
    def test_default_progress_created(self):
        self.assertTrue((self.data / "progress.json").exists())
        status, p = self.req("GET", "/api/progress")
        self.assertEqual(status, 200)
        self.assertEqual(p, server.DEFAULT_PROGRESS)
        self.assertEqual(p["settings"]["font"], "system")

    def test_lowercase_track_default_and_missing(self):
        self.assertEqual(server.DEFAULT_PROGRESS["settings"]["lowercase_track"], "off")
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        del p["settings"]["lowercase_percent"]  # missing reads as 0
        self.assertEqual(self.put(p)[0], 200)
        p["settings"]["lowercase_percent"] = 100
        self.assertEqual(self.put(p)[0], 200)
        del p["settings"]["lowercase_track"]  # older file without the field is accepted (reads as "off")
        self.assertEqual(self.put(p)[0], 200)
        p["settings"]["lowercase_track"] = "on"
        self.assertEqual(self.put(p)[0], 200)
        self.assertEqual(self.req("GET", "/api/progress")[1]["settings"]["lowercase_track"], "on")

    def test_put_valid_roundtrip(self):
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["inventory"]["coal"] = 3
        p["letter_stats"]["b"] = {"recent": ["correct", "miss"], "total_correct": 1, "total_tries": 2}
        p["house"] = [{"x": 0, "y": 7, "block": "stone"}]
        p["stories"]["gold-pig"] = {"smallcaps_done": True, "lowercase_done": False, "resume_page": 2}
        self.assertEqual(self.put(p)[0], 200)
        self.assertEqual(self.req("GET", "/api/progress")[1], dict(p, rev=1))

    def test_put_invalid_shapes_name_the_field(self):
        def mut(f):
            p = copy.deepcopy(server.DEFAULT_PROGRESS)
            f(p)
            return p
        cases = [
            (lambda p: p.pop("house"), "house"),
            (lambda p: p.update(extra=1), "extra"),
            (lambda p: p.update(v=2), "v"),
            (lambda p: p["inventory"].update(coal="3"), "inventory.coal"),
            (lambda p: p["inventory"].update(coal=True), "inventory.coal"),
            (lambda p: p["inventory"].update(coal=-1), "inventory.coal"),
            (lambda p: p["inventory"].pop("gold"), "inventory.gold"),
            (lambda p: p.update(active_letters=["z"]), "active_letters[0]"),
            (lambda p: p.update(active_letters=[]), "active_letters"),
            (lambda p: p["letter_stats"].update(b={"recent": ["nope"], "total_correct": 0, "total_tries": 1}),
             "letter_stats.b.recent[0]"),
            (lambda p: p["letter_stats"].update(b={"recent": ["miss"] * 11, "total_correct": 0, "total_tries": 11}),
             "letter_stats.b.recent"),
            (lambda p: p["letter_stats"].update(b={"recent": [], "total_correct": 2, "total_tries": 1}),
             "letter_stats.b.total_correct"),
            (lambda p: p.update(house=[{"x": 99, "y": 0, "block": "wood"}]), "house[0]"),
            (lambda p: p.update(house=[{"x": 0, "y": 0, "block": "lava"}]), "house[0].block"),
            (lambda p: p.update(house=[{"x": 0, "y": 0, "block": "wood"}] * 2), "house[1]"),
            (lambda p: p["stories"].update(a={"smallcaps_done": "yes", "lowercase_done": False, "resume_page": 0}),
             "stories.a.smallcaps_done"),
            (lambda p: p["stories"].update(a={"smallcaps_done": False, "lowercase_done": False}),
             "stories.a.resume_page"),
            (lambda p: p["settings"].update(font="comic"), "settings.font"),
            (lambda p: p["settings"].update(lowercase_track="maybe"), "settings.lowercase_track"),
            (lambda p: p["settings"].update(lowercase_track=True), "settings.lowercase_track"),
            (lambda p: p["settings"].update(lowercase_percent=101), "settings.lowercase_percent"),
            (lambda p: p["settings"].update(lowercase_percent=-1), "settings.lowercase_percent"),
            (lambda p: p["settings"].update(lowercase_percent=30.5), "settings.lowercase_percent"),
            (lambda p: p["settings"].update(lowercase_percent="30"), "settings.lowercase_percent"),
            (lambda p: p["settings"].update(lowercase_percent=True), "settings.lowercase_percent"),
            (lambda p: p["settings"].update(sound="loud"), "settings.sound"),
            (lambda p: p["settings"].update(sound=True), "settings.sound"),
        ]
        for f, field in cases:
            status, body = self.put(mut(f))
            self.assertEqual(status, 400, field)
            self.assertIn(field, body["error"])
        # nothing invalid was written
        self.assertEqual(self.req("GET", "/api/progress")[1], server.DEFAULT_PROGRESS)

    def test_put_non_json_is_400(self):
        r = urllib.request.Request(self.base + "/api/progress", data=b"{nope", method="PUT")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(r)
        self.assertEqual(cm.exception.code, 400)


class Concurrency(ServerCase):
    """Optimistic concurrency: progress.json carries an integer rev (docs/design.md, 2026-10-18)."""

    def test_default_rev_is_zero_and_put_bumps_it(self):
        self.assertEqual(self.req("GET", "/api/progress")[1]["rev"], 0)
        status, saved = self.req("PUT", "/api/progress", dict(server.DEFAULT_PROGRESS, rev=0))
        self.assertEqual((status, saved["rev"]), (200, 1))
        self.assertEqual(self.req("GET", "/api/progress")[1]["rev"], 1)

    def test_stale_rev_is_409_and_writes_nothing(self):
        self.put(server.DEFAULT_PROGRESS)  # rev 0 -> 1
        stale = copy.deepcopy(server.DEFAULT_PROGRESS)
        stale["rev"] = 0
        stale["inventory"]["coal"] = 7
        status, body = self.req("PUT", "/api/progress", stale)
        self.assertEqual(status, 409)
        self.assertIn("rev", body["error"])
        got = self.req("GET", "/api/progress")[1]
        self.assertEqual((got["rev"], got["inventory"]["coal"]), (1, 0))

    def test_put_without_or_with_bad_rev_is_400(self):
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        del p["rev"]
        status, body = self.req("PUT", "/api/progress", p)
        self.assertEqual(status, 400)
        self.assertIn("rev", body["error"])
        for bad in ("0", -1, 1.5, True, None):
            status, body = self.req("PUT", "/api/progress", dict(p, rev=bad))
            self.assertEqual(status, 400, bad)
            self.assertIn("rev", body["error"])

    def test_file_without_rev_reads_as_zero_and_next_put_makes_it_one(self):
        raw = copy.deepcopy(server.DEFAULT_PROGRESS)
        del raw["rev"]
        (self.data / "progress.json").write_text(json.dumps(raw))
        self.assertEqual(self.req("GET", "/api/progress")[1]["rev"], 0)
        status, saved = self.req("PUT", "/api/progress", dict(raw, rev=0))
        self.assertEqual((status, saved["rev"]), (200, 1))

    def test_two_racing_puts_exactly_one_wins(self):
        results = []
        def go(n):
            p = copy.deepcopy(server.DEFAULT_PROGRESS)
            p["rev"] = 0
            p["inventory"]["coal"] = n
            results.append(self.req("PUT", "/api/progress", p)[0])
        threads = [threading.Thread(target=go, args=(n,)) for n in (1, 2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.req("GET", "/api/progress")[1]["rev"], 1)

    def test_get_progress_validates_the_file(self):
        bad = copy.deepcopy(server.DEFAULT_PROGRESS)
        bad["inventory"]["wood"] = -5
        (self.data / "progress.json").write_text(json.dumps(bad))
        status, body = self.req("GET", "/api/progress")
        self.assertEqual(status, 500)
        self.assertIn("inventory.wood", body["error"])
        (self.data / "progress.json").write_text("{nope")
        self.assertEqual(self.req("GET", "/api/progress")[0], 500)


class Events(ServerCase):
    def test_every_type_accepted_and_appended(self):
        for t in VALID_BY_TYPE:
            self.assertEqual(self.req("POST", "/api/event", event_of(t))[0], 200, t)
        status, events = self.req("GET", "/api/events")
        self.assertEqual([e["type"] for e in events], list(VALID_BY_TYPE))
        lines = (self.data / "events.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), len(VALID_BY_TYPE))

    def test_every_required_field_omission_is_400(self):
        for t in VALID_BY_TYPE:
            for field in list(event_of(t)):
                if field == "type":
                    continue
                ev = event_of(t)
                del ev[field]
                status, body = self.req("POST", "/api/event", ev)
                self.assertEqual(status, 400, f"{t} without {field}")
                self.assertIn(field, body["error"])
        self.assertFalse((self.data / "events.jsonl").exists())

    def test_missing_type_and_unknown_type(self):
        ev = good_event()
        del ev["type"]
        self.assertEqual(self.req("POST", "/api/event", ev)[0], 400)
        status, body = self.req("POST", "/api/event", good_event(type="dance"))
        self.assertEqual(status, 400)
        self.assertIn("type", body["error"])

    def test_wrong_types_and_values(self):
        bad = [
            ({"v": "1"}, "v"), ({"v": 2}, "v"), ({"ts": "yesterday"}, "ts"),
            ({"ts": "2026-10-18T09:00:00"}, "ts"),  # no offset
            ({"session_id": ""}, "session_id"), ({"session_id": 5}, "session_id"),
            ({"track": "upper"}, "track"), ({"result": "wrong"}, "result"),
            ({"item": 7}, "item"), ({"item": ""}, "item"),
            ({"page": 1}, "page"),  # page not allowed on card
            ({"extra": 1}, "extra"),
        ]
        for over, field in bad:
            status, body = self.req("POST", "/api/event", good_event(**over))
            self.assertEqual(status, 400, over)
            self.assertIn(field, body["error"])
        for over, field in [({"page": -1}, "page"), ({"page": "0"}, "page"), ({"page": True}, "page")]:
            ev = event_of("story_page")
            ev.update(over)
            status, body = self.req("POST", "/api/event", ev)
            self.assertEqual(status, 400, over)
            self.assertIn(field, body["error"])
        for pc in (-1, 101, 30.5, "30", True):
            ev = event_of("swap_page")
            ev["percent"] = pc
            status, body = self.req("POST", "/api/event", ev)
            self.assertEqual(status, 400, pc)
            self.assertIn("percent", body["error"])
        for cell in ([1], [1, "2"], [12, 0], [0, 8], "1,2", [True, 0]):
            ev = event_of("block_placed")
            ev["cell"] = cell
            self.assertEqual(self.req("POST", "/api/event", ev)[0], 400, cell)
        ev = event_of("block_placed")
        ev["block"] = "lava"
        self.assertEqual(self.req("POST", "/api/event", ev)[0], 400)
        self.assertFalse((self.data / "events.jsonl").exists())

    def test_swap_events_accepted(self):
        for t in ("swap_page", "swap_done", "tricky_word"):
            ev = event_of(t)
            ev["percent"] = 30
            self.assertEqual(self.req("POST", "/api/event", ev)[0], 200, t)

    def test_swap_page_requires_lowercase_track(self):
        for t in ("swap_page", "swap_done"):
            ev = event_of(t)
            ev["track"] = "smallcaps"
            status, body = self.req("POST", "/api/event", ev)
            self.assertEqual(status, 400, t)
            self.assertIn("track", body["error"])

    def test_card_and_match_items_must_be_drill_letters(self):
        for t in ("card", "match"):
            for item in ("zz", "a", "B", "bd"):
                ev = event_of(t)
                ev["item"] = item
                status, body = self.req("POST", "/api/event", ev)
                self.assertEqual(status, 400, (t, item))
                self.assertIn("item", body["error"])
        for l in server.LETTERS:
            ev = event_of("card")
            ev["item"] = l
            self.assertEqual(self.req("POST", "/api/event", ev)[0], 200, l)

    def test_get_events_names_first_bad_line_and_field(self):
        good = json.dumps(event_of("session_start"))
        bad_ts = {k: v for k, v in event_of("word").items() if k != "ts"}
        cases = [
            ("{}\n", "line 1", "ts"),
            (good + "\n" + json.dumps(bad_ts) + "\n", "line 2", "ts"),
            (good + "\n" + json.dumps(dict(event_of("match"), result="oops")) + "\n", "line 2", "result"),
            (good + "\n" + json.dumps(dict(event_of("session_start"), type="bogus")) + "\n", "line 2", "type"),
            (good + "\nnot json\n", "line 2", "not valid JSON"),
        ]
        for text, line, field in cases:
            (self.data / "events.jsonl").write_text(text)
            status, body = self.req("GET", "/api/events")
            self.assertEqual(status, 500, text)
            self.assertIn(line, body["error"])
            self.assertIn(field, body["error"])

    def test_unknown_route_404(self):
        self.assertEqual(self.req("GET", "/api/nope")[0], 404)


class CraftContract(ServerCase):
    """Crafting Table: the strict "craft" event and the optional progress.crafted map."""

    def post(self, **over):
        ev = event_of("craft")
        ev.update(over)
        return self.req("POST", "/api/event", ev)

    def test_valid_craft_events(self):
        for result in ("correct", "assisted"):
            self.assertEqual(self.post(result=result)[0], 200)

    def test_craft_rejects_bad_fields_naming_them(self):
        cases = [({"result": "miss"}, "result"), ({"track": "lowercase"}, "track"), ({"item": "pig"}, "item"),
                 ({"item": "DUCK"}, "item"), ({"item": ""}, "item"), ({"chosen": "P"}, "chosen"), ({"page": 0}, "page")]
        for over, field in cases:
            status, body = self.post(**over)
            self.assertEqual(status, 400, over)
            self.assertIn(field, body["error"], over)
        ev = event_of("craft")
        del ev["track"]
        status, body = self.req("POST", "/api/event", ev)
        self.assertEqual((status, "track" in body["error"]), (400, True))

    def test_crafted_is_optional_and_validated(self):
        p = self.req("GET", "/api/progress")[1]
        self.assertNotIn("crafted", p, "missing crafted reads as {} on the client; the default file has none")
        self.assertEqual(self.put({**p, "crafted": {"PIG": 2, "BED": 1}})[0], 200)
        self.assertEqual(self.req("GET", "/api/progress")[1]["crafted"], {"PIG": 2, "BED": 1})
        for bad in ({"pig": 1}, {"PIG": 0}, {"PIG": "1"}, {"PIG": True}, {"PIGGYBANKSS": 1}, [1]):
            status, body = self.put({**p, "crafted": bad})
            self.assertEqual(status, 400, bad)
            self.assertIn("crafted", body["error"])


class Atomicity(ServerCase):
    def test_failed_replace_leaves_old_file_and_no_temp(self):
        before = (self.data / "progress.json").read_text()
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["inventory"]["coal"] = 9
        with mock.patch("server.os.replace", side_effect=OSError("disk full")):
            status, body = self.put(p)
        self.assertEqual(status, 500)
        self.assertIn("disk full", body["error"])
        self.assertEqual((self.data / "progress.json").read_text(), before)
        self.assertEqual([f for f in os.listdir(self.data) if f.endswith(".tmp")], [])  # no half-written temp file

    def test_write_uses_temp_then_replace(self):
        with mock.patch("server.os.replace", wraps=os.replace) as rep:
            server.write_json_atomic(self.data / "x.json", {"a": 1})
        src, dst = rep.call_args.args
        self.assertNotEqual(Path(src), Path(dst))
        self.assertEqual(Path(src).parent, self.data)
        self.assertEqual(json.loads((self.data / "x.json").read_text()), {"a": 1})


    def test_directory_is_fsynced_after_the_rename(self):
        """The rename must be made durable: fsync on the parent directory after os.replace."""
        order = []
        real_replace, real_fsync = os.replace, os.fsync
        def fsync(fd):
            import stat
            order.append("dir-fsync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file-fsync")
            return real_fsync(fd)
        def replace(a, b):
            order.append("replace")
            return real_replace(a, b)
        with mock.patch("server.os.fsync", fsync), mock.patch("server.os.replace", replace):
            server.write_json_atomic(self.data / "y.json", {"a": 1})
        self.assertEqual(order, ["file-fsync", "replace", "dir-fsync"])


class CorruptFile(unittest.TestCase):
    def run_server(self, data_dir):
        return subprocess.run([sys.executable, str(ROOT / "server.py"), "--no-browser", "--port", "0",
                               "--data-dir", str(data_dir)], capture_output=True, text=True, timeout=20)

    def test_corrupt_json_refuses_and_is_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "progress.json").write_text("{not json")
            r = self.run_server(d)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("REFUSING TO START", r.stderr)
            self.assertEqual((Path(d) / "progress.json").read_text(), "{not json")

    def test_invalid_shape_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "progress.json").write_text(json.dumps({"v": 1}))
            r = self.run_server(d)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("REFUSING TO START", r.stderr)

    def test_make_server_raises_systemexit(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "progress.json").write_text("")
            with self.assertRaises(SystemExit):
                server.make_server(d, 0)


class Static(ServerCase):
    def test_app_and_path_escape(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertEqual(r.status, 200)
        for path in ("/../server.py", "/stories/../server.py", "/%2e%2e/server.py"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as cm:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(cm.exception.code, 404)




class LoopbackBindTest(unittest.TestCase):
    """localhost must reach the game on both ::1 and 127.0.0.1, and an IPv6 clash must fail loudly."""

    def test_binds_both_and_clash_raises(self):
        import socket
        import server
        with tempfile.TemporaryDirectory() as d:
            v4, v6 = server.make_loopback_servers(d, 0)
            port = v4.server_address[1]
            try:
                self.assertEqual(v6.server_address[1], port)
                self.assertIs(v6.write_lock, v4.write_lock)
            finally:
                v4.server_close(); v6.server_close()
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            s.bind(("::1", 0)); s.listen(1)
            try:
                with self.assertRaises(OSError):
                    server.make_loopback_servers(d, s.getsockname()[1])
            finally:
                s.close()

    def test_ipv6_twin_carries_every_server_attribute_and_saves(self):
        """Regression: ::1 lacked `levels`, so every PUT via "localhost" crashed."""
        with tempfile.TemporaryDirectory() as d:
            v4, v6 = server.make_loopback_servers(d, 0)
            try:
                # Every non-socket attribute make_server attached must be on the twin too.
                extra = {k for k in vars(v4) if not k.startswith("_") and k not in vars(v6)}
                self.assertEqual(extra - {"socket", "server_address", "RequestHandlerClass", "allow_reuse_address",
                                          "allow_reuse_port", "daemon_threads", "server_name", "server_port"}, set())
                threading.Thread(target=v6.serve_forever, daemon=True).start()
                base = f"http://[::1]:{v6.server_address[1]}"
                with urllib.request.urlopen(base + "/api/progress", timeout=5) as r:
                    p = json.loads(r.read())
                req = urllib.request.Request(base + "/api/progress", data=json.dumps(p).encode(), method="PUT",
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    self.assertEqual(r.status, 200)
            finally:
                v6.shutdown(); v4.server_close(); v6.server_close()


class ResetEndpoint(ServerCase):
    def seed(self):
        """Give the server some non-default progress and two events."""
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["inventory"]["wood"] = 5
        self.assertEqual(self.put(p)[0], 200)
        for _ in range(2):
            self.assertEqual(self.req("POST", "/api/event", good_event())[0], 200)

    def test_reset_archives_both_files_and_writes_default(self):
        self.seed()
        before_p = (self.data / "progress.json").read_text()
        before_e = (self.data / "events.jsonl").read_text()
        status, body = self.req("POST", "/api/reset", {"confirm": "RESET"})
        self.assertEqual(status, 200)
        arch = Path(body["archived_to"])
        self.assertEqual(arch.parent, self.data / "archive")
        self.assertRegex(arch.name, r"^\d{8}-\d{6}")
        self.assertEqual((arch / "progress.json").read_text(), before_p)  # nothing lost
        self.assertEqual((arch / "events.jsonl").read_text(), before_e)
        self.assertFalse((self.data / "events.jsonl").exists())
        fresh = self.req("GET", "/api/progress")[1]
        self.assertEqual(fresh["inventory"]["wood"], 0)
        self.assertEqual({k: v for k, v in fresh.items() if k != "rev"},
                         {k: v for k, v in server.DEFAULT_PROGRESS.items() if k != "rev"})
        self.assertEqual(fresh["rev"], json.loads(before_p)["rev"] + 1)  # a stale tab gets 409, not a silent overwrite

    def test_stale_rev_after_reset_is_409(self):
        self.seed()
        stale = self.req("GET", "/api/progress")[1]
        self.assertEqual(self.req("POST", "/api/reset", {"confirm": "RESET"})[0], 200)
        self.assertEqual(self.req("PUT", "/api/progress", stale)[0], 409)

    def test_two_resets_do_not_collide(self):
        self.seed()
        a = self.req("POST", "/api/reset", {"confirm": "RESET"})[1]["archived_to"]
        b = self.req("POST", "/api/reset", {"confirm": "RESET"})[1]["archived_to"]
        self.assertNotEqual(a, b)
        self.assertTrue((Path(a) / "progress.json").exists() and (Path(b) / "progress.json").exists())

    def test_wrong_confirm_is_400_and_deletes_nothing(self):
        self.seed()
        before = (self.data / "progress.json").read_text(), (self.data / "events.jsonl").read_text()
        for body in ({"confirm": "reset"}, {"confirm": "yes"}, {}, {"confirm": "RESET", "x": 1}, {"confirm": None}, [], "RESET"):
            self.assertEqual(self.req("POST", "/api/reset", body)[0], 400, body)
        self.assertEqual(((self.data / "progress.json").read_text(), (self.data / "events.jsonl").read_text()), before)
        self.assertFalse((self.data / "archive").exists())

    def test_failure_is_500_and_files_are_restored(self):
        self.seed()
        before = (self.data / "progress.json").read_text(), (self.data / "events.jsonl").read_text()
        with mock.patch.object(server, "write_json_atomic", side_effect=OSError("disk full")):
            status, body = self.req("POST", "/api/reset", {"confirm": "RESET"})
        self.assertEqual(status, 500)
        self.assertIn("disk full", body["error"])
        self.assertEqual(((self.data / "progress.json").read_text(), (self.data / "events.jsonl").read_text()), before)


class FamilyConfig(unittest.TestCase):
    """config/family.json: strict, loud validation at startup, and the validated copy served at /data/family.json."""
    GOOD = {"v": 1, "child": {"name": "Sam"}, "village_name": "Sam's Village", "home_grown_up": "Dad",
            "away_label": "Mom's house"}

    def load(self, obj, raw=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "family.json"
            p.write_text(raw if raw is not None else json.dumps(obj))
            return server.load_family_config(p)

    def test_shipped_file_is_valid(self):
        self.assertEqual(server.load_family_config()["child"]["name"], "Sam")

    def test_each_failure_names_the_field(self):
        cases = []
        for k in ("child", "village_name", "home_grown_up", "away_label"):
            cases.append(({kk: v for kk, v in self.GOOD.items() if kk != k}, f"missing required field {k}"))
        cases += [
            ({**self.GOOD, "colour": "red"}, "unknown field colour"),
            ({**self.GOOD, "child": {"name": "Sam", "age": 6}}, "unknown field child.age"),
            ({**self.GOOD, "child": {}}, "missing required field child.name"),
            ({**self.GOOD, "child": {"name": ""}}, "child.name must be a non-empty string"),
            ({**self.GOOD, "village_name": 5}, "village_name must be a non-empty string"),
            ({**self.GOOD, "child": "Sam"}, "child must be a JSON object"),
            ({**self.GOOD, "v": 2}, "v must be the integer 1"),
            ([], "must be a JSON object"),
        ]
        for obj, want in cases:
            with self.subTest(want=want), self.assertRaises(server.FamilyConfigError) as cm:
                self.load(obj)
            self.assertIn(want, str(cm.exception))

    def test_missing_file_and_bad_json_fail(self):
        with self.assertRaises(server.FamilyConfigError):
            server.load_family_config(Path("/nonexistent/family.json"))
        with self.assertRaises(server.FamilyConfigError):
            self.load(None, raw="{not json")

    def test_make_server_refuses_a_bad_config_and_serves_a_good_one(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{}")
            with self.assertRaises(server.FamilyConfigError):
                server.make_server(Path(d) / "data", 0, family_config=bad)
            good = Path(d) / "good.json"
            good.write_text(json.dumps(self.GOOD))
            srv = server.make_server(Path(d) / "data", 0, family_config=good)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/data/family.json") as r:
                    self.assertEqual(json.loads(r.read()), self.GOOD)
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
