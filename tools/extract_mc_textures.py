#!/usr/bin/env python3
"""Extract real Minecraft textures from the parent's own client jar into app/assets/mc/ for LOCAL use only.

The output directory is .gitignored and must never be committed or shared (see docs/textures.md).

What it writes (relative to --out, default <repo>/app/assets/mc):
  items/<name>.png, blocks/<name>.png   16x16 textures from the jar (animated ones: first frame), native size
  blocks/chest.png, blocks/bed.png      composites cropped from the entity / bed textures
  villagers/<profession>.png            FRONT VIEW of a villager, composed from the layered entity textures
  villagers/wandering_trader.png        FRONT VIEW of the wandering trader
  villagers/trader_llama.png            FRONT VIEW of a llama (cream coat)
  mobs/<mob>.png                        SIDE (animals, fish, bee) or FRONT (piglin, blaze, slime, bat) view of a mob,
                                        composed from its entity texture(s); see MOBS for the variant of each
  badges/<tier>.png                     the profession-level layer (stone..diamond) rendered on the villager model
  manifest.json                         {"v":1,"source_jar","jar_sha256","minecraft_version","files":{...},"sprites":{...}}

What to extract is defined by app/js/mctextures_map.json (sprite id -> jar texture), shared with mctextures.js.

Loud failure: a missing jar, missing mapped texture or unreadable image prints a FAILED banner listing every
problem and exits non-zero BEFORE anything is written (all outputs are built in memory first).
Re-running is idempotent (output is deterministic).

Villager rendering: the 64x64 entity textures are mapped onto the real model's boxes (head, nose, body, robe,
crossed arms, legs, hat) with an orthographic front-view box rasteriser, layered base -> type -> profession exactly
as the game does (shared depth buffer, hat visibility from each layer's .mcmeta). Box dimensions come from the
decompiled VillagerModel / LlamaModel of the 26.3 client.

Mob pictures use the same rasteriser with a camera (yaw/pitch) and nested model parts: the boxes, pivots and UV
offsets of each mob (pig, cow, sheep and its wool, hen, baby chicken, baby wolf with collar, fox, frog, squid, cod,
goat, bee, mule, slime, blaze, rabbit, panda, camel, piglin, hoglin, bat) were read from the client's model classes
(javap on createBodyLayer). A texture whose size differs from the layout the boxes expect is a FAILED line.
"""
import argparse
import hashlib
import io
import json
import math
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # loud, not silent: this tool cannot run without Pillow
    print("FAILED: Pillow is required (pip install Pillow)", file=sys.stderr)
    raise SystemExit(2)

REPO = Path(__file__).resolve().parent.parent
DEFAULT_JAR = Path.home() / "Library/Application Support/minecraft/versions/26.3/26.3.jar"
DEFAULT_OUT = REPO / "app/assets/mc"
MAP_PATH = REPO / "app/js/mctextures_map.json"
TEX = "assets/minecraft/textures/"
MANIFEST_V = 1

PROFESSIONS = ["armorer", "butcher", "cartographer", "cleric", "farmer", "fisherman", "fletcher",
               "leatherworker", "librarian", "mason", "shepherd", "toolsmith", "weaponsmith"]
TIERS = ["stone", "iron", "gold", "emerald", "diamond"]


class ExtractError(Exception):
    """Raised with a list of problems; main() prints them under a FAILED banner."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


# --------------------------------------------------------------------------------------------------
# Box model + front-view rasteriser
# --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    """One textured cuboid, in Minecraft model space (x right-of-viewer, y DOWN, entity faces -z).

    tex: (u, v) texture offset. origin/size: the cube relative to its part pivot. inflate: grows the cube on
    every side but NOT its texture rectangles. pose: pivot position; rot_x: pivot rotation about x (radians).
    group: which hat state shows it: "body" always, "hat" when hat is partial/full, "rim" only when full.
    """
    tex: tuple
    origin: tuple
    size: tuple
    inflate: float = 0.0
    mirror: bool = False
    pose: tuple = (0.0, 0.0, 0.0)
    rot_x: float = 0.0
    group: str = "body"
    mat: tuple = None   # optional 3x3 rotation (rows); when set it replaces rot_x (nested mob parts)


# VillagerModel (26.3): values read from the client class, in order head, hat, hat_rim, nose, body, jacket, arms, legs.
VILLAGER_BOXES = [
    Box((0, 0), (-4, -10, -4), (8, 10, 8)),                                   # head
    Box((32, 0), (-4, -10, -4), (8, 10, 8), inflate=0.51, group="hat"),       # hat (profession/type overlay)
    Box((30, 47), (-8, -8, -6), (16, 16, 1), rot_x=-math.pi / 2, group="rim"),  # hat brim (full hats only)
    Box((24, 0), (-1, -1, -6), (2, 4, 2), pose=(0, -2, 0)),                   # nose
    Box((16, 20), (-4, 0, -3), (8, 12, 6)),                                   # body
    Box((0, 38), (-4, 0, -3), (8, 20, 6), inflate=0.5),                       # robe ("jacket"), hangs to the ankles
    # crossed arms: two 4x8x4 cuffs and the 8x4x4 forearm band, pivot (0,3,-1) tilted 0.75 rad forward
    Box((44, 22), (-8, -2, -2), (4, 8, 4), pose=(0, 3, -1), rot_x=-0.75),
    Box((44, 22), (4, -2, -2), (4, 8, 4), mirror=True, pose=(0, 3, -1), rot_x=-0.75),
    Box((40, 38), (-4, 2, -2), (8, 4, 4), pose=(0, 3, -1), rot_x=-0.75),
    Box((0, 22), (-2, 0, -2), (4, 12, 4), pose=(-2, 12, 0)),                  # right leg (viewer's left)
    Box((0, 22), (-2, 0, -2), (4, 12, 4), mirror=True, pose=(2, 12, 0)),      # left leg
]
VILLAGER_BOUNDS = (-10.0, -11.0, 10.0, 25.0)   # x0, y0, x1, y1 in model units

# LlamaModel (26.3): head, neck (carries the face), ears, body (lying, rotated 90 deg), four legs.
LLAMA_BOXES = [
    Box((0, 14), (-4, -16, -6), (8, 18, 6), pose=(0, 7, -6)),                 # neck (front shows the eyes)
    Box((0, 0), (-2, -14, -10), (4, 4, 9), pose=(0, 7, -6)),                  # muzzle
    Box((17, 0), (-4, -19, -4), (3, 3, 2), pose=(0, 7, -6)),                  # ears
    Box((17, 0), (1, -19, -4), (3, 3, 2), mirror=True, pose=(0, 7, -6)),
    Box((29, 0), (-6, -10, -7), (12, 18, 10), pose=(0, 5, 2), rot_x=math.pi / 2),  # body
    Box((29, 29), (-2, 0, -2), (4, 14, 4), pose=(-3.5, 10, -5)),              # front legs
    Box((29, 29), (-2, 0, -2), (4, 14, 4), mirror=True, pose=(3.5, 10, -5)),
]
LLAMA_BOUNDS = (-9.0, -14.0, 9.0, 25.0)


def _rot_x(p, a):
    """Rotate point/vector p about the x axis (Minecraft convention, y down)."""
    c, s = math.cos(a), math.sin(a)
    return (p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c)


def _faces(b):
    """Yield (name, P0, A, B, normal, rect) in LOCAL coordinates for the faces of box b.

    P0 is the face corner at texture (0,0); A/B are the edge vectors along texture u/v; rect is the
    (u, v, w, h) texel rectangle. Layout is Minecraft's standard box UV unwrap.
    """
    u, v = b.tex
    w, h, d = b.size
    g = b.inflate
    x0, y0, z0 = b.origin[0] - g, b.origin[1] - g, b.origin[2] - g
    x1, y1, z1 = b.origin[0] + w + g, b.origin[1] + h + g, b.origin[2] + d + g
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    right = (u, v + d, d, h)
    left = (u + d + w, v + d, d, h)
    if b.mirror:  # a mirrored box swaps its left/right regions (u is flipped per face at sampling time)
        right, left = left, right
    return [
        ("front", (x0, y0, z0), (dx, 0, 0), (0, dy, 0), (0, 0, -1), (u + d, v + d, w, h)),
        ("back", (x1, y0, z1), (-dx, 0, 0), (0, dy, 0), (0, 0, 1), (u + 2 * d + w, v + d, w, h)),
        ("top", (x0, y0, z1), (dx, 0, 0), (0, 0, -dz), (0, -1, 0), (u + d, v, w, d)),
        # bottom: the unwrap places it beside the top face; its first texel row is at the front edge
        ("bottom", (x0, y1, z0), (dx, 0, 0), (0, 0, dz), (0, 1, 0), (u + d + w, v, w, d)),
        ("right", (x0, y0, z1), (0, 0, -dz), (0, dy, 0), (-1, 0, 0), right),
        ("left", (x1, y0, z0), (0, 0, dz), (0, dy, 0), (1, 0, 0), left),
    ]


def _mat_apply(m, v):
    """3x3 matrix (rows) times vector."""
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def _mat_mul(a, b):
    """Matrix product a @ b (3x3, rows)."""
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def rot_matrix(rx, ry, rz):
    """Minecraft part rotation (PartPose x/y/z radians): the game rotates about x, then y, then z, so R = Rz Ry Rx."""
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    mx = ((1, 0, 0), (0, cx, -sx), (0, sx, cx))
    my = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    mz = ((cz, -sz, 0), (sz, cz, 0), (0, 0, 1))
    return _mat_mul(mz, _mat_mul(my, mx))


def view_matrix(yaw_deg, pitch_deg):
    """Camera rotation applied to model space before projecting. yaw 0 = front view (model faces the viewer);
    yaw 90 = side view with the model facing the viewer's left. pitch > 0 looks down from above."""
    return _mat_mul(rot_matrix(math.radians(pitch_deg), 0, 0), rot_matrix(0, math.radians(yaw_deg), 0))


