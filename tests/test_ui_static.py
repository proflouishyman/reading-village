"""Browser tests for the static website copy (docs/away-from-home.md §1), Playwright.

The test builds its own static site into a temp dir (it does NOT use tools/publish_web.py): a copy of app/ without the
parts the real build strips, runmode.js rewritten to STATIC = true, and a snapshot.json assembled from a real server's
own replies (so the shapes are the real ones). The site is served from a sub-path (/reading-village/) to prove that
every URL is relative. The real data/ is never touched.
Playwright is required: if it is missing these tests ERROR (a skipped check would look like a pass).
"""
import copy
import functools
import http.server
import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import server  # noqa: E402
import test_ui_smallcaps as base  # noqa: E402  (module import: its TestCase classes must not run twice)

PREFIX = "/reading-village/"
STRIPPED = ("dashboard.html", "render.html", "js/dashboard.js", "js/renderpage.js", ".DS_Store")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def build_site(site: Path, snapshot: dict):
    """app/ minus the stripped parts and assets/mc, runmode.js STATIC=true, snapshot.json, data/family.json, stories/ at the site root."""
    shutil.copytree(ROOT / "app", site, ignore=shutil.ignore_patterns("mc", ".DS_Store"))
    for rel in STRIPPED:
        p = site / rel
        if p.exists():
            p.unlink()
    (site / "js" / "runmode.js").write_text("export const STATIC = true;\n")
    (site / "snapshot.json").write_text(json.dumps(snapshot))
    (site / "data").mkdir(exist_ok=True)  # the publisher writes the validated config/family.json here
    shutil.copy(ROOT / "config" / "family.json", site / "data" / "family.json")
    shutil.copytree(ROOT / "stories", site / "stories", ignore=shutil.ignore_patterns("*.docx", "~$*"))


def snapshot_from_server(data: Path):
    """A snapshot made from a real server's replies on a fresh temp data dir."""
    srv = server.make_server(data, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        get = lambda p: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}{p}").read())  # noqa: E731
        progress = get("/api/progress")
        return {
            "format": "reading-village-snapshot", "v": 1, "snapshot_id": "test-snapshot-1",
            "published_at": "2026-10-21T10:00:00-04:00", "source": {"commit": "test", "progress_rev": progress["rev"]},
            "progress": progress, "events": get("/api/events"), "village": get("/api/village"),
            "treasure": get("/api/treasure"), "history": get("/api/history"), "imported": {},
        }
    finally:
        srv.shutdown()
        srv.server_close()


class StaticCase(base.UiCase):
    def start_static(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data = root / "data"
        data.mkdir()
        p = copy.deepcopy(server.DEFAULT_PROGRESS)
        p["inventory"]["emerald"] = 4
        (data / "progress.json").write_text(json.dumps(p))
        (data / "events.jsonl").write_text("")
        snap = snapshot_from_server(data)
        site = root / "www" / PREFIX.strip("/")
        build_site(site, snap)
        handler = functools.partial(QuietHandler, directory=str(root / "www"))
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close()))
        self.url = f"http://127.0.0.1:{httpd.server_address[1]}{PREFIX}"
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        self.addCleanup(self.page.close)
        self.errors = []
        self.requests = []
        self.failed = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("request", lambda r: self.requests.append(r.url))
        self.page.on("response", lambda r: self.failed.append((r.status, r.url)) if r.status >= 400 else None)
        self.page.goto(self.url)
        self.page.wait_for_selector(".home, .loud")
        return self.page

    def play_a_word_round(self, page):
        """Word Blocks tile: answer every word correctly until Home returns (or an interlude, which is clicked through)."""
        page.click(".stage-btn >> nth=0")
        page.wait_for_selector(".big-word")
        for _ in range(40):
            page.wait_for_timeout(1300)
            if page.query_selector(".home"):
                return
            if page.query_selector(".interlude"):
                page.click(".interlude .btn")
                continue
            page.click("button.good:not([disabled])")
        self.fail("the word round never finished")


