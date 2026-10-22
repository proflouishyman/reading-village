#!/usr/bin/env python3
"""The Magic Chest shrine: a pagoda with a beacon, built around chest 1 (Addenda 5 and 6 of the spec).

The design is DATA: tools/shrine_blocks.json (boxes and single cells, offsets relative to the cell of chest 1).
This module turns it into absolute cells, SURVEYS every one of them in the live world, and only builds when the survey
is clean. Safety rules (the family's real world, never negotiable):

  * every target cell must hold air or a replaceable plant (short_grass, tall_grass, fern, large_fern, dead_bush,
    flowers). Anything else (stone, a tree, water, a chest that is not ours) REFUSES the build: nothing is placed and
    every blocked cell is listed;
  * there is no `fill` and no replacing of anything but a surveyed plant: each block is one `setblock` that is
    `keep` (air only) or, for a surveyed plant cell, `execute if block <cell> <that plant> run setblock ... replace`,
    so a block placed there after the survey is never overwritten (the guard fails and the build stops loudly);
  * foundations under the platform fill only air or a surveyed plant, written the same guarded way (a column stops
    at the first solid block; liquid or no ground within `max_depth` refuses the build);
  * nothing is ever placed on the world spawn point or the cell above it (config `forbidden`, plus the spawn read
    from level.dat);
  * idempotent: a tagged marker armor stand records that the shrine is ours; a re-run accepts cells that already hold
    the intended block (and the lanterns/amethyst the delivery worker adds beside overflow chests) and only fills what
    is missing.

Also here: the village-name sign beside the world spawn point and an isometric PNG render of the block list
(`python3 tools/shrine.py --render OUT.png`, using the local real textures from the Minecraft jar).
"""
import argparse
import gzip
import io
import json
import math
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import minecraft_bridge as mcb  # noqa: E402
import server  # noqa: E402  (load_family_config: the sign text is the village name)

BLOCKS_FILE = ROOT / "tools" / "shrine_blocks.json"
SPEC_VERSION = 1
MARKER_TAG = "reading_village_shrine"
SIGN_BLOCK = "minecraft:oak_sign"  # a sign type that renders on Bedrock (Geyser)
PLANTS = ("minecraft:short_grass", "minecraft:tall_grass", "minecraft:fern", "minecraft:large_fern",
          "minecraft:dead_bush", "#minecraft:flowers")
# What may sit in a "clear" cell (not a build cell) on a re-run: the chests and the lanterns / amethyst clusters the
# delivery worker places beside overflow chests (Bridge.decorate).
RERUN_OK_IDS = ("minecraft:chest", "minecraft:lantern", "minecraft:amethyst_cluster")
# Probes used only to NAME a blocked cell in the refusal message (best effort; the cell is refused either way).
BLOCK_PROBES = ("#minecraft:leaves", "#minecraft:logs", "#minecraft:dirt", "#minecraft:sand", "#minecraft:snow",
                "#minecraft:base_stone_overworld", "minecraft:water", "minecraft:lava", "minecraft:chest",
                "#minecraft:planks", "#minecraft:wool")
MAX_BLOCKED_LISTED = 60
STOP_AFTER_BLOCKED = 80  # a hopeless site is reported early instead of surveying thousands of cells
SKY_Y = 318  # a reference column of air to compare columns against (one command instead of one per cell)
BEACON_WAIT_SECONDS = 20
SIGN_LINES = 4


class ShrineError(ValueError):
    """The shrine data is invalid or breaks one of its own rules (before touching any world)."""


class SurveyRefused(RuntimeError):
    """The survey found cells that are not free; carries the blocked list. Nothing was built."""

    def __init__(self, blocked, stopped_early=False):
        self.blocked, self.stopped_early = blocked, stopped_early
        super().__init__(format_blocked(blocked, stopped_early))


