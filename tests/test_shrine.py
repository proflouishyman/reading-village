"""The Magic Chest shrine and the village-name signs: block-list rules, survey-then-build safety, idempotence,
the spawn sign and the install tool's config checks. Runs against FakeWorld (below), a small in-memory block world that
answers the console commands tools/shrine.py sends; the real thing was built and checked on a Paper test copy."""
import contextlib
import copy
import gzip
import io
import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import minecraft_bridge as mcb  # noqa: E402
import minecraft_install  # noqa: E402
import shrine  # noqa: E402

CFG = json.loads((ROOT / "config" / "minecraft.json").read_text())
SPEC = shrine.load_spec()
VILLAGE = "Sam's Village"  # sign text comes from config/family.json village_name
JAR = Path.home() / "Library/Application Support/minecraft/versions/26.3/26.3.jar"
PLANTS = ("minecraft:short_grass", "minecraft:tall_grass", "minecraft:fern", "minecraft:large_fern", "minecraft:dead_bush",
          "minecraft:dandelion")
TAGS = {
    "#minecraft:replaceable": {"minecraft:air", "minecraft:cave_air", "minecraft:water", "minecraft:lava", "minecraft:snow",
                               *PLANTS},
    "#minecraft:flowers": {"minecraft:dandelion"},
    "#minecraft:leaves": {"minecraft:oak_leaves"},
    "#minecraft:logs": {"minecraft:oak_log"},
    "#minecraft:dirt": {"minecraft:dirt", "minecraft:grass_block"},
    "#minecraft:base_stone_overworld": {"minecraft:stone"},
}