class StaticSite(StaticCase):
    def test_home_has_send_to_dad_and_no_dashboard_or_reset_and_never_calls_the_api(self):
        page = self.start_static()
        self.assertTrue(page.query_selector("#send-dad-btn"))
        self.assertRegex(page.inner_text("#send-dad-status"), re.compile(r"nothing new to send", re.I))
        self.assertEqual(page.query_selector_all("a[href*='dashboard']"), [])
        page.click(".settings-gear")
        page.wait_for_selector(".settings")
        self.assertEqual(page.query_selector_all(".settings a[href*='dashboard'], .settings-reset, #reset-go"), [])
        self.assertEqual([u for u in self.requests if "/api/" in u], [], "static mode must not touch the network API")
        self.assertEqual(self.failed, [], "every file the page asked for exists under the sub-path (all URLs relative)")
        self.assertFalse(self.errors, self.errors)

    def test_village_is_read_only_and_treasure_send_is_off(self):
        page = self.start_static()
        page.click(".stage-btn:has-text('Village')")
        page.wait_for_selector("#static-note")
        self.assertRegex(page.inner_text("#static-note"), re.compile(r"shop opens at dad's house.*emeralds are safe", re.I | re.S))
        self.assertTrue(page.query_selector("#sell-btn[disabled]"))
        plots = page.query_selector_all("button.plot")
        self.assertTrue(plots)
        self.assertTrue(all(p.get_attribute("disabled") is not None for p in plots))
        page.click("#pile-btn")
        page.wait_for_selector(".pile")
        self.assertRegex(page.inner_text("#static-send-note"), re.compile(r"sending to minecraft happens at dad's house", re.I))
        self.assertFalse(page.query_selector("#send-btn:not([disabled])"))
        self.assertEqual([u for u in self.requests if "/api/" in u], [])
        self.assertFalse(self.errors, self.errors)

    def test_play_is_kept_in_the_browser_and_send_to_dad_downloads_the_export(self):
        page = self.start_static()
        self.play_a_word_round(page)
        page.wait_for_selector(".home")
        self.assertRegex(page.inner_text("#send-dad-status"), re.compile(r"\d+ new things? to send", re.I))
        stored = json.loads(page.evaluate("localStorage.getItem('cv_offline_v1')"))
        n_events = len(stored["events"])
        self.assertGreater(n_events, 0)
        self.assertEqual(stored["base"]["snapshot_id"], "test-snapshot-1")

        with page.expect_download() as dl:
            page.click("#send-dad-btn")
        d = dl.value
        self.assertRegex(d.suggested_filename, r"^reading-village-\d{4}-\d{2}-\d{2}-\d{4}\.json$")
        exported = json.loads(Path(d.path()).read_text())
        self.assertEqual(exported["format"], "reading-village-export")
        self.assertEqual(len(exported["events"]), n_events)
        self.assertEqual(sorted(exported["progress"]), sorted(["inventory", "active_letters", "letter_stats", "house", "stories", "crafted", "settings"]))
        self.assertGreater(exported["progress"]["inventory"]["emerald"], 4, "the emeralds earned here are in the export")
        page.wait_for_selector("#send-dad-instructions")
        self.assertRegex(page.inner_text("#send-dad-instructions"), re.compile(r"attach this file \(in your downloads folder\) to an email to dad", re.I))
        page.click("#send-dad-ok")
        page.wait_for_selector(".home")
        self.assertRegex(page.inner_text("#send-dad-status"), re.compile(r"all sent .*last sent", re.I))

        page.reload()  # progress survives a reload, and is not cleared by exporting
        page.wait_for_selector(".home")
        self.assertRegex(page.inner_text("#send-dad-status"), re.compile(r"all sent", re.I))
        self.assertEqual(len(json.loads(page.evaluate("localStorage.getItem('cv_offline_v1')"))["events"]), n_events)
        self.assertEqual([u for u in self.requests if "/api/" in u], [])
        self.assertFalse(self.errors, self.errors)

    def test_finish_session_offers_the_send_screen(self):
        page = self.start_static()
        self.play_a_word_round(page)
        page.wait_for_selector(".home")
        page.click("text=Finish session")
        page.wait_for_selector("#send-dad-prompt-btn")
        with page.expect_download():
            page.click("#send-dad-prompt-btn")
        page.wait_for_selector("#send-dad-ok")
        page.click("#send-dad-ok")
        page.wait_for_selector(".home")

    def test_a_save_that_fails_shows_the_loud_banner_without_python_advice(self):
        page = self.start_static()
        page.evaluate("() => { Storage.prototype.setItem = () => { throw new Error('quota exceeded'); }; }")
        page.click(".stage-btn >> nth=0")  # starting a stage logs session_start, which must fail to save
        page.wait_for_selector(".loud")
        text = page.inner_text("#overlay")
        self.assertIn("PROGRESS NOT SAVED", text)
        self.assertRegex(text, re.compile(r"ask a grown-up to reload the page", re.I))
        self.assertNotIn("python3 server.py", text)

    def test_a_missing_snapshot_is_a_loud_fatal_screen(self):
        page = self.start_static()
        page.route("**/snapshot.json", lambda r: r.fulfill(status=404, body="nope"))
        page.evaluate("localStorage.clear()")
        page.reload()
        page.wait_for_selector(".loud")
        self.assertIn("Could not load Sam's status from the website", page.inner_text("#overlay"))


if __name__ == "__main__":
    unittest.main()
