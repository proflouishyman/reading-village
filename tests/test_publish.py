"""tools/publish_web.py: site build, snapshot shape, strip list and the scrub guard. Temp dirs only; never pushes."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import publish_web as pw  # noqa: E402

TAG = "SecretTag99"
NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


def make_root(tmp):
    """A fake repo root: a tiny app/ (with files that must be excluded), config, and a git commit."""
    root = Path(tmp) / "repo"
    app = root / "app"
    for rel, text in {
        "index.html": "<html></html>", "dashboard.html": "x", "render.html": "x", ".DS_Store": "x",
        "js/main.js": "//", "js/dashboard.js": "//", "js/renderpage.js": "//",
        "js/runmode.js": "export const STATIC = false;\n",
        "css/style.css": "body{}", "assets/mc/block.png": "png", "assets/keep.txt": "ok",
    }.items():
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / rel).write_text(text)
    (root / "config").mkdir()
    (root / "config" / "web.json").write_text(json.dumps(
        {"enabled": True, "auto": True, "repo": "someone/site", "branch": "main", "work_dir": "build/web-repo"}))
    shutil.copy(ROOT / "config" / "family.json", root / "config" / "family.json")
    (root / "config" / "private_overrides.json").write_text(json.dumps({"player": TAG}))
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@example.test",
                                                 "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True, capture_output=True)
    return root


def make_data(tmp):
    data = Path(tmp) / "data"
    data.mkdir()
    sys.path.insert(0, str(ROOT))
    import server  # noqa: E402
    (data / "progress.json").write_text(json.dumps(server.DEFAULT_PROGRESS))
    return data


class PublishTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.root = make_root(self.tmp)
        self.data = make_data(self.tmp)

    def tearDown(self):
        self._t.cleanup()

    def publish(self, **kw):
        return pw.build_and_publish(self.root, self.data, push=False, **kw)

    def test_site_contents(self):
        r = self.publish()
        site = self.root / "build" / "web"
        self.assertTrue(r["ok"] and not r["pushed"])
        self.assertTrue((site / "index.html").is_file() and (site / "snapshot.json").is_file())
        self.assertTrue((site / "assets" / "keep.txt").is_file())
        for gone in ("assets/mc", "dashboard.html", "render.html", "js/dashboard.js", "js/renderpage.js", ".DS_Store"):
            self.assertFalse((site / gone).exists(), gone)
        self.assertEqual((site / "js" / "runmode.js").read_text(), "export const STATIC = true;\n")
        self.assertEqual(r["files"], len([f for f in site.rglob("*") if f.is_file()]))
        # the repo's own app/ is untouched
        self.assertIn("false", (self.root / "app" / "js" / "runmode.js").read_text())

    def test_stories_json_is_copied_and_nothing_else(self):
        st = self.root / "stories"
        st.mkdir()
        (st / "index.json").write_text(json.dumps({"v": 1, "stories": ["a-tale"]}))
        (st / "a-tale.json").write_text("{}")
        (st / "x.docx").write_text("d")
        (st / "~$x.docx").write_text("d")
        (st / "backup").mkdir()
        (st / "backup" / "old.json").write_text("{}")
        self.publish()
        got = sorted(p.name for p in (self.root / "build" / "web" / "stories").rglob("*"))
        self.assertEqual(got, ["a-tale.json", "index.json"])

    def test_delivery_failed_error_text_with_a_path_does_not_block_publishing(self):
        line = {"v": 1, "ts": "2026-10-18T19:25:44-04:00", "kind": "delivery_failed",
                "what": {"delivery": "d1", "tid": "t1", "error": "cannot read /Users/someone/mc/logs/latest.log"},
                "wallet_after": None, "ref": "d1"}
        (self.data / "rewards_history.jsonl").write_text(json.dumps(line) + "\n")
        r = self.publish()
        self.assertTrue(r["ok"])
        snap = (self.root / "build" / "web" / "snapshot.json").read_text()
        self.assertNotIn("/Users/", snap)

    def test_snapshot_shape_and_determinism(self):
        a = pw.build_snapshot(self.root, self.data, now=NOW)
        b = pw.build_snapshot(self.root, self.data, now=NOW)
        self.assertEqual(a, b)
        self.assertEqual(list(a)[:3], ["snapshot_id", "format", "v"])
        self.assertEqual(set(a), {"snapshot_id", "format", "v", "published_at", "source", "progress", "events",
                                  "village", "treasure", "history", "imported"})
        self.assertEqual(a["format"], "reading-village-snapshot")
        self.assertEqual(a["v"], 1)
        self.assertRegex(a["snapshot_id"], r"^[0-9a-f]{16}$")
        self.assertEqual(a["snapshot_id"], pw.snapshot_id_of(a))
        self.assertEqual(a["imported"], {})
        self.assertEqual(a["source"]["progress_rev"], a["progress"]["rev"])
        self.assertEqual(a["events"], [])
        later = pw.build_snapshot(self.root, self.data, now=datetime(2026, 10, 22, tzinfo=timezone.utc))
        self.assertNotEqual(a["snapshot_id"], later["snapshot_id"])

    def test_imports_become_imported(self):
        (self.data / "imports.jsonl").write_text(
            json.dumps({"device_id": "d1", "base_snapshot_id": "aa", "events_total": 3}) + "\n"
            + json.dumps({"device_id": "d1", "base_snapshot_id": "bb", "events_total": 5}) + "\n")
        self.assertEqual(pw.read_imports(self.data), {"d1": {"base_snapshot_id": "bb", "events": 5}})
        (self.data / "imports.jsonl").write_text("not json\n")
        with self.assertRaises(pw.PublishError):
            pw.read_imports(self.data)

    def test_strip_list(self):
        line = {"v": 1, "kind": "delivered",
                "what": {"label": "Sword", "chest": {"x": 1, "y": 2, "z": 3}, "delivery": "d1", "log": ["gave"],
                         "nested": {"player": TAG, "keep": 1}}}
        out = pw.strip_keys({"lines": [line]})["lines"][0]["what"]
        self.assertEqual(out, {"label": "Sword", "nested": {"keep": 1}})
        self.assertIn("chest", line["what"])  # input not mutated
        body = {"treasure": [{"tid": "t1", "state": "in_chest", "delivery": {
            "id": "d1", "status": "delivered", "attempts": 1, "last_error": f"boom {TAG}",
            "delivered_ts": "x", "chest": {"x": 1, "y": 2, "z": 3}}}, {"tid": "t2", "delivery": None}],
            "problem": f"{TAG} offline", "enabled": True}
        t = pw.strip_treasure(body)
        self.assertIsNone(t["treasure"][0]["delivery"]["chest"])
        self.assertIsNone(t["treasure"][0]["delivery"]["last_error"])
        self.assertEqual(t["treasure"][0]["delivery"]["status"], "delivered")
        self.assertIsNone(t["treasure"][1]["delivery"])
        self.assertIsNone(t["problem"])
        self.assertNotIn(TAG, json.dumps(t))

    def test_history_in_snapshot_is_stripped(self):
        line = {"v": 1, "ts": "2026-10-18T19:25:44-04:00", "kind": "delivered",
                "what": {"tid": "t000001", "label": "Book", "items": [{"item": "minecraft:stick", "count": 1}],
                         "delivery": "d000001", "chest": {"x": 1, "y": 2, "z": 3}, "log": ["ok"]},
                "wallet_after": None, "ref": "d000001"}
        (self.data / "rewards_history.jsonl").write_text(json.dumps(line) + "\n")
        snap = pw.build_snapshot(self.root, self.data, now=NOW)
        what = snap["history"]["lines"][0]["what"]
        self.assertEqual(set(what), {"tid", "label", "items"})
        self.assertEqual(snap["history"]["count"], 1)

    def _guard_fails(self, plant, expect):
        """Plant content in the app, publish with a pushing stub, and require a loud failure and no push."""
        plant(self.root / "app")
        with mock.patch.object(pw, "push_orphan") as push:
            with self.assertRaises(pw.PublishError) as cm:
                pw.build_and_publish(self.root, self.data, push=True)
        push.assert_not_called()
        self.assertIn(expect, str(cm.exception))

    def test_guard_gamertag_any_case(self):
        self._guard_fails(lambda a: (a / "js" / "main.js").write_text(f"// {TAG.upper()}"), "gamertag")

    def test_guard_gamertag_without_floodgate_prefix_any_case(self):
        # The real tag is stored WITH a leading "." (Floodgate); the site contains it without the dot, in other case.
        (self.root / "config" / "private_overrides.json").write_text(json.dumps({"player": "." + TAG}))
        site = Path(self.tmp) / "site4"
        (site / "js").mkdir(parents=True)
        (site / "js" / "runmode.js").write_text(pw.RUNMODE_STATIC)
        (site / "x.txt").write_text(f"hello {TAG.lower()} there")
        with self.assertRaises(pw.PublishError) as cm:
            pw.scrub(site, pw.load_gamertag(self.root))
        self.assertIn("contains the gamertag", str(cm.exception))
        self.assertNotIn(TAG.lower(), str(cm.exception).lower(), "the message must never print the gamertag")
        with self.assertRaises(pw.PublishError) as cm:  # nothing but punctuation cannot be searched for
            pw.scrub(site, "..")
        self.assertIn("the gamertag", str(cm.exception))

    def test_imports_are_read_from_the_copied_data_dir_not_the_live_one(self):
        seen = []
        real = pw.read_imports

        def spy(d):
            seen.append(Path(d).resolve())
            return real(d)
        with mock.patch.object(pw, "read_imports", spy):
            pw.build_snapshot(self.root, self.data, now=NOW)
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], self.data.resolve())
        self.assertNotIn(self.data.resolve(), seen[0].parents)

    def test_guard_email(self):
        self._guard_fails(lambda a: (a / "js" / "main.js").write_text("// dad@example.org"), "email address")

    def test_guard_ip(self):
        self._guard_fails(lambda a: (a / "js" / "main.js").write_text("fetch('http://192.168.1.20:8000')"),
                          "IPv4 address 192.168.1.20")

    def test_guard_loopback_allowed(self):
        (self.root / "app" / "js" / "main.js").write_text("// 127.0.0.1")
        self.assertTrue(self.publish()["ok"])

    def test_guard_users_path(self):
        self._guard_fails(lambda a: (a / "js" / "main.js").write_text("// /Users/someone/x"), "/Users/")

    def test_guard_assets_mc_file(self):
        # the build excludes assets/mc, so the guard is tested directly on a site dir that has one
        site = Path(self.tmp) / "site"
        (site / "js").mkdir(parents=True)
        (site / "js" / "runmode.js").write_text(pw.RUNMODE_STATIC)
        (site / "assets" / "mc").mkdir(parents=True)
        (site / "assets" / "mc" / "a.png").write_bytes(b"\x89PNG")
        with self.assertRaises(pw.PublishError) as cm:
            pw.scrub(site, TAG)
        self.assertIn("assets/mc/", str(cm.exception))

    def test_guard_forbidden_files_and_runmode(self):
        site = Path(self.tmp) / "site2"
        (site / "js").mkdir(parents=True)
        (site / "js" / "runmode.js").write_text("export const STATIC = false;\n")
        (site / "dashboard.html").write_text("x")
        (site / "x.txt").write_text("see private_overrides")
        with self.assertRaises(pw.PublishError) as cm:
            pw.scrub(site, TAG)
        msg = str(cm.exception)
        for s in ("dashboard.html", "runmode.js", "private_overrides"):
            self.assertIn(s, msg)

    def test_site_carries_the_validated_family_config(self):
        self.publish()
        got = json.loads((self.root / "build" / "web" / "data" / "family.json").read_text())
        self.assertEqual(got, json.loads((ROOT / "config" / "family.json").read_text()))

    def test_bad_family_config_stops_the_publish(self):
        (self.root / "config" / "family.json").write_text(json.dumps({"v": 1, "child": {"name": "Sam"}}))
        with self.assertRaises(pw.PublishError) as cm:
            self.publish()
        self.assertIn("village_name", str(cm.exception))

    def test_guard_private_strings(self):
        (self.root / "config" / "private_overrides.json").write_text(
            json.dumps({"player": TAG, "private_strings": ["Zorkington", "Elm Street"]}))
        self.assertEqual(pw.load_private_strings(self.root), ["Zorkington", "Elm Street"])
        (self.root / "app" / "js" / "main.js").write_text("// the zorkington family")
        with self.assertRaises(pw.PublishError) as cm:
            self.publish()
        self.assertIn("private_strings[0]", str(cm.exception))
        self.assertNotIn("orkington", str(cm.exception), "the message must never print the private word")

    def test_private_strings_must_be_a_list_of_strings(self):
        (self.root / "config" / "private_overrides.json").write_text(
            json.dumps({"player": TAG, "private_strings": "Zorkington"}))
        with self.assertRaises(pw.PublishError):
            pw.load_private_strings(self.root)

    def test_placeholder_repo_cannot_be_pushed(self):
        with self.assertRaises(pw.PublishError) as cm:
            pw.require_real_repo({"repo": pw.PLACEHOLDER_REPO})
        self.assertIn("placeholder", str(cm.exception))

    def test_missing_gamertag_config_fails(self):
        (self.root / "config" / "private_overrides.json").unlink()
        with self.assertRaises(pw.PublishError):
            self.publish()

    def test_work_dir_must_be_under_build(self):
        site = Path(self.tmp) / "site3"
        site.mkdir()
        with self.assertRaises(pw.PublishError):
            pw.push_orphan(self.root, site, {"work_dir": "../elsewhere", "branch": "main", "repo": "a/b"})

    def test_publish_does_not_touch_data_dir(self):
        before = {p.name: p.read_bytes() for p in self.data.iterdir()}
        self.publish()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.data.iterdir()})

    def test_missing_progress_fails_loudly(self):
        (self.data / "progress.json").unlink()
        with self.assertRaises(pw.PublishError):
            self.publish()


if __name__ == "__main__":
    unittest.main()
