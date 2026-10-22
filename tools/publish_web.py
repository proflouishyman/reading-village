#!/usr/bin/env python3
"""Publish the web copy of the reading game (docs/away-from-home.md sections 2, 4 and 6).

    python3 tools/publish_web.py [--no-push] [--setup]

Builds build/web/ (the app minus Dad-only files and the Minecraft textures, runmode.js set to STATIC = true, plus
snapshot.json), runs the scrub guard over every byte, then force-pushes ONE orphan commit to the public GitHub Pages
repo so that repo never accumulates history of the child's data. Any failure raises PublishError (exit 1, FAILED banner).

The scrub guard also refuses the site if it contains the gamertag (config/private_overrides.json "player", required) or
any word of the optional list "private_strings" in the same file (e.g. a surname). See docs/away-from-home.md.

Library entry point: build_and_publish(root, data_dir, push=True) -> {ok, snapshot_id, url, pushed, files}.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SNAPSHOT_FORMAT = "reading-village-snapshot"
SNAPSHOT_V = 1
RUNMODE_STATIC = "export const STATIC = true;\n"

# Paths (relative to app/) that never go on the public site.
EXCLUDE_DIRS = ("assets/mc",)
EXCLUDE_FILES = ("dashboard.html", "render.html", "js/dashboard.js", "js/renderpage.js")
EXCLUDE_NAMES = (".DS_Store",)

# STRIP LIST. The web copy does not need Minecraft delivery internals, and they can carry the player's gamertag,
# chest coordinates and the server commands' output. These keys are removed at ANY depth of history lines.
STRIP_KEYS = ("chest", "delivery", "log", "player", "command", "last_error",
              "error")  # delivery_failed lines carry McError/VerifyError text: log paths (/Users/...), chest contents
# Treasure entries keep a `delivery` object (the client reads its keys), but with the private values blanked:
# `chest` and `last_error` become null; id, status, attempts and delivered_ts are kept.
TREASURE_DELIVERY_BLANKED = ("chest", "last_error")

EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
IPV4_RE = re.compile(rb"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
FORBIDDEN_NAMES = ("dashboard.html", "render.html", ".DS_Store")
FORBIDDEN_SUBSTRINGS = (b"/Users/", b"private_overrides")


class PublishError(Exception):
    """Anything that stops a publish. The message names what failed and where."""


# ---------------------------------------------------------------------------------------------------- config

def load_web_config(root):
    """config/web.json -> dict; every key is required (no defaults)."""
    path = Path(root) / "config" / "web.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PublishError(f"could not read {path}: {e}") from None
    expected = {"enabled": bool, "auto": bool, "repo": str, "branch": str, "work_dir": str}
    if not isinstance(cfg, dict) or set(cfg) != set(expected):
        raise PublishError(f"{path}: must be an object with exactly the keys {sorted(expected)}")
    for k, t in expected.items():
        if type(cfg[k]) is not t or (t is str and not cfg[k]):
            raise PublishError(f"{path}: {k} must be a {'boolean' if t is bool else 'non-empty string'}")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", cfg["repo"]):
        raise PublishError(f"{path}: repo must look like owner/name")
    return cfg


PLACEHOLDER_REPO = "YOUR-GITHUB-USER/YOUR-REPO"


def require_real_repo(cfg):
    """Pushing needs a real repo: the shipped config/web.json holds a placeholder, which must fail loudly."""
    if cfg["repo"] == PLACEHOLDER_REPO:
        raise PublishError(f"config/web.json: repo is still the placeholder {PLACEHOLDER_REPO!r}; set your own "
                           f"owner/name (and enabled: true) before publishing")


def page_url(repo):
    owner, name = repo.split("/")
    return f"https://{owner.lower()}.github.io/{name}/"


def load_private_strings(root):
    """The optional `private_strings` list in config/private_overrides.json: extra words this family never wants on the
    public site (a surname, a school, a street). Absent = none. Present but not a list of non-empty strings is a
    failure (loud: a typo must not quietly switch the guard off). Returns a list of str."""
    path = Path(root) / "config" / "private_overrides.json"
    try:
        extra = json.loads(path.read_text(encoding="utf-8")).get("private_strings", [])
    except (OSError, ValueError, AttributeError) as e:
        raise PublishError(f"scrub guard cannot read private_strings from {path}: {e}") from None
    if not isinstance(extra, list) or not all(isinstance(t, str) and t.strip() for t in extra):
        raise PublishError(f"{path}: private_strings must be a list of non-empty strings")
    return extra


def load_gamertag(root):
    """The private gamertag the scrub guard searches for. Missing or empty is a failure: the guard cannot work."""
    path = Path(root) / "config" / "private_overrides.json"
    try:
        tag = json.loads(path.read_text(encoding="utf-8")).get("player")
    except (OSError, ValueError, AttributeError) as e:
        raise PublishError(f"scrub guard cannot read the gamertag from {path}: {e}") from None
    if not isinstance(tag, str) or not tag.strip():
        raise PublishError(f"{path}: needs a non-empty string 'player' for the scrub guard")
    return tag


# -------------------------------------------------------------------------------------------------- snapshot

def strip_keys(obj):
    """Return a deep copy of obj with every STRIP_KEYS key removed at any depth."""
    if isinstance(obj, dict):
        return {k: strip_keys(v) for k, v in obj.items() if k not in STRIP_KEYS}
    if isinstance(obj, list):
        return [strip_keys(v) for v in obj]
    return obj


def strip_treasure(body):
    """GET /api/treasure body -> the same shape with delivery internals blanked (see TREASURE_DELIVERY_BLANKED)."""
    out = dict(body)
    entries = []
    for e in body["treasure"]:
        e = dict(e)
        d = e["delivery"]
        if d is not None:
            d = dict(d)
            for k in TREASURE_DELIVERY_BLANKED:
                d[k] = None
            e["delivery"] = d
        entries.append(e)
    out["treasure"] = entries
    # `problem` is free text from the delivery worker; it may name the player or a path.
    out["problem"] = None
    return out


def read_imports(data_dir):
    """data/imports.jsonl -> {device_id: {base_snapshot_id, events}} from each device's latest receipt.
    A missing file is {}. A malformed line is a failure naming the line."""
    path = Path(data_dir) / "imports.jsonl"
    if not path.exists():
        return {}
    out = {}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            r = json.loads(raw)
            dev, base, total = r["device_id"], r["base_snapshot_id"], r["events_total"]
        except (ValueError, KeyError, TypeError) as e:
            raise PublishError(f"{path} line {n}: bad import receipt ({e!r})") from None
        if not (isinstance(dev, str) and dev and isinstance(base, str) and isinstance(total, int)
                and not isinstance(total, bool) and total >= 0):
            raise PublishError(f"{path} line {n}: device_id/base_snapshot_id must be strings, events_total an int >= 0")
        out[dev] = {"base_snapshot_id": base, "events": total}
    return out


def git_head(root):
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise PublishError(f"could not read git HEAD of {root}: {getattr(e, 'stderr', e)}") from None


def snapshot_id_of(body):
    """First 16 hex of sha256 over the canonical JSON of every field except snapshot_id."""
    canon = json.dumps({k: v for k, v in body.items() if k != "snapshot_id"}, sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _import_server():
    """server.py (imported late: it is only needed to build the snapshot and to validate config/family.json)."""
    sys.path.insert(0, str(ROOT))
    try:
        import server  # noqa: E402
    except Exception as e:
        raise PublishError(f"could not import server.py: {e!r}") from None
    finally:
        sys.path.remove(str(ROOT))
    return server


def build_snapshot(root, data_dir, now=None):
    """Build the snapshot dict (contract section 2) by calling server.py's own read/view functions in-process.

    The data dir is first copied to a temp dir: make_server runs startup repairs that may write to it, and a
    publish must never touch the real data. `now` is injectable so tests get a deterministic snapshot_id."""
    root, data_dir = Path(root), Path(data_dir)
    server = _import_server()
    if not (data_dir / "progress.json").exists():
        raise PublishError(f"{data_dir}/progress.json does not exist")
    srv = None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "data"
        shutil.copytree(data_dir, work, ignore=shutil.ignore_patterns("archive"))
        try:
            srv = server.make_server(work, port=0)
            history = srv.mc.history
            hist = {"v": server.mcb.HISTORY_VERSION, "kind": None, "count": None, "lines": history.read(),
                    "totals": None}
            hist["count"] = len(hist["lines"])
            hist["totals"] = server.mcb.history_totals(hist["lines"])
            progress = server.read_progress(work)
            body = {
                "format": SNAPSHOT_FORMAT, "v": SNAPSHOT_V,
                "published_at": (now or datetime.now().astimezone()).isoformat(timespec="seconds"),
                "source": {"commit": git_head(root), "progress_rev": progress["rev"]},
                "progress": progress,
                "events": server.read_events(work),
                "village": server.village_view(srv),
                "treasure": strip_treasure(server.treasure_view_body(srv)),
                "history": strip_keys(hist),
                # From the COPY, the same bytes the rest of the snapshot was built from (never the live dir, which an
                # import may be appending to). The publisher API (root, data_dir, push) has no srv, so the copy itself
                # is taken without write_lock. That is safe: an import writes events and progress first and appends
                # its receipt LAST, and every import triggers another publish, so a copy that catches an import half
                # done shows events without a receipt (the browser keeps its old base: harmless) and is replaced by
                # the next publish.
                "imported": read_imports(work),
            }
        except PublishError:
            raise
        except (SystemExit, Exception) as e:
            raise PublishError(f"could not build the snapshot from {data_dir}: {e!r}") from None
        finally:
            if srv is not None:
                srv.server_close()
    body["snapshot_id"] = snapshot_id_of(body)
    return {"snapshot_id": body.pop("snapshot_id"), **body}


# ------------------------------------------------------------------------------------------------ site build

def build_site(root, snapshot, out_dir):
    """Copy app/ minus the excluded paths into out_dir, force STATIC = true, write data/family.json (validated) and snapshot.json. Returns out_dir."""
    app = Path(root) / "app"
    if not app.is_dir():
        raise PublishError(f"{app} does not exist")
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)

    def ignore(d, names):
        rel = Path(d).relative_to(app)
        skip = []
        for n in names:
            r = (rel / n).as_posix()
            if n in EXCLUDE_NAMES or r in EXCLUDE_DIRS or r in EXCLUDE_FILES:
                skip.append(n)
        return skip

    shutil.copytree(app, out_dir, ignore=ignore)
    # stories.js fetches stories/index.json and stories/<id>.json relative to the page; server.py serves them from the
    # repo-root stories/, so they are not under app/. Only top-level *.json (not .docx, ~$ temp files, backups).
    stories = Path(root) / "stories"
    if stories.is_dir():
        (out_dir / "stories").mkdir()
        for f in sorted(stories.glob("*.json")):
            shutil.copy2(f, out_dir / "stories" / f.name)
    # config/ is not under app/, so the validated family config is written where the client fetches it (data/family.json).
    srv_mod = _import_server()
    try:
        family = srv_mod.load_family_config(Path(root) / "config" / "family.json")
    except srv_mod.FamilyConfigError as e:
        raise PublishError(f"invalid family config: {e}") from None
    (out_dir / "data").mkdir(exist_ok=True)
    (out_dir / "data" / "family.json").write_text(json.dumps(family, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")
    (out_dir / "js").mkdir(exist_ok=True)
    (out_dir / "js" / "runmode.js").write_text(RUNMODE_STATIC, encoding="utf-8")
    (out_dir / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                                           encoding="utf-8")
    return out_dir


# -------------------------------------------------------------------------------------------- scrub guard

def scrub(site_dir, gamertag, private_strings=()):
    """The final loud check (contract section 4). Scans every file under site_dir byte for byte and raises
    PublishError listing EVERY finding (file and what), or returns the number of files scanned.
    private_strings (config/private_overrides.json "private_strings") are searched like the gamertag, case-insensitive;
    findings name the list position, never the word."""
    site_dir = Path(site_dir)
    # The full tag and the tag with any leading non-alphanumerics removed (Floodgate prefixes Bedrock names with "."),
    # lowercased. Findings only ever say "the gamertag", never the value.
    full = gamertag.encode("utf-8").lower()
    i = 0
    while i < len(gamertag) and not gamertag[i].isalnum():
        i += 1
    bare = gamertag[i:].encode("utf-8").lower()
    if not bare:
        raise PublishError("the gamertag has no letters or digits; the scrub guard cannot search for it")
    tags = {full, bare}
    extras = [(f"private_strings[{i}]", t.strip().encode("utf-8").lower()) for i, t in enumerate(private_strings)]
    problems = []
    n = 0
    for f in sorted(site_dir.rglob("*")):
        if not f.is_file():
            continue
        n += 1
        rel = f.relative_to(site_dir).as_posix()
        if rel.startswith("assets/mc/"):
            problems.append(f"{rel}: file under assets/mc/")
        if f.name in FORBIDDEN_NAMES:
            problems.append(f"{rel}: forbidden file {f.name}")
        data = f.read_bytes()
        if any(t in data.lower() for t in tags):
            problems.append(f"{rel}: contains the gamertag")
        for label, t in extras:
            if t in data.lower():
                problems.append(f"{rel}: contains {label}")
        for m in EMAIL_RE.finditer(data):
            problems.append(f"{rel}: email address {m.group().decode('latin-1')!r}")
        for m in IPV4_RE.finditer(data):
            if m.group() != b"127.0.0.1":
                problems.append(f"{rel}: IPv4 address {m.group().decode('latin-1')}")
        for s in FORBIDDEN_SUBSTRINGS:
            if s in data:
                problems.append(f"{rel}: contains {s.decode()!r}")
    rm = site_dir / "js" / "runmode.js"
    if not rm.is_file() or rm.read_text(encoding="utf-8") != RUNMODE_STATIC:
        problems.append("js/runmode.js: missing or not exactly 'export const STATIC = true;'")
    if problems:
        raise PublishError(f"SCRUB GUARD FOUND {len(problems)} PROBLEM(S); nothing was pushed:\n  "
                           + "\n  ".join(problems))
    return n


# ----------------------------------------------------------------------------------------------------- push

def _run(cmd, cwd=None):
    """Run a command; any failure raises PublishError with its stderr."""
    try:
        return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise PublishError(f"`{' '.join(cmd)}` failed: {getattr(e, 'stderr', '') or e}") from None


def noreply_email():
    """The GitHub no-reply commit address of the logged-in gh user (public repo: no real email in commits)."""
    login = _run(["gh", "api", "user", "--jq", ".login"])
    uid = _run(["gh", "api", "user", "--jq", ".id"])
    return login, f"{uid}+{login}@users.noreply.github.com"


def push_orphan(root, site_dir, cfg):
    """Replace work_dir with a fresh repo holding site_dir as a single orphan commit, and force-push it."""
    require_real_repo(cfg)
    build = (Path(root) / "build").resolve()
    work = (Path(root) / cfg["work_dir"]).resolve()
    if build not in work.parents:
        raise PublishError(f"work_dir {work} must be inside {build} (it is deleted and rebuilt on every publish)")
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(site_dir, work)
    (work / ".nojekyll").write_text("", encoding="utf-8")
    login, email = noreply_email()
    ident = ["-c", f"user.name={login}", "-c", f"user.email={email}"]
    branch = cfg["branch"]
    _run(["git", "init", "-q", "-b", branch], cwd=work)
    _run(["git", "remote", "add", "origin", f"https://github.com/{cfg['repo']}.git"], cwd=work)
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", *ident, "commit", "-q", "-m", "Publish the village"], cwd=work)
    _run(["git", "push", "-q", "--force", "origin", f"HEAD:{branch}"], cwd=work)


def build_and_publish(root, data_dir, push=True):
    """Build, scrub and (if push) publish. Returns {ok: True, snapshot_id, url, pushed, files}; raises PublishError."""
    root, data_dir = Path(root), Path(data_dir)
    cfg = load_web_config(root)
    gamertag = load_gamertag(root)
    snapshot = build_snapshot(root, data_dir)
    site = build_site(root, snapshot, root / "build" / "web")
    files = scrub(site, gamertag, load_private_strings(root))
    if push:
        push_orphan(root, site, cfg)
    return {"ok": True, "snapshot_id": snapshot["snapshot_id"], "url": page_url(cfg["repo"]), "pushed": push,
            "files": files}


def setup(root):
    """One-off: create the public repo if missing, publish once (Pages needs the branch to exist), enable Pages."""
    cfg = load_web_config(root)
    require_real_repo(cfg)
    exists = subprocess.run(["gh", "repo", "view", cfg["repo"]], capture_output=True).returncode == 0
    if not exists:
        _run(["gh", "repo", "create", cfg["repo"], "--public",
              "--description", "Reading Village game, web copy"])
    result = build_and_publish(root, root / "data", push=True)
    pages = subprocess.run(["gh", "api", "-X", "POST", f"repos/{cfg['repo']}/pages",
                            "-f", f"source[branch]={cfg['branch']}", "-f", "source[path]=/"],
                           capture_output=True, text=True)
    if pages.returncode != 0 and "already" not in (pages.stderr + pages.stdout).lower() \
            and "409" not in pages.stderr:
        raise PublishError(f"could not enable GitHub Pages: {pages.stderr or pages.stdout}")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-push", action="store_true", help="build and scrub only")
    ap.add_argument("--setup", action="store_true", help="create the public repo and enable Pages (once)")
    args = ap.parse_args(argv)
    try:
        r = setup(ROOT) if args.setup else build_and_publish(ROOT, ROOT / "data", push=not args.no_push)
    except PublishError as e:
        print(f"\n*** PUBLISH FAILED ***\n{e}\n", file=sys.stderr)
        return 1
    print(json.dumps(r))
    print(r["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