def _box_transform(b):
    """Function mapping a box-local vector to model space (rotation only, the pose is added after)."""
    if b.mat is not None:
        return lambda v: _mat_apply(b.mat, v)
    return lambda v: _rot_x(v, b.rot_x)


def view_bounds(boxes, view):
    """(x0, y0, x1, y1) of every box corner after the view rotation: the canvas for a mob."""
    xs, ys = [], []
    for b in boxes:
        g = b.inflate
        w, h, d = b.size
        f = _box_transform(b)
        for cx in (b.origin[0] - g, b.origin[0] + w + g):
            for cy in (b.origin[1] - g, b.origin[1] + h + g):
                for cz in (b.origin[2] - g, b.origin[2] + d + g):
                    q = f((cx, cy, cz))
                    q = _mat_apply(view, (q[0] + b.pose[0], q[1] + b.pose[1], q[2] + b.pose[2]))
                    xs.append(q[0])
                    ys.append(q[1])
    return (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5)


def rasterise(layers, boxes, bounds, scale, hat_of=None, view=None, keep_alpha=False, cull=True):
    """Orthographic view of `boxes` textured by each layer in turn, sharing one depth buffer.

    layers: list of (RGBA texture Image, hat[, boxes]) with hat in {"none","partial","full"} controlling which
    "hat"/"rim" boxes that layer draws; a third item replaces `boxes` for that layer (mob overlays such as sheep wool).
    Later layers win depth ties (the game's LEQUAL depth test), so a profession robe replaces the base robe
    underneath it. view: optional 3x3 camera matrix (view_matrix); None = the front view the villagers use.
    bounds None = fit the corners of every box. keep_alpha: keep translucent texels (slime shell) instead of
    snapping them opaque. cull False draws faces turned away from the viewer too (the game's entityCutoutNoCull: a
    mob whose front texels are transparent, like the chicken's thin legs, shows the inside of the back face).
    Returns an RGBA image of ((x1-x0)*scale, (y1-y0)*scale) pixels, nearest-neighbour
    sampled: pixels stay crisp.
    """
    view = view or IDENTITY
    if bounds is None:
        every = list(boxes) + [b for layer in layers if len(layer) > 2 for b in layer[2]]
        bounds = view_bounds(every, view)
    bx0, by0, bx1, by1 = bounds
    W, H = round((bx1 - bx0) * scale), round((by1 - by0) * scale)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    opx = out.load()
    INF = float("inf")
    zbuf = [INF] * (W * H)
    for layer in layers:
        tex, hat = layer[0], layer[1]
        layer_boxes = layer[2] if len(layer) > 2 else boxes
        tpx = tex.load()
        tw_img, th_img = tex.size
        for b in layer_boxes:
            if b.group == "hat" and hat == "none":
                continue
            if b.group == "rim" and hat != "full":
                continue
            pose = b.pose
            xf = _box_transform(b)
            for _name, p0, A, B, n, rect in _faces(b):
                # local -> model: rotate about the pivot, translate by the pose; then rotate into the view
                P = xf(p0)
                Ar, Br, Nr = xf(A), xf(B), xf(n)
                P = _mat_apply(view, (P[0] + pose[0], P[1] + pose[1], P[2] + pose[2]))
                Ar, Br, Nr = _mat_apply(view, Ar), _mat_apply(view, Br), _mat_apply(view, Nr)
                if cull and Nr[2] >= -1e-9:  # faces away from (or edge-on to) the viewer at -z
                    continue
                Px, Py, Pz = P
                det = Ar[0] * Br[1] - Ar[1] * Br[0]
                if abs(det) < 1e-9:
                    continue
                xs = [Px + i * Ar[0] + j * Br[0] for i in (0, 1) for j in (0, 1)]
                ys = [Py + i * Ar[1] + j * Br[1] for i in (0, 1) for j in (0, 1)]
                ix0 = max(0, math.floor((min(xs) - bx0) * scale))
                ix1 = min(W - 1, math.ceil((max(xs) - bx0) * scale))
                iy0 = max(0, math.floor((min(ys) - by0) * scale))
                iy1 = min(H - 1, math.ceil((max(ys) - by0) * scale))
                ru, rv, rw, rh = rect
                for py in range(iy0, iy1 + 1):
                    y = by0 + (py + 0.5) / scale - Py
                    for px in range(ix0, ix1 + 1):
                        x = bx0 + (px + 0.5) / scale - Px
                        s = (x * Br[1] - y * Br[0]) / det
                        t = (Ar[0] * y - Ar[1] * x) / det
                        if s < 0 or s >= 1 or t < 0 or t >= 1:
                            continue
                        if b.mirror:
                            s = 1 - s - 1e-12
                        tx = int(ru) + min(int(rw) - 1, int(s * rw))
                        ty = int(rv) + min(int(rh) - 1, int(t * rh))
                        if tx >= tw_img or ty >= th_img or tx < 0 or ty < 0:
                            raise ExtractError([f"texture {tw_img}x{th_img} too small for UV ({tx},{ty})"])
                        r, g, bl, a = tpx[tx, ty]
                        if a == 0:
                            continue
                        z = Pz + s * Ar[2] + t * Br[2]
                        i = py * W + px
                        if z <= zbuf[i] + 1e-6:
                            zbuf[i] = z
                            opx[px, py] = (r, g, bl, a if keep_alpha else (255 if a > 127 else a))
    return out


def hat_state(mcmeta_bytes):
    """Hat visibility from a layer's .mcmeta ({"villager":{"hat":"partial"|"full"}}); none if absent."""
    if not mcmeta_bytes:
        return "none"
    state = json.loads(mcmeta_bytes).get("villager", {}).get("hat", "none")
    if state not in ("none", "partial", "full"):
        raise ExtractError([f"unknown hat state {state!r}"])
    return state


# --------------------------------------------------------------------------------------------------
# Mobs: side / front pictures composed from the entity textures
# --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Cube:
    """One cuboid of a model part: tex (u, v), origin and size relative to the part pivot, inflate, mirror."""
    tex: tuple
    origin: tuple
    size: tuple
    inflate: float = 0.0
    mirror: bool = False


@dataclass(frozen=True)
class Part:
    """A model part: pivot `offset` and `rot` (x, y, z radians) relative to its parent ("" = the model root)."""
    name: str
    parent: str
    offset: tuple = (0.0, 0.0, 0.0)
    rot: tuple = (0.0, 0.0, 0.0)
    cubes: tuple = ()


@dataclass(frozen=True)
class MobLayer:
    """One texture drawn on a set of parts. translucent: composited over the layers before it, alpha kept (slime
    shell). tint: multiplies the texture (dyed overlays such as the wolf collar). size: the texture's expected size."""
    texture: str
    size: tuple
    parts: tuple
    translucent: bool = False
    tint: tuple = None