def format_blocked(blocked, stopped_early=False):
    head = (f"{'at least ' if stopped_early else ''}{len(blocked)} target cells are not free (air or a replaceable "
            f"plant); NOTHING was built. Blocked cells:")
    rows = [f"  {c[0]} {c[1]} {c[2]}: {why}" for c, why in blocked[:MAX_BLOCKED_LISTED]]
    if len(blocked) > MAX_BLOCKED_LISTED:
        rows.append(f"  ... and {len(blocked) - MAX_BLOCKED_LISTED} more")
    return "\n".join([head] + rows)


# --- Data -------------------------------------------------------------------------------------------
def _need(cond, field, msg):
    if not cond:
        raise ShrineError(f"{field}: {msg}")


def _triple(v, field):
    _need(isinstance(v, list) and len(v) == 3 and all(mcb._is_int(n) for n in v), field, "must be [dx, dy, dz] integers")


def parse_block(text):
    """'minecraft:dark_oak_log[axis=y]' -> ('minecraft:dark_oak_log', '[axis=y]'); the properties part may be ''."""
    m = re.fullmatch(r"(minecraft:[a-z0-9_]+)(\[[a-z_]+=[a-z0-9_]+(?:,[a-z_]+=[a-z0-9_]+)*\])?", text)
    if not m:
        raise ShrineError(f"bad block {text!r}: must look like minecraft:name or minecraft:name[prop=value]")
    return m.group(1), m.group(2) or ""


def load_spec(path=BLOCKS_FILE):
    """Read and strictly validate the block list. Raises ShrineError."""
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ShrineError(f"{path}: cannot read as JSON ({e})") from None
    req = ("v", "name", "origin", "chests", "beacon", "sign", "foundation", "clear", "ops")
    _need(isinstance(spec, dict) and set(spec) == set(req), "spec", f"keys must be exactly {list(req)}")
    _need(spec["v"] == SPEC_VERSION, "v", f"must be {SPEC_VERSION}")
    _need(spec["chests"] and spec["chests"][0] == [0, 0, 0], "chests", "must start with chest 1 at [0, 0, 0]")
    for i, c in enumerate(spec["chests"]):
        _triple(c, f"chests[{i}]")
        for j in range(i):
            _need(max(abs(a - b) for a, b in zip(c, spec["chests"][j])) >= 3, f"chests[{i}]",
                  f"touches chests[{j}] (spots must be at least 3 apart)")
    _triple(spec["beacon"], "beacon")
    sg = spec["sign"]
    _need(set(sg) == {"at", "rotation"}, "sign", "needs exactly at, rotation (the text comes from config/family.json village_name)")
    _triple(sg["at"], "sign.at")
    _need(mcb._is_int(sg["rotation"]) and 0 <= sg["rotation"] <= 15, "sign.rotation", "must be 0..15 (0 = faces south)")
    fd = spec["foundation"]
    _need(set(fd) == {"under", "block", "max_depth"}, "foundation", "needs exactly under, block, max_depth")
    parse_block(fd["block"])
    _need(mcb._is_int(fd["max_depth"]) and 1 <= fd["max_depth"] <= 12, "foundation.max_depth", "must be 1..12")
    for i, b in enumerate(fd["under"]):
        _need(isinstance(b, list) and len(b) == 4 and all(mcb._is_int(n) for n in b) and b[0] <= b[2] and b[1] <= b[3],
              f"foundation.under[{i}]", "must be [x1, z1, x2, z2] with x1<=x2, z1<=z2")
    for i, b in enumerate(spec["clear"]):
        _need(isinstance(b, list) and len(b) == 6 and all(mcb._is_int(n) for n in b)
              and all(b[k] <= b[k + 3] for k in range(3)), f"clear[{i}]", "must be [x1, y1, z1, x2, y2, z2] low to high")
    for i, op in enumerate(spec["ops"]):
        f = f"ops[{i}]"
        _need(isinstance(op, dict) and set(op) in ({"box", "block"}, {"at", "block"}), f, "needs box+block or at+block")
        parse_block(op["block"])
        if "box" in op:
            b = op["box"]
            _need(isinstance(b, list) and len(b) == 6 and all(mcb._is_int(n) for n in b)
                  and all(b[k] <= b[k + 3] for k in range(3)), f"{f}.box", "must be [x1, y1, z1, x2, y2, z2] low to high")
        else:
            _triple(op["at"], f"{f}.at")
    return spec


