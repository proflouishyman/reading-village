#!/usr/bin/env python3
"""Local server for the reading village game (Python stdlib only).

Serves app/ at /, stories/ at /stories/, and the JSON API described in
docs/design.md. Validation is strict: a bad field is a 400 naming the field;
nothing is coerced or defaulted.
"""
import argparse
import copy
import json
import os
import random
import re
import socket
import sys
import tempfile
import threading
import webbrowser
from collections import Counter
from urllib.parse import parse_qs, urlsplit
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import minecraft_bridge as mcb

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
STORIES_DIR = ROOT / "stories"
MC_CONFIG = ROOT / "config" / "minecraft.json"
FAMILY_CONFIG = ROOT / "config" / "family.json"  # the one place a parent personalizes (docs/family.md)
CRAFT_WORDS_FILE = APP_DIR / "data" / "craft_words.json"
LEVELS_FILE = APP_DIR / "data" / "levels.json"  # per-game level thresholds (also read by app/js/levels.js)


# --- config/family.json (the one personalization file; the client reads it at /data/family.json) -----
FAMILY_REQUIRED = {"child": dict, "village_name": str, "home_grown_up": str, "away_label": str}
FAMILY_CHILD_REQUIRED = {"name": str}
# Optional fields: none yet. When one is added, document its default in docs/family.md and list it here as
# {name: type}; an absent optional field then means that documented default, anything else unknown still fails.
FAMILY_OPTIONAL = {}
FAMILY_CHILD_OPTIONAL = {}


class FamilyConfigError(Exception):
    """config/family.json is missing, unreadable or invalid. The message names the file and the field."""


def _family_check(obj, required, optional, where, path):
    """Validate one object level: no unknown key, every required key present, exact types, strings non-empty."""
    if not isinstance(obj, dict):
        raise FamilyConfigError(f"{path}: {where or 'the file'} must be a JSON object")
    pre = f"{where}." if where else ""
    for k in obj:
        if k not in required and k not in optional and not (not where and k == "v"):
            raise FamilyConfigError(f"{path}: unknown field {pre}{k}")
    for k, t in required.items():
        if k not in obj:
            raise FamilyConfigError(f"{path}: missing required field {pre}{k}")
    for k, t in {**required, **optional}.items():
        if k in obj and (type(obj[k]) is not t or (t is str and not obj[k].strip())):
            raise FamilyConfigError(f"{path}: {pre}{k} must be a {'non-empty string' if t is str else 'JSON object'}")


def load_family_config(path=None):
    """config/family.json -> validated dict {"v":1, "child":{"name"}, "village_name", "home_grown_up", "away_label"}.
    Strict and loud: a missing file, bad JSON, unknown key, wrong type or missing required key raises
    FamilyConfigError naming the field. Nothing is defaulted. app/js/family.js loadFamily applies the same rules."""
    path = Path(path or FAMILY_CONFIG)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise FamilyConfigError(f"{path}: cannot read: {e}") from None
    _family_check(cfg, FAMILY_REQUIRED, FAMILY_OPTIONAL, "", path)
    if cfg.get("v") != 1 or type(cfg.get("v")) is not int:
        raise FamilyConfigError(f"{path}: v must be the integer 1")
    _family_check(cfg["child"], FAMILY_CHILD_REQUIRED, FAMILY_CHILD_OPTIONAL, "child", path)
    return cfg

# --- Contract constants (mirrored in app/js/rules.js; keep in sync) --------
LETTERS = list("bdpqmwnu")
RESULTS = ("correct", "assisted", "miss")
TRACKS = ("smallcaps", "lowercase")
INVENTORY_KEYS = ("coal", "iron", "gold", "diamond", "wood", "stone", "emerald")
BLOCKS = ("wood", "stone", "door", "torch", "pig", "bed", "chest")
FONTS = ("opendyslexic", "system")
LOWERCASE_TRACK = ("off", "on")
SOUND = ("on", "off")
MAX_PERCENT = 100
GRID_W, GRID_H = 12, 8
MAX_BODY = 1_000_000
IMPORT_MAX_BODY = 50_000_000  # an export file carries every event made at Mom's since the base snapshot
WEB_CONFIG = ROOT / "config" / "web.json"
RESET_PHRASE = "RESET"

DEFAULT_PROGRESS = {
    "v": 1,
    "rev": 0,
    "active_letters": ["b", "d"],
    "letter_stats": {},
    "inventory": {k: 0 for k in INVENTORY_KEYS},
    "house": [],
    "stories": {},
    "settings": {"font": "system", "lowercase_track": "off", "lowercase_percent": 0, "sound": "on"},
    # A fresh (or just reset) progress starts the promotion ladder explicitly at 0 spent, so a reset never has to
    # consult the append-only history to know where the current era began (see village_spent).
    "village": {"unlocked": [], "bells_spent": 0, "emeralds_spent": 0, "levels": {}},
}

# type -> (required fields, optional fields), beyond the base v/ts/session_id/type
EVENT_FIELDS = {
    "session_start": ((), ()),
    "session_end": ((), ()),
    "card": (("track", "item", "result"), ("level",)),
    "match": (("item", "result", "chosen"), ("level",)),
    "word": (("track", "item", "result"), ("level",)),
    "story_page": (("track", "story_id", "page"), ()),
    "story_done": (("track", "story_id"), ()),
    "tricky_word": (("item", "story_id"), ("track", "percent")),
    "swap_page": (("track", "story_id", "page", "percent"), ()),
    "swap_done": (("track", "story_id", "percent"), ()),
    "block_placed": (("cell", "block"), ()),
    "craft": (("track", "item", "result"), ("level",)),
    "adventure_done": (("adventure",), ()),
}
ADVENTURES = ("smallcaps", "lowercase")  # which "Start today's adventure" sequence was finished
STREAK_LEN = 10  # independent-correct answers in a row (one session) that earn the streak10 surprise
STREAK_TYPES = ("card", "match", "word")
TID = re.compile(r"t\d{6,}")  # treasure id: t000001, never reused (also checked against the delivery ledger)
TREASURE_STATUSES = ("kept", "sent")
TID_COUNTER_FILE = "treasure_counter.json"  # data/: {"v":1,"last":N}, the highest treasure number ever issued
HISTORY_FILE = "rewards_history.jsonl"  # data/: append-only master list (minecraft_bridge.History)
EVENT_SUMMARY_KEYS = ("type", "ts", "session_id", "track", "item", "story_id", "adventure", "result", "block")
DEFAULT_SERVER_OWNED = {"village": {"unlocked": [], "bells_spent": 0}, "treasure": []}  # what a missing key reads as
VILLAGER_LEVEL_FIELD_MAX = 99  # generic bound on a villager level in progress.json; the real top comes from config
ARCHIVE_STAMP = re.compile(r"(\d{8}-\d{6})(-\d+)?")  # data/archive/<YYYYMMDD-HHMMSS>[-n], made by reset_progress
INITIAL_LETTERS = len(DEFAULT_PROGRESS["active_letters"])  # letters he starts with; each one beyond counts as "mastered"
CRAFT_RESULTS = ("correct", "assisted")  # a craft is never a miss
CRAFT_WORD = re.compile(r"[A-Z]{3,10}")  # the crafted word (from app/data/craft_words.json), capitals
# Minigame levels (docs/design.md "Levels"). Event type -> the game whose level it counts toward. Levels are DERIVED
# from events (derive_levels), never stored; app/data/levels.json holds the thresholds.
LEVEL_GAMES = ("craft", "blocks", "mine", "match")
EVENT_GAME = {"craft": "craft", "word": "blocks", "card": "mine", "match": "match"}
LEVEL_FIELD_MAX = 99  # generic bound on any "level" field; the per-game max comes from levels.json (checked in the handlers)
LEVEL_SURPRISE_TIER = "rare"  # tier of the once-per-game-and-level surprise (config tiers.rare)
BASE_FIELDS = ("v", "ts", "session_id", "type")


class ValidationError(ValueError):
    """Raised with a message that names the offending field."""


# --- Validation helpers -----------------------------------------------------
def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _is_str(x):
    return isinstance(x, str) and x != ""


def _check(cond, field, msg):
    if not cond:
        raise ValidationError(f"{field}: {msg}")


def _check_keys(obj, field, required, optional=()):
    """Object must be a dict with exactly the required keys plus any allowed optional ones."""
    _check(isinstance(obj, dict), field or "body", "must be an object")
    for k in required:
        _check(k in obj, f"{field}.{k}" if field else k, "is required")
    for k in obj:
        _check(k in required or k in optional, f"{field}.{k}" if field else k, "unknown field")