@dataclass(frozen=True)
class MobSpec:
    """How to draw one mob: its layers (in draw order), the camera (yaw 0 front, 90 side; pitch looks down)."""
    layers: tuple
    yaw: float = 90.0
    pitch: float = 0.0
    what: str = ""   # the variant chosen, for the docs and the tool's output


def C(tex, origin, size, inflate=0.0, mirror=False):
    return Cube(tuple(tex), tuple(origin), tuple(size), inflate, mirror)


def P(name, parent, offset=(0, 0, 0), rot=(0, 0, 0), *cubes):
    return Part(name, parent, tuple(offset), tuple(rot), tuple(cubes))


HALF_PI = math.pi / 2


def compose_parts(parts):
    """Resolve nested parts (parent before child) to world-space Boxes: each part's pivot and rotation compose
    with its parent's exactly as the game's pose stack does (translate to the pivot, then rotate)."""
    world = {"": (IDENTITY, (0.0, 0.0, 0.0))}
    boxes = []
    for p in parts:
        if p.parent not in world:
            raise ExtractError([f"model part {p.name!r}: parent {p.parent!r} is not defined before it"])
        pr, pt = world[p.parent]
        off = _mat_apply(pr, p.offset)
        t = (pt[0] + off[0], pt[1] + off[1], pt[2] + off[2])
        r = _mat_mul(pr, rot_matrix(*p.rot))
        world[p.name] = (r, t)
        for c in p.cubes:
            boxes.append(Box(c.tex, c.origin, c.size, inflate=c.inflate, mirror=c.mirror, pose=t, mat=r))
    return boxes


def _legs(tex, origin, size, spots, mirror_left=False):
    """Four legs of a quadruped: spots = [(name, (x, y, z))]; left legs are mirrored when mirror_left."""
    return [P(n, "", pos, (0, 0, 0), C(tex, origin, size, mirror=mirror_left and n.startswith("left")))
            for n, pos in spots]


def _quad_spots(x, y, zh, zf):
    return [("right_hind_leg", (-x, y, zh)), ("left_hind_leg", (x, y, zh)),
            ("right_front_leg", (-x, y, zf)), ("left_front_leg", (x, y, zf))]


# All part boxes below were read from the 26.3 client's model classes (createBodyLayer of PigModel, CowModel, ...)
# with javap; the comments name the class. y points down, the mob faces -z, the ground is y = 24.

PIG = [  # PigModel (QuadrupedModel body mesh, legHeight 6)
    P("head", "", (0, 12, -6), (0, 0, 0), C((0, 0), (-4, -4, -8), (8, 8, 8)), C((16, 16), (-2, 0, -9), (4, 3, 1))),
    P("body", "", (0, 11, 2), (HALF_PI, 0, 0), C((28, 8), (-5, -10, -7), (10, 16, 8))),
    *_legs((0, 16), (-2, 0, -2), (4, 6, 4), _quad_spots(3, 18, 7, -5)),
]

COW = [  # CowModel
    P("head", "", (0, 4, -8), (0, 0, 0), C((0, 0), (-4, -4, -6), (8, 8, 6)), C((1, 33), (-3, 1, -7), (6, 3, 1)),
      C((22, 0), (-5, -5, -5), (1, 3, 1)), C((22, 0), (4, -5, -5), (1, 3, 1))),
    P("body", "", (0, 5, 2), (HALF_PI, 0, 0), C((18, 4), (-6, -10, -7), (12, 18, 10)), C((52, 0), (-2, 2, -8), (4, 6, 1))),
    *_legs((0, 16), (-2, 0, -2), (4, 12, 4), _quad_spots(4, 12, 7, -5), mirror_left=True),
]

SHEEP_SKIN = [  # SheepModel
    P("head", "", (0, 6, -8), (0, 0, 0), C((0, 0), (-3, -4, -6), (6, 6, 8))),
    P("body", "", (0, 5, 2), (HALF_PI, 0, 0), C((28, 8), (-4, -10, -7), (8, 16, 6))),
    *_legs((0, 16), (-2, 0, -2), (4, 12, 4), _quad_spots(3, 12, 7, -5)),
]
SHEEP_FUR = [  # SheepFurModel (the wool layer, inflated)
    P("head", "", (0, 6, -8), (0, 0, 0), C((0, 0), (-3, -4, -4), (6, 6, 6), inflate=0.6)),
    P("body", "", (0, 5, 2), (HALF_PI, 0, 0), C((28, 8), (-4, -10, -7), (8, 16, 6), inflate=1.75)),
    *[P(n, "", pos, (0, 0, 0), C((0, 16), (-2, 0, -2), (4, 6, 4), inflate=0.5)) for n, pos in _quad_spots(3, 12, 7, -5)],
]

HEN = [  # AdultChickenModel
    P("head", "", (0, 15, -4), (0, 0, 0), C((0, 0), (-2, -6, -2), (4, 6, 3))),
    P("beak", "head", (0, 0, 0), (0, 0, 0), C((14, 0), (-2, -4, -4), (4, 2, 2))),
    P("red_thing", "head", (0, 0, 0), (0, 0, 0), C((14, 4), (-1, -2, -3), (2, 2, 2))),
    P("body", "", (0, 16, 0), (HALF_PI, 0, 0), C((0, 9), (-3, -4, -3), (6, 8, 6))),
    P("right_leg", "", (-2, 19, 1), (0, 0, 0), C((26, 0), (-1, 0, -3), (3, 5, 3))),
    P("left_leg", "", (1, 19, 1), (0, 0, 0), C((26, 0), (-1, 0, -3), (3, 5, 3))),
    P("right_wing", "", (-4, 13, 0), (0, 0, 0), C((24, 13), (0, 0, -3), (1, 4, 6))),
    P("left_wing", "", (4, 13, 0), (0, 0, 0), C((24, 13), (-1, 0, -3), (1, 4, 6))),
]

CHICK = [  # BabyChickenModel
    P("body", "", (0, 20.25, -1.25), (0, 0, 0), C((0, 0), (-2, -2.25, -0.75), (4, 4, 4)), C((10, 8), (-1, -0.25, -1.75), (2, 1, 1))),
    P("left_leg", "", (1, 22, 0.5), (0, 0, 0), C((2, 2), (-0.5, 0, 0), (1, 2, 0)), C((0, 1), (-0.5, 2, -1), (1, 0, 1))),
    P("right_leg", "", (-1, 22, 0.5), (0, 0, 0), C((0, 2), (-0.5, 0, 0), (1, 2, 0)), C((0, 0), (-0.5, 2, -1), (1, 0, 1))),
    P("right_wing", "", (2, 20, 0), (0, 0, 0), C((6, 8), (0, 0, -1), (1, 0, 2))),
    P("left_wing", "", (-2, 20, 0), (0, 0, 0), C((4, 8), (-1, 0, -1), (1, 0, 2))),
]

WOLF_BABY = [  # BabyWolfModel
    P("head", "", (0, 18.25, -4), (0, 0, 0), C((0, 12), (-2.99, -3.25, -3), (6, 5, 5), inflate=0.025),
      C((17, 12), (-1.5, -0.24, -5), (3, 2, 2))),
    P("right_ear", "head", (-2, -4.25, -0.5), (0, 0, 0), C((0, 5), (-1, -1, -0.5), (2, 2, 1))),
    P("left_ear", "head", (2, -4.25, -0.5), (0, 0, 0), C((20, 5), (-1, -1, -0.5), (2, 2, 1))),
    P("body", "", (0, 19, 0), (0, 0, 0), C((0, 0), (-3, -2, -4), (6, 4, 8))),
    P("right_hind_leg", "", (-1.5, 21, 3), (0, 0, 0), C((0, 22), (-1, 0, -1), (2, 3, 2))),
    P("left_hind_leg", "", (1.5, 21, 3), (0, 0, 0), C((8, 22), (-1, 0, -1), (2, 3, 2))),
    P("right_front_leg", "", (-1.5, 21, -3), (0, 0, 0), C((0, 0), (-1, 0, -1), (2, 3, 2))),
    P("left_front_leg", "", (1.5, 21, -3), (0, 0, 0), C((20, 0), (-1, 0, -1), (2, 3, 2))),
    P("tail", "", (0, 19, 3), (-0.5236, 0, 0)),
    P("tail_r1", "tail", (0, -0.6, 0.2), (-3.1, 0, 0), C((22, 16), (-1, -5.7, -1), (2, 6, 2))),
]