SIGN_LINE_MAX = 15  # characters a sign line holds


def sign_lines(village_name):
    """village_name (config/family.json) -> the SIGN_LINES sign lines: words wrapped greedily at SIGN_LINE_MAX
    characters, padded with empty lines. Raises ShrineError when a word is too long or the name needs more lines
    (loud: a sign must never silently show a cut-off name)."""
    lines = []
    for word in village_name.split():
        _need(len(word) <= SIGN_LINE_MAX, "village_name", f"the word {word!r} is longer than {SIGN_LINE_MAX} characters")
        if lines and len(lines[-1]) + 1 + len(word) <= SIGN_LINE_MAX:
            lines[-1] += " " + word
        else:
            lines.append(word)
    _need(lines, "village_name", "is empty")
    _need(len(lines) <= SIGN_LINES, "village_name", f"needs {len(lines)} sign lines; a sign has {SIGN_LINES}")
    for t in lines:
        _need('"' not in t and "\\" not in t, "village_name", "must not contain quotes or backslashes (sign text)")
    return lines + [""] * (SIGN_LINES - len(lines))


class Plan:
    """The spec placed at an origin: absolute cells, in build order.

    cells      {(x, y, z): 'minecraft:block[props]'} the blocks the build places (the sign included, last)
    clear      set of cells that must be free but get nothing from the build (hall interior, beam column, chest spots)
    chests     [{'x','y','z'}] chest spots in config order (chest 1 first)
    beacon     (x, y, z)
    sign       {'cell', 'rotation', 'lines'}
    columns    [(x, z)] every column the platform covers (foundations are checked under each)
    platform_y y of the platform layer (= chest y - 1)
    """

    def __init__(self, spec, origin, village_name):
        ox, oy, oz = origin["x"], origin["y"], origin["z"]
        self.origin = (ox, oy, oz)

        def absolute(t):
            return (ox + t[0], oy + t[1], oz + t[2])
        self.spec = spec
        self.cells = {}
        for op in spec["ops"]:
            if "at" in op:
                self.cells[absolute(op["at"])] = op["block"]
            else:
                x1, y1, z1, x2, y2, z2 = op["box"]
                for x in range(x1, x2 + 1):
                    for y in range(y1, y2 + 1):
                        for z in range(z1, z2 + 1):
                            self.cells[absolute((x, y, z))] = op["block"]
        self.chests = [{"x": ox + c[0], "y": oy + c[1], "z": oz + c[2]} for c in spec["chests"]]
        self.chest_cells = [(c["x"], c["y"], c["z"]) for c in self.chests]
        self.beacon = absolute(spec["beacon"])
        sg = spec["sign"]
        self.sign = {"cell": absolute(sg["at"]), "rotation": sg["rotation"], "lines": sign_lines(village_name)}
        self.cells[self.sign["cell"]] = f"{SIGN_BLOCK}[rotation={sg['rotation']}]"
        self.clear = set()
        for x1, y1, z1, x2, y2, z2 in spec["clear"]:
            for x in range(x1, x2 + 1):
                for y in range(y1, y2 + 1):
                    for z in range(z1, z2 + 1):
                        self.clear.add(absolute((x, y, z)))
        self.clear |= set(self.chest_cells)
        self.clear -= set(self.cells)
        self.platform_y = oy - 1
        self.columns = sorted({(ox + x, oz + z) for x1, z1, x2, z2 in spec["foundation"]["under"]
                               for x in range(x1, x2 + 1) for z in range(z1, z2 + 1)})
        self.check()

    def check(self):
        """The design's own rules (loud, before any command is sent)."""
        bx, by, bz = self.beacon
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                block = self.cells.get((bx + dx, by - 1, bz + dz))
                _need(block == "minecraft:iron_block", "beacon", f"needs a 3x3 iron_block base under it; cell "
                      f"{bx + dx} {by - 1} {bz + dz} is {block}")
        _need(self.cells.get(self.beacon) == "minecraft:beacon", "beacon", "the beacon cell must hold minecraft:beacon")
        for (x, y, z), block in self.cells.items():
            if (x, z) == (bx, bz) and y > by:
                _need("stained_glass" in block or block.startswith("minecraft:glass"), "beacon",
                      f"{block} at {x} {y} {z} would block the beam (only glass may stand above the beacon)")
        for c in self.chest_cells:
            _need(c not in self.cells, "chests", f"chest spot {c} is also a build cell")
        _need(set(self.chest_cells[0]) and self.chest_cells[0] == self.origin, "chests", "chest 1 must be the origin")

    def all_cells(self):
        return set(self.cells) | self.clear

    def blocks_in_order(self):
        """[(cell, block id, properties)] in build order (supports before the blocks that hang from them)."""
        return [(c, *parse_block(b)) for c, b in self.cells.items()]

    def foundation_block(self):
        return parse_block(self.spec["foundation"]["block"])