def validate_event(ev):
    """Validate one event against the table in docs/design.md. Raises ValidationError."""
    _check_keys(ev, "", BASE_FIELDS, tuple(sum((list(r + o) for r, o in EVENT_FIELDS.values()), [])))
    _check(ev["v"] == 1 and _is_int(ev["v"]), "v", "must be the integer 1")
    _check(isinstance(ev["type"], str) and ev["type"] in EVENT_FIELDS, "type",
           f"must be one of {sorted(EVENT_FIELDS)}")
    required, optional = EVENT_FIELDS[ev["type"]]
    for k in ev:
        _check(k in BASE_FIELDS or k in required or k in optional, k,
               f"not allowed for type {ev['type']}")
    for k in required:
        _check(k in ev, k, f"is required for type {ev['type']}")
    _check(_is_str(ev["session_id"]), "session_id", "must be a non-empty string")
    _check(isinstance(ev["ts"], str), "ts", "must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(ev["ts"])
    except ValueError:
        raise ValidationError("ts: not a valid ISO-8601 timestamp") from None
    _check(parsed.tzinfo is not None, "ts", "must include a UTC offset")
    if "track" in ev:
        _check(ev["track"] in TRACKS, "track", f"must be one of {list(TRACKS)}")
    for k in ("item", "chosen", "story_id"):
        if k in ev:
            _check(_is_str(ev[k]), k, "must be a non-empty string")
    if "result" in ev:
        _check(ev["result"] in RESULTS, "result", f"must be one of {list(RESULTS)}")
    if "level" in ev:
        _check(_is_int(ev["level"]) and 1 <= ev["level"] <= LEVEL_FIELD_MAX, "level", f"must be an integer 1..{LEVEL_FIELD_MAX}")
    if "page" in ev:
        _check(_is_int(ev["page"]) and ev["page"] >= 0, "page", "must be an integer >= 0")
    if "percent" in ev:
        _check(_is_int(ev["percent"]) and 0 <= ev["percent"] <= MAX_PERCENT, "percent", "must be an integer 0..100")
    if ev["type"] in ("swap_page", "swap_done"):
        _check(ev["track"] == "lowercase", "track", f"must be \"lowercase\" for {ev['type']}")
    if ev["type"] in ("card", "match"):
        _check(ev["item"] in LETTERS, "item", f"must be one of {LETTERS} for type {ev['type']}")
    if ev["type"] == "craft":
        _check(ev["track"] == "smallcaps", "track", "must be \"smallcaps\" for craft")
        _check(ev["result"] in CRAFT_RESULTS, "result", f"must be one of {list(CRAFT_RESULTS)} for craft")
        _check(CRAFT_WORD.fullmatch(ev["item"]) is not None, "item", "must be a 3 to 10 letter capital word for craft")
    if "adventure" in ev:
        _check(ev["adventure"] in ADVENTURES, "adventure", f"must be one of {list(ADVENTURES)}")
    if "cell" in ev:
        _check_cell(ev["cell"], "cell")
    if "block" in ev:
        _check(ev["block"] in BLOCKS, "block", f"must be one of {list(BLOCKS)}")


def _check_cell(cell, field):
    ok = (isinstance(cell, list) and len(cell) == 2 and all(_is_int(c) for c in cell)
          and 0 <= cell[0] < GRID_W and 0 <= cell[1] < GRID_H)
    _check(ok, field, f"must be [x, y] integers with 0<=x<{GRID_W}, 0<=y<{GRID_H}")


def validate_progress(p):
    """Validate the full progress.json shape. Raises ValidationError."""
    _check_keys(p, "", ("v", "active_letters", "letter_stats", "inventory", "house", "stories", "settings"),
                ("rev", "crafted", "village", "treasure"))
    _check(p["v"] == 1 and _is_int(p["v"]), "v", "must be the integer 1")
    # rev is optional on read: a file without it reads as 0 (documented default, docs/design.md).
    _check(_is_int(p.get("rev", 0)) and p.get("rev", 0) >= 0, "rev", "must be an integer >= 0")

    al = p["active_letters"]
    _check(isinstance(al, list) and len(al) > 0, "active_letters", "must be a non-empty list")
    for i, l in enumerate(al):
        _check(l in LETTERS, f"active_letters[{i}]", f"must be one of {LETTERS}")
    _check(len(set(al)) == len(al), "active_letters", "must not repeat letters")

    ls = p["letter_stats"]
    _check(isinstance(ls, dict), "letter_stats", "must be an object")
    for l, st in ls.items():
        f = f"letter_stats.{l}"
        _check(l in LETTERS, f, f"key must be one of {LETTERS}")
        _check_keys(st, f, ("recent", "total_correct", "total_tries"))
        r = st["recent"]
        _check(isinstance(r, list) and len(r) <= 10, f"{f}.recent", "must be a list of at most 10 results")
        for i, x in enumerate(r):
            _check(x in RESULTS, f"{f}.recent[{i}]", f"must be one of {list(RESULTS)}")
        for k in ("total_correct", "total_tries"):
            _check(_is_int(st[k]) and st[k] >= 0, f"{f}.{k}", "must be an integer >= 0")
        _check(st["total_correct"] <= st["total_tries"], f"{f}.total_correct", "must not exceed total_tries")

    inv = p["inventory"]
    _check_keys(inv, "inventory", INVENTORY_KEYS)
    for k in INVENTORY_KEYS:
        _check(_is_int(inv[k]) and inv[k] >= 0, f"inventory.{k}", "must be an integer >= 0")

    house = p["house"]
    _check(isinstance(house, list), "house", "must be a list")
    seen = set()
    for i, b in enumerate(house):
        f = f"house[{i}]"
        _check_keys(b, f, ("x", "y", "block"))
        _check_cell([b["x"], b["y"]], f"{f}.x/y")
        _check(b["block"] in BLOCKS, f"{f}.block", f"must be one of {list(BLOCKS)}")
        _check((b["x"], b["y"]) not in seen, f, "cell is used twice")
        seen.add((b["x"], b["y"]))

    st = p["stories"]
    _check(isinstance(st, dict), "stories", "must be an object")
    for sid, s in st.items():
        f = f"stories.{sid}"
        _check(sid != "", "stories", "story id must be non-empty")
        _check_keys(s, f, ("smallcaps_done", "lowercase_done", "resume_page"))
        for k in ("smallcaps_done", "lowercase_done"):
            _check(isinstance(s[k], bool), f"{f}.{k}", "must be a boolean")
        _check(_is_int(s["resume_page"]) and s["resume_page"] >= 0, f"{f}.resume_page", "must be an integer >= 0")

    # crafted is optional: missing reads as {} (documented default); word (capitals) -> times crafted, >= 1.
    crafted = p.get("crafted", {})
    _check(isinstance(crafted, dict), "crafted", "must be an object")
    for word, n in crafted.items():
        _check(CRAFT_WORD.fullmatch(word) is not None, f"crafted.{word}", "key must be a 3 to 10 letter capital word")
        _check(_is_int(n) and n >= 1, f"crafted.{word}", "must be an integer >= 1")

    # village is optional: missing reads as {"unlocked": [], "bells_spent": 0}. Server-owned (see do_PUT).
    # emeralds_spent (total spent this era; absent in older files = derived once from the history, see village_spent)
    # and levels (profession id -> 0..top; absent = every villager Novice) are optional for the same reason.
    if "village" in p:
        v = p["village"]
        _check_keys(v, "village", ("unlocked", "bells_spent"), ("emeralds_spent", "levels"))
        _check(isinstance(v["unlocked"], list) and all(_is_str(x) for x in v["unlocked"]), "village.unlocked",
               "must be a list of profession ids")
        _check(len(set(v["unlocked"])) == len(v["unlocked"]), "village.unlocked", "must not repeat a profession")
        _check(_is_int(v["bells_spent"]) and v["bells_spent"] >= 0, "village.bells_spent", "must be an integer >= 0")
        if "emeralds_spent" in v:
            _check(_is_int(v["emeralds_spent"]) and v["emeralds_spent"] >= 0, "village.emeralds_spent",
                   "must be an integer >= 0")
        if "levels" in v:
            _check(isinstance(v["levels"], dict), "village.levels", "must be an object")
            for pid, lv in v["levels"].items():
                _check(pid in v["unlocked"], f"village.levels.{pid}", "only an unlocked villager can have a level")
                _check(_is_int(lv) and 0 <= lv <= VILLAGER_LEVEL_FIELD_MAX, f"village.levels.{pid}",
                       f"must be an integer 0..{VILLAGER_LEVEL_FIELD_MAX}")

    # treasure is optional: missing reads as []. Server-owned (see do_PUT); entries are never removed.
    if "treasure" in p:
        _check(isinstance(p["treasure"], list), "treasure", "must be a list")
        tids = set()
        for i, t in enumerate(p["treasure"]):
            f = f"treasure[{i}]"
            _check_keys(t, f, ("tid", "label", "sprite", "items", "source", "status"), ("event",))
            _check(isinstance(t["tid"], str) and TID.fullmatch(t["tid"]) is not None, f"{f}.tid", "must look like t000001")
            _check(t["tid"] not in tids, f"{f}.tid", "duplicate treasure id")
            tids.add(t["tid"])
            _check(_is_str(t["label"]) and _is_str(t["sprite"]), f"{f}.label/sprite", "must be non-empty strings")
            try:
                mcb.validate_items(t["items"], f"{f}.items")
            except mcb.ConfigError as e:
                raise ValidationError(str(e)) from None
            _check_keys(t["source"], f"{f}.source", ("kind", "ref"))
            _check(t["source"]["kind"] in mcb.SOURCE_KINDS, f"{f}.source.kind", f"must be one of {list(mcb.SOURCE_KINDS)}")
            _check(_is_str(t["source"]["ref"]), f"{f}.source.ref", "must be a non-empty string")
            _check(t["status"] in TREASURE_STATUSES, f"{f}.status", f"must be one of {list(TREASURE_STATUSES)}")
            # event (optional, absent for shop/unlock treasure): which accepted event created this entry, so a retried
            # event cannot create it twice (see event_key)
            _check("event" not in t or _is_str(t["event"]), f"{f}.event", "must be a non-empty string")

    se = p["settings"]
    # lowercase_track is optional: a file without it reads as "off" (documented default, docs/design.md).
    _check_keys(se, "settings", ("font",), ("lowercase_track", "lowercase_percent", "sound", "level_override"))
    _check(se.get("lowercase_track", "off") in LOWERCASE_TRACK, "settings.lowercase_track",
           f"must be one of {list(LOWERCASE_TRACK)}")
    # lowercase_percent is optional: missing reads as 0 (documented default).
    pct = se.get("lowercase_percent", 0)
    _check(_is_int(pct) and 0 <= pct <= MAX_PERCENT, "settings.lowercase_percent", "must be an integer 0..100")
    # sound is optional: missing reads as "on" (documented default).
    _check(se.get("sound", "on") in SOUND, "settings.sound", f"must be one of {list(SOUND)}")
    _check(se["font"] in FONTS, "settings.font", f"must be one of {list(FONTS)}")
    # level_override is optional: missing = no override (levels are derived). Dad's per-game level; the per-game max is
    # checked against levels.json by check_level_override (the PUT handler).
    lo = se.get("level_override", {})
    _check(isinstance(lo, dict), "settings.level_override", "must be an object {game: level}")
    for g, n in lo.items():
        _check(g in LEVEL_GAMES, f"settings.level_override.{g}", f"game must be one of {list(LEVEL_GAMES)}")
        _check(_is_int(n) and 1 <= n <= LEVEL_FIELD_MAX, f"settings.level_override.{g}", f"must be an integer 1..{LEVEL_FIELD_MAX}")


# --- Storage ---------------------------------------------------------------
def write_json_atomic(path, obj):
    """Write obj as JSON to path via temp file + os.replace, so a crash never leaves a half file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # Persist the rename itself: without a directory fsync a power cut can lose the new name.
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_progress(data_dir):
    """Read and validate progress.json; a missing rev is reported as 0. Raises ValueError/OSError."""
    p = json.loads((Path(data_dir) / "progress.json").read_text(encoding="utf-8"))
    validate_progress(p)
    p.setdefault("rev", 0)
    return p


def read_events(data_dir):
    """Read events.jsonl, validating every line like POST does. The first bad line raises
    ValidationError naming its line number and field; nothing is skipped."""
    ef = Path(data_dir) / "events.jsonl"
    events = []
    if not ef.exists():
        return events
    for n, line in enumerate(ef.read_text(encoding="utf-8").splitlines(), 1):
        try:
            ev = json.loads(line)
        except ValueError:
            raise ValidationError(f"events.jsonl line {n}: not valid JSON") from None
        try:
            validate_event(ev)
        except ValidationError as e:
            raise ValidationError(f"events.jsonl line {n}: {e}") from None
        events.append(ev)
    return events


def init_data_dir(data_dir):
    """Create data_dir and a default progress.json if missing.

    A progress.json that exists but is unreadable or invalid raises SystemExit:
    it is never overwritten.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    pf = data_dir / "progress.json"
    if not pf.exists():
        write_json_atomic(pf, DEFAULT_PROGRESS)
        return
    try:
        validate_progress(json.loads(pf.read_text(encoding="utf-8")))
    except (ValueError, OSError) as e:  # JSONDecodeError and ValidationError are ValueErrors
        raise SystemExit(
            f"REFUSING TO START: {pf} is corrupt or invalid ({e}).\n"
            f"It has NOT been touched. Fix or move it aside, then start again."
        )


class Handler(SimpleHTTPRequestHandler):
    """Static files from app/ and stories/, plus /api/*."""

    server_version = "ReadingVillage/1"

    def translate_path(self, path):
        # Map URL paths to app/ or stories/; reject anything that escapes them.
        url = path.split("?", 1)[0].split("#", 1)[0]
        if url.startswith("/stories/"):
            base, rel = STORIES_DIR, url[len("/stories/"):]
        else:
            base, rel = APP_DIR, url.lstrip("/") or "index.html"
        target = (base / rel).resolve()
        if base.resolve() not in target.parents and target != base.resolve():
            return str(base / "__forbidden__")
        return str(target)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # edits to cues/stories show on reload
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # successes are silent; errors go through log_error below

    def log_error(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}\n")

    def _json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, status, message):
        self.log_error("%s %s", status, message)
        self._json(status, {"error": message})

    def _read_json(self, limit=MAX_BODY):
        """Parse the request body as JSON, or raise ValidationError. `limit` is the largest body accepted."""
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise ValidationError("Content-Length: required") from None
        if n > limit:
            raise ValidationError("body: too large")
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ValidationError(f"body: not valid JSON ({e})") from None

    def do_GET(self):
        if self.path.split("?")[0] == "/data/family.json":  # config/ is not under app/; serve the validated copy
            return self._json(200, self.server.family)
        if self.path.split("?")[0].startswith("/api/"):
            return self._api_get()
        super().do_GET()

    def _api_get(self):
        route = self.path.split("?")[0]
        data_dir = self.server.data_dir
        try:
            if route == "/api/progress":
                return self._json(200, read_progress(data_dir))
            if route == "/api/events":
                return self._json(200, read_events(data_dir))
            if route == "/api/village":
                return self._json(200, village_view(self.server))
            if route == "/api/treasure":
                return self._json(200, treasure_view_body(self.server))
            if route == "/api/minecraft":
                return self._json(200, minecraft_view(self.server))
            if route in ("/api/history", "/api/history.csv"):
                return self._history_get(route)
            if route == "/api/web":
                return self._json(200, web_view(self.server))
        except (OSError, ValueError) as e:  # ValidationError and JSONDecodeError are ValueErrors
            return self._fail(500, f"could not read {route}: {e}")
        self._fail(404, f"no such API route: {route}")

    def _history_get(self, route):
        """GET /api/history[?kind=K] -> {"v","kind","count","lines","totals"}; GET /api/history.csv[?kind=K] -> CSV.
        An unknown kind or query parameter is a 400. Totals always cover the whole file; only `lines` is filtered."""
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        extra = sorted(set(query) - {"kind"})
        kind = query["kind"][0] if "kind" in query else None
        if extra or (kind is not None and kind not in mcb.HISTORY_KINDS) or len(query.get("kind", [])) > 1:
            return self._fail(400, f"query: only ?kind= is allowed, one of {list(mcb.HISTORY_KINDS)}")
        history = self.server.mc.history
        lines = history.read(kind)
        if route == "/api/history.csv":
            body = mcb.history_csv(lines).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="rewards_history.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(200, {"v": mcb.HISTORY_VERSION, "kind": kind, "count": len(lines), "lines": lines,
                         "totals": mcb.history_totals(history.read())})

    def do_PUT(self):
        if self.path != "/api/progress":
            return self._fail(404, f"no such API route: {self.path}")
        try:
            p = self._read_json()
            # Optional `cause`: the full event this save belongs to (the client saves progress BEFORE it posts the
            # event, so the server cannot infer the cause). It is history provenance only and is never stored in
            # progress.json. A malformed cause is a 400, never ignored.
            cause = p.pop("cause", None) if isinstance(p, dict) else None
            if cause is not None:
                validate_event(cause)
            validate_progress(p)
            check_level_override(p, self.server.levels)
            _check("rev" in p, "rev", "is required: the rev this save was based on")
        except ValidationError as e:
            return self._fail(400, str(e))
        # Optimistic concurrency: the stored rev must equal the rev the client based this save on.
        # Compare-and-write happen under one lock so two racing PUTs cannot both win.
        try:
            with self.server.write_lock:
                current = read_progress(self.server.data_dir)
                if p["rev"] != current["rev"]:
                    return self._fail(409, f"rev mismatch: saved progress is at rev {current['rev']}, "
                                           f"this save was based on rev {p['rev']}")
                # village and treasure change only through the village/shop/treasure endpoints and accepted events;
                # a client that saves a different value would undo an unlock, a purchase or a "sent" mark.
                for key in ("village", "treasure"):
                    if p.get(key, DEFAULT_SERVER_OWNED[key]) != current.get(key, DEFAULT_SERVER_OWNED[key]):
                        return self._fail(400, f"{key}: is owned by the server and cannot be changed by a save")
                p["rev"] = current["rev"] + 1
                record_client_changes(self.server, current, p, cause)
                write_json_atomic(self.server.data_dir / "progress.json", p)
        except (OSError, ValueError) as e:
            return self._fail(500, f"could not update progress.json: {e}")
        self._json(200, p)

    def do_POST(self):
        if self.path == "/api/reset":
            return self._reset()
        if self.path == "/api/shop/buy":
            return self._shop(buy=True)
        if self.path == "/api/shop/trade":
            return self._shop(buy=False)
        if self.path == "/api/village/unlock":
            return self._unlock()
        if self.path == "/api/village/promote":
            return self._promote()
        if self.path == "/api/treasure/send":
            return self._send()
        if self.path == "/api/import":
            return self._import()
        if self.path == "/api/web/publish":
            return self._web_publish()
        if self.path != "/api/event":
            return self._fail(404, f"no such API route: {self.path}")
        try:
            ev = self._read_json()
            with self.server.write_lock:
                body = accept_event(self.server, ev)
        except ValidationError as e:
            return self._fail(400, str(e))
        except (OSError, ValueError) as e:  # LedgerError, a corrupt events.jsonl read, disk errors
            return self._fail(500, f"could not record the event: {e}")
        if ev["type"] == "session_end":
            maybe_auto_publish(self.server)
        self._json(200, body)

    def _import(self):
        """POST /api/import <export file JSON>: replay Mom's-house play into the real record (docs/away-from-home.md §5).
        400 names the bad field or event index and nothing has changed; 200 carries the counts."""
        try:
            export = self._read_json(IMPORT_MAX_BODY)
            with self.server.write_lock:
                result = import_export(self.server, export)
        except ValidationError as e:
            return self._fail(400, str(e))
        except (OSError, ValueError) as e:  # a corrupt data file, a disk error (everything was rolled back)
            return self._fail(500, f"import failed and was rolled back (nothing changed): {e}")
        if not result["already_imported"]:
            maybe_auto_publish(self.server)
        self._json(200, result)

    def _web_publish(self):
        """POST /api/web/publish: start a snapshot publish now (the Dashboard's Update button). 409 when web
        publishing is not configured or switched off; otherwise 200 with the status (state "running")."""
        try:
            cfg = load_web_config(self.server)
        except ValidationError as e:
            return self._fail(409, f"web publishing is not available: {e}")
        if not cfg["enabled"]:
            return self._fail(409, "web publishing is not available: config/web.json has enabled=false")
        request_publish(self.server)
        self._json(200, web_view(self.server))

    def _shop(self, buy):
        """POST /api/shop/buy {"offer_id"} or /api/shop/trade {"trade_id"}. 400 unknown id or bad body, 409 not
        enough emeralds / villager not unlocked / village level too low. The server prices everything from config: the
        client sends only an id."""
        key = "offer_id" if buy else "trade_id"
        try:
            body = self._read_json()
            _check(isinstance(body, dict) and set(body) == {key}, "body", f'must be exactly {{"{key}": "..."}}')
            _check(_is_str(body[key]), key, "must be a non-empty string")
            table = self.server.mc.offers if buy else self.server.mc.trades
            _check(body[key] in table, key, f"unknown {'offer' if buy else 'trade'} {body[key]!r}")
        except ValidationError as e:
            return self._fail(400, str(e))
        try:
            with self.server.write_lock:
                result = shop_buy(self.server, body[key]) if buy else shop_trade(self.server, body[key])
        except ShopRefused as e:
            return self._fail(409, str(e))
        except (OSError, ValueError) as e:
            return self._fail(500, f"shop failed (see message; check the wallet): {e}")
        self._json(200, result)

    def _unlock(self):
        """POST /api/village/unlock {"profession","pay"}: 400 bad body, unknown or already unlocked; 409 no bell, not
        enough emeralds, or the Wandering Trader's requirement unmet. The first unlock is free whatever `pay` is."""
        try:
            body = self._read_json()
            _check(isinstance(body, dict) and set(body) == {"profession", "pay"}, "body",
                   'must be exactly {"profession": "...", "pay": "bell"|"emeralds"}')
            _check(body["pay"] in mcb.PAY_CHOICES, "pay", f"must be one of {list(mcb.PAY_CHOICES)}")
            _check(isinstance(body["profession"], str) and body["profession"] in self.server.mc.professions,
                   "profession", f"unknown profession {body['profession']!r}")
        except ValidationError as e:
            return self._fail(400, str(e))
        try:
            with self.server.write_lock:
                result = village_unlock(self.server, body["profession"], body["pay"])
        except ValidationError as e:
            return self._fail(400, str(e))
        except ShopRefused as e:
            return self._fail(409, str(e))
        except (OSError, ValueError) as e:
            return self._fail(500, f"unlock failed (see message; check progress.json): {e}")
        self._json(200, result)

    def _promote(self):
        """POST /api/village/promote {"profession"}: 400 bad body or unknown profession; 409 not unlocked, already
        Master, or no promotion available. Checked and saved under the write lock, so a double tap earns one."""
        try:
            body = self._read_json()
            _check(isinstance(body, dict) and set(body) == {"profession"}, "body", 'must be exactly {"profession": "..."}')
            _check(isinstance(body["profession"], str) and body["profession"] in self.server.mc.professions,
                   "profession", f"unknown profession {body['profession']!r}")
        except ValidationError as e:
            return self._fail(400, str(e))
        try:
            with self.server.write_lock:
                result = village_promote(self.server, body["profession"])
        except ShopRefused as e:
            return self._fail(409, str(e))
        except (OSError, ValueError) as e:
            return self._fail(500, f"promotion failed (see message; check progress.json): {e}")
        self._json(200, result)

    def _send(self):
        """POST /api/treasure/send {"tids":[...]}: one delivery per tid; 400 bad body / unknown tid, 409 a tid was
        already sent (or delivery is disabled). Nothing is changed unless every tid is valid."""
        try:
            body = self._read_json()
            _check(isinstance(body, dict) and set(body) == {"tids"}, "body", 'must be exactly {"tids": ["t000001", ...]}')
            tids = body["tids"]
            _check(isinstance(tids, list) and tids and all(isinstance(t, str) for t in tids), "tids",
                   "must be a non-empty list of treasure ids")
            _check(len(set(tids)) == len(tids), "tids", "must not repeat a treasure id")
        except ValidationError as e:
            return self._fail(400, str(e))
        try:
            with self.server.write_lock:
                result = treasure_send(self.server, tids)
        except ValidationError as e:
            return self._fail(400, str(e))
        except ShopRefused as e:
            return self._fail(409, str(e))
        except (OSError, ValueError) as e:
            return self._fail(500, f"send failed (see message; check data/minecraft_deliveries.json): {e}")
        self._json(200, result)

    def _reset(self):
        """POST /api/reset {"confirm": "RESET"}: archive progress.json and events.jsonl, start fresh. Never deletes."""
        try:
            body = self._read_json()
            _check(isinstance(body, dict) and set(body) == {"confirm"}, "body", 'must be exactly {"confirm": "RESET"}')
            _check(body["confirm"] == RESET_PHRASE, "confirm", f"must be the exact text {RESET_PHRASE}")
        except ValidationError as e:
            return self._fail(400, str(e))
        try:
            with self.server.write_lock:
                archived = reset_progress(self.server.data_dir)
        except (OSError, ValueError) as e:
            return self._fail(500, f"could not reset progress (nothing was deleted): {e}")
        self._json(200, {"archived_to": str(archived)})


