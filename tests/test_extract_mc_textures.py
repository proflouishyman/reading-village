"""Tests for tools/extract_mc_textures.py. No real Minecraft jar needed: textures are synthetic."""
import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from PIL import Image  # noqa: E402

import extract_mc_textures as x  # noqa: E402


def fill(im, rect, colour):
    """Paint rect=(u,v,w,h) of a PIL image a solid colour."""
    u, v, w, h = rect
    for j in range(v, v + h):
        for i in range(u, u + w):
            im.putpixel((i, j), colour)


RED, GREEN, BLUE, YELLOW, CYAN, ORANGE, MAGENTA = (
    (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255),
    (0, 255, 255, 255), (255, 128, 0, 255), (255, 0, 255, 255))


def synthetic_villager_texture():
    """64x64 texture whose UV regions (as the model reads them) carry known colours."""
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    fill(im, (8, 8, 4, 10), RED)            # head front, left half (entity right side)
    fill(im, (12, 8, 4, 10), BLUE)          # head front, right half
    fill(im, (26, 2, 2, 4), GREEN)          # nose front
    fill(im, (22, 26, 8, 12), CYAN)         # body front (hidden behind the robe)
    fill(im, (6, 44, 8, 20), YELLOW)        # robe front
    fill(im, (44, 42, 8, 4), MAGENTA)       # crossed-arms band front
    fill(im, (40, 8, 8, 10), ORANGE)        # hat front
    return im


def px(im, wx, wy, scale=1):
    """Pixel at model-space (wx, wy) for an image rendered with VILLAGER_BOUNDS."""
    bx0, by0 = x.VILLAGER_BOUNDS[0], x.VILLAGER_BOUNDS[1]
    return im.getpixel((int((wx - bx0) * scale), int((wy - by0) * scale)))


class RasteriserTest(unittest.TestCase):
    def render(self, hat="none", scale=1):
        return x.rasterise([(synthetic_villager_texture(), hat)], x.VILLAGER_BOXES, x.VILLAGER_BOUNDS, scale)

    def test_head_front_uses_uv_and_is_not_mirrored(self):
        im = self.render()
        self.assertEqual(px(im, -3, -8), RED)    # viewer's left = left half of the head front region
        self.assertEqual(px(im, 3, -8), BLUE)

    def test_nose_sits_in_front_of_the_face(self):
        self.assertEqual(px(self.render(), 0, -1), GREEN)

    def test_robe_covers_body(self):
        im = self.render()
        self.assertEqual(px(im, -3, 14), YELLOW)   # jacket (inflated) wins over the body behind it
        self.assertNotEqual(px(im, -3, 14), CYAN)

    def test_crossed_arms_band_is_in_front_of_robe(self):
        im = self.render(scale=4)
        found = {px(im, 0, y / 4, 4) for y in range(4, 40)}
        self.assertIn(MAGENTA, found)

    def test_hat_visibility_follows_state(self):
        self.assertNotEqual(px(self.render("none"), 0, -9), ORANGE)
        self.assertEqual(px(self.render("partial"), -3, -9), ORANGE)
        # the brim box is only drawn for full hats: it spans x +-8, wider than the head
        tex = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        fill(tex, (30, 47, 64 - 30, 17), ORANGE)  # everything the brim could sample
        partial = x.rasterise([(tex, "partial")], x.VILLAGER_BOXES, x.VILLAGER_BOUNDS, 4)
        full = x.rasterise([(tex, "full")], x.VILLAGER_BOXES, x.VILLAGER_BOUNDS, 4)
        self.assertIsNone(partial.getbbox())
        self.assertIsNotNone(full.getbbox())

    def test_nearest_neighbour_only_two_colours_no_blending(self):
        im = self.render(scale=8)
        colours = {c for _, c in im.getcolors(maxcolors=1 << 16)}
        self.assertTrue(colours <= {RED, BLUE, GREEN, YELLOW, CYAN, MAGENTA, (0, 0, 0, 0)}, colours)

    def test_later_layer_wins_depth_tie(self):
        base = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        top = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        fill(base, (8, 8, 8, 10), RED)
        fill(top, (8, 8, 8, 10), BLUE)
        im = x.rasterise([(base, "none"), (top, "none")], x.VILLAGER_BOXES, x.VILLAGER_BOUNDS, 1)
        self.assertEqual(px(im, -3, -8), BLUE)

    def test_small_texture_fails_loudly(self):
        with self.assertRaises(x.ExtractError):
            x.rasterise([(Image.new("RGBA", (16, 16), RED), "none")], x.VILLAGER_BOXES, x.VILLAGER_BOUNDS, 1)