def chests_for(spec, origin):
    """The config.chests list a shrine at `origin` implies (tests and the install tool compare config to this)."""
    return Plan(spec, origin, "Village").chests


# --- Spawn point from level.dat ---------------------------------------------------------------------
def _nbt_read(f, t):
    if t == 1:
        return struct.unpack(">b", f.read(1))[0]
    if t == 2:
        return struct.unpack(">h", f.read(2))[0]
    if t == 3:
        return struct.unpack(">i", f.read(4))[0]
    if t == 4:
        return struct.unpack(">q", f.read(8))[0]
    if t == 5:
        return struct.unpack(">f", f.read(4))[0]
    if t == 6:
        return struct.unpack(">d", f.read(8))[0]
    if t == 7:
        return list(f.read(struct.unpack(">i", f.read(4))[0]))
    if t == 8:
        return f.read(struct.unpack(">H", f.read(2))[0]).decode("utf-8", "replace")
    if t == 9:
        et, n = f.read(1)[0], struct.unpack(">i", f.read(4))[0]
        return [_nbt_read(f, et) for _ in range(n)]
    if t == 10:
        out = {}
        while True:
            tt = f.read(1)[0]
            if tt == 0:
                return out
            name = f.read(struct.unpack(">H", f.read(2))[0]).decode("utf-8")
            out[name] = _nbt_read(f, tt)
    if t == 11:
        n = struct.unpack(">i", f.read(4))[0]
        return list(struct.unpack(f">{n}i", f.read(4 * n)))
    if t == 12:
        n = struct.unpack(">i", f.read(4))[0]
        return list(struct.unpack(f">{n}q", f.read(8 * n)))
    raise ShrineError(f"level.dat: unknown NBT tag type {t}")


def read_spawn(mc_dir):
    """The world spawn point {'x','y','z','yaw'} from <mc_dir>/world/level.dat (26.x layout: Data.spawn.pos).
    READ-ONLY. Raises ShrineError when the file or the field is not there; never guesses."""
    path = Path(mc_dir) / "world" / "level.dat"
    try:
        f = io.BytesIO(gzip.open(path).read())
        f.read(1)
        f.read(struct.unpack(">H", f.read(2))[0])
        data = _nbt_read(f, 10)["Data"]
        x, y, z = data["spawn"]["pos"]
        return {"x": x, "y": y, "z": z, "yaw": data["spawn"].get("yaw", 0.0)}
    except (OSError, KeyError, ValueError, TypeError, struct.error, IndexError) as e:
        raise ShrineError(f"cannot read the world spawn point from {path}: {type(e).__name__}: {e}") from None