def reset_progress(data_dir):
    """Move progress.json and events.jsonl into data/archive/<YYYYMMDD-HHMMSS>/ and write fresh default progress.

    Nothing is deleted. The fresh file carries rev = old rev + 1, so a tab still holding the old progress gets a
    409 on its next save instead of silently overwriting the reset. If any step fails, files already moved are
    moved back and the error is raised. Caller holds the write lock. Returns the archive directory.
    """
    data_dir = Path(data_dir)
    pf, ef = data_dir / "progress.json", data_dir / "events.jsonl"
    old_rev = json.loads(pf.read_text(encoding="utf-8")).get("rev", 0)  # raises (loudly) if unreadable
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = data_dir / "archive" / stamp
    n = 1
    while dest.exists():  # two resets in one second must not collide or overwrite
        n += 1
        dest = data_dir / "archive" / f"{stamp}-{n}"
    dest.mkdir(parents=True)
    moved = []
    try:
        for src in (ef, pf):
            if src.exists():
                os.replace(src, dest / src.name)
                moved.append(src)
        fresh = copy.deepcopy(DEFAULT_PROGRESS)
        fresh["rev"] = old_rev + 1
        write_json_atomic(pf, fresh)
    except BaseException:
        for src in moved:
            os.replace(dest / src.name, src)
        raise
    return dest