def cube_parts(tex=(0, 0), size=(4, 4, 4)):
    """One part holding one cube centred on the origin (cube origin = -size/2)."""
    o = tuple(-d / 2 for d in size)
    return (x.P("cube", "", (0, 0, 0), (0, 0, 0), x.C(tex, o, size)),)


def cube_texture():
    """16x16 texture for a 4x4x4 cube at (0,0): the unwrap puts left=(8,4), front=(4,4), back=(12,4), top=(4,0)."""
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    fill(im, (8, 4, 2, 4), RED)     # left face, its front half (texture u starts at the front edge)
    fill(im, (10, 4, 2, 4), BLUE)   # left face, its back half
    fill(im, (4, 4, 4, 4), GREEN)   # front face
    return im


class MobCompositorTest(unittest.TestCase):
    """The side/front compositor on a tiny synthetic texture (no jar needed)."""

    def test_side_view_shows_the_left_face_with_the_front_on_the_viewers_left(self):
        im = x.compose_mob([(cube_texture(), cube_parts())], x.view_matrix(90, 0), 2)
        self.assertEqual(im.size, (8, 8))                  # cropped to the cube: 4 model units at 2 px
        self.assertEqual(im.getpixel((1, 4)), RED)         # front half of the side face is on the left
        self.assertEqual(im.getpixel((6, 4)), BLUE)
        self.assertNotIn(GREEN, {c for _, c in im.getcolors()})   # the front face is edge-on from the side

    def test_front_view_shows_the_front_face(self):
        im = x.compose_mob([(cube_texture(), cube_parts())], x.view_matrix(0, 0), 2)
        self.assertEqual({c for _, c in im.getcolors()}, {GREEN})

    def test_pitch_looks_down_onto_the_top_face(self):
        tex = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        fill(tex, (4, 0, 4, 4), YELLOW)                    # top face
        with self.assertRaises(x.ExtractError):            # nothing but the top is painted: invisible head-on
            x.compose_mob([(tex, cube_parts())], x.view_matrix(0, 0), 2)
        im = x.compose_mob([(tex, cube_parts())], x.view_matrix(0, 40), 2)
        self.assertEqual({c for _, c in im.getcolors()}, {YELLOW})

    def test_transparent_front_shows_the_inside_of_the_back_face(self):
        tex = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        fill(tex, (12, 4, 4, 4), MAGENTA)                  # back face only (the chicken's thin legs work this way)
        im = x.compose_mob([(tex, cube_parts())], x.view_matrix(0, 0), 2)
        self.assertEqual({c for _, c in im.getcolors()}, {MAGENTA})
        culled = x.rasterise([(tex, "full", x.compose_parts(cube_parts()))], [], None, 2, view=x.view_matrix(0, 0))
        self.assertIsNone(culled.getbbox())                # the villager path still culls back faces

    def test_nested_parts_compose_pivot_and_rotation_like_the_game(self):
        parts = (x.P("a", "", (10, 0, 0), (0, math.pi, 0)), x.P("b", "a", (3, 0, 0), (0, 0, 0), x.C((0, 0), (0, 0, 0), (1, 1, 1))))
        (box,) = x.compose_parts(parts)
        self.assertAlmostEqual(box.pose[0], 7.0)           # a is turned half a circle about y, so b's +3 becomes -3
        self.assertAlmostEqual(box.pose[1], 0.0)
        self.assertAlmostEqual(box.mat[0][0], -1.0)

    def test_part_before_its_parent_fails_loudly(self):
        with self.assertRaises(x.ExtractError):
            x.compose_parts((x.P("child", "missing"),))

    def test_translucent_shell_is_blended_over_the_core(self):
        core = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        fill(core, (4, 4, 4, 4), RED)
        shell = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        fill(shell, (4, 4, 4, 4), (0, 0, 255, 128))
        im = x.compose_mob([(core, cube_parts())], x.view_matrix(0, 0), 2, [(shell, cube_parts())])
        r, g, b, a = im.getpixel((4, 4))
        self.assertGreater(b, 100)
        self.assertGreater(r, 100)                         # neither pure core nor pure shell: they blend
        self.assertEqual(a, 255)

    def test_tint_multiplies_the_texture(self):
        t = x._tinted(Image.new("RGBA", (2, 2), (255, 255, 255, 255)), (176, 46, 38))
        self.assertEqual(t.getpixel((0, 0)), (176, 46, 38, 255))