WOLF = [  # AdultWolfModel (the real_head / real_tail children carry the boxes)
    P("head", "", (-1, 13.5, -7)),
    P("real_head", "head", (0, 0, 0), (0, 0, 0), C((0, 0), (-2, -3, -2), (6, 6, 4)), C((16, 14), (-2, -5, 0), (2, 2, 1)),
      C((16, 14), (2, -5, 0), (2, 2, 1)), C((0, 10), (-0.5, -0.001, -5), (3, 3, 4))),
    P("body", "", (0, 14, 2), (HALF_PI, 0, 0), C((18, 14), (-3, -2, -3), (6, 9, 6))),
    P("upper_body", "", (-1, 14, -3), (HALF_PI, 0, 0), C((21, 0), (-3, -3, -3), (8, 6, 7))),
    P("right_hind_leg", "", (-2.5, 16, 7), (0, 0, 0), C((0, 18), (0, 0, -1), (2, 8, 2), mirror=True)),
    P("left_hind_leg", "", (0.5, 16, 7), (0, 0, 0), C((0, 18), (0, 0, -1), (2, 8, 2))),
    P("right_front_leg", "", (-2.5, 16, -4), (0, 0, 0), C((0, 18), (0, 0, -1), (2, 8, 2), mirror=True)),
    P("left_front_leg", "", (0.5, 16, -4), (0, 0, 0), C((0, 18), (0, 0, -1), (2, 8, 2))),
    P("tail", "", (-1, 12, 8), (0.62831855, 0, 0)),
    P("real_tail", "tail", (0, 0, 0), (0, 0, 0), C((9, 18), (0, 0, -1), (2, 8, 2))),
]

FOX = [  # AdultFoxModel
    P("head", "", (-1, 16.5, -3), (0, 0, 0), C((1, 5), (-3, -2, -5), (8, 6, 6))),
    P("right_ear", "head", (0, 0, 0), (0, 0, 0), C((8, 1), (-3, -4, -4), (2, 2, 1))),
    P("left_ear", "head", (0, 0, 0), (0, 0, 0), C((15, 1), (3, -4, -4), (2, 2, 1))),
    P("nose", "head", (0, 0, 0), (0, 0, 0), C((6, 18), (-1, 2.01, -8), (4, 2, 3))),
    P("body", "", (0, 16, -6), (HALF_PI, 0, 0), C((24, 15), (-3, 3.999, -3.5), (6, 11, 6))),
    P("right_hind_leg", "", (-5, 17.5, 7), (0, 0, 0), C((13, 24), (2, 0.5, -1), (2, 6, 2), inflate=0.001)),
    P("left_hind_leg", "", (-1, 17.5, 7), (0, 0, 0), C((4, 24), (2, 0.5, -1), (2, 6, 2), inflate=0.001)),
    P("right_front_leg", "", (-5, 17.5, 0), (0, 0, 0), C((13, 24), (2, 0.5, -1), (2, 6, 2), inflate=0.001)),
    P("left_front_leg", "", (-1, 17.5, 0), (0, 0, 0), C((4, 24), (2, 0.5, -1), (2, 6, 2), inflate=0.001)),
    P("tail", "body", (-4, 15, -1), (-0.05235988, 0, 0), C((30, 0), (2, 0, -1), (4, 9, 5))),
]

FROG = [  # FrogModel (no tongue / croaking sac: they are hidden until the frog croaks)
    P("root", "", (0, 24, 0)),
    P("body", "root", (0, -2, 4), (0, 0, 0), C((3, 1), (-3.5, -2, -8), (7, 3, 9)), C((23, 22), (-3.5, -1, -8), (7, 0, 9))),
    P("head", "body", (0, -2, -1), (0, 0, 0), C((23, 13), (-3.5, -1, -7), (7, 0, 9)), C((0, 13), (-3.5, -2, -7), (7, 3, 9))),
    P("eyes", "head", (-0.5, 0, 2)),
    P("right_eye", "eyes", (-1.5, -3, -6.5), (0, 0, 0), C((0, 0), (-1.5, -1, -1.5), (3, 2, 3))),
    P("left_eye", "eyes", (2.5, -3, -6.5), (0, 0, 0), C((0, 5), (-1.5, -1, -1.5), (3, 2, 3))),
    P("left_arm", "body", (4, -1, -6.5), (0, 0, 0), C((0, 32), (-1, 0, -1), (2, 3, 3))),
    P("left_hand", "left_arm", (0, 3, -1), (0, 0, 0), C((18, 40), (-4, 0.01, -4), (8, 0, 8))),
    P("right_arm", "body", (-4, -1, -6.5), (0, 0, 0), C((0, 38), (-1, 0, -1), (2, 3, 3))),
    P("right_hand", "right_arm", (0, 3, 0), (0, 0, 0), C((2, 40), (-4, 0.01, -5), (8, 0, 8))),
    P("left_leg", "root", (3.5, -3, 4), (0, 0, 0), C((14, 25), (-1, 0, -2), (3, 3, 4))),
    P("left_foot", "left_leg", (2, 3, 0), (0, 0, 0), C((2, 32), (-4, 0.01, -4), (8, 0, 8))),
    P("right_leg", "root", (-3.5, -3, 4), (0, 0, 0), C((0, 25), (-2, 0, -2), (3, 3, 4))),
    P("right_foot", "right_leg", (-2, 3, 0), (0, 0, 0), C((18, 32), (-4, 0.01, -4), (8, 0, 8))),
]

SQUID = [  # SquidModel: body block plus eight tentacles in a ring (angle i * 2pi / 8)
    P("body", "", (0, 8, 0), (0, 0, 0), C((0, 0), (-6, -8, -6), (12, 16, 12), inflate=0.02)),
    *[P(f"tentacle{i}", "", (math.cos(i * math.pi / 4) * 5, 15, math.sin(i * math.pi / 4) * 5),
        (0, -i * math.pi / 4 + HALF_PI, 0), C((48, 0), (-1, 0, -1), (2, 18, 2))) for i in range(8)],
]

COD = [  # CodModel
    P("body", "", (0, 22, 0), (0, 0, 0), C((0, 0), (-1, -2, 0), (2, 4, 7))),
    P("head", "", (0, 22, 0), (0, 0, 0), C((11, 0), (-1, -2, -3), (2, 4, 3))),
    P("nose", "", (0, 22, -3), (0, 0, 0), C((0, 0), (-1, -2, -1), (2, 3, 1))),
    P("right_fin", "", (-1, 23, 0), (0, 0, -0.7853982), C((22, 1), (-2, 0, -1), (2, 0, 2))),
    P("left_fin", "", (1, 23, 0), (0, 0, 0.7853982), C((22, 4), (0, 0, -1), (2, 0, 2))),
    P("tail_fin", "", (0, 22, 7), (0, 0, 0), C((22, 3), (0, -2, 0), (0, 4, 4))),
    P("top_fin", "", (0, 20, 0), (0, 0, 0), C((20, -6), (0, -1, -1), (0, 1, 6))),
]

GOAT = [  # GoatModel (the head is the long nose box tilted 55 degrees)
    P("head", "", (1, 14, 0), (0, 0, 0), C((2, 61), (-6, -11, -10), (3, 2, 1)),
      C((2, 61), (2, -11, -10), (3, 2, 1), mirror=True), C((23, 52), (-0.5, -3, -14), (0, 7, 5))),
    P("left_horn", "head", (0, 0, 0), (0, 0, 0), C((12, 55), (-0.01, -16, -10), (2, 7, 2))),
    P("right_horn", "head", (0, 0, 0), (0, 0, 0), C((12, 55), (-2.99, -16, -10), (2, 7, 2))),
    P("nose", "head", (0, -8, -8), (0.9599, 0, 0), C((34, 46), (-3, -4, -8), (5, 7, 10))),
    P("body", "", (0, 24, 0), (0, 0, 0), C((1, 1), (-4, -17, -7), (9, 11, 16)), C((0, 28), (-5, -18, -8), (11, 14, 11))),
    P("left_hind_leg", "", (1, 14, 4), (0, 0, 0), C((36, 29), (0, 4, 0), (3, 6, 3))),
    P("right_hind_leg", "", (-3, 14, 4), (0, 0, 0), C((49, 29), (0, 4, 0), (3, 6, 3))),
    P("left_front_leg", "", (1, 14, -6), (0, 0, 0), C((49, 2), (0, 0, 0), (3, 10, 3))),
    P("right_front_leg", "", (-3, 14, -6), (0, 0, 0), C((35, 2), (0, 0, 0), (3, 10, 3))),
]