class ShopRefused(Exception):
    """A valid request that cannot be done right now (not enough resources, locked, disabled): HTTP 409."""


class MinecraftState:
    """The validated config, the delivery ledger and (once started) the delivery worker, shared by all servers."""

    def __init__(self, cfg, ledger, craft_sprites, history):
        self.cfg, self.ledger = cfg, ledger
        self.history = history  # minecraft_bridge.History over data/rewards_history.jsonl (append-only)
        self.craft_sprites = craft_sprites  # craft word -> sprite name, from app/data/craft_words.json
        self.professions = {p["id"]: p for p in cfg["village"]["professions"]}
        self.offers = {o["id"]: (p, o) for p in cfg["village"]["professions"] for o in p["offers"]}
        self.trades = {t["id"]: t for t in cfg["trades"]}
        self.rng = random.Random()
        self.worker = None


PATTERN_LEVEL = {"cvc": 1, "blend": 2, "digraph": 3, "silent_e": 4, "vowel_team": 5, "two_syllable": 6}  # phonics ladder


def load_craft_words():
    """{word: sprite} the game ships (app/data/craft_words.json, {"v":2,"words":[{word,level,pattern,sprite}]}); every
    word must have a configured real item (checked by mcb.load_config). Any contract violation raises ValueError."""
    f = CRAFT_WORDS_FILE
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{f}: could not read ({e})") from None
    if not isinstance(obj, dict) or obj.get("v") != 2 or not isinstance(obj.get("words"), list):
        raise ValueError(f'{f}: must be {{"v":2,"words":[...]}}')
    out = {}
    for i, w in enumerate(obj["words"]):
        at = f"{f}: words[{i}]"
        if not isinstance(w, dict) or set(w) != {"word", "level", "pattern", "sprite"}:
            raise ValueError(f"{at}: must have exactly word, level, pattern, sprite")
        if not isinstance(w["word"], str) or CRAFT_WORD.fullmatch(w["word"]) is None:
            raise ValueError(f"{at}: word must be 3 to 10 capital letters")
        if w["pattern"] not in PATTERN_LEVEL or w["level"] != PATTERN_LEVEL[w["pattern"]] or isinstance(w["level"], bool):
            raise ValueError(f"{at}: {w['word']} pattern/level must be one of {PATTERN_LEVEL}")
        if not isinstance(w["sprite"], str) or not w["sprite"] or w["word"] in out:
            raise ValueError(f"{at}: {w['word']} needs a sprite and must not repeat")
        out[w["word"]] = w["sprite"]
    return out


def load_levels():
    """app/data/levels.json -> {game: {"max","window","need"}}. Strict: exactly the four games, integers, need <= window.
    Raises ValueError naming the file and field."""
    f = LEVELS_FILE
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{f}: could not read ({e})") from None
    if not isinstance(obj, dict) or set(obj) != {"v", "games"} or obj["v"] != 1 or not isinstance(obj["games"], dict):
        raise ValueError(f'{f}: must be {{"v":1,"games":{{...}}}}')
    if set(obj["games"]) != set(LEVEL_GAMES):
        raise ValueError(f"{f}: games must be exactly {list(LEVEL_GAMES)}")
    for g, c in obj["games"].items():
        if not isinstance(c, dict) or set(c) != {"max", "window", "need"} or not all(_is_int(c[k]) and c[k] >= 1 for k in c):
            raise ValueError(f"{f}: games.{g} must be {{max, window, need}} integers >= 1")
        if c["need"] > c["window"] or c["max"] > LEVEL_FIELD_MAX:
            raise ValueError(f"{f}: games.{g}: need must not exceed window, max must be <= {LEVEL_FIELD_MAX}")
    return obj["games"]


def derive_levels(events, levels):
    """Per-game level state DERIVED from `events` (never stored). level = 1 + consecutive level-ups; a level-up happens
    when at least `window` attempts were made AT the current level (events whose `level` equals it; no `level` counts as
    1) and at least `need` of the last `window` of them are "correct" (assisted and miss are not independent). Never
    demotes; the count restarts at each new level; no level-up beyond `max`. Returns {game: {"level","max","window",
    "need","attempts","independent"}} where attempts/independent describe the last `window` attempts at that level
    (`attempts` is the total at the level, `independent` counts the last `window` of them)."""
    out = {}
    for g, c in levels.items():
        level, results, attempts = 1, [], 0
        for ev in events:
            if EVENT_GAME.get(ev["type"]) != g or ev.get("level", 1) != level:
                continue
            results = (results + [ev["result"]])[-c["window"]:]
            attempts += 1
            if level < c["max"] and attempts >= c["window"] and results.count("correct") >= c["need"]:
                level, results, attempts = level + 1, [], 0
        out[g] = {"level": level, **c, "attempts": attempts, "independent": results.count("correct")}
    return out


def check_level_override(progress, levels):
    """Dad's level_override values must not exceed the game's max (levels.json). Raises ValidationError."""
    for g, n in progress["settings"].get("level_override", {}).items():
        _check(n <= levels[g]["max"], f"settings.level_override.{g}", f"must be at most {levels[g]['max']} (levels.json)")


def make_server(data_dir, port=0, host="127.0.0.1", mc_config=None, family_config=None):
    """Initialise data_dir (may SystemExit on corrupt progress) and return an unstarted server.

    Loads and validates config/minecraft.json (mc_config overrides the path); a bad config raises
    minecraft_bridge.ConfigError. Also validates config/family.json (family_config overrides the path); a bad
    one raises FamilyConfigError, so a broken personalization file stops startup. The delivery worker is NOT started here (see start_minecraft_worker).
    """
    family = load_family_config(family_config)
    init_data_dir(data_dir)
    words = load_craft_words()
    levels = load_levels()
    cfg = mcb.load_config(mc_config or MC_CONFIG, craft_words=list(words))
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.data_dir = Path(data_dir)
    srv.write_lock = threading.Lock()
    srv.mc = MinecraftState(cfg, mcb.Ledger(srv.data_dir / "minecraft_deliveries.json", write_json_atomic), words,
                            mcb.History(srv.data_dir / HISTORY_FILE))
    srv.levels = levels
    srv.family = family  # served verbatim at /data/family.json
    # Web publishing (docs/away-from-home.md §6). Like the delivery worker, it is only live for the real data dir: a
    # temp --data-dir used by a test or tool must never push its data to the public site (tests set
    # web_config_path and publisher themselves). web_status is mutated in place, never replaced, so the ::1 twin
    # (which shares these attributes by reference) always sees the same status.
    srv.web_config_path = WEB_CONFIG if Path(data_dir).resolve() == (ROOT / "data").resolve() else None
    srv.web_status = {"state": "idle", "at": None, "snapshot_id": None, "error": None}
    srv.web_lock = threading.Lock()  # guards web_status and web_flags
    srv.web_flags = {"running": False, "again": False}  # one publish at a time; "again" coalesces later requests
    srv.publisher = real_publisher
    reconcile_sent_treasure(srv)
    return srv


def start_minecraft_worker(srv, poll=mcb.POLL_SECONDS):
    """Start the delivery thread when the config says enabled. Returns the worker or None."""
    if not srv.mc.cfg["enabled"]:
        return None
    srv.mc.worker = mcb.build_worker(srv.mc.cfg, srv.mc.ledger, poll=poll, history=srv.mc.history)
    srv.mc.worker.start()
    return srv.mc.worker


# --- Minecraft: village, treasure, surprises, shop, status ---------------------------------------------
def village_of(progress):
    """progress['village'] with the documented default for a missing key."""
    return progress.get("village", DEFAULT_SERVER_OWNED["village"])