class FakeWorld:
    """Answers the console commands of tools/shrine.py and the Bridge. Flat world: ground_y is the top solid layer;
    `overrides` {cell: block id} puts anything anywhere. Records every command in `sent`."""

    def __init__(self, ground_y=64, ground_for=None):
        self.ground_y = ground_y
        self.ground_for = ground_for or {}  # (x, z) -> ground y for that column (uneven terrain)
        self.blocks = {}  # cell -> full block string (what setblock wrote, or an override)
        self.log, self._ptr, self.sent = [], 0, []
        self.entities = []
        self.running = True
        self.nbt = {}

    # transport interface
    def server_running(self):
        return self.running

    def skip_to_end(self):
        self._ptr = len(self.log)

    def new_lines(self):
        out = [f"[12:00:00] [Server thread/INFO]: System chat: {t}" for t in self.log[self._ptr:]]
        self._ptr = len(self.log)
        return out

    def send(self, cmd):
        self.sent.append(cmd)
        self._handle(cmd)

    # world
    def block_id(self, cell):
        if cell in self.blocks:
            return self.blocks[cell].split("[")[0].split("{")[0]
        x, y, z = cell
        g = self.ground_for.get((x, z), self.ground_y)
        if y < g:
            return "minecraft:stone"
        if y == g:
            return "minecraft:grass_block"
        return "minecraft:air"

    def matches(self, cell, want):
        want = want.split("[")[0]
        have = self.block_id(cell)
        if want.startswith("#"):
            return have in TAGS.get(want, set())
        if want == "minecraft:sign":
            return have.endswith("_sign")
        return have == want

    def say(self, t):
        self.log.append(t)

    def _handle(self, cmd):
        num = r"(-?\d+)"
        if cmd.startswith("forceload add"):
            return self.say("Marked chunk 0, 0 to be force loaded")
        m = re.match(rf"execute (if|unless) block {num} {num} {num} (\S+)$", cmd)
        if m:
            cell = tuple(int(g) for g in m.groups()[1:4])
            ok = self.matches(cell, m.group(5)) == (m.group(1) == "if")
            return self.say("Test passed" if ok else "Test failed")
        m = re.match(rf"execute if blocks {num} {num} {num} {num} {num} {num} {num} {num} {num} all$", cmd)
        if m:
            x, y1, z, _x2, y2, _z2, _dx, ref, _dz = (int(g) for g in m.groups())
            ok = all(self.block_id((x, y, z)) == "minecraft:air" for y in range(y1, y2 + 1))
            return self.say(f"Test passed. Count: {y2 - y1 + 1}" if ok else "Test failed")
        m = re.match(rf"execute if block {num} {num} {num} (\S+) run (setblock .*)$", cmd)
        if m:  # the guarded write: runs only while the surveyed plant is still there, silent otherwise (as in the game)
            cell = tuple(int(g) for g in m.groups()[:3])
            if self.matches(cell, m.group(4)):
                return self._handle(m.group(5))
            return
        m = re.match(rf"setblock {num} {num} {num} (\S+?)(\{{.*\}})? (keep|replace)$", cmd)
        if m:
            cell = tuple(int(g) for g in m.groups()[:3])
            block, nbt, mode = m.group(4), m.group(5), m.group(6)
            if mode == "keep" and self.block_id(cell) != "minecraft:air":
                return self.say("Could not set the block")
            self.blocks[cell] = block
            if nbt:
                self.nbt[cell] = nbt
            return self.say(f"Changed the block at {cell[0]}, {cell[1]}, {cell[2]}")
        if cmd.startswith("execute if entity"):
            return self.say("Test passed" if self.entities else "Test failed")
        if cmd.startswith("summon"):
            self.entities.append(cmd)
            return self.say("Summoned new Armor Stand")
        m = re.match(rf"data get block {num} {num} {num} Levels$", cmd)
        if m:
            cell = tuple(int(g) for g in m.groups())
            return self.say(f"{cell[0]}, {cell[1]}, {cell[2]} has the following block data: "
                            f"{1 if self.block_id(cell) == 'minecraft:beacon' else 0}")
        m = re.match(rf"data get block {num} {num} {num} front_text.messages$", cmd)
        if m:
            cell = tuple(int(g) for g in m.groups())
            texts = re.findall(r'text:"([^"]*)"', self.nbt.get(cell, ""))
            if not texts:
                return self.say("Found no elements matching front_text.messages")
            return self.say(f'{cell[0]}, {cell[1]}, {cell[2]} has the following block data: '
                            f'[{", ".join(json.dumps(t) for t in texts)}]')
        m = re.match(rf"data get block {num} {num} {num} CustomName$", cmd)
        if m:
            cell = tuple(int(g) for g in m.groups())
            if self.block_id(cell) == "minecraft:chest":
                return self.say('has the following block data: {bold: 1b, color: "gold", text: "Magic Chest"}')
            return self.say("Found no elements matching CustomName")
        m = re.match(rf"data get block {num} {num} {num} Items$", cmd)
        if m:
            return self.say("has the following block data: []")
        raise AssertionError(f"FakeWorld got an unexpected command: {cmd}")

    def placed(self):
        return [c for c in self.sent if c.startswith("setblock") or " run setblock " in c]


def bridge_for(world):
    return mcb.Bridge(world, CFG["chests"], reply_timeout=0.05, sleep=lambda s: None, forbidden=CFG["forbidden"])


def plan_at(ground_y=64, origin=None):
    o = origin or {"x": 100, "y": ground_y + 2, "z": 100}  # platform at ground_y + 1, chest one above
    return shrine.Plan(SPEC, o, VILLAGE)