BEE = [  # AdultBeeModel
    P("bone", "", (0, 19, 0)),
    P("body", "bone", (0, 0, 0), (0, 0, 0), C((0, 0), (-3.5, -4, -5), (7, 7, 10))),
    P("stinger", "body", (0, 0, 0), (0, 0, 0), C((26, 7), (0, -1, 5), (0, 1, 2))),
    P("left_antenna", "body", (0, -2, -5), (0, 0, 0), C((2, 0), (1.5, -2, -3), (1, 2, 3))),
    P("right_antenna", "body", (0, -2, -5), (0, 0, 0), C((2, 3), (-2.5, -2, -3), (1, 2, 3))),
    P("right_wing", "bone", (-1.5, -4, -3), (0, -0.2618, 0), C((0, 18), (-9, 0, 0), (9, 0, 6), inflate=0.001)),
    P("left_wing", "bone", (1.5, -4, -3), (0, 0.2618, 0), C((0, 18), (0, 0, 0), (9, 0, 6), inflate=0.001, mirror=True)),
    P("front_legs", "bone", (1.5, 3, -2), (0, 0, 0), C((26, 1), (-5, 0, 0), (7, 2, 0))),
    P("middle_legs", "bone", (1.5, 3, 0), (0, 0, 0), C((26, 3), (-5, 0, 0), (7, 2, 0))),
    P("back_legs", "bone", (1.5, 3, 2), (0, 0, 0), C((26, 5), (-5, 0, 0), (7, 2, 0))),
]

MULE = [  # AbstractEquineModel body mesh + DonkeyModel's long ears (chests are only shown on a laden mule)
    P("body", "", (0, 11, 5), (0, 0, 0), C((0, 32), (-5, -8, -17), (10, 10, 22), inflate=0.05)),
    P("head_parts", "", (0, 4, -12), (0.5235988, 0, 0), C((0, 35), (-2.05, -6, -2), (4, 12, 7))),
    P("head", "head_parts", (0, 0, 0), (0, 0, 0), C((0, 13), (-3, -11, -2), (6, 5, 7))),
    P("mane", "head_parts", (0, 0, 0), (0, 0, 0), C((56, 36), (-1, -11, 5.01), (2, 16, 2))),
    P("upper_mouth", "head_parts", (0, 0, 0), (0, 0, 0), C((0, 25), (-2, -11, -7), (4, 5, 5))),
    P("left_hind_leg", "", (4, 14, 7), (0, 0, 0), C((48, 21), (-3, -1.01, -1), (4, 11, 4), mirror=True)),
    P("right_hind_leg", "", (-4, 14, 7), (0, 0, 0), C((48, 21), (-1, -1.01, -1), (4, 11, 4))),
    P("left_front_leg", "", (4, 14, -10), (0, 0, 0), C((48, 21), (-3, -1.01, -1.9), (4, 11, 4), mirror=True)),
    P("right_front_leg", "", (-4, 14, -10), (0, 0, 0), C((48, 21), (-1, -1.01, -1.9), (4, 11, 4))),
    P("tail", "body", (0, -5, 2), (0.5235988, 0, 0), C((42, 36), (-1.5, 0, 0), (3, 14, 4))),
    P("left_ear", "head", (1.25, -10, 4), (0.2617994, 0, 0.2617994), C((0, 12), (-1, -7, 0), (2, 7, 1))),
    P("right_ear", "head", (-1.25, -10, 4), (0.2617994, 0, -0.2617994), C((0, 12), (-1, -7, 0), (2, 7, 1))),
]

SLIME_INNER = [  # SlimeModel inner body layer (core, eyes, mouth)
    P("cube", "", (0, 0, 0), (0, 0, 0), C((0, 16), (-3, 17, -3), (6, 6, 6))),
    P("right_eye", "", (0, 0, 0), (0, 0, 0), C((32, 0), (-3.25, 18, -3.5), (2, 2, 2))),
    P("left_eye", "", (0, 0, 0), (0, 0, 0), C((32, 4), (1.25, 18, -3.5), (2, 2, 2))),
    P("mouth", "", (0, 0, 0), (0, 0, 0), C((32, 8), (0, 21, -3.5), (1, 1, 1))),
]
SLIME_OUTER = [P("cube", "", (0, 0, 0), (0, 0, 0), C((0, 0), (-4, 16, -4), (8, 8, 8)))]  # translucent shell


def _blaze_rods():
    """BlazeModel: three rings of four rods (radius 9, 7, 5), the rod heights wobble by a cosine of the index."""
    rods = []
    rings = [(0.0, 9, -2.0, 0.5, 0), (math.pi / 4, 7, 2.0, 0.5, 4), (0.47123894, 5, 11.0, 0.75, 8)]
    for start, radius, y0, k, first in rings:
        for j in range(4):
            a = start + j * HALF_PI
            i = first + j
            rods.append(P(f"rod{i}", "", (math.cos(a) * radius, y0 + math.cos(i * k), math.sin(a) * radius), (0, 0, 0),
                          C((0, 16), (0, 0, 0), (2, 8, 2))))
    return rods


BLAZE = [P("head", "", (0, 0, 0), (0, 0, 0), C((0, 0), (-4, -4, -4), (8, 8, 8))), *_blaze_rods()]

RABBIT = [  # AdultRabbitModel
    P("body", "", (0, 23, 4), (-0.3927, 0, 0), C((0, 0), (-4, -6, -9), (8, 6, 10))),
    P("tail", "body", (0, -4.9916, 0.0125), (0, 0, 0), C((20, 16), (-2, -3.0084, -1.0125), (4, 4, 4))),
    P("head", "body", (0, -5.2929, -8.1213), (0.3927, 0, 0), C((0, 16), (-2.5, -3, -4), (5, 5, 5))),
    P("left_ear", "head", (1.5, -3.7071, -0.8787), (0, 0, 0), C((32, 0), (-1, -4.2929, -0.1213), (2, 5, 1))),
    P("right_ear", "head", (-1.5, -3.7071, -0.8787), (0, 0, 0), C((26, 0), (-1, -4.2929, -0.1213), (2, 5, 1))),
    P("frontlegs", "body", (0, -1.5349, -6.3108)),
    P("right_front_leg", "frontlegs", (-2, 1.9239, 0.3827), (0.3927, 0, 0), C((36, 18), (-0.9, -1, -0.9), (2, 4, 2))),
    P("left_front_leg", "frontlegs", (2, 1.9239, 0.4827), (0.3927, 0, 0), C((44, 18), (-1, -1, -1), (2, 4, 2))),
    P("backlegs", "", (0, 23, 4)),
    P("right_hind_leg", "backlegs", (-3, 0.5, 0)),
    P("right_haunch", "right_hind_leg", (0, -0.5, 0), (0, 0.3927, 0), C((20, 24), (-1, 0, -5), (2, 1, 6))),
    P("left_hind_leg", "backlegs", (3, 0.5, 0)),
    P("left_haunch", "left_hind_leg", (0, -0.5, 0), (0, -0.3927, 0), C((36, 24), (-1, 0, -5), (2, 1, 6))),
]

PANDA = [  # PandaModel
    P("head", "", (0, 11.5, -17), (0, 0, 0), C((0, 6), (-6.5, -5, -4), (13, 10, 9)), C((45, 16), (-3.5, 0, -6), (7, 5, 2)),
      C((52, 25), (3.5, -8, -1), (5, 4, 1)), C((52, 25), (-8.5, -8, -1), (5, 4, 1))),
    P("body", "", (0, 10, 0), (HALF_PI, 0, 0), C((0, 25), (-9.5, -13, -6.5), (19, 26, 13))),
    *_legs((40, 0), (-3, 0, -3), (6, 9, 6), [("right_hind_leg", (-5.5, 15, 9)), ("left_hind_leg", (5.5, 15, 9)),
                                            ("right_front_leg", (-5.5, 15, -9)), ("left_front_leg", (5.5, 15, -9))]),
]