# --- Survey -----------------------------------------------------------------------------------------
class Survey:
    """What the survey found: modes {cell: 'air'|'plant'|'ours'} for every cell the build may write, the foundation
    cells to fill, and `blocked` [(cell, reason)] (non-empty = refuse)."""

    def __init__(self):
        self.modes = {}
        self.foundation = {}
        self.plants = {}  # cell -> the plant probe (block id or #tag) the survey matched there; guards its write
        self.blocked = []
        self.stopped_early = False
        self.commands = 0


def _p(cell):
    return f"{cell[0]} {cell[1]} {cell[2]}"


def _runs(cells):
    """Group cells into vertical runs [(x, z, y_low, y_high)] of consecutive y in one column."""
    cols = {}
    for x, y, z in cells:
        cols.setdefault((x, z), []).append(y)
    out = []
    for (x, z), ys in sorted(cols.items()):
        ys.sort()
        lo = prev = ys[0]
        for y in ys[1:]:
            if y != prev + 1:
                out.append((x, z, lo, prev))
                lo = y
            prev = y
        out.append((x, z, lo, prev))
    return out


class Surveyor:
    """Classifies cells through a Bridge (any transport, so tests run on the fake). Counts the commands it sends."""

    def __init__(self, bridge, marker_present, log=lambda m: None):
        self.b, self.marker, self.log = bridge, marker_present, log
        self.n = 0
        self.plant_probe = None  # which PLANTS entry the last "plant" classification matched

    def test(self, cmd):
        self.n += 1
        return self.b.test(cmd)

    def is_block(self, cell, block):
        return self.test(f"execute if block {_p(cell)} {block}")

    def name_of(self, cell):
        for probe in BLOCK_PROBES:
            if self.is_block(cell, probe):
                return probe
        return "something that is not air or a plant"

    def classify(self, cell, intended_id):
        """'air' | 'plant' | 'ours' | ('blocked', why)."""
        if self.marker and intended_id and self.is_block(cell, intended_id):
            return "ours"
        if self.is_block(cell, "minecraft:air") or self.is_block(cell, "minecraft:cave_air"):
            return "air"
        if not self.is_block(cell, "#minecraft:replaceable"):
            return ("blocked", self.name_of(cell))
        if self.is_block(cell, "minecraft:water") or self.is_block(cell, "minecraft:lava"):
            return ("blocked", "liquid")
        for plant in PLANTS:
            if self.is_block(cell, plant):
                self.plant_probe = plant
                return "plant"
        return ("blocked", "a replaceable block that is not a plant (snow?)")

    def column_is_air(self, x, z, y_lo, y_hi):
        """One command: the cells x,y_lo..y_hi,z all equal the same-sized column of sky."""
        n = y_hi - y_lo + 1
        ref = SKY_Y - n + 1
        return self.test(f"execute if blocks {x} {y_lo} {z} {x} {y_hi} {z} {x} {ref} {z} all")