def era_start(data_dir):
    """When the current progress era began: the newest data/archive/<YYYYMMDD-HHMMSS>[-n] stamp (a reset archives the
    old progress there; local time, as reset_progress wrote it), or None if there never was a reset. Only needed once,
    to seed emeralds_spent for a progress.json that predates the counter."""
    archive = Path(data_dir) / "archive"
    stamps = []
    if archive.is_dir():
        for d in archive.iterdir():
            m = ARCHIVE_STAMP.fullmatch(d.name)
            if m and d.is_dir():
                stamps.append(datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").astimezone())
    return max(stamps) if stamps else None


def village_spent(srv, progress):
    """Total emeralds the child has spent in the CURRENT era (shop buys + emerald unlocks). Source of truth is the
    server-owned counter progress.village.emeralds_spent, incremented in the SAME atomic progress write as the wallet
    change, so it can never disagree with what was actually taken (a history line is appended before the save and
    could outlive a failed save), and "Reset progress" zeroes it for free (the fresh progress carries 0).
    A progress.json from before the counter has no key: it is derived ONCE from the append-only history (emerald
    `spend` lines at or after era_start), and the next spend or promotion writes it back."""
    v = village_of(progress)
    if "emeralds_spent" in v:
        return v["emeralds_spent"]
    start = era_start(srv.data_dir)
    return sum(l["what"]["amount"] for l in srv.mc.history.read("spend")
               if l["what"]["resource"] == "emerald" and (start is None or datetime.fromisoformat(l["ts"]) >= start))


def village_levels(srv, progress):
    """profession id -> level for every UNLOCKED villager (a missing entry is Novice, 0). Raises if a stored level is
    beyond the configured names (a config shrunk under a saved progress)."""
    top = len(srv.mc.cfg["village"]["levels"]["names"]) - 1
    stored = village_of(progress).get("levels", {})
    for pid, lv in stored.items():
        if lv > top:
            raise ValueError(f"progress.village.levels.{pid}={lv} is beyond the configured top level {top}")
    return {pid: stored.get(pid, 0) for pid in village_of(progress)["unlocked"]}


def promotion_state(srv, progress):
    """{"earned","used","available","spent","next_at"}: earned from total emeralds spent (config promotions), used =
    sum of villager levels. available < 0 (more levels than earned) is corrupt data and raises."""
    spent = village_spent(srv, progress)
    earned = mcb.promotions_earned(srv.mc.cfg, spent)
    used = sum(village_levels(srv, progress).values())
    if used > earned:
        raise ValueError(f"progress.village.levels sum to {used} but only {earned} promotions are earned by {spent} "
                         "emeralds spent")
    return {"earned": earned, "used": used, "available": earned - used, "spent": spent,
            "next_at": mcb.next_promotion_at(srv.mc.cfg, spent)}


def treasure_of(progress):
    return progress.get("treasure", DEFAULT_SERVER_OWNED["treasure"])


def village_state(srv, progress, extra_event=None):
    """Reading points, level and bells, DERIVED from events.jsonl (+ `extra_event`, an event about to be appended)
    and from progress.active_letters (letters mastered = letters beyond the starting INITIAL_LETTERS). Never stored."""
    events = read_events(srv.data_dir)
    if extra_event is not None:
        events = events + [extra_event]
    cfg = srv.mc.cfg
    letters = max(0, len(progress["active_letters"]) - INITIAL_LETTERS)
    points = mcb.reading_points(cfg, events, letters)
    earned = mcb.bells_earned(cfg, events, points)
    spent = village_of(progress)["bells_spent"]
    return {"points": points, "level": mcb.level_for(cfg, points),
            "bells": {"earned": earned, "spent": spent, "available": earned - spent}}


def _tid_counter(srv):
    """The highest treasure number ever issued, from data/treasure_counter.json (survives "Reset progress", which
    archives the pile). A missing file is seeded once from everything that still shows a number: the pile, the
    delivery ledger and every archived progress.json. A corrupt file raises and is never overwritten."""
    path = srv.data_dir / TID_COUNTER_FILE
    if path.exists():
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
            _check_keys(c, TID_COUNTER_FILE, ("v", "last"))
            _check(c["v"] == 1 and _is_int(c["v"]) and _is_int(c["last"]) and c["last"] >= 0, TID_COUNTER_FILE,
                   'must be {"v": 1, "last": integer >= 0}')
        except ValueError as e:
            raise ValueError(f"{path} is invalid ({e}); it was not touched") from None
        return c["last"]
    nums = [int(d["source"]["ref"][1:]) for d in srv.mc.ledger.deliveries() if TID.fullmatch(d["source"]["ref"])]
    for old in sorted((srv.data_dir / "archive").glob("*/progress.json")):
        try:
            nums += [int(t["tid"][1:]) for t in json.loads(old.read_text(encoding="utf-8")).get("treasure", [])]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise ValueError(f"cannot read {old} to seed the treasure counter ({e})") from None
    return max(nums, default=0)


def next_tid(srv, progress):
    """A treasure id never used before. The number comes from the persisted monotonic counter (so a reset, which
    archives the pile and its never-sent entries, cannot make ids restart), and is also kept above everything in the
    current pile and the delivery ledger. The counter is written BEFORE the id is handed out: a failed save later can
    leave a gap in the numbers but never a reuse."""
    nums = [int(t["tid"][1:]) for t in treasure_of(progress)]
    nums += [int(d["source"]["ref"][1:]) for d in srv.mc.ledger.deliveries() if TID.fullmatch(d["source"]["ref"])]
    n = 1 + max([_tid_counter(srv), *nums])
    write_json_atomic(srv.data_dir / TID_COUNTER_FILE, {"v": 1, "last": n})
    return f"t{n:06d}"


def add_treasure(srv, progress, kind, ref, label, sprite, items):
    """Append a 'kept' treasure entry to `progress` (in memory) and return it. Caller saves progress."""
    entry = {"tid": next_tid(srv, progress), "label": label, "sprite": sprite,
             "items": [mcb.normalize_item(e) for e in items], "source": {"kind": kind, "ref": ref}, "status": "kept"}
    progress["treasure"] = treasure_of(progress) + [entry]
    return entry


def replay_count(events, story_id):
    """How many replays of `story_id` the events on file already hold, DERIVED (never stored). A replay is a
    story_done for a track that already had a story_done for this story (the first pass per track is not a replay),
    or any swap_done (a finished letter swap-in read; it needs a finished small-caps pass, so it is never a first pass).
    The next surprise is for replay number replay_count + 1. Counted across tracks: it is the same story."""
    seen, n = set(), 0
    for e in events:
        if e.get("story_id") != story_id:
            continue
        if e["type"] == "story_done":
            if e["track"] in seen:
                n += 1
            seen.add(e["track"])
        elif e["type"] == "swap_done":
            n += 1
    return n


def event_rewards(srv, ev, progress):
    """Add the treasure an accepted event earns to `progress` (in memory). Caller holds write_lock, has validated
    ev, and saves progress. Returns the list of new treasure entries. Decided HERE from events.jsonl, never
    from the client:
      craft           -> the word's real item (400 if the config has none)
      story_done      -> surprise 'story_first' if no earlier story_done for this story+track, else a replay surprise
      swap_done       -> a replay surprise (a finished letter swap-in read is always a replay)
                         (replay N of a story gets tier surprises.story_replay_tiers[min(N-1, len-1)]; see replay_count)
      card/match/word -> surprise 'streak10' each time this session's run of independent-correct answers
                         reaches a multiple of STREAK_LEN
      adventure_done  -> surprise 'adventure_done', once per session and adventure
      (the shared reading-points village level no longer earns a surprise; villagers are promoted instead)
    Reading events.jsonl raises (loudly) if it holds a bad line."""
    mc = srv.mc
    t = ev["type"]
    new = []
    if t == "craft":
        items = mc.cfg["craft_items"].get(ev["item"])
        _check(items is not None, "item", f"no Minecraft item is configured for craft word {ev['item']}")
        new.append(add_treasure(srv, progress, "craft", ev["item"], mcb.describe_items(items),
                                mc.craft_sprites[ev["item"]], items))
    elif t in ("story_done", "swap_done", "adventure_done") or (t in STREAK_TYPES and ev["result"] == "correct"):
        prior = read_events(srv.data_dir)
        key = ref = tier = None  # tier stays None unless the event picks one itself (replays), else surprises[key]
        if t in ("story_done", "swap_done"):
            first = t == "story_done" and not any(
                e["type"] == "story_done" and e["story_id"] == ev["story_id"] and e["track"] == ev["track"]
                for e in prior)
            track = "swap" if t == "swap_done" else ev["track"]
            if first:
                key, ref = "story_first", f"story_first:{track}:{ev['story_id']}"
            else:
                key = "story_replay"
                n = replay_count(prior, ev["story_id"]) + 1
                tier = mcb.replay_tier(mc.cfg, n)
                ref = f"story_replay:{track}:{ev['story_id']}:replay{n}:{tier}"
        elif t == "adventure_done":
            if not any(e["type"] == "adventure_done" and e["session_id"] == ev["session_id"]
                       and e["adventure"] == ev["adventure"] for e in prior):
                key, ref = "adventure_done", f"adventure_done:{ev['adventure']}:{ev['session_id']}"
        else:
            run = 1
            for e in reversed(prior):
                if e["session_id"] != ev["session_id"] or e["type"] not in STREAK_TYPES:
                    continue
                if e["result"] != "correct":
                    break
                run += 1
            if run % STREAK_LEN == 0:
                key, ref = "streak10", f"streak10:{ev['session_id']}:{run}"
        if key:
            rolled = mcb.roll_tier(mc.cfg, tier or mc.cfg["surprises"][key], mc.rng)
            new.append(add_treasure(srv, progress, "surprise", ref, rolled["label"], rolled["sprite"], rolled["items"]))
    have = {tr["source"]["ref"] for tr in treasure_of(progress)}
    game = EVENT_GAME.get(t)
    if game:
        # A minigame level reached (derive_levels over the events on file plus this one): one rare surprise per game and
        # level, ever (ref "minigame_level:<game>:<level>"; a level already holding one is skipped).
        reached = derive_levels(read_events(srv.data_dir) + [ev], srv.levels)[game]["level"]
        for n in range(2, reached + 1):
            ref = f"minigame_level:{game}:{n}"
            if ref in have:
                continue
            rolled = mcb.roll_tier(mc.cfg, LEVEL_SURPRISE_TIER, mc.rng)
            new.append(add_treasure(srv, progress, "surprise", ref, rolled["label"], rolled["sprite"], rolled["items"]))
    return new


def game_level_ups(new):
    """[{"game","level"}] for the minigame-level surprises among `new` treasure entries (ref minigame_level:<game>:<n>)."""
    out = []
    for t in new:
        ref = t["source"]["ref"]
        if t["source"]["kind"] == "surprise" and ref.startswith("minigame_level:"):
            _, game, n = ref.split(":")
            out.append({"game": game, "level": int(n)})
    return out


def accept_event(srv, ev):
    """Validate one event and record it: treasure and history first, then the event line. This is the body of POST
    /api/event, also used by the import (so imported events earn surprises exactly like live play). The CALLER holds
    srv.write_lock. A ValidationError (bad event, level above the game's max, a craft word with no configured item)
    means nothing was written for this event. Returns the reply body {"ok", ["treasure"], ["game_level_ups"]}."""
    validate_event(ev)
    if "level" in ev:
        top = srv.levels[EVENT_GAME[ev["type"]]]["max"]
        _check(ev["level"] <= top, "level", f"must be at most {top} for type {ev['type']} (levels.json)")
    # Treasure is saved BEFORE the event line is appended: a crash in between can only give an extra
    # item, never take one away. A bad craft word is a 400 and nothing is written.
    progress = read_progress(srv.data_dir)
    # A retry of an event whose first attempt saved the treasure but failed to append the event line
    # finds its entries by event key and creates nothing again (see event_key).
    key = event_key(srv, ev)
    new = [t for t in treasure_of(progress) if t.get("event") == key]
    if not new:
        new = event_rewards(srv, ev, progress)
        for t in new:
            t["event"] = key
        if new:
            record_event_treasure(srv, progress, ev, new)
            _save_progress_bumped(srv, progress, treasure=progress["treasure"])
    with open(srv.data_dir / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
        f.flush()
        os.fsync(f.fileno())
    body = {"ok": True}
    if new:
        body["treasure"] = [{"label": t["label"], "sprite": t["sprite"]} for t in new]
    if game_level_ups(new):
        body["game_level_ups"] = game_level_ups(new)
    return body


def event_key(srv, ev):
    """Identity of one accepted event, for idempotent treasure: '<events already on file>:<sha256 of the event>'.
    A retry after a failed append (treasure saved, event line not) has the same count and the same content, so it
    finds its treasure instead of creating it again. Not covered (documented in docs/design.md): a retry after the
    event line WAS appended (a lost response) is a new event with a new count; the client has no event id."""
    import hashlib
    digest = hashlib.sha256(json.dumps(ev, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"{len(read_events(srv.data_dir))}:{digest}"


def record_event_treasure(srv, progress, ev, new):
    """A `treasure` history line per entry an accepted event created (caller holds write_lock; written BEFORE the
    progress save). The village `level` line is gone with the shared level (history keeps the old ones)."""
    for t in new:
        record_treasure(srv, t)


def record_treasure(srv, entry, wallet_after=None):
    """The `treasure` history line for a new treasure entry."""
    srv.mc.history.append("treasure", {"tid": entry["tid"], "label": entry["label"], "items": entry["items"],
                                       "source": entry["source"]}, entry["tid"], wallet_after)


def record_client_changes(srv, current, new, cause):
    """The game client grants and uses up resources itself (it saves a changed inventory with PUT /api/progress), so
    the server records them when it accepts the save: an `earn` line with the per-resource increase and a `spend`
    line per resource that went down (old vs new inventory; only the NET change per resource per save is visible).
    `cause` is the event the client sent with the save (None for a progress-only save such as a setting): the earn
    line carries its summary as `last_event`, a spend line names it in `on`. Nothing is inferred from events on
    file. Caller holds write_lock; lines are written before the save and a failed write fails the request."""
    inv_old, inv_new = current["inventory"], new["inventory"]
    gained = {k: inv_new[k] - inv_old[k] for k in INVENTORY_KEYS if inv_new[k] > inv_old[k]}
    used = {k: inv_old[k] - inv_new[k] for k in INVENTORY_KEYS if inv_new[k] < inv_old[k]}
    summary = {k: cause[k] for k in EVENT_SUMMARY_KEYS if k in cause} if cause else None
    ref = f"progress_rev:{new['rev']}"
    if gained:
        srv.mc.history.append("earn", {"resources": gained, "last_event": summary}, ref, wallet_after=inv_new)
    detail = next((str(cause[k]) for k in ("block", "item", "story_id", "adventure") if k in cause), "") if cause else ""
    on = (f"{cause['type']} {detail}".strip() if cause else "the game (no event named)")
    for res, n in used.items():
        srv.mc.history.append("spend", {"resource": res, "amount": n, "on": on}, ref, wallet_after=inv_new)


def _save_progress_bumped(srv, progress, **changes):
    """Write progress with `changes` merged in and rev+1 (caller holds write_lock). Returns the saved progress."""
    saved = copy.deepcopy(progress)
    saved.update(copy.deepcopy(changes))
    saved["rev"] = progress["rev"] + 1
    validate_progress(saved)
    write_json_atomic(srv.data_dir / "progress.json", saved)
    return saved


def treasure_view(srv, entry, deliveries_by_ref):
    """One treasure entry as GET /api/treasure shows it: the entry plus `state` and `delivery`.
    state: kept | on_the_way (delivery pending) | in_chest (delivered) | failed (delivery failed)."""
    d = deliveries_by_ref.get(entry["tid"])
    if d is None:
        state = "kept" if entry["status"] == "kept" else "failed"  # sent without a delivery is an error, shown as failed
        delivery = None
    else:
        state = {"pending": "on_the_way", "delivered": "in_chest", "failed": "failed"}[d["status"]]
        delivery = {k: d[k] for k in ("id", "status", "attempts", "last_error", "delivered_ts", "chest")}
    return {**entry, "state": state, "delivery": delivery}


def treasure_list(srv, progress):
    by_ref = {d["source"]["ref"]: d for d in srv.mc.ledger.deliveries()}
    return [treasure_view(srv, t, by_ref) for t in treasure_of(progress)]


def reconcile_sent_treasure(srv):
    """Startup repair: a treasure marked 'sent' with no delivery (crash between the two writes) gets its delivery now.
    Loud on stderr; never creates a second delivery for a tid."""
    with srv.write_lock:
        progress = read_progress(srv.data_dir)
        for t in treasure_of(progress):
            if t["status"] == "sent" and srv.mc.ledger.find_by_ref(t["tid"]) is None:
                srv.mc.ledger.create(t["source"]["kind"], t["tid"], t["label"], t["items"])
                sys.stderr.write(f"[minecraft] RECOVERED: treasure {t['tid']} was marked sent but had no delivery; "
                                 f"created it now\n")


def treasure_send(srv, tids):
    """POST /api/treasure/send (caller holds write_lock). Marks every tid 'sent' in ONE progress write, then creates
    one delivery per tid, then writes the `send` history line (last, so a rolled-back send leaves none). A tid already sent (or delivered) is a 409 and nothing changes. If creating a delivery
    fails the 'sent' marks are rolled back; if that fails too the error says so."""
    mc = srv.mc
    if not mc.cfg["enabled"]:
        raise ShopRefused("Minecraft delivery is disabled in config/minecraft.json (enabled: false)")
    progress = read_progress(srv.data_dir)
    pile = {t["tid"]: t for t in treasure_of(progress)}
    for tid in tids:
        _check(tid in pile, "tids", f"unknown treasure {tid!r}")
    already = [tid for tid in tids if pile[tid]["status"] != "kept" or mc.ledger.find_by_ref(tid) is not None]
    if already:
        raise ShopRefused(f"already sent: {', '.join(already)}")
    sent = [dict(t, status="sent") if t["tid"] in tids else t for t in treasure_of(progress)]
    chosen = [pile[tid] for tid in tids]
    saved = _save_progress_bumped(srv, progress, treasure=sent)
    made = []
    try:
        for tid in tids:
            t = pile[tid]
            made.append(mc.ledger.create(t["source"]["kind"], tid, t["label"], t["items"]))
    except Exception as e:
        try:
            _save_progress_bumped(srv, saved, treasure=treasure_of(progress))
        except Exception as e2:
            raise OSError(f"could not create all deliveries ({e}) AND could not undo the 'sent' marks ({e2}); "
                          f"deliveries already created: {[d['id'] for d in made]}") from None
        raise
    # The `send` line is written only now that the send is durable (marks saved AND deliveries created): a rolled-back
    # send must leave no line behind. If this write fails the send has still happened; the 500 says so loudly
    # (the treasure shows as on its way after a reload) and the line is missing from the history.
    try:
        mc.history.append("send", {"tids": list(tids), "items": [it for t in chosen for it in t["items"]]}, ",".join(tids))
    except mcb.HistoryError as e:
        raise OSError(f"the send DID happen (deliveries {[d['id'] for d in made]}) but its history line could not be "
                      f"written: {e}") from None
    return {"treasure": treasure_list_for(srv, saved, tids), "deliveries": made, "rev": saved["rev"]}


def treasure_list_for(srv, progress, tids):
    return [t for t in treasure_list(srv, progress) if t["tid"] in tids]


def village_view(srv):
    """GET /api/village body (docs/design.md): wallet, reading points, bells, promotions and every profession with its
    own level and offers (`locked` = THAT villager's level is below the offer's min_level; `unlocked` = he has this villager; `can_unlock` = the
    profession's own requirement is met)."""
    mc = srv.mc
    progress = read_progress(srv.data_dir)
    st = village_state(srv, progress)
    unlocked = village_of(progress)["unlocked"]
    levels = village_levels(srv, progress)
    promo = promotion_state(srv, progress)
    names = mc.cfg["village"]["levels"]["names"]
    others = [pid for pid, p in mc.professions.items() if "requires" not in p]
    profs = []
    for p in mc.cfg["village"]["professions"]:
        met = p.get("requires") != "all_professions" or all(pid in unlocked for pid in others)
        profs.append({
            "id": p["id"], "name": p["name"], "job_block_sprite": p["job_block_sprite"],
            "unlock_emeralds": p["unlock_emeralds"], "requires": p.get("requires"),
            "unlocked": p["id"] in unlocked, "can_unlock": p["id"] not in unlocked and met,
            "level": levels.get(p["id"], 0), "level_name": names[levels.get(p["id"], 0)],
            "can_promote": p["id"] in unlocked and levels[p["id"]] < len(names) - 1 and promo["available"] > 0,
            "offers": [dict(o, locked=levels.get(p["id"], 0) < o["min_level"]) for o in p["offers"]]})
    return {"enabled": mc.cfg["enabled"], "wallet": progress["inventory"], "points": st["points"],
            "level": st["level"], "levels": mc.cfg["village"]["levels"], "bells": st["bells"],
            "promotions": promo, "first_free": not unlocked, "professions": profs, "trades": mc.cfg["trades"], "earn": mc.cfg["earn"],
            "rev": progress["rev"]}


def village_unlock(srv, profession, pay):
    """Unlock a villager (caller holds write_lock). The first unlock is free whatever `pay` says; later ones cost one
    Village Bell (pay "bell") or the profession's unlock_emeralds (pay "emeralds"). The Wandering Trader needs every
    other villager first. Wallet, bells, village and the new treasure are saved in ONE progress write."""
    mc = srv.mc
    prof = mc.professions[profession]
    progress = read_progress(srv.data_dir)
    village = dict(village_of(progress))
    # Persist both server-owned keys on every village write (an older file lacks them; see village_spent).
    spent_before = village["emeralds_spent"] = village_spent(srv, progress)
    village["levels"] = dict(village.get("levels", {}))
    progress_unlocked_before = bool(village["unlocked"])  # False = this is his first, free, unlock
    _check(profession not in village["unlocked"], "profession", f"{profession} is already unlocked")
    if prof.get("requires") == "all_professions":
        missing = [p["name"] for pid, p in mc.professions.items() if "requires" not in p and pid not in village["unlocked"]]
        if missing:
            raise ShopRefused(f"unlock every villager first; still locked: {', '.join(missing)}")
    inv = dict(progress["inventory"])
    if village["unlocked"]:  # not the first: he pays
        if pay == "bell":
            avail = village_state(srv, progress)["bells"]["available"]
            if avail < 1:
                raise ShopRefused("no Village Bell available")
            village["bells_spent"] += 1
        else:
            if inv["emerald"] < prof["unlock_emeralds"]:
                raise ShopRefused(f"not enough emeralds: have {inv['emerald']}, need {prof['unlock_emeralds']}")
            inv["emerald"] -= prof["unlock_emeralds"]
            village["emeralds_spent"] = spent_before + prof["unlock_emeralds"]
    village["unlocked"] = village["unlocked"] + [profession]
    work = copy.deepcopy(progress)
    label = prof["name"] if "unlock_items" in prof else f"{prof['name']} Villager"
    entry = add_treasure(srv, work, "unlock", f"unlock:{profession}", label, prof["job_block_sprite"],
                         mcb.profession_unlock_items(prof))
    paid = "free" if not progress_unlocked_before else pay
    mc.history.append("unlock", {"profession": profession, "name": prof["name"], "paid": paid}, profession, inv)
    if paid == "bell":
        mc.history.append("spend", {"resource": "bell", "amount": 1, "on": f"unlock {prof['name']}"}, profession, inv)
    elif paid == "emeralds":
        mc.history.append("spend", {"resource": "emerald", "amount": prof["unlock_emeralds"],
                                    "on": f"unlock {prof['name']}"}, profession, inv)
    record_treasure(srv, entry, inv)
    saved = _save_progress_bumped(srv, progress, village=village, inventory=inv, treasure=work["treasure"])
    return {"village": village_view(srv), "wallet": saved["inventory"], "treasure": entry, "rev": saved["rev"]}


def shop_trade(srv, trade_id):
    """Apply one trade atomically (caller holds write_lock). Raises ShopRefused if he cannot afford it."""
    trade = srv.mc.trades[trade_id]
    progress = read_progress(srv.data_dir)
    inv = dict(progress["inventory"])
    for k, n in trade["give"].items():
        if inv[k] < n:
            raise ShopRefused(f"not enough {k}: have {inv[k]}, need {n}")
        inv[k] -= n
    for k, n in trade["get"].items():
        inv[k] += n
    srv.mc.history.append("trade", {"trade_id": trade_id, "give": trade["give"], "get": trade["get"]}, trade_id, inv)
    saved = _save_progress_bumped(srv, progress, inventory=inv)
    return {"wallet": saved["inventory"], "rev": saved["rev"]}


def shop_buy(srv, offer_id):
    """Buy an offer (caller holds write_lock): its villager must be unlocked, the village level must reach its
    min_level, and he needs the emeralds. Wallet and the new treasure are saved in ONE progress write, so a purchase
    can never take emeralds without giving the treasure."""
    prof, offer = srv.mc.offers[offer_id]
    progress = read_progress(srv.data_dir)
    if prof["id"] not in village_of(progress)["unlocked"]:
        raise ShopRefused(f"{prof['name']} is not unlocked yet")
    names = srv.mc.cfg["village"]["levels"]["names"]
    lv = village_levels(srv, progress)[prof["id"]]
    if lv < offer["min_level"]:
        raise ShopRefused(f"needs the {prof['name']} to be {names[offer['min_level']]} (now {names[lv]}); "
                          "spend emeralds to earn a promotion")
    have = progress["inventory"]["emerald"]
    if have < offer["price"]:
        raise ShopRefused(f"not enough emeralds: have {have}, need {offer['price']}")
    inv = dict(progress["inventory"])
    inv["emerald"] -= offer["price"]
    work = copy.deepcopy(progress)
    entry = add_treasure(srv, work, "shop", offer_id, offer["label"], offer["sprite"], offer["items"])
    # BEFORE this spend's history line: on an old progress.json (no emeralds_spent) village_spent sums history, which
    # would otherwise already include this purchase and count its price twice.
    spent_before = village_spent(srv, progress)
    srv.mc.history.append("spend", {"resource": "emerald", "amount": offer["price"], "on": offer["label"],
                                    "offer_id": offer_id}, offer_id, inv)
    record_treasure(srv, entry, inv)
    village = {**village_of(progress), "emeralds_spent": spent_before + offer["price"],
               "levels": dict(village_of(progress).get("levels", {}))}
    saved = _save_progress_bumped(srv, progress, inventory=inv, treasure=work["treasure"], village=village)
    return {"wallet": saved["inventory"], "treasure": entry, "rev": saved["rev"]}


def village_promote(srv, profession):
    """Promote one villager one level (caller holds write_lock): he must be unlocked and below the top level, and a
    promotion must be available (earned from emeralds spent, minus levels already given). Level, history line and
    rev bump are one atomic write; a repeated tap finds available == 0 and is refused."""
    mc = srv.mc
    prof = mc.professions[profession]
    progress = read_progress(srv.data_dir)
    names = mc.cfg["village"]["levels"]["names"]
    levels = village_levels(srv, progress)
    if profession not in levels:
        raise ShopRefused(f"{prof['name']} is not unlocked yet")
    if levels[profession] >= len(names) - 1:
        raise ShopRefused(f"{prof['name']} is already {names[-1]}")
    promo = promotion_state(srv, progress)
    if promo["available"] < 1:
        raise ShopRefused(f"no promotion available: spend {promo['next_at'] - promo['spent']} more emeralds")
    new_level = levels[profession] + 1
    village = {**village_of(progress), "emeralds_spent": promo["spent"],
               "levels": {**village_of(progress).get("levels", {}), profession: new_level}}
    mc.history.append("promote", {"profession": profession, "name": prof["name"], "from_level": new_level - 1,
                                  "level": new_level, "level_name": names[new_level], "spent": promo["spent"]},
                      profession, progress["inventory"])
    saved = _save_progress_bumped(srv, progress, village=village)
    return {"village": village_view(srv), "wallet": saved["inventory"],
            "profession": {"id": profession, "name": prof["name"], "level": new_level, "level_name": names[new_level]},
            "rev": saved["rev"]}


def treasure_view_body(srv):
    """GET /api/treasure body: every treasure entry with its state, plus the delivery problem (if any) and whether
    sending is possible at all."""
    progress = read_progress(srv.data_dir)
    worker = srv.mc.worker
    return {"treasure": treasure_list(srv, progress), "enabled": srv.mc.cfg["enabled"],
            "server_running": bool(worker and worker.server_running),
            "problem": worker.problem if worker else None, "rev": progress["rev"]}


def minecraft_view(srv):
    """GET /api/minecraft body: status, pending/failed/recent deliveries, chest count, loud problem string.
    `worker_running` is false when the delivery thread was not started (temp data dir, or enabled: false)."""
    mc = srv.mc
    ds = mc.ledger.deliveries()
    worker = mc.worker
    seen = {(d["chest"]["x"], d["chest"]["y"], d["chest"]["z"]) for d in ds if d["chest"]}
    if worker is not None:
        seen |= worker.bridge.known
    return {"enabled": mc.cfg["enabled"],
            "worker_running": worker is not None,
            "server_running": bool(worker and worker.server_running),
            "pending": [d for d in ds if d["status"] == "pending"],
            "failed": [d for d in ds if d["status"] == "failed"],
            "recent": [d for d in ds if d["status"] == "delivered"][-10:],
            "chests": len(seen),
            "problem": worker.problem if worker else None}


# --- Import of Mom's-house play (docs/away-from-home.md §3 and §5) -----------------------------------------
IMPORTS_FILE = "imports.jsonl"  # data/: one receipt line per imported export (append-only)
CLIENT_OWNED_KEYS = ("inventory", "active_letters", "letter_stats", "house", "stories", "crafted", "settings")
EXPORT_KEYS = ("format", "v", "export_id", "device_id", "created", "base", "progress", "events")
EXPORT_FORMAT = "reading-village-export"
# Every data file a full import can touch; they are restored byte for byte if the import fails part-way.
IMPORT_TOUCHED_FILES = ("progress.json", "events.jsonl", HISTORY_FILE, TID_COUNTER_FILE, IMPORTS_FILE)


def _check_client_progress(p, field):
    """`p` must hold exactly the client-owned keys and be a valid progress once `v` is added. Raises ValidationError."""
    _check(isinstance(p, dict), field, "must be an object")
    _check(set(p) == set(CLIENT_OWNED_KEYS), field,
           f"must have exactly the keys {list(CLIENT_OWNED_KEYS)} (missing {sorted(set(CLIENT_OWNED_KEYS) - set(p))}, "
           f"unexpected {sorted(set(p) - set(CLIENT_OWNED_KEYS))})")
    try:
        validate_progress({"v": 1, **p})
    except ValidationError as e:
        raise ValidationError(f"{field}.{e}") from None


def validate_export(srv, ex):
    """Check the whole export file (shape, format/v, every event, both progress objects) before anything is touched.
    Raises ValidationError naming the field, or `events[i]` for a bad event."""
    _check_keys(ex, "", EXPORT_KEYS)
    _check(ex["format"] == EXPORT_FORMAT, "format", f"must be {EXPORT_FORMAT!r}")
    _check(ex["v"] == 1 and _is_int(ex["v"]), "v", "must be the integer 1")
    for k in ("export_id", "device_id"):
        _check(_is_str(ex[k]), k, "must be a non-empty string")
    _check(isinstance(ex["created"], str), "created", "must be an ISO-8601 string")
    try:
        created = datetime.fromisoformat(ex["created"])
    except ValueError:
        raise ValidationError("created: not a valid ISO-8601 timestamp") from None
    _check(created.tzinfo is not None, "created", "must include a UTC offset")
    _check_keys(ex["base"], "base", ("snapshot_id", "progress"))
    _check(_is_str(ex["base"]["snapshot_id"]), "base.snapshot_id", "must be a non-empty string")
    _check_client_progress(ex["base"]["progress"], "base.progress")
    _check_client_progress(ex["progress"], "progress")
    _check(isinstance(ex["events"], list), "events", "must be a list")
    for i, ev in enumerate(ex["events"]):
        try:
            validate_event(ev)
            if "level" in ev:
                top = srv.levels[EVENT_GAME[ev["type"]]]["max"]
                _check(ev["level"] <= top, "level", f"must be at most {top} for type {ev['type']} (levels.json)")
        except ValidationError as e:
            raise ValidationError(f"events[{i}]: {e}") from None


def read_receipts(data_dir):
    """Every line of data/imports.jsonl (oldest first); a missing file is no receipts. A bad line raises ValueError
    naming its number: receipts decide what is already imported, so a damaged one must stop the import."""
    f = Path(data_dir) / IMPORTS_FILE
    out = []
    if not f.exists():
        return out
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        try:
            r = json.loads(line)
            ok = (isinstance(r, dict) and r.get("v") == 1 and all(k in r for k in
                  ("ts", "export_id", "device_id", "base_snapshot_id", "events_total", "events_new", "duplicates", "progress")))
        except ValueError:
            ok = False
        if not ok:
            raise ValidationError(f"{IMPORTS_FILE} line {n}: not a valid import receipt")
        out.append(r)
    return out


def _event_hash(ev):
    import hashlib
    return hashlib.sha256(json.dumps(ev, sort_keys=True).encode("utf-8")).hexdigest()


def merge_client_progress(current, export, prev, house_conflicts=None):
    """The client-owned progress after importing `export` (docs/away-from-home.md §5.3), as a new dict built from the
    current progress. `prev` is what the previous import from this device and base (or the base itself) already
    brought in, so only the difference export - prev is applied. Raises ValidationError (400) if an inventory or
    craft count would go below 0. A house cell Dad's record already holds with a DIFFERENT block keeps Dad's block;
    each skipped cell is appended to `house_conflicts` (if given) as {x, y, dads, moms}. settings are Dad's and never
    change."""
    merged = copy.deepcopy(current)
    _fam = load_family_config()  # labels for the error text only; never hard-code a family's names
    for field in ("inventory", "crafted"):
        out = dict(current.get(field, {}))
        for k in set(export[field]) | set(prev[field]):
            n = out.get(k, 0) + export[field].get(k, 0) - prev[field].get(k, 0)
            _check(n >= 0, f"{field}.{k}", f"import would leave {n} ({_fam['home_grown_up']}'s record has {out.get(k, 0)}, "
                   f"{_fam['away_label']} changed it by {export[field].get(k, 0) - prev[field].get(k, 0)}): nothing was imported")
            if n or field == "inventory":
                out[k] = n
            else:
                out.pop(k, None)
        merged[field] = out
        if field == "crafted" and not out and "crafted" not in current:
            del merged["crafted"]  # keep "absent" absent
    for field in ("letter_stats", "stories"):
        out = dict(current[field])
        for k, v in export[field].items():
            if prev[field].get(k) != v:
                out[k] = copy.deepcopy(v)
        merged[field] = out
    letters = list(current["active_letters"])
    letters += [l for l in export["active_letters"] if l not in letters]
    merged["active_letters"] = letters
    house = list(current["house"])
    taken = {(b["x"], b["y"]): b["block"] for b in house}
    before = {(b["x"], b["y"]) for b in prev["house"]}
    for b in export["house"]:
        cell = (b["x"], b["y"])
        if cell in before:
            continue
        if cell in taken:
            if taken[cell] != b["block"] and house_conflicts is not None:
                house_conflicts.append({"x": b["x"], "y": b["y"], "dads": taken[cell], "moms": b["block"]})
            continue
        taken[cell] = b["block"]
        house.append(copy.deepcopy(b))
    merged["house"] = house
    return merged


def _rollback_history(srv, f, saved):
    """Undo the import's lines in the append-only history without erasing lines the delivery worker appended meanwhile:
    the file becomes the saved bytes plus any later `delivered` / `delivery_failed` lines (the worker's own kinds)."""
    with srv.mc.history.lock:
        now = f.read_bytes() if f.exists() else b""
        if not now.startswith(saved):
            raise OSError(f"{f} changed before the saved start; cannot roll the import back safely")
        keep = [l for l in now[len(saved):].splitlines(keepends=True)
                if json.loads(l)["kind"] in ("delivered", "delivery_failed")]
        f.write_bytes(saved + b"".join(keep))


def import_export(srv, ex):
    """Import one export file into the real record. The CALLER holds srv.write_lock. All or nothing: the whole file
    is validated first (ValidationError, nothing touched); after that every data file the import can write is
    restored byte for byte if any step fails. Returns the reply body of POST /api/import."""
    validate_export(srv, ex)
    data = srv.data_dir
    receipts = read_receipts(data)
    for r in receipts:
        if r["export_id"] == ex["export_id"]:  # the same download imported again: nothing changes
            return {"ok": True, "already_imported": True, "events_new": r["events_new"], "duplicates": r["duplicates"],
                    "treasure": [], "game_level_ups": [], "house_conflicts": [], "emeralds_added": 0,
                    "rev": read_progress(data)["rev"]}
    same = [r for r in receipts if r["device_id"] == ex["device_id"] and r["base_snapshot_id"] == ex["base"]["snapshot_id"]]
    if same and len(ex["events"]) < same[-1]["events_total"]:
        # Exports are cumulative: an older one (fewer events) than what was already imported from this device and
        # base would apply a negative difference and overwrite newer values.
        raise ValidationError(f"events: this export has {len(ex['events'])} events but an export with "
                              f"{same[-1]['events_total']} from the same device and base was already imported; it is "
                              "older than an export already imported; nothing changed")
    prev = same[-1]["progress"] if same else ex["base"]["progress"]
    _check_client_progress(prev, "previous receipt progress")
    # A multiset: Mom's file may hold two identical events (same second, same answer). Each copy already on Dad's side
    # cancels exactly one copy in the export, so identical events are deduped by count, never collapsed.
    have = Counter(_event_hash(e) for e in read_events(data))
    fresh = []
    for e in ex["events"]:
        h = _event_hash(e)
        if have[h] > 0:
            have[h] -= 1
        else:
            fresh.append(e)
    duplicates = len(ex["events"]) - len(fresh)

    # Fail before writing anything when the merge cannot work (negative counts, conflicting cell).
    start = read_progress(data)
    merge_client_progress(start, ex["progress"], prev)
    for i, e in enumerate(fresh):  # accept_event would reject these mid-way; catch them while nothing is written
        if e["type"] == "craft" and srv.mc.cfg["craft_items"].get(e["item"]) is None:
            raise ValidationError(f"events[{i}]: item: no Minecraft item is configured for craft word {e['item']}")

    saved = {}
    for name in IMPORT_TOUCHED_FILES:
        f = data / name
        saved[name] = f.read_bytes() if f.exists() else None
    treasure, level_ups = [], []
    try:
        for ev in fresh:  # file order: streaks, first-pass and level surprises depend on it
            body = accept_event(srv, ev)
            treasure += body.get("treasure", [])
            level_ups += body.get("game_level_ups", [])
        current = read_progress(data)  # accept_event changed treasure and rev only; client-owned keys are as at `start`
        house_conflicts = []
        merged = merge_client_progress(current, ex["progress"], prev, house_conflicts)
        merged["rev"] = current["rev"] + 1
        validate_progress(merged)
        record_client_changes(srv, current, merged, None)
        write_json_atomic(data / "progress.json", merged)
        receipt = {"v": 1, "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "export_id": ex["export_id"], "device_id": ex["device_id"],
                   "base_snapshot_id": ex["base"]["snapshot_id"], "events_total": len(ex["events"]),
                   "events_new": len(fresh), "duplicates": duplicates, "progress": ex["progress"]}
        with open(data / IMPORTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        for name, content in saved.items():
            f = data / name
            if name == HISTORY_FILE:
                _rollback_history(srv, f, content or b"")
            elif content is None:
                f.unlink(missing_ok=True)
            else:
                f.write_bytes(content)
        raise
    return {"ok": True, "already_imported": False, "events_new": len(fresh), "duplicates": duplicates,
            "treasure": treasure, "game_level_ups": level_ups, "house_conflicts": house_conflicts,
            "emeralds_added": merged["inventory"]["emerald"] - start["inventory"]["emerald"], "rev": merged["rev"]}


# --- Publishing the web snapshot (docs/away-from-home.md §6) -----------------------------------------------
WEB_CONFIG_FIELDS = {"enabled": bool, "auto": bool, "repo": str, "branch": str, "work_dir": str}


def load_web_config(srv):
    """config/web.json as a dict, validated. The file is optional: it is only required once a publish is wanted.
    Raises ValidationError with a message naming the problem (missing file, bad JSON, wrong field)."""
    path = srv.web_config_path
    if path is None:
        raise ValidationError("web publishing is off for a temp --data-dir")
    if not Path(path).exists():
        raise ValidationError("config/web.json missing")
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise ValidationError(f"config/web.json invalid: {e}") from None
    ok = isinstance(cfg, dict) and set(cfg) == set(WEB_CONFIG_FIELDS) and all(
        isinstance(cfg[k], t) and (t is bool or cfg[k] != "") for k, t in WEB_CONFIG_FIELDS.items())
    if not ok:
        raise ValidationError(f"config/web.json invalid: must be exactly {WEB_CONFIG_FIELDS_TEXT}")
    return cfg


WEB_CONFIG_FIELDS_TEXT = '{"enabled": bool, "auto": bool, "repo": str, "branch": str, "work_dir": str}'


def real_publisher(root, data_dir, push):
    """The real publish (tools/publish_web.py), imported lazily so the server starts without it."""
    from tools.publish_web import build_and_publish
    return build_and_publish(root, data_dir, push=push)


def web_view(srv):
    """GET /api/web: {state, at, snapshot_id, error, enabled, auto}. state is idle|running|ok|failed as in the
    contract, plus "disabled" when config/web.json is missing or enabled=false (error says why; a missing or invalid
    file is always spelled out)."""
    try:
        cfg = load_web_config(srv)
    except ValidationError as e:
        invalid = "invalid" in str(e)
        return {"state": "failed" if invalid else "disabled", "at": None, "snapshot_id": None, "error": str(e),
                "enabled": False, "auto": False}
    with srv.web_lock:
        status = dict(srv.web_status)
    if not cfg["enabled"]:
        return {**status, "state": "disabled", "error": None, "enabled": False, "auto": cfg["auto"]}
    return {**status, "enabled": True, "auto": cfg["auto"]}


def request_publish(srv):
    """Start a publish in a background thread, one at a time: a request that arrives while one is running makes
    exactly one more run after it (the data may have changed since the running build read it)."""
    with srv.web_lock:
        if srv.web_flags["running"]:
            srv.web_flags["again"] = True
            return
        srv.web_flags["running"] = True
        srv.web_status.update(state="running", error=None)
    threading.Thread(target=_publish_loop, args=(srv,), daemon=True, name="web-publish").start()


def _publish_loop(srv):
    """Thread body: publish, record the outcome in web_status, repeat while requests arrived meanwhile."""
    while True:
        try:
            res = srv.publisher(ROOT, srv.data_dir, True)
            if not (isinstance(res, dict) and res.get("ok") is True and _is_str(res.get("snapshot_id"))):
                raise ValueError(f"publisher returned a malformed result: {res!r}")
            outcome = {"state": "ok", "snapshot_id": res["snapshot_id"], "error": None}
        except Exception as e:  # PublishError or anything unexpected: both must be visible, never swallowed
            sys.stderr.write(f"WEB PUBLISH FAILED: {type(e).__name__}: {e}\n")
            outcome = {"state": "failed", "error": f"{type(e).__name__}: {e}"}
        with srv.web_lock:
            srv.web_status.update(outcome, at=datetime.now().astimezone().isoformat(timespec="seconds"))
            if srv.web_flags["again"]:
                srv.web_flags["again"] = False
                srv.web_status.update(state="running", error=None)
                continue
            srv.web_flags["running"] = False
            return


def maybe_auto_publish(srv):
    """After a session_end event or an import: publish when web.json says enabled and auto. A missing file is
    fine (optional feature, nothing happens); an invalid one is recorded as a failed status so it shows on the
    Dashboard."""
    try:
        cfg = load_web_config(srv)
    except ValidationError as e:
        if "invalid" in str(e):
            sys.stderr.write(f"WEB PUBLISH SKIPPED: {e}\n")
        return
    if cfg["enabled"] and cfg["auto"]:
        request_publish(srv)


# Attributes make_server attaches to a server; the ::1 twin must carry all of them (checked by a test).
SHARED_SERVER_ATTRS = ("data_dir", "write_lock", "mc", "levels", "family", "web_config_path", "web_status", "web_lock",
                       "web_flags", "publisher")


class _V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def make_loopback_servers(data_dir, port, mc_config=None, family_config=None):
    """Return [IPv4 127.0.0.1, IPv6 ::1] servers on one port, sharing data_dir and one write lock.

    Browsers resolve "localhost" to ::1 first. Binding only 127.0.0.1 let an unrelated IPv6 server
    on the same port answer "localhost" silently, so both are bound and a
    failure to bind either one is fatal. Loopback only: nothing is reachable from the network.
    """
    v4 = make_server(data_dir, port, mc_config=mc_config, family_config=family_config)
    try:
        v6 = _V6Server(("::1", v4.server_address[1]), Handler)
    except OSError:
        v4.server_close()
        raise
    # Share every per-server attribute make_server set (data_dir, write_lock, mc, levels, ...), so a new one can
    # never be forgotten on ::1 again.
    for name in SHARED_SERVER_ATTRS:
        setattr(v6, name, getattr(v4, name))
    return [v4, v6]


def main():
    ap = argparse.ArgumentParser(description="Reading Village game server")
    ap.add_argument("--port", type=int, default=8642)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    ap.add_argument("--data-dir", default=str(ROOT / "data"), help="where progress.json/events.jsonl live")
    ap.add_argument("--minecraft-config", default=str(MC_CONFIG), help="Minecraft shop/delivery config (JSON)")
    ap.add_argument("--minecraft-worker", choices=("auto", "on", "off"), default="auto",
                    help="run the delivery worker: auto = only with the real data dir (a temp --data-dir used by a "
                         "test or tool must never deliver into the real Minecraft world)")
    ap.add_argument("--minecraft-poll", type=float, default=mcb.POLL_SECONDS, help="seconds between delivery passes")
    args = ap.parse_args()
    try:
        srv, srv6 = make_loopback_servers(args.data_dir, args.port, mc_config=args.minecraft_config)
    except FamilyConfigError as e:
        sys.exit(f"FAILED: invalid family config: {e}")
    except mcb.ConfigError as e:
        sys.exit(f"FAILED: invalid Minecraft config {args.minecraft_config}: {e}")
    except OSError as e:
        sys.exit(f"FAILED: could not start server on port {args.port} (127.0.0.1 and ::1): {e}. "
                 f"See what holds it: lsof -nP -iTCP:{args.port} -sTCP:LISTEN")
    threading.Thread(target=srv6.serve_forever, daemon=True).start()
    real_data = Path(args.data_dir).resolve() == (ROOT / "data").resolve()
    run_worker = args.minecraft_worker == "on" or (args.minecraft_worker == "auto" and real_data)
    worker = start_minecraft_worker(srv, args.minecraft_poll) if run_worker else None
    why = "worker off (temp --data-dir; pass --minecraft-worker on)" if not run_worker else "OFF (enabled: false)"
    print(f"Minecraft deliveries: {'ON, mc_dir ' + srv.mc.cfg['mc_dir'] if worker else why}", flush=True)
    url = f"http://localhost:{args.port}"
    print(f"Serving {url}  (data: {args.data_dir})  Ctrl-C to stop", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