CAMEL = [  # AdultCamelModel
    P("body", "", (0, 4, 9.5), (0, 0, 0), C((0, 25), (-7.5, -12, -23.5), (15, 12, 27))),
    P("hump", "body", (0, -12, -10), (0, 0, 0), C((74, 0), (-4.5, -5, -5.5), (9, 5, 11))),
    P("tail", "body", (0, -9, 3.5), (0, 0, 0), C((122, 0), (-1.5, 0, 0), (3, 14, 0))),
    P("head", "body", (0, -3, -19.5), (0, 0, 0), C((60, 24), (-3.5, -7, -15), (7, 8, 19)),
      C((21, 0), (-3.5, -21, -15), (7, 14, 7)), C((50, 0), (-2.5, -21, -21), (5, 5, 6))),
    P("left_ear", "head", (2.5, -21, -9.5), (0, 0, 0), C((45, 0), (-0.5, 0.5, -1), (3, 1, 2))),
    P("right_ear", "head", (-2.5, -21, -9.5), (0, 0, 0), C((67, 0), (-2.5, 0.5, -1), (3, 1, 2))),
    P("left_hind_leg", "", (4.9, 1, 9.5), (0, 0, 0), C((58, 16), (-2.5, 2, -2.5), (5, 21, 5))),
    P("right_hind_leg", "", (-4.9, 1, 9.5), (0, 0, 0), C((94, 16), (-2.5, 2, -2.5), (5, 21, 5))),
    P("left_front_leg", "", (4.9, 1, -10.5), (0, 0, 0), C((0, 0), (-2.5, 2, -2.5), (5, 21, 5))),
    P("right_front_leg", "", (-4.9, 1, -10.5), (0, 0, 0), C((0, 26), (-2.5, 2, -2.5), (5, 21, 5))),
]

PIGLIN = [  # AdultPiglinModel on the player body plan (classic 4px arms); ears flare out at 30 degrees
    P("head", "", (0, 0, 0), (0, 0, 0), C((0, 0), (-5, -8, -4), (10, 8, 8)), C((31, 1), (-2, -4, -5), (4, 4, 1)),
      C((2, 4), (2, -2, -5), (1, 2, 1)), C((2, 0), (-3, -2, -5), (1, 2, 1))),
    P("left_ear", "head", (4.5, -6, 0), (0, 0, -0.5235988), C((51, 6), (0, 0, -2), (1, 5, 4))),
    P("right_ear", "head", (-4.5, -6, 0), (0, 0, 0.5235988), C((39, 6), (-1, 0, -2), (1, 5, 4))),
    P("body", "", (0, 0, 0), (0, 0, 0), C((16, 16), (-4, 0, -2), (8, 12, 4))),
    P("right_arm", "", (-5, 2, 0), (0, 0, 0), C((40, 16), (-3, -2, -2), (4, 12, 4))),
    P("left_arm", "", (5, 2, 0), (0, 0, 0), C((32, 48), (-1, -2, -2), (4, 12, 4))),
    P("right_leg", "", (-1.9, 12, 0), (0, 0, 0), C((0, 16), (-2, 0, -2), (4, 12, 4))),
    P("left_leg", "", (1.9, 12, 0), (0, 0, 0), C((16, 48), (-2, 0, -2), (4, 12, 4))),
]

HOGLIN = [  # HoglinModel
    P("body", "", (0, 7, 0), (0, 0, 0), C((1, 1), (-8, -7, -13), (16, 14, 26))),
    P("mane", "body", (0, -14, -7), (0, 0, 0), C((90, 33), (0, 0, -9), (0, 10, 19), inflate=0.001)),
    P("head", "", (0, 2, -12), (0.87266463, 0, 0), C((61, 1), (-7, -3, -19), (14, 6, 19))),
    P("right_ear", "head", (-6, -2, -3), (0, 0, -0.6981317), C((1, 1), (-6, -1, -2), (6, 1, 4))),
    P("left_ear", "head", (6, -2, -3), (0, 0, 0.6981317), C((1, 6), (0, -1, -2), (6, 1, 4))),
    P("right_horn", "head", (-7, 2, -12), (0, 0, 0), C((10, 13), (-1, -11, -1), (2, 11, 2))),
    P("left_horn", "head", (7, 2, -12), (0, 0, 0), C((1, 13), (-1, -11, -1), (2, 11, 2))),
    P("right_front_leg", "", (-4, 10, -8.5), (0, 0, 0), C((66, 42), (-3, 0, -3), (6, 14, 6))),
    P("left_front_leg", "", (4, 10, -8.5), (0, 0, 0), C((41, 42), (-3, 0, -3), (6, 14, 6))),
    P("right_hind_leg", "", (-5, 13, 10), (0, 0, 0), C((21, 45), (-2.5, 0, -2.5), (5, 11, 5))),
    P("left_hind_leg", "", (5, 13, 10), (0, 0, 0), C((0, 45), (-2.5, 0, -2.5), (5, 11, 5))),
]

BAT = [  # BatModel, wings spread (the model's rest pose)
    P("body", "", (0, 17, 0), (0, 0, 0), C((0, 0), (-1.5, 0, -1), (3, 5, 2))),
    P("head", "", (0, 17, 0), (0, 0, 0), C((0, 7), (-2, -3, -1), (4, 3, 2))),
    P("right_ear", "head", (-1.5, -2, 0), (0, 0, 0), C((1, 15), (-2.5, -4, 0), (3, 5, 0))),
    P("left_ear", "head", (1.1, -3, 0), (0, 0, 0), C((8, 15), (-0.1, -3, 0), (3, 5, 0))),
    P("right_wing", "body", (-1.5, 0, 0), (0, 0, 0), C((12, 0), (-2, -2, 0), (2, 7, 0))),
    P("right_wing_tip", "right_wing", (-2, 0, 0), (0, 0, 0), C((16, 0), (-6, -2, 0), (6, 8, 0))),
    P("left_wing", "body", (1.5, 0, 0), (0, 0, 0), C((12, 7), (0, -2, 0), (2, 7, 0))),
    P("left_wing_tip", "left_wing", (2, 0, 0), (0, 0, 0), C((16, 8), (0, -2, 0), (6, 8, 0))),
    P("feet", "body", (0, 5, 0), (0, 0, 0), C((16, 16), (-1.5, 0, 0), (3, 2, 0))),
]

WOLF_COLLAR_RED = (0xB0, 0x2E, 0x26)   # DyeColor.RED, the game's default collar