class SpecRules(unittest.TestCase):
    def test_spec_loads_and_is_bedrock_friendly(self):
        ids = {shrine.parse_block(b)[0].split(":")[1] for b in (op["block"] for op in SPEC["ops"])}
        allowed = {"stone_bricks", "polished_andesite", "polished_blackstone_bricks", "iron_block", "sea_lantern",
                   "glowstone", "dark_oak_log", "stripped_dark_oak_log", "dark_oak_planks", "dark_oak_stairs",
                   "dark_oak_slab", "crimson_stairs", "dark_oak_fence", "lantern", "soul_lantern", "end_rod",
                   "amethyst_cluster", "amethyst_block", "beacon", "purple_stained_glass"}
        self.assertLessEqual(ids, allowed)  # every block renders on Bedrock (checked list); a new one is a decision
        self.assertTrue({"beacon", "lantern", "end_rod", "sea_lantern", "amethyst_cluster"} <= ids)

    def test_chest_spots_are_inside_the_hall_three_apart_and_chest_one_is_the_middle(self):
        self.assertEqual(SPEC["chests"][0], [0, 0, 0])
        for c in SPEC["chests"]:
            self.assertTrue(abs(c[0]) <= 3 and abs(c[2]) <= 3 and c[1] == 0, c)  # inside the 9x9 hall
        for i, a in enumerate(SPEC["chests"]):
            for b in SPEC["chests"][:i]:
                self.assertGreaterEqual(max(abs(p - q) for p, q in zip(a, b)), 3)  # never touching: no double chests

    def test_beacon_has_an_iron_base_and_only_glass_above(self):
        plan = plan_at()
        bx, by, bz = plan.beacon
        self.assertEqual({plan.cells[(bx + dx, by - 1, bz + dz)] for dx in (-1, 0, 1) for dz in (-1, 0, 1)},
                         {"minecraft:iron_block"})
        above = [b for (x, y, z), b in plan.cells.items() if (x, z) == (bx, bz) and y > by]
        self.assertEqual(above, ["minecraft:purple_stained_glass"])
        bad = copy.deepcopy(SPEC)
        bad["ops"].append({"at": [0, 5, 9], "block": "minecraft:dark_oak_planks"})
        with self.assertRaises(shrine.ShrineError) as cm:
            shrine.Plan(bad, {"x": 0, "y": 70, "z": 0}, VILLAGE)
        self.assertIn("beam", str(cm.exception))
        bad = copy.deepcopy(SPEC)
        bad["ops"].append({"at": [1, -1, 9], "block": "minecraft:stone_bricks"})  # a hole in the 3x3 base
        with self.assertRaises(shrine.ShrineError) as cm:
            shrine.Plan(bad, {"x": 0, "y": 70, "z": 0}, VILLAGE)
        self.assertIn("iron_block", str(cm.exception))

    def test_the_hall_roof_never_covers_the_beacon_column(self):
        plan = plan_at()
        bx, _by, bz = plan.beacon
        roof_cells = [c for c in plan.cells if c[1] >= plan.origin[1] + 5]
        self.assertTrue(all(abs(c[0] - bx) > 1 or abs(c[2] - bz) > 1 for c in roof_cells))

    def test_no_build_cell_is_a_chest_spot_and_sign_is_in_the_plan(self):
        plan = plan_at()
        self.assertFalse(set(plan.chest_cells) & set(plan.cells))
        self.assertIn(plan.sign["cell"], plan.cells)
        self.assertEqual(plan.sign["lines"], ["Sam's Village", "", "", ""])

    def test_validation_names_the_field(self):
        for mutate, field in ((lambda s: s.update(v=2), "v"), (lambda s: s["chests"].append([1, 0, 0]), "chests[9]"),
                              (lambda s: s["ops"].append({"at": [0, 0, 0], "block": "stone"}), "bad block"),
                              (lambda s: s["sign"].update(rotation=99), "sign.rotation"),
                              (lambda s: s.pop("beacon"), "keys must be exactly")):
            spec = copy.deepcopy(SPEC)
            mutate(spec)
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "s.json"
                p.write_text(json.dumps(spec))
                with self.assertRaises(shrine.ShrineError) as cm:
                    shrine.load_spec(p)
                self.assertIn(field, str(cm.exception))