def survey(bridge, plan, marker_present, log=lambda m: None, forbidden=()):
    """Survey EVERY cell the build can touch before anything is built. Returns a Survey; `blocked` empty = clean.

    Cells: the build cells and the clear cells (free or, on a re-run, already ours) and the foundation columns under
    the platform (air/plants above the first solid block, which is where a column stops)."""
    s = Survey()
    sv = Surveyor(bridge, marker_present, log)
    forb = mcb.forbidden_set(forbidden)
    intended = {c: parse_block(b)[0] for c, b in plan.cells.items()}
    for c in plan.chest_cells:
        intended[c] = "minecraft:chest"
    cells = plan.all_cells()
    for c in sorted(cells & forb):
        s.blocked.append((c, "the world spawn point (forbidden)"))
    ok_cells = cells - forb

    def refuse(cell, why):
        s.blocked.append((cell, why))
        if len(s.blocked) >= STOP_AFTER_BLOCKED:
            s.stopped_early = True
            return True
        return False

    # 1) the columns that are entirely air, one command per run; the rest cell by cell
    todo = []
    # A fresh build expects every cell to be air, so whole columns are tested with one command. On a re-run the build
    # cells mostly hold their blocks: only the clear-only cells go through the column test, the rest cell by cell.
    column_cells = ok_cells - set(plan.cells) if marker_present else ok_cells
    todo += sorted(c for c in ok_cells if c not in column_cells)
    for x, z, lo, hi in _runs(column_cells):
        if hi > lo and sv.column_is_air(x, z, lo, hi):
            for y in range(lo, hi + 1):
                s.modes[(x, y, z)] = "air"
        else:
            todo += [(x, y, z) for y in range(lo, hi + 1)]
    log(f"surveying {len(todo)} cells one by one ({len(ok_cells) - len(todo)} cells passed as whole air columns)")
    for cell in todo:
        r = sv.classify(cell, intended.get(cell))
        if r in ("ours", "air", "plant"):
            s.modes[cell] = r
            if r == "plant":
                s.plants[cell] = sv.plant_probe
            continue
        # blocked. On a re-run a clear cell may hold a chest or what the delivery worker put beside one.
        if marker_present and cell not in plan.cells and any(sv.is_block(cell, i) for i in RERUN_OK_IDS):
            s.modes[cell] = "ours"
        elif refuse(cell, r[1]):
            return _finish(s, sv)
    # 2) foundations: under every platform column, air/plants down to the first solid block
    fblock = plan.foundation_block()[0]
    depth_max = plan.spec["foundation"]["max_depth"]
    for x, z in plan.columns:
        if (x, plan.platform_y, z) in forb:
            continue
        for depth in range(1, depth_max + 1):
            cell = (x, plan.platform_y - depth, z)
            if cell in forb:
                refuse(cell, "the world spawn point (forbidden)")
                break
            if not sv.is_block(cell, "#minecraft:replaceable"):
                break  # solid ground reached: the foundation (if any) ends here
            if sv.is_block(cell, "minecraft:water") or sv.is_block(cell, "minecraft:lava"):
                if refuse(cell, "liquid under the platform"):
                    return _finish(s, sv)
                break
            r = sv.classify(cell, None)
            if r in ("air", "plant"):
                s.foundation[cell] = r
                if r == "plant":
                    s.plants[cell] = sv.plant_probe
            else:
                if refuse(cell, r[1]):
                    return _finish(s, sv)
                break
        else:
            if refuse((x, plan.platform_y - depth_max, z), f"no solid ground within {depth_max} blocks below the platform"):
                return _finish(s, sv)
    return _finish(s, sv)


def _finish(s, sv):
    s.commands = sv.n
    return s


# --- Build ------------------------------------------------------------------------------------------
def ask_set(bridge, cell, block, mode, plant=None):
    """One setblock; the reply must be 'Changed the block' (a refusal raises, naming the cell). mode 'air' = `keep`.
    mode 'plant' = the survey found `plant` (a block id or #tag) there: the write is
    `execute if block <cell> <plant> run setblock ... replace`, so it only happens while that plant is still there;
    if the guard fails (nothing answers, or the game says so) the build stops loudly instead of overwriting."""
    if mode == "plant":
        if not plant:
            raise mcb.McError(f"setblock {block} at {_p(cell)}: a plant cell with no recorded plant (survey bug)")
        cmd = f"execute if block {_p(cell)} {plant} run setblock {_p(cell)} {block} replace"
    else:
        cmd = f"setblock {_p(cell)} {block} keep"
    try:
        name, m = bridge.ask(cmd, {"yes": r"^Changed the block", "no": r"^Could not set the block|^Test failed"})
    except mcb.McError as e:
        if mode == "plant":
            raise mcb.McError(f"setblock {block} at {_p(cell)} did not happen: the {plant} that was surveyed there is "
                              f"gone or changed (a block was placed after the survey); nothing was overwritten ({e})") from None
        raise
    if name != "yes":
        raise mcb.McError(f"setblock {block} at {_p(cell)} was refused ({m.string}); the cell changed since the survey")


def sign_nbt(lines):
    msgs = ",".join('{text:"%s"}' % t for t in lines)
    return "{is_waxed:1b,front_text:{messages:[%s]}}" % msgs


