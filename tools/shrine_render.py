"""Isometric PNG of the shrine block list, drawn with the REAL block textures from the local Minecraft jar.

For review only (the parent looks at the design before it is built). The jar's textures are Mojang's: the
picture is for local viewing and is never committed (see docs/textures.md). Loud failure: a block without a mapping
or a texture missing from the jar raises ShrineError listing every one; nothing half-drawn is saved.

Projection: 2:1 isometric looking from the south-east above (+x, +y, +z). South faces (the entrance side) are on the
left, east faces on the right. Boxes are drawn far to near (ascending x+y+z), each face an affine-mapped texture.
"""
import io
import zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # loud: rendering cannot work without Pillow
    raise SystemExit("FAILED: Pillow is required to render (pip install Pillow)")

import shrine

# block name -> (top texture, side texture, shape). shape: cube | slab | stair | post | small | sign
TEXTURES = {
    "stone_bricks": ("stone_bricks", "stone_bricks", "cube"),
    "polished_andesite": ("polished_andesite", "polished_andesite", "cube"),
    "polished_blackstone_bricks": ("polished_blackstone_bricks", "polished_blackstone_bricks", "cube"),
    "iron_block": ("iron_block", "iron_block", "cube"),
    "sea_lantern": ("sea_lantern", "sea_lantern", "cube"),
    "glowstone": ("glowstone", "glowstone", "cube"),
    "dark_oak_log": ("dark_oak_log_top", "dark_oak_log", "cube"),
    "stripped_dark_oak_log": ("stripped_dark_oak_log_top", "stripped_dark_oak_log", "cube"),
    "dark_oak_planks": ("dark_oak_planks", "dark_oak_planks", "cube"),
    "dark_oak_stairs": ("dark_oak_planks", "dark_oak_planks", "stair"),
    "dark_oak_slab": ("dark_oak_planks", "dark_oak_planks", "slab"),
    "crimson_stairs": ("crimson_planks", "crimson_planks", "stair"),
    "dark_oak_fence": ("dark_oak_planks", "dark_oak_planks", "post"),
    "lantern": ("lantern", "lantern", "small"),
    "soul_lantern": ("soul_lantern", "soul_lantern", "small"),
    "end_rod": ("end_rod", "end_rod", "post"),
    "amethyst_cluster": ("amethyst_cluster", "amethyst_cluster", "small"),
    "amethyst_block": ("amethyst_block", "amethyst_block", "cube"),
    "beacon": ("beacon", "beacon", "cube"),
    "purple_stained_glass": ("purple_stained_glass", "purple_stained_glass", "cube"),
    "oak_sign": ("oak_planks", "oak_planks", "sign"),
    "chest": ("oak_planks", "oak_planks", "chest"),
}
GRASS_TINT = (0.49, 0.74, 0.42)  # plains grass colour multiplied onto the grey grass_block_top texture
FACING = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def _prop(props, key):
    for kv in props.strip("[]").split(","):
        if kv.startswith(key + "="):
            return kv.split("=", 1)[1]
    return None


def _boxes(name, shape, props):
    """[(x0, x1, y0, y1, z0, z1)] sub-boxes of the unit cell for a block shape."""
    if shape == "cube":
        return [(0, 1, 0, 1, 0, 1)]
    if shape == "slab":
        return [(0, 1, 0, .5, 0, 1)]
    if shape == "stair":
        dx, dz = FACING[_prop(props, "facing")]  # the tall back is on the facing side
        if dx < 0:
            step = (0, .5, .5, 1, 0, 1)
        elif dx > 0:
            step = (.5, 1, .5, 1, 0, 1)
        elif dz < 0:
            step = (0, 1, .5, 1, 0, .5)
        else:
            step = (0, 1, .5, 1, .5, 1)
        return [(0, 1, 0, .5, 0, 1), step]
    if shape == "post":
        return [(.4, .6, 0, 1, .4, .6)]
    if shape == "small":
        return [(.3, .7, 0, .6, .3, .7)]
    if shape == "sign":
        return [(.45, .55, 0, .55, .45, .55), (.1, .9, .5, .9, .45, .55)]
    if shape == "chest":
        return [(.06, .94, 0, .88, .06, .94)]
    raise shrine.ShrineError(f"render: unknown shape {shape}")


def _affine_paste(canvas, tex, origin, du, dv, shade=1.0, tint=None):
    """Map the texture's unit square onto the parallelogram origin + a*du + b*dv (screen pixels) and composite it."""
    t = tex.copy()
    if shade != 1.0 or tint:
        px = t.load()
        mul = tint or (1, 1, 1)
        for j in range(t.height):
            for i in range(t.width):
                r, g, b, a = px[i, j]
                px[i, j] = (int(min(255, r * shade * mul[0])), int(min(255, g * shade * mul[1])),
                            int(min(255, b * shade * mul[2])), a)
    tw, th = t.size
    xs = [origin[0], origin[0] + du[0], origin[0] + dv[0], origin[0] + du[0] + dv[0]]
    ys = [origin[1], origin[1] + du[1], origin[1] + dv[1], origin[1] + du[1] + dv[1]]
    x0, y0, x1, y1 = int(min(xs)) - 1, int(min(ys)) - 1, int(max(xs)) + 2, int(max(ys)) + 2
    det = du[0] * dv[1] - du[1] * dv[0]
    if abs(det) < 1e-6:
        return
    # inverse of [[du.x, dv.x], [du.y, dv.y]] gives (a, b) in [0,1) for an output pixel; scale to texture pixels
    ia, ib = dv[1] / det, -dv[0] / det
    ic, idd = -du[1] / det, du[0] / det
    # (a, b) = inv * (X - origin); texture coords = (a*tw, b*th); PIL wants output(X, Y) -> input(u, v)
    ox, oy = origin
    coef = (ia * tw, ib * tw, -(ia * ox + ib * oy) * tw, ic * th, idd * th, -(ic * ox + idd * oy) * th)
    patch = t.transform((x1 - x0, y1 - y0), Image.AFFINE,
                        (coef[0], coef[1], coef[0] * x0 + coef[1] * y0 + coef[2],
                         coef[3], coef[4], coef[3] * x0 + coef[4] * y0 + coef[5]),
                        resample=Image.NEAREST)
    _clipped(canvas, patch, x0, y0)