# The mob pictures. `texture` is under assets/minecraft/textures/; `size` is the layout the boxes were read for.
MOBS = {
    "pig": MobSpec((MobLayer("entity/pig/pig_temperate.png", (64, 64), tuple(PIG)),), 90, 0, "temperate pig, side"),
    "cow": MobSpec((MobLayer("entity/cow/cow_temperate.png", (64, 64), tuple(COW)),), 90, 0, "temperate cow, side"),
    "sheep": MobSpec((MobLayer("entity/sheep/sheep.png", (64, 32), tuple(SHEEP_SKIN)),
                      MobLayer("entity/sheep/sheep_wool.png", (64, 32), tuple(SHEEP_FUR))), 90, 0,
                     "white sheep with wool, side"),
    "hen": MobSpec((MobLayer("entity/chicken/chicken_temperate.png", (64, 32), tuple(HEN)),), 60, 8,
                   "temperate chicken, three-quarter view (its legs are 1px lines on the back faces)"),
    "chick": MobSpec((MobLayer("entity/chicken/chicken_temperate_baby.png", (16, 16), tuple(CHICK)),), 35, 18,
                     "temperate baby chicken, three-quarter view from above (its legs and wings are flat quads)"),
    "pup": MobSpec((MobLayer("entity/wolf/wolf_tame.png", (64, 32), tuple(WOLF)),
                    MobLayer("entity/wolf/wolf_collar.png", (64, 32), tuple(WOLF), tint=WOLF_COLLAR_RED)),
                   90, 0, "tame wolf with the red collar, side (the baby wolf model draws a stubby tail that reads as a 5th leg)"),
    "fox": MobSpec((MobLayer("entity/fox/fox.png", (48, 32), tuple(FOX)),), 90, 0, "red fox, side"),
    "frog": MobSpec((MobLayer("entity/frog/frog_temperate.png", (48, 48), tuple(FROG)),), 50, 22,
                    "temperate frog, three-quarter view from above (its eyes sit on top of the head)"),
    "squid": MobSpec((MobLayer("entity/squid/squid.png", (64, 32), tuple(SQUID)),), 0, 0, "squid, front (the eyes are on its front face)"),
    "cod": MobSpec((MobLayer("entity/fish/cod.png", (32, 32), tuple(COD)),), 90, 0, "cod, side"),
    "goat": MobSpec((MobLayer("entity/goat/goat.png", (64, 64), tuple(GOAT)),), 90, 0, "goat, side"),
    "bee": MobSpec((MobLayer("entity/bee/bee.png", (64, 64), tuple(BEE)),), 60, 30,
                   "calm bee, three-quarter view from above (flat wings)"),
    "mule": MobSpec((MobLayer("entity/horse/mule.png", (64, 64), tuple(MULE)),), 90, 0, "mule, side"),
    "slime": MobSpec((MobLayer("entity/slime/slime.png", (64, 32), tuple(SLIME_INNER)),
                      MobLayer("entity/slime/slime.png", (64, 32), tuple(SLIME_OUTER), translucent=True)), 0, 0,
                     "green slime, front, translucent shell over the core"),
    "blaze": MobSpec((MobLayer("entity/blaze/blaze.png", (64, 32), tuple(BLAZE)),), 0, 0, "blaze, front"),
    "rabbit": MobSpec((MobLayer("entity/rabbit/rabbit_brown.png", (64, 64), tuple(RABBIT)),), 60, 8,
                      "brown rabbit, three-quarter view"),
    "panda": MobSpec((MobLayer("entity/panda/panda.png", (64, 64), tuple(PANDA)),), 90, 0, "classic panda, side"),
    "camel": MobSpec((MobLayer("entity/camel/camel.png", (128, 128), tuple(CAMEL)),), 90, 0, "camel, side"),
    "piglin": MobSpec((MobLayer("entity/piglin/piglin.png", (64, 64), tuple(PIGLIN)),), 0, 0, "piglin, front"),
    "hoglin": MobSpec((MobLayer("entity/hoglin/hoglin.png", (128, 64), tuple(HOGLIN)),), 60, 10, "hoglin, three-quarter view (shows the face and tusks)"),
    "bat": MobSpec((MobLayer("entity/bat/bat.png", (32, 32), tuple(BAT)),), 0, 0, "bat, front, wings spread"),
}