def marker_exists(bridge, plan):
    x, y, z = plan.origin
    name, _ = bridge.ask(f"execute if entity @e[type=minecraft:armor_stand,tag={MARKER_TAG},x={x},y={y},z={z},distance=..3]",
                         {"yes": r"^Test passed", "no": r"^Test failed"})
    return name == "yes"


def ensure_marker(bridge, plan):
    """The invisible marker armor stand that says 'this shrine is ours'. Returns True when it was created."""
    if marker_exists(bridge, plan):
        return False
    x, y, z = plan.origin
    bridge.ask(f"summon minecraft:armor_stand {x + 0.5} {y + 0.2} {z + 0.5} "
               f'{{Invisible:1b,Marker:1b,NoGravity:1b,Tags:["{MARKER_TAG}"]}}', {"ok": r"Summoned new"})
    return True


def build(bridge, plan, sv, log=lambda m: None):
    """Place everything the survey cleared. Returns counts {'foundation','placed','kept','sign'}.
    The marker is created FIRST so a half-finished build is repaired (not refused) by the next run."""
    if sv.blocked:
        raise SurveyRefused(sv.blocked, sv.stopped_early)
    log(f"marker: {'created' if ensure_marker(bridge, plan) else 'already there'}")
    counts = {"foundation": 0, "placed": 0, "kept": 0, "sign": 0}
    fid, fprops = plan.foundation_block()
    for cell, mode in sorted(sv.foundation.items(), key=lambda kv: -kv[0][1]):  # from the top down: nothing floats
        ask_set(bridge, cell, fid + fprops, mode, sv.plants.get(cell))
        counts["foundation"] += 1
    for cell, bid, props in plan.blocks_in_order():
        mode = sv.modes.get(cell)
        if mode == "ours":
            counts["kept"] += 1
            continue
        if cell == plan.sign["cell"]:
            ask_set(bridge, cell, f"{bid}{props}{sign_nbt(plan.sign['lines'])}", mode, sv.plants.get(cell))
            counts["sign"] += 1
            continue
        ask_set(bridge, cell, bid + props, mode, sv.plants.get(cell))
        counts["placed"] += 1
    return counts


def beacon_levels(bridge, plan, wait=BEACON_WAIT_SECONDS, sleep=None):
    """Poll the beacon's Levels until it is >= 1 (active). Returns the level; raises McError if it never activates."""
    import time
    sleep = sleep or time.sleep
    x, y, z = plan.beacon
    last = None
    for _ in range(max(1, int(wait))):
        name, m = bridge.ask(f"data get block {x} {y} {z} Levels", {"lv": r"block data: (-?\d+)",
                                                                       "none": r"not a block entity"})
        if name == "lv":
            last = int(m.group(1))
            if last >= 1:
                return last
        sleep(1)
    raise mcb.McError(f"the beacon at {x} {y} {z} did not activate within {wait}s (Levels={last}): its iron base or the "
                      f"sky above it is blocked")


# --- The village-name sign beside the spawn point -----------------------------------------------
def sign_rotation_towards(frm, target):
    """Sign rotation (0 = south, 4 = west, 8 = north, 12 = east) for text that faces from `frm` towards `target`."""
    vx, vz = target[0] - frm[0], target[2] - frm[2]
    return round(16 * math.atan2(-vx, vz) / (2 * math.pi)) % 16


def spawn_sign_candidates(spawn, avoid):
    """Cells beside the spawn point, nearest ring first, level with it before one step up; the spawn cell and anything
    in `avoid` (forbidden cells, shrine cells) excluded."""
    sx, sy, sz = spawn["x"], spawn["y"], spawn["z"]
    out = []
    for ring in (1, 2):
        cells = [(sx + dx, sz + dz) for dx in range(-ring, ring + 1) for dz in range(-ring, ring + 1)
                 if max(abs(dx), abs(dz)) == ring]
        # the south side first (where a player who spawns looking south sees it), diagonals before straight ahead
        cells.sort(key=lambda c: (-(c[1] - sz), abs(c[0] - sx) == 0))
        for dy in (0, 1):
            out += [(x, sy + dy, z) for x, z in cells]
    return [c for c in out if c not in avoid and (c[0], c[1], c[2]) != (sx, sy, sz)]


