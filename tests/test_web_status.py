"""GET /api/web, POST /api/web/publish and the auto-publish hook (docs/away-from-home.md section 6). The real publisher
is never called: a fake is injected as srv.publisher, so nothing is ever pushed."""
import json
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import server  # noqa: E402
import test_server  # noqa: E402
import test_import  # noqa: E402

CFG = {"enabled": True, "auto": True, "repo": "o/r", "branch": "main", "work_dir": "build/web-repo"}


class WebCase(test_server.ServerCase):
    def setUp(self):
        super().setUp()
        self.cfg_path = Path(self.tmp.name) / "web.json"
        self.srv.web_config_path = self.cfg_path
        self.calls = []
        self.gate = None  # a threading.Event the fake waits on, to hold a publish open
        self.fail_with = None

        def fake(root, data_dir, push):
            self.calls.append((root, Path(data_dir), push))
            if self.gate is not None:
                self.gate.wait(10)
            if self.fail_with:
                raise RuntimeError(self.fail_with)
            return {"ok": True, "snapshot_id": f"snap{len(self.calls)}", "url": "u", "pushed": push, "files": 1}
        self.srv.publisher = fake

    def write_cfg(self, **over):
        self.cfg_path.write_text(json.dumps({**CFG, **over}))

    def wait_idle(self):
        for _ in range(200):
            s = self.req("GET", "/api/web")[1]
            if s["state"] != "running":
                return s
            time.sleep(0.02)
        self.fail("publish never finished")


class Status(WebCase):
    def test_missing_config_is_disabled_loudly(self):
        status, body = self.req("GET", "/api/web")
        self.assertEqual(status, 200)
        self.assertEqual((body["state"], body["error"]), ("disabled", "config/web.json missing"))
        status, body = self.req("POST", "/api/web/publish")
        self.assertEqual(status, 409)
        self.assertIn("config/web.json missing", body["error"])
        self.assertEqual(self.calls, [])

    def test_invalid_config_is_failed_loudly(self):
        self.cfg_path.write_text('{"enabled": true}')
        body = self.req("GET", "/api/web")[1]
        self.assertEqual(body["state"], "failed")
        self.assertIn("invalid", body["error"])

    def test_disabled_config(self):
        self.write_cfg(enabled=False)
        self.assertEqual(self.req("GET", "/api/web")[1]["state"], "disabled")
        self.assertEqual(self.req("POST", "/api/web/publish")[0], 409)

    def test_idle_before_any_publish(self):
        self.write_cfg()
        body = self.req("GET", "/api/web")[1]
        self.assertEqual((body["state"], body["snapshot_id"], body["error"], body["at"]), ("idle", None, None, None))

    def test_manual_publish_ok(self):
        self.write_cfg(auto=False)
        status, body = self.req("POST", "/api/web/publish")
        self.assertEqual(status, 200)
        self.assertIn(body["state"], ("running", "ok"))  # the fake may already be done
        done = self.wait_idle()
        self.assertEqual((done["state"], done["snapshot_id"], done["error"]), ("ok", "snap1", None))
        self.assertIsNotNone(done["at"])
        self.assertEqual(self.calls, [(server.ROOT, self.data, True)])

    def test_failure_is_recorded_loudly(self):
        self.write_cfg(auto=False)
        self.fail_with = "git push rejected"
        self.req("POST", "/api/web/publish")
        done = self.wait_idle()
        self.assertEqual(done["state"], "failed")
        self.assertIn("git push rejected", done["error"])

    def test_malformed_publisher_result_is_failed(self):
        self.write_cfg(auto=False)
        self.srv.publisher = lambda *a: {"ok": True}
        self.req("POST", "/api/web/publish")
        self.assertEqual(self.wait_idle()["state"], "failed")

    def test_requests_while_running_coalesce_into_one_more_run(self):
        self.write_cfg(auto=False)
        self.gate = threading.Event()
        self.req("POST", "/api/web/publish")
        for _ in range(3):
            self.req("POST", "/api/web/publish")
        self.gate.set()
        done = self.wait_idle()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(done["snapshot_id"], "snap2")


class AutoHook(WebCase):
    def test_session_end_publishes_when_enabled_and_auto(self):
        self.write_cfg()
        self.assertEqual(self.req("POST", "/api/event", test_server.event_of("session_start"))[0], 200)
        self.assertEqual(self.req("POST", "/api/event", test_server.event_of("session_end"))[0], 200)
        self.assertEqual(self.wait_idle()["state"], "ok")
        self.assertEqual(len(self.calls), 1)

    def test_no_publish_when_auto_off_or_missing_config(self):
        self.req("POST", "/api/event", test_server.event_of("session_end"))  # no config file at all
        self.write_cfg(auto=False)
        self.req("POST", "/api/event", test_server.event_of("session_end"))
        time.sleep(0.2)
        self.assertEqual(self.calls, [])

    def test_other_events_do_not_publish(self):
        self.write_cfg()
        self.req("POST", "/api/event", test_server.event_of("word"))
        time.sleep(0.2)
        self.assertEqual(self.calls, [])

    def test_import_publishes_but_reimport_does_not(self):
        self.write_cfg()
        events, prog = test_import.ImportCase.played(self)
        export = test_import.make_export(events, prog)
        self.assertEqual(self.req("POST", "/api/import", export)[0], 200)
        self.wait_idle()
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.req("POST", "/api/import", export)[1]["already_imported"])
        time.sleep(0.2)
        self.assertEqual(len(self.calls), 1)

    def test_rejected_import_does_not_publish(self):
        self.write_cfg()
        self.req("POST", "/api/import", {"format": "x"})
        time.sleep(0.2)
        self.assertEqual(self.calls, [])


class TempDataDir(unittest.TestCase):
    def test_temp_data_dir_never_publishes_by_default(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            srv = server.make_server(Path(d) / "data", 0)
            try:
                self.assertIsNone(srv.web_config_path)
                self.assertEqual(server.web_view(srv)["state"], "disabled")
            finally:
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