class ShippedConfigAndSpawn(unittest.TestCase):
    def test_config_chests_are_the_shrines_spots(self):
        self.assertEqual(CFG["chests"], shrine.Plan(SPEC, CFG["shrine"], VILLAGE).chests)
        self.assertEqual(CFG["chests"][0], CFG["shrine"])

    def test_the_spawn_point_is_forbidden_and_no_shrine_cell_is_on_it(self):
        spawn = (108, 65, 90)
        self.assertIn({"x": 108, "y": 65, "z": 90}, CFG["forbidden"])
        plan = shrine.Plan(SPEC, CFG["shrine"], VILLAGE)
        forb = mcb.forbidden_set(CFG["forbidden"])
        self.assertFalse(plan.all_cells() & forb)
        self.assertFalse({(x, z) for x, _y, z in plan.all_cells()} & {(spawn[0], spawn[2])})
        self.assertFalse({(x, z) for x, z in plan.columns} & {(spawn[0], spawn[2])})

    def test_install_refuses_a_config_whose_chests_are_not_the_shrines(self):
        plan = shrine.Plan(SPEC, CFG["shrine"], VILLAGE)
        cfg = copy.deepcopy(CFG)
        cfg["chests"][1]["x"] += 1
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            minecraft_install.check_config_matches_shrine(cfg, plan, "cfg")
        minecraft_install.check_config_matches_shrine(CFG, plan, "cfg")

    def test_install_refuses_when_the_spawn_is_not_forbidden(self):
        cfg = copy.deepcopy(CFG)
        cfg["forbidden"] = []
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            minecraft_install.check_spawn_is_forbidden(cfg, {"x": 108, "y": 65, "z": 90}, "cfg")
        minecraft_install.check_spawn_is_forbidden(CFG, {"x": 108, "y": 65, "z": 90}, "cfg")

    def _props(self, text):
        d = tempfile.mkdtemp()
        if text is not None:
            (Path(d) / "server.properties").write_text(text)
        return d

    def _protection(self, text, spawn):
        plan = shrine.Plan(SPEC, CFG["shrine"], VILLAGE)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                minecraft_install.check_spawn_protection(self._props(text), plan, spawn)
                return None, err.getvalue()
            except SystemExit as e:
                return e.code, err.getvalue()

    def test_spawn_protection_covering_the_shrine_fails_loudly(self):
        code, err = self._protection("spawn-protection=16\n", {"x": 108, "y": 65, "z": 90})
        self.assertEqual(code, 1)
        self.assertIn("FAILED", err)
        self.assertIn("spawn-protection=16", err)
        self.assertIn("spawn-protection=0", err)

    def test_spawn_protection_zero_passes(self):
        self.assertEqual(self._protection("spawn-protection=0\n", {"x": 108, "y": 65, "z": 90})[0], None)

    def test_shrine_outside_the_protected_square_passes(self):
        # the pure rule: spawn far away, r=16 cannot reach the shrine; near spawn it does
        plan = shrine.Plan(SPEC, CFG["shrine"], VILLAGE)
        far = {"x": 5000, "y": 65, "z": 5000}
        self.assertEqual(minecraft_install.spawn_protected(plan.all_cells(), far, 16), [])
        self.assertTrue(minecraft_install.spawn_protected(plan.all_cells(), {"x": 108, "y": 65, "z": 90}, 16))

    def test_protected_square_edge_is_inclusive(self):
        sp = {"x": 0, "y": 0, "z": 0}
        self.assertEqual(minecraft_install.spawn_protected([(16, 5, -16), (17, 5, 0)], sp, 16), [(16, 5, -16)])

    def test_missing_key_missing_file_or_bad_value_fail(self):
        sp = {"x": 108, "y": 65, "z": 90}
        for text in ("motd=hi\n", None, "spawn-protection=abc\n", "spawn-protection=-1\n"):
            code, err = self._protection(text, sp)
            self.assertEqual(code, 1, text)
            self.assertIn("FAILED", err)

    def test_read_spawn_from_level_dat(self):
        def tag(t, name, payload):
            n = name.encode()
            return bytes([t]) + struct.pack(">H", len(n)) + n + payload
        pos = struct.pack(">i", 3) + struct.pack(">3i", 108, 65, 90)  # TAG_Int_Array: length, then the ints
        spawn = tag(11, "pos", pos) + tag(5, "yaw", struct.pack(">f", 0.0)) + b"\x00"
        data = tag(10, "spawn", spawn) + b"\x00"
        root = tag(10, "Data", data) + b"\x00"
        raw = b"\x0a" + struct.pack(">H", 0) + root
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "world").mkdir()
            with gzip.open(Path(d) / "world" / "level.dat", "wb") as f:
                f.write(raw)
            self.assertEqual(shrine.read_spawn(d), {"x": 108, "y": 65, "z": 90, "yaw": 0.0})
            with self.assertRaises(shrine.ShrineError):
                shrine.read_spawn(Path(d) / "nope")