def _tinted(im, rgb):
    """Multiply an RGBA texture by an RGB tint (the game's dye colours on overlay layers)."""
    out = im.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            px[x, y] = (r * rgb[0] // 255, g * rgb[1] // 255, b * rgb[2] // 255, a)
    return out


def compose_mob(layers, view, scale, translucent_layers=()):
    """Compose a mob picture. layers: [(RGBA texture, parts)] drawn with one shared depth buffer, then
    translucent_layers [(texture, parts)] each composited over it with its own alpha. Returns an RGBA image cropped
    to the mob's pixels (transparent background, nearest-neighbour at `scale` pixels per model unit)."""
    solid = [(tex, "full", compose_parts(parts)) for tex, parts in layers]
    shells = [(tex, "full", compose_parts(parts)) for tex, parts in translucent_layers]
    every = [b for layer in solid + shells for b in layer[2]]
    bounds = view_bounds(every, view)
    im = rasterise(solid, [], bounds, scale, view=view, cull=False)
    for shell in shells:
        im.alpha_composite(rasterise([shell], [], bounds, scale, view=view, keep_alpha=True, cull=False))
    box = im.getbbox()
    if box is None:
        raise ExtractError(["mob rendered nothing (texture regions empty?)"])
    return im.crop(box)


def build_mob(jar, name, scale):
    """The picture of mob `name` (a key of MOBS); None after recording a missing texture. A texture whose size is
    not the layout the boxes were read for is a loud error: the UV map would be garbage."""
    spec = MOBS.get(name)
    if spec is None:
        raise ExtractError([f"unknown mob {name!r} (known: {', '.join(sorted(MOBS))})"])
    solid, shells = [], []
    for lyr in spec.layers:
        tex = jar.image(lyr.texture)
        if tex is None:
            return None
        if tex.size != lyr.size:
            raise ExtractError([f"{lyr.texture} is {tex.size[0]}x{tex.size[1]}, the {name} model expects "
                                f"{lyr.size[0]}x{lyr.size[1]}: the entity model changed, re-read it"])
        if lyr.tint:
            tex = _tinted(tex, lyr.tint)
        (shells if lyr.translucent else solid).append((tex, lyr.parts))
    return compose_mob(solid, view_matrix(spec.yaw, spec.pitch), scale, shells)


# --------------------------------------------------------------------------------------------------
# Jar access
# --------------------------------------------------------------------------------------------------

class Jar:
    """Read-only view of the client jar that records every texture it could not find."""

    def __init__(self, path):
        self.path = Path(path)
        self.missing = []
        try:
            self.zip = zipfile.ZipFile(self.path)
        except (OSError, zipfile.BadZipFile) as e:
            raise ExtractError([f"cannot open jar {self.path}: {e}"])
        self.names = set(self.zip.namelist())

    def sha256(self):
        h = hashlib.sha256()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def version(self):
        try:
            return json.loads(self.zip.read("version.json"))["id"]
        except (KeyError, ValueError) as e:
            raise ExtractError([f"jar has no readable version.json: {e}"])

    def optional_bytes(self, rel):
        name = TEX + rel
        return self.zip.read(name) if name in self.names else None

    def image(self, rel):
        """RGBA image of textures/<rel>; records a missing texture and returns None."""
        name = TEX + rel
        if name not in self.names:
            self.missing.append(rel)
            return None
        return Image.open(io.BytesIO(self.zip.read(name))).convert("RGBA")

    def first_frame(self, rel):
        """The first frame of a (possibly animated) texture: crop the top square of the strip per .mcmeta."""
        im = self.image(rel)
        if im is None:
            return None
        meta = self.optional_bytes(rel + ".mcmeta")
        w, h = im.size
        if meta is None and h == w:
            return im
        fw, fh, index = w, w, 0
        if meta is not None:
            anim = json.loads(meta).get("animation", {})
            fw, fh = anim.get("width", w), anim.get("height", anim.get("width", w))
            frames = anim.get("frames")
            if frames:
                first = frames[0]
                index = first["index"] if isinstance(first, dict) else first
        per_row = max(1, w // fw)
        x, y = (index % per_row) * fw, (index // per_row) * fh
        if y + fh > h:
            raise ExtractError([f"{rel}: animation frame {index} lies outside {w}x{h}"])
        return im.crop((x, y, x + fw, y + fh))


# --------------------------------------------------------------------------------------------------
# Builders: each returns an RGBA image (or None after recording a missing texture on the jar)
# --------------------------------------------------------------------------------------------------

def build_villager(jar, profession, scale, with_layers=("base", "type", "profession")):
    """Front view of a villager: villager.png + type/plains.png + profession/<p>.png (+ optional level)."""
    layers = []
    if profession == "wandering_trader":
        tex = jar.image("entity/wandering_trader/wandering_trader.png")
        if tex is None:
            return None
        # the trader's single texture carries its hood in the hat region; it shows without a brim
        return rasterise([(tex, "partial")], VILLAGER_BOXES, VILLAGER_BOUNDS, scale)
    base = jar.image("entity/villager/villager.png")
    typ = jar.image("entity/villager/type/plains.png")
    prof = jar.image(f"entity/villager/profession/{profession}.png")
    if base is None or typ is None or prof is None:
        return None
    layers.append((base, "none"))
    layers.append((typ, hat_state(jar.optional_bytes("entity/villager/type/plains.png.mcmeta"))))
    layers.append((prof, hat_state(jar.optional_bytes(f"entity/villager/profession/{profession}.png.mcmeta"))))
    return rasterise(layers, VILLAGER_BOXES, VILLAGER_BOUNDS, scale)


def build_badge(jar, tier, scale):
    """The profession-level layer alone, drawn on the villager model and cropped to its pixels."""
    tex = jar.image(f"entity/villager/profession_level/{tier}.png")
    if tex is None:
        return None
    im = rasterise([(tex, "full")], VILLAGER_BOXES, VILLAGER_BOUNDS, scale)
    bbox = im.getbbox()
    if bbox is None:
        raise ExtractError([f"badge {tier}: level layer rendered nothing"])
    return im.crop(bbox)


def build_llama(jar, scale):
    tex = jar.image("entity/llama/llama_creamy.png")
    if tex is None:
        return None
    return rasterise([(tex, "none")], LLAMA_BOXES, LLAMA_BOUNDS, scale)


def build_chest(jar):
    """Chest front 14x15 cropped from entity/chest/normal.png: lid front, base front and the lock."""
    tex = jar.image("entity/chest/normal.png")
    if tex is None:
        return None
    im = Image.new("RGBA", (14, 15), (0, 0, 0, 0))
    im.paste(tex.crop((42, 14, 56, 19)), (0, 0))      # lid, south face of the 14x5x14 box at (0,0)
    im.paste(tex.crop((42, 33, 56, 43)), (0, 5))      # base, south face of the 14x10x14 box at (0,19)
    im.paste(tex.crop((4, 1, 6, 5)), (6, 3))          # lock, south face of the 2x4x1 box at (0,0)
    return im


def build_bed(jar):
    """Top-down bed 16x32: the head half above the foot half (white wool bed)."""
    head, foot = jar.image("block/white_bed_head_up.png"), jar.image("block/white_bed_foot_up.png")
    if head is None or foot is None:
        return None
    im = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    im.paste(head, (0, 0))
    im.paste(foot, (0, 16))
    return im


COMPOSITES = {"chest": build_chest, "bed": build_bed}


def load_mapping(path=MAP_PATH):
    """Read + validate the shared sprite-id mapping. Contract documented in docs/textures.md."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise ExtractError([f"cannot read mapping {path}: {e}"])
    problems = []
    if data.get("v") != 1:
        problems.append(f"mapping v must be 1, got {data.get('v')!r}")
    entries = data.get("entries", {})
    for sid, e in entries.items():
        kind = e.get("kind")
        need = {"item": "jar", "block": "jar", "villager": "profession", "badge": "tier",
                "composite": "name", "trader": None, "llama": None, "mob": "mob"}
        if kind not in need:
            problems.append(f"{sid}: unknown kind {kind!r}")
        elif kind == "mob" and e.get("mob") not in MOBS:
            problems.append(f"{sid}: unknown mob {e.get('mob')!r} (known: {', '.join(sorted(MOBS))})")
        elif need[kind] and need[kind] not in e:
            problems.append(f"{sid}: kind {kind} needs field {need[kind]!r}")
        # Optional "tint": [r,g,b] multiplies an item/block texture that the game colours at runtime (leaves, vine
        # are grey in the jar and tinted by biome). Anything else is rejected, not ignored.
        if "tint" in e and not (kind in ("item", "block") and isinstance(e["tint"], list) and len(e["tint"]) == 3
                                and all(isinstance(c, int) and 0 <= c <= 255 for c in e["tint"])):
            problems.append(f"{sid}: tint must be [r,g,b] (ints 0-255) on an item/block entry, got {e['tint']!r}")
    if problems:
        raise ExtractError(problems)
    return data


def out_path(entry):
    """Relative output path for a mapping entry (the manifest 'sprites' value)."""
    k = entry["kind"]
    if k in ("item", "block"):
        suffix = "_tinted" if "tint" in entry else ""  # a tinted copy never overwrites the plain texture
        return f"{k}s/{entry['jar'].split('/')[-1]}{suffix}.png"
    if k == "villager":
        return f"villagers/{entry['profession']}.png"
    if k == "trader":
        return "villagers/wandering_trader.png"
    if k == "llama":
        return "villagers/trader_llama.png"
    if k == "mob":
        return f"mobs/{entry['mob']}.png"
    if k == "badge":
        return f"badges/{entry['tier']}.png"
    return f"blocks/{entry['name']}.png"  # composite


def build_all(jar, mapping, scale, mob_scale=2):
    """Build every mapped output in memory. Returns ({relpath: Image}, {sprite id: relpath})."""
    images, sprites = {}, {}
    for sid, e in mapping["entries"].items():
        rel = out_path(e)
        sprites[sid] = rel
        if rel in images:
            continue
        k = e["kind"]
        if k in ("item", "block"):
            im = jar.first_frame(f"{e['jar']}.png")
            if im is not None and "tint" in e:
                im = _tinted(im.convert("RGBA"), tuple(e["tint"]))
        elif k == "villager":
            im = build_villager(jar, e["profession"], scale)
        elif k == "trader":
            im = build_villager(jar, "wandering_trader", scale)
        elif k == "llama":
            im = build_llama(jar, scale)
        elif k == "mob":
            im = build_mob(jar, e["mob"], mob_scale)
        elif k == "badge":
            im = build_badge(jar, e["tier"], scale)
        else:
            if e["name"] not in COMPOSITES:
                raise ExtractError([f"{sid}: unknown composite {e['name']!r}"])
            im = COMPOSITES[e["name"]](jar)
        if im is not None:
            images[rel] = im
    if jar.missing:
        raise ExtractError([f"missing in jar: textures/{m}" for m in sorted(set(jar.missing))])
    return images, sprites


def png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def check_git_ignored(out):
    """Refuse to write inside the repo unless git ignores the target: the textures must never be committed."""
    try:
        out.resolve().relative_to(REPO)
    except ValueError:
        return  # outside the repo: nothing to commit
    probe = out / "manifest.json"
    r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", str(probe)], capture_output=True)
    if r.returncode != 0:
        raise ExtractError([f"{out} is not git-ignored; refusing to write Minecraft textures there"])


def extract(jar_path, out, scale=8, mapping_path=MAP_PATH, mob_scale=2):
    """Run the whole extraction. Returns the manifest dict. Raises ExtractError (nothing written) on failure."""
    jar_path, out = Path(jar_path), Path(out)
    if not jar_path.is_file():
        raise ExtractError([f"jar not found: {jar_path} (pass --jar)"])
    mapping = load_mapping(mapping_path)
    check_git_ignored(out)
    jar = Jar(jar_path)
    version = jar.version()
    images, sprites = build_all(jar, mapping, scale, mob_scale)
    files = {}
    for rel, im in sorted(images.items()):
        data = png_bytes(im)
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[rel] = {"w": im.width, "h": im.height, "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {"v": MANIFEST_V, "source_jar": str(jar_path), "jar_sha256": jar.sha256(),
                "minecraft_version": version, "files": files, "sprites": sprites}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def contact_sheet(out, manifest, dest, kinds=("villagers", "badges")):
    """Scratch helper: lay the composed outputs on a magenta sheet so they can be eyeballed."""
    items = [r for r in sorted(manifest["files"]) if r.split("/")[0] in kinds]
    ims = [Image.open(Path(out) / r).convert("RGBA") for r in items]
    cw = max(i.width for i in ims) + 8
    ch = max(i.height for i in ims) + 8
    cols = 5
    rows = -(-len(ims) // cols)
    sheet = Image.new("RGBA", (cols * cw, rows * ch), (90, 140, 200, 255))
    for n, im in enumerate(ims):
        sheet.alpha_composite(im, ((n % cols) * cw + 4, (n // cols) * ch + 4))
    sheet.convert("RGB").save(dest)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jar", default=str(DEFAULT_JAR), help="Minecraft client jar (default: %(default)s)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output dir (default: %(default)s)")
    ap.add_argument("--scale", type=int, default=8, help="villager/llama/badge pixel scale (nearest-neighbour)")
    ap.add_argument("--mob-scale", type=int, default=2,
                    help="mob picture pixels per model unit (default %(default)s: the app upscales by whole numbers)")
    ap.add_argument("--contact-sheet", help="also write a villager contact sheet PNG here (for eyeballing)")
    args = ap.parse_args(argv)
    try:
        manifest = extract(args.jar, args.out, args.scale, mob_scale=args.mob_scale)
        if args.contact_sheet:
            contact_sheet(args.out, manifest, args.contact_sheet)
    except ExtractError as e:
        print("=" * 64, file=sys.stderr)
        print("FAILED: Minecraft texture extraction did not complete", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        print("=" * 64, file=sys.stderr)
        return 1
    print(f"OK: {len(manifest['files'])} files, {len(manifest['sprites'])} sprite ids "
          f"(Minecraft {manifest['minecraft_version']}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