def _clipped(canvas, patch, x0, y0):
    canvas.alpha_composite(patch, (max(0, x0), max(0, y0)), (max(0, -x0), max(0, -y0), patch.width, patch.height))


def render_iso(plan, jar_path, out_path, scale=6, margin=7):
    """Draw plan to out_path (PNG); returns (width, height). scale = pixels per texel (a cube is 16*scale wide)."""
    try:
        jar = zipfile.ZipFile(jar_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise shrine.ShrineError(f"cannot open the Minecraft jar {jar_path}: {e}") from None
    blocks = {c: shrine.parse_block(b) for c, b in plan.cells.items()}
    blocks[plan.chest_cells[0]] = ("minecraft:chest", "[facing=south]")
    unmapped = sorted({bid for bid, _ in blocks.values() if bid.split(":")[1] not in TEXTURES})
    if unmapped:
        raise shrine.ShrineError(f"render: no texture mapping for {unmapped}")
    cache, problems = {}, []

    def tex(name):
        if name not in cache:
            try:
                im = Image.open(io.BytesIO(jar.read(f"assets/minecraft/textures/block/{name}.png"))).convert("RGBA")
            except KeyError:
                problems.append(f"block/{name}.png")
                im = Image.new("RGBA", (16, 16), (255, 0, 255, 255))
            cache[name] = im.crop((0, 0, 16, 16))  # animated strips: first frame
        return cache[name]
    for bid, _ in blocks.values():
        top, side, _s = TEXTURES[bid.split(":")[1]]
        tex(top), tex(side)
    tex("grass_block_top"), tex("stone_bricks")
    if problems:
        raise shrine.ShrineError(f"render: missing textures in {jar_path}: {sorted(set(problems))}")

    W = 16 * scale  # cube width on screen; vertical edge W/2
    ox_, oy_, oz_ = plan.origin
    x_lo, x_hi = ox_ - margin - 3, ox_ + margin + 3
    z_lo, z_hi = oz_ - margin - 3, oz_ + margin + 12
    y_ground = plan.platform_y - 3

    def P(x, y, z):
        return ((x - z) * W / 2, (x + z) * W / 4 - y * W / 2)
    corners = [P(x, y, z) for x in (x_lo, x_hi + 1) for z in (z_lo, z_hi + 1) for y in (y_ground, plan.origin[1] + 14)]
    minx, maxx = min(c[0] for c in corners), max(c[0] for c in corners)
    miny, maxy = min(c[1] for c in corners), max(c[1] for c in corners)
    canvas = Image.new("RGBA", (int(maxx - minx) + 4, int(maxy - miny) + 4), (176, 210, 240, 255))
    shift = (-minx + 2, -miny + 2)

    def S(x, y, z):
        p = P(x, y, z)
        return (p[0] + shift[0], p[1] + shift[1])

    def draw_box(cell, box, top, side):
        x, y, z = cell
        bx0, bx1, by0, by1, bz0, bz1 = box
        X0, X1, Y0, Y1, Z0, Z1 = x + bx0, x + bx1, y + by0, y + by1, z + bz0, z + bz1
        # south face (z = Z1), u along +x
        o = S(X0, Y1, Z1)
        _affine_paste(canvas, tex(side), o, (S(X1, Y1, Z1)[0] - o[0], S(X1, Y1, Z1)[1] - o[1]),
                      (S(X0, Y0, Z1)[0] - o[0], S(X0, Y0, Z1)[1] - o[1]), 0.8)
        # east face (x = X1), u along -z
        o = S(X1, Y1, Z1)
        _affine_paste(canvas, tex(side), o, (S(X1, Y1, Z0)[0] - o[0], S(X1, Y1, Z0)[1] - o[1]),
                      (S(X1, Y0, Z1)[0] - o[0], S(X1, Y0, Z1)[1] - o[1]), 0.62)
        # top face (y = Y1), u along +x, v along +z
        o = S(X0, Y1, Z0)
        _affine_paste(canvas, tex(top), o, (S(X1, Y1, Z0)[0] - o[0], S(X1, Y1, Z0)[1] - o[1]),
                      (S(X0, Y1, Z1)[0] - o[0], S(X0, Y1, Z1)[1] - o[1]), 1.0,
                      GRASS_TINT if top == "grass_block_top" else None)

    for x in range(x_lo, x_hi + 1):  # the grass around the site, one slab thick
        for z in range(z_lo, z_hi + 1):
            draw_box((x, y_ground, z), (0, 1, 0, 1, 0, 1), "grass_block_top", "grass_block_top")
    order = sorted(blocks, key=lambda c: (c[0] + c[1] + c[2], c[1], c[0]))
    # a little masonry under the platform (the real foundation depends on the terrain)
    plat = sorted(plan.columns)
    for x, z in plat:
        for y in range(y_ground + 1, plan.platform_y):
            draw_box((x, y, z), (0, 1, 0, 1, 0, 1), "stone_bricks", "stone_bricks")
    for cell in order:
        bid, props = blocks[cell]
        name = bid.split(":")[1]
        top, side, shape = TEXTURES[name]
        for box in _boxes(name, shape, props):
            draw_box(cell, box, top, side)
    out = canvas.convert("RGB")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)
    return out.size