def mob_jar(path, size=(16, 16), drop=False):
    """Fake jar holding one entity texture for the synthetic mob below."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("version.json", json.dumps({"id": "test-1"}))
        if not drop:
            z.writestr(x.TEX + "entity/test/mob.png", png(Image.new("RGBA", size, GREEN)))


TEST_MOB = x.MobSpec((x.MobLayer("entity/test/mob.png", (16, 16), cube_parts()),), 0, 0, "test")


class BuildMobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_builds_a_cropped_picture(self):
        mob_jar(self.tmp / "a.jar")
        with mock.patch.dict(x.MOBS, {"testmob": TEST_MOB}):
            im = x.build_mob(x.Jar(self.tmp / "a.jar"), "testmob", 2)
        self.assertEqual(im.size, (8, 8))

    def test_unknown_mob_fails_loudly(self):
        mob_jar(self.tmp / "a.jar")
        with self.assertRaises(x.ExtractError) as cm:
            x.build_mob(x.Jar(self.tmp / "a.jar"), "dragon", 2)
        self.assertIn("unknown mob 'dragon'", cm.exception.problems[0])

    def test_texture_of_the_wrong_size_fails_loudly(self):
        mob_jar(self.tmp / "a.jar", size=(64, 64))
        with mock.patch.dict(x.MOBS, {"testmob": TEST_MOB}), self.assertRaises(x.ExtractError) as cm:
            x.build_mob(x.Jar(self.tmp / "a.jar"), "testmob", 2)
        self.assertIn("64x64", cm.exception.problems[0])
        self.assertIn("16x16", cm.exception.problems[0])

    def test_missing_texture_is_recorded_and_extract_fails_before_writing(self):
        mob_jar(self.tmp / "a.jar", drop=True)
        mapping = self.tmp / "map.json"
        mapping.write_text(json.dumps({"v": 1, "entries": {"testmob": {"kind": "mob", "mob": "testmob"}}, "unmapped": {}}))
        with mock.patch.dict(x.MOBS, {"testmob": TEST_MOB}), self.assertRaises(x.ExtractError) as cm:
            x.extract(self.tmp / "a.jar", self.tmp / "out", mapping_path=mapping)
        self.assertEqual(cm.exception.problems, ["missing in jar: textures/entity/test/mob.png"])
        self.assertFalse((self.tmp / "out").exists())

    def test_mapping_with_an_unknown_mob_is_rejected(self):
        mapping = self.tmp / "map.json"
        mapping.write_text(json.dumps({"v": 1, "entries": {"x": {"kind": "mob", "mob": "dragon"}}, "unmapped": {}}))
        with self.assertRaises(x.ExtractError) as cm:
            x.load_mapping(mapping)
        self.assertIn("unknown mob", cm.exception.problems[0])

    def test_tint_is_checked_and_gets_its_own_file(self):
        """Leaves/vine are grey in the jar: an optional [r,g,b] tint, validated, written beside (never over) the plain one."""
        mapping = self.tmp / "map.json"
        for bad in ([72, 181], [72, 181, 300], "green"):
            mapping.write_text(json.dumps({"v": 1, "entries": {"leaf": {"kind": "block", "jar": "block/oak_leaves",
                                                                         "tint": bad}}, "unmapped": {}}))
            with self.assertRaises(x.ExtractError) as cm:
                x.load_mapping(mapping)
            self.assertIn("tint must be", cm.exception.problems[0])
        self.assertEqual(x.out_path({"kind": "block", "jar": "block/oak_leaves", "tint": [72, 181, 24]}),
                         "blocks/oak_leaves_tinted.png")
        self.assertEqual(x.out_path({"kind": "block", "jar": "block/oak_leaves"}), "blocks/oak_leaves.png")

    def test_extract_writes_mobs_dir_and_manifest(self):
        mob_jar(self.tmp / "a.jar")
        mapping = self.tmp / "map.json"
        mapping.write_text(json.dumps({"v": 1, "entries": {"testmob": {"kind": "mob", "mob": "testmob"}}, "unmapped": {}}))
        with mock.patch.dict(x.MOBS, {"testmob": TEST_MOB}):
            m = x.extract(self.tmp / "a.jar", self.tmp / "out", mapping_path=mapping, mob_scale=2)
        self.assertEqual(m["sprites"], {"testmob": "mobs/testmob.png"})
        self.assertEqual(Image.open(self.tmp / "out/mobs/testmob.png").size, (8, 8))

    def test_every_shipped_mob_spec_is_well_formed(self):
        for name, spec in x.MOBS.items():
            for lyr in spec.layers:
                boxes = x.compose_parts(lyr.parts)         # parents resolve
                self.assertTrue(boxes, name)
                w, h = lyr.size
                for b in boxes:                            # every drawn UV rectangle of every cube fits its texture
                    for _face, _p0, _A, _B, _n, (u, v, rw, rh) in x._faces(b):
                        if rw > 0 and rh > 0:
                            self.assertTrue(0 <= u and 0 <= v and u + rw <= w and v + rh <= h, (name, b, (u, v, rw, rh)))



def png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def make_jar(path, drop=()):
    """A tiny fake client jar: one animated item, plus the three layers for a librarian."""
    anim = Image.new("RGBA", (16, 48), (0, 0, 0, 0))
    fill(anim, (0, 0, 16, 16), RED)
    fill(anim, (0, 16, 16, 16), BLUE)
    fill(anim, (0, 32, 16, 16), GREEN)
    files = {
        "version.json": json.dumps({"id": "test-1"}).encode(),
        x.TEX + "item/diamond.png": png(anim),
        x.TEX + "item/diamond.png.mcmeta": json.dumps({"animation": {"frames": [1, 0, 2]}}).encode(),
        x.TEX + "entity/villager/villager.png": png(synthetic_villager_texture()),
        x.TEX + "entity/villager/type/plains.png": png(Image.new("RGBA", (64, 64), (0, 0, 0, 0))),
        x.TEX + "entity/villager/profession/librarian.png": png(Image.new("RGBA", (64, 64), (0, 0, 0, 0))),
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            if name not in drop:
                z.writestr(name, data)


MAPPING = {"v": 1, "entries": {
    "diamond": {"kind": "item", "jar": "item/diamond"},
    "villager_librarian": {"kind": "villager", "profession": "librarian"}}, "unmapped": {}}


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.map = self.tmp / "map.json"
        self.map.write_text(json.dumps(MAPPING))

    def test_missing_jar_fails_loudly(self):
        with self.assertRaises(x.ExtractError) as cm:
            x.extract(self.tmp / "nope.jar", self.tmp / "out", mapping_path=self.map)
        self.assertIn("jar not found", cm.exception.problems[0])
        self.assertFalse((self.tmp / "out").exists())

    def test_main_prints_failed_banner_and_exits_nonzero(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = x.main(["--jar", str(self.tmp / "nope.jar"), "--out", str(self.tmp / "out")])
        self.assertEqual(code, 1)
        self.assertIn("FAILED", err.getvalue())

    def test_missing_texture_fails_before_writing_anything(self):
        jar = self.tmp / "a.jar"
        make_jar(jar, drop={x.TEX + "entity/villager/profession/librarian.png"})
        with self.assertRaises(x.ExtractError) as cm:
            x.extract(jar, self.tmp / "out", mapping_path=self.map)
        self.assertEqual(cm.exception.problems, ["missing in jar: textures/entity/villager/profession/librarian.png"])
        self.assertFalse((self.tmp / "out").exists())

    def test_extracts_first_listed_frame_and_manifest_and_is_idempotent(self):
        jar = self.tmp / "a.jar"
        make_jar(jar)
        out = self.tmp / "out"
        m1 = x.extract(jar, out, scale=2, mapping_path=self.map)
        self.assertEqual(Image.open(out / "items/diamond.png").getpixel((3, 3)), BLUE)  # frames [1,0,2] -> index 1
        self.assertEqual(Image.open(out / "items/diamond.png").size, (16, 16))
        self.assertEqual(Image.open(out / "villagers/librarian.png").size, (40, 72))
        self.assertEqual(m1["sprites"], {"diamond": "items/diamond.png", "villager_librarian": "villagers/librarian.png"})
        self.assertEqual(m1["minecraft_version"], "test-1")
        self.assertEqual(len(m1["jar_sha256"]), 64)
        self.assertEqual(json.loads((out / "manifest.json").read_text()), m1)
        m2 = x.extract(jar, out, scale=2, mapping_path=self.map)
        self.assertEqual(m1, m2)

    def test_repo_mapping_is_valid_and_has_no_duplicate_classification(self):
        data = x.load_mapping()
        self.assertFalse(set(data["entries"]) & set(data["unmapped"]))
        for entry in data["entries"].values():
            self.assertTrue(x.out_path(entry).endswith(".png"))

    def test_refuses_unignored_repo_directory(self):
        with self.assertRaises(x.ExtractError):
            x.check_git_ignored(x.REPO / "app" / "js")


if __name__ == "__main__":
    unittest.main()