class SurveyAndBuild(unittest.TestCase):
    def setUp(self):
        self.w = FakeWorld()
        self.b = bridge_for(self.w)
        self.plan = plan_at()

    def survey(self, marker=False):
        return shrine.survey(self.b, self.plan, marker, forbidden=CFG["forbidden"])

    def test_a_clear_site_is_surveyed_fully_and_built_with_no_fill_and_no_blanket_replace(self):
        sv = self.survey()
        self.assertEqual(sv.blocked, [])
        self.assertEqual(set(sv.modes), self.plan.all_cells())  # EVERY target cell was surveyed
        counts = shrine.build(self.b, self.plan, sv)
        self.assertEqual(counts["placed"] + counts["sign"], len(self.plan.cells))
        self.assertFalse([c for c in self.w.sent if c.startswith("fill")])  # never a fill
        self.assertFalse([c for c in self.w.placed() if c.endswith(" replace")])  # air cells only used `keep`
        for cell, block in self.plan.cells.items():
            self.assertEqual(self.w.block_id(cell), shrine.parse_block(block)[0], cell)
        self.assertEqual(self.w.nbt[self.plan.sign["cell"]].count('{text:"'), 4)
        self.assertEqual(shrine.beacon_levels(self.b, self.plan, wait=1, sleep=lambda s: None), 1)

    def test_nothing_is_placed_before_the_survey_has_looked_at_every_cell(self):
        self.survey()
        self.assertFalse(self.w.placed())
        self.assertFalse([c for c in self.w.sent if c.startswith("summon")])

    def test_foundations_fill_only_air_down_to_solid_ground(self):
        ox, oz = self.plan.origin[0], self.plan.origin[2]
        self.w.ground_for[(ox + 2, oz + 2)] = 61  # a hole: 3 air cells below the platform in that column
        sv = self.survey()
        shrine.build(self.b, self.plan, sv)
        py = self.plan.platform_y
        self.assertEqual([self.w.block_id((ox + 2, y, oz + 2)) for y in (py - 1, py - 2, py - 3)],
                         ["minecraft:stone_bricks"] * 3)
        self.assertEqual(self.w.block_id((ox + 2, py - 4, oz + 2)), "minecraft:grass_block")  # the ground is untouched
        self.assertEqual(len(sv.foundation), 3)
        for c in self.w.placed():  # nothing below the platform was placed except into air
            self.assertTrue(c.endswith(" keep"))

    def test_a_block_placed_on_a_surveyed_plant_cell_after_the_survey_is_never_overwritten(self):
        # Review finding 6: plant cells were written with a bare `setblock ... replace` minutes after the survey.
        plant_cell = (self.plan.origin[0] - 2, self.plan.platform_y, self.plan.origin[2] - 5)
        self.w.blocks[plant_cell] = "minecraft:short_grass"
        sv = self.survey()
        self.assertEqual(sv.modes[plant_cell], "plant")
        self.w.blocks[plant_cell] = "minecraft:diamond_block"  # the child builds there while the survey/build runs
        with self.assertRaises(mcb.McError) as cm:
            shrine.build(self.b, self.plan, sv)
        self.assertIn("nothing was overwritten", str(cm.exception))
        self.assertEqual(self.w.block_id(plant_cell), "minecraft:diamond_block")

    def test_a_plant_in_a_foundation_column_is_guarded_the_same_way(self):
        ox, oz = self.plan.origin[0], self.plan.origin[2]
        self.w.ground_for[(ox + 2, oz + 2)] = 61
        py = self.plan.platform_y
        self.w.blocks[(ox + 2, py - 2, oz + 2)] = "minecraft:fern"
        sv = self.survey()
        self.assertEqual(sv.foundation[(ox + 2, py - 2, oz + 2)], "plant")
        shrine.build(self.b, self.plan, sv)
        under = [c for c in self.w.placed() if "%d %d %d minecraft:stone_bricks" % (ox + 2, py - 2, oz + 2) in c]
        self.assertTrue(under[0].startswith("execute if block %d %d %d minecraft:fern run setblock" % (ox + 2, py - 2, oz + 2)))

    def test_a_block_placed_in_a_foundation_plant_cell_after_the_survey_is_never_overwritten(self):
        ox, oz = self.plan.origin[0], self.plan.origin[2]
        self.w.ground_for[(ox + 2, oz + 2)] = 61
        py = self.plan.platform_y
        self.w.blocks[(ox + 2, py - 3, oz + 2)] = "minecraft:fern"
        sv = self.survey()
        self.w.blocks[(ox + 2, py - 3, oz + 2)] = "minecraft:gold_block"
        with self.assertRaises(mcb.McError):
            shrine.build(self.b, self.plan, sv)
        self.assertEqual(self.w.block_id((ox + 2, py - 3, oz + 2)), "minecraft:gold_block")

    def test_a_non_air_target_cell_refuses_everything_and_lists_it(self):
        cell = (self.plan.origin[0] + 1, self.plan.origin[1] + 2, self.plan.origin[2] + 1)  # inside the hall volume
        self.w.blocks[cell] = "minecraft:stone"
        self.w.blocks[(self.plan.origin[0] - 5, self.plan.platform_y, self.plan.origin[2])] = "minecraft:oak_log"
        sv = self.survey()
        self.assertEqual({c for c, _ in sv.blocked}, {cell, (self.plan.origin[0] - 5, self.plan.platform_y, self.plan.origin[2])})
        with self.assertRaises(shrine.SurveyRefused) as cm:
            shrine.build(self.b, self.plan, sv)
        self.assertIn(f"{cell[0]} {cell[1]} {cell[2]}", str(cm.exception))
        self.assertIn("NOTHING was built", str(cm.exception))
        self.assertFalse(self.w.placed())  # nothing at all was placed
        self.assertFalse([c for c in self.w.sent if c.startswith("summon")])

    def test_water_and_lava_are_never_acceptable(self):
        self.w.blocks[(self.plan.origin[0], self.plan.platform_y, self.plan.origin[2] + 2)] = "minecraft:water"
        sv = self.survey()
        self.assertEqual(len(sv.blocked), 1)
        self.assertIn("liquid", sv.blocked[0][1])

    def test_liquid_under_the_platform_refuses(self):
        ox, oz = self.plan.origin[0], self.plan.origin[2]
        self.w.ground_for[(ox, oz + 3)] = 50
        self.w.blocks[(ox, self.plan.platform_y - 1, oz + 3)] = "minecraft:water"
        sv = self.survey()
        self.assertTrue(any("liquid" in why for _, why in sv.blocked))

    def test_no_ground_within_max_depth_refuses(self):
        ox, oz = self.plan.origin[0], self.plan.origin[2]
        self.w.ground_for[(ox + 1, oz + 1)] = 10  # a pit far deeper than foundation.max_depth
        sv = self.survey()
        self.assertTrue(any("no solid ground" in why for _, why in sv.blocked))

    def test_replaceable_plants_are_allowed_and_replaced_everything_else_is_not(self):
        plant_cell = (self.plan.origin[0] - 2, self.plan.platform_y, self.plan.origin[2] - 5)
        for name in ("short_grass", "tall_grass", "fern", "dandelion"):
            self.w.blocks[plant_cell] = f"minecraft:{name}"
            sv = self.survey()
            self.assertEqual(sv.blocked, [], name)
            self.assertEqual(sv.modes[plant_cell], "plant")
        shrine.build(self.b, self.plan, sv)
        self.assertEqual(self.w.block_id(plant_cell), "minecraft:stone_bricks")
        guarded = [c for c in self.w.placed() if " run setblock %d %d %d " % plant_cell in c]
        self.assertEqual(len(guarded), 1)
        self.assertTrue(guarded[0].startswith("execute if block %d %d %d #minecraft:flowers run setblock" % plant_cell))
        self.assertTrue(guarded[0].endswith(" replace"))
        self.assertFalse([c for c in self.w.placed() if c.startswith("setblock %d %d %d " % plant_cell)])  # never unguarded
        self.w.blocks[plant_cell] = "minecraft:snow"  # replaceable by the game, but not a plant
        fresh = bridge_for(self.w)
        self.assertTrue(shrine.survey(fresh, self.plan, False, forbidden=CFG["forbidden"]).blocked)

    def test_the_spawn_cell_in_the_footprint_is_refused(self):
        spawn = {"x": self.plan.origin[0] + 2, "y": self.plan.origin[1] + 3, "z": self.plan.origin[2] + 2}
        sv = shrine.survey(self.b, self.plan, False, forbidden=[spawn])
        self.assertTrue(any("spawn point" in why for _, why in sv.blocked))
        spawn_above = {**spawn, "y": spawn["y"] - 1}  # the cell above a forbidden cell is protected too
        self.assertTrue(shrine.survey(self.b, self.plan, False, forbidden=[spawn_above]).blocked)

    def test_a_hopeless_site_stops_early_and_says_so(self):
        for x in range(self.plan.origin[0] - 5, self.plan.origin[0] + 6):
            for z in range(self.plan.origin[2] - 5, self.plan.origin[2] + 6):
                self.w.blocks[(x, self.plan.platform_y, z)] = "minecraft:stone"
        sv = self.survey()
        self.assertTrue(sv.stopped_early)
        self.assertIn("at least", shrine.format_blocked(sv.blocked, sv.stopped_early))

    def test_rerun_is_idempotent_and_repairs_only_what_is_missing(self):
        sv = self.survey()
        shrine.build(self.b, self.plan, sv)
        self.assertTrue(self.b.place_chest(self.plan.chests[0], 1))  # chest 1, as the install tool does
        before = dict(self.w.blocks)
        self.w.sent.clear()
        marker = shrine.marker_exists(self.b, self.plan)
        self.assertTrue(marker)
        sv2 = self.survey(marker=True)
        self.assertEqual(sv2.blocked, [])
        counts = shrine.build(self.b, self.plan, sv2)
        self.assertEqual((counts["placed"], counts["foundation"], counts["sign"]), (0, 0, 0))
        self.assertEqual(self.w.blocks, before)
        self.assertFalse([c for c in self.w.sent if c.startswith("summon")])  # no second marker
        # now break something and run again: only that block is put back
        lost = (self.plan.origin[0] + 4, self.plan.origin[1] + 1, self.plan.origin[2] + 4)
        del self.w.blocks[lost]
        self.w.sent.clear()
        counts = shrine.build(self.b, self.plan, self.survey(marker=True))
        self.assertEqual(counts["placed"], 1)
        self.assertEqual(self.w.block_id(lost), shrine.parse_block(self.plan.cells[lost])[0])

    def test_without_the_marker_our_own_blocks_count_as_blocked(self):
        shrine.build(self.b, self.plan, self.survey())
        self.assertTrue(self.survey(marker=False).blocked)  # unmarked: a stone-brick cell is not "air or plant"

    def test_a_rerun_accepts_overflow_chests_and_the_workers_decorations(self):
        shrine.build(self.b, self.plan, self.survey())
        ox, oy, oz = self.plan.origin
        self.w.blocks[(ox, oy, oz - 3)] = "minecraft:chest"  # overflow chest 2 (a chest spot)
        self.w.blocks[(ox - 1, oy, oz - 3)] = "minecraft:lantern[hanging=false]"  # Bridge.decorate beside it
        self.w.blocks[(ox, oy, oz - 4 + 1)] = "minecraft:amethyst_cluster[facing=up]"
        sv = self.survey(marker=True)
        self.assertEqual(sv.blocked, [])

    def test_a_stranger_chest_blocks_a_fresh_build(self):
        self.w.blocks[(self.plan.origin[0] + 1, self.plan.origin[1], self.plan.origin[2] + 1)] = "minecraft:chest"
        self.assertTrue(self.survey().blocked)