def find_spawn_sign(bridge, spawn, avoid, forbidden=(), first_line=None):
    """('exists', cell) when one of our signs already stands beside the spawn, else ('place', cell, rotation) for the
    first candidate that is free (air or plant), has solid ground below and is not forbidden. Raises McError when no
    candidate fits (loud: nothing is placed). Surveys only; places nothing. `first_line` is the first sign line
    (sign_lines(village_name)[0]); an oak sign whose text holds it counts as ours. Required."""
    _need(first_line, "first_line", "required: the village sign's first line identifies our sign")
    forb = mcb.forbidden_set(forbidden)
    cands = [c for c in spawn_sign_candidates(spawn, avoid) if c not in forb]
    for c in cands:
        if bridge.test(f"execute if block {_p(c)} {SIGN_BLOCK}"):
            name, m = bridge.ask(f"data get block {_p(c)} front_text.messages", {"msg": r"block data: (\[.*\])", "no": r"Found no"})
            if name == "msg" and first_line in m.group(1):
                return ("exists", c)
    sv = Surveyor(bridge, False)
    for c in cands:
        if sv.classify(c, None) in ("air", "plant") and bridge.test(
                f"execute unless block {c[0]} {c[1] - 1} {c[2]} #minecraft:replaceable"):
            mode = sv.classify(c, None)
            return ("place", c, sign_rotation_towards(c, (spawn["x"], spawn["y"], spawn["z"])), mode, sv.plant_probe)
    raise mcb.McError(f"no free cell with solid ground beside the spawn point {spawn['x']} {spawn['y']} {spawn['z']} "
                      f"for the sign ({len(cands)} candidates checked); nothing placed")


def place_spawn_sign(bridge, found, lines):
    """Place the sign chosen by find_spawn_sign. Returns 'exists' or 'placed'."""
    if found[0] == "exists":
        return "exists"
    _, cell, rot, mode, plant = found
    ask_set(bridge, cell, f"{SIGN_BLOCK}[rotation={rot}]{sign_nbt(lines)}", mode, plant)
    return "placed"


def main():
    ap = argparse.ArgumentParser(description="Inspect or render the Magic Chest shrine (never touches a server)")
    ap.add_argument("--blocks", default=str(BLOCKS_FILE))
    ap.add_argument("--origin", nargs=3, type=int, metavar=("X", "Y", "Z"), help="cell of chest 1 (default: config shrine)")
    ap.add_argument("--render", metavar="OUT.png", help="write an isometric picture of the block list")
    ap.add_argument("--jar", default=str(Path.home() / "Library/Application Support/minecraft/versions/26.3/26.3.jar"))
    ap.add_argument("--scale", type=int, default=5)
    ap.add_argument("--chests", action="store_true", help="print the config.chests list this shrine implies")
    args = ap.parse_args()
    try:
        spec = load_spec(args.blocks)
        if args.origin:
            origin = dict(zip("xyz", args.origin))
        else:
            origin = json.loads((ROOT / "config" / "minecraft.json").read_text())["shrine"]
        plan = Plan(spec, origin, server.load_family_config()["village_name"])
        print(f"{spec['name']}\n  origin {_p(plan.origin)}; {len(plan.cells)} blocks, {len(plan.clear)} clear cells, "
              f"{len(plan.chests)} chest spots, beacon at {_p(plan.beacon)}")
        if args.chests:
            print(json.dumps(plan.chests))
        if args.render:
            import shrine_render
            size = shrine_render.render_iso(plan, args.jar, args.render, scale=args.scale)
            print(f"  rendered {args.render} {size[0]}x{size[1]}")
    except (ShrineError, OSError, KeyError, server.FamilyConfigError) as e:
        print(f"\n*** FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