class SpawnSign(unittest.TestCase):
    SPAWN = {"x": 108, "y": 65, "z": 90}

    def test_candidates_are_beside_the_spawn_never_on_it_nearest_first(self):
        cands = shrine.spawn_sign_candidates(self.SPAWN, avoid=set())
        self.assertNotIn((108, 65, 90), cands)
        self.assertTrue(all(max(abs(c[0] - 108), abs(c[2] - 90)) in (1, 2) for c in cands))
        self.assertEqual(max(abs(cands[0][0] - 108), abs(cands[0][2] - 90)), 1)
        self.assertGreater(cands[0][2], 90)  # the south side first: where a player spawning looking south sees it
        self.assertNotIn((107, 65, 91), shrine.spawn_sign_candidates(self.SPAWN, avoid={(107, 65, 91)}))

    def test_rotation_faces_the_spawn(self):
        for frm, want in (((108, 65, 92), 8), ((108, 65, 88), 0), ((110, 65, 90), 4), ((106, 65, 90), 12)):
            self.assertEqual(shrine.sign_rotation_towards(frm, (108, 65, 90)), want, frm)
        self.assertEqual(shrine.sign_rotation_towards((107, 65, 91), (108, 65, 90)), 10)  # south-west of it: faces NE

    def test_sign_goes_on_a_free_cell_beside_the_spawn_with_solid_ground(self):
        w = FakeWorld(ground_y=64)
        b = bridge_for(w)
        found = shrine.find_spawn_sign(b, self.SPAWN, avoid=set(), forbidden=CFG["forbidden"],
                                       first_line=shrine.sign_lines(VILLAGE)[0])
        self.assertEqual(found[0], "place")
        cell = found[1]
        self.assertNotEqual(cell, (108, 65, 90))
        self.assertEqual(max(abs(cell[0] - 108), abs(cell[2] - 90)), 1)
        self.assertEqual(shrine.place_spawn_sign(b, found, shrine.sign_lines(VILLAGE)), "placed")
        self.assertEqual(w.block_id(cell), "minecraft:oak_sign")
        self.assertIn("rotation=", [c for c in w.placed()][0])
        self.assertIn("{text:\"Sam's Village\"}", w.placed()[0])
        self.assertEqual(w.block_id((108, 65, 90)), "minecraft:air")  # the spawn cell stays empty
        again = shrine.find_spawn_sign(b, self.SPAWN, avoid=set(), forbidden=CFG["forbidden"],
                                       first_line=shrine.sign_lines(VILLAGE)[0])
        self.assertEqual(again[:2], ("exists", cell))  # idempotent: found again, not duplicated
        self.assertEqual(shrine.place_spawn_sign(b, again, []), "exists")

    def test_blocked_neighbours_are_skipped_and_water_or_a_pit_is_never_used(self):
        w = FakeWorld(ground_y=64)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if (dx, dz) != (0, 0):
                    w.blocks[(108 + dx, 65, 90 + dz)] = "minecraft:stone"  # the whole first ring is rock at y 65
        w.blocks[(108 + 2, 65, 90)] = "minecraft:water"
        found = shrine.find_spawn_sign(bridge_for(w), self.SPAWN, avoid=set(), forbidden=CFG["forbidden"],
                                       first_line=shrine.sign_lines(VILLAGE)[0])
        self.assertTrue(found[1] != (108 + 2, 65, 90))
        self.assertTrue(max(abs(found[1][0] - 108), abs(found[1][2] - 90)) >= 1)

    def test_no_candidate_is_a_loud_failure_and_places_nothing(self):
        w = FakeWorld(ground_y=64)
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for y in (65, 66):
                    if (dx, dz) != (0, 0) or y == 66:
                        w.blocks[(108 + dx, y, 90 + dz)] = "minecraft:stone"
        with self.assertRaises(mcb.McError):
            shrine.find_spawn_sign(bridge_for(w), self.SPAWN, avoid=set(), forbidden=CFG["forbidden"],
                                       first_line=shrine.sign_lines(VILLAGE)[0])
        self.assertFalse(w.placed())

    def test_the_shrine_cells_are_never_a_sign_candidate(self):
        plan = shrine.Plan(SPEC, {"x": 108, "y": 67, "z": 92}, VILLAGE)  # a shrine built right beside the spawn
        cands = shrine.spawn_sign_candidates(self.SPAWN, avoid=plan.all_cells() | set())
        self.assertFalse(set(cands) & plan.all_cells())


@unittest.skipUnless(JAR.exists(), "needs the local Minecraft jar (textures stay on the parent's machine)")
class Render(unittest.TestCase):
    def test_renders_a_png(self):
        import shrine_render
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "s.png"
            w, h = shrine_render.render_iso(plan_at(), JAR, out, scale=2)
            self.assertTrue(out.read_bytes().startswith(b"\x89PNG"))
            self.assertGreater(w, 300)
            self.assertGreater(h, 300)

    def test_every_block_in_the_spec_has_a_texture_mapping(self):
        import shrine_render
        names = {shrine.parse_block(op["block"])[0].split(":")[1] for op in SPEC["ops"]} | {"oak_sign", "chest"}
        self.assertLessEqual(names, set(shrine_render.TEXTURES))


if __name__ == "__main__":
    unittest.main()
