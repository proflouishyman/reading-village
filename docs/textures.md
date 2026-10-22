# Real Minecraft textures (local art mode)

## What this is
An optional, local-only art mode that draws real Minecraft textures (villagers, the wandering trader, items,
blocks, and real mob pictures for the 21 mob craft words) instead of the hand-drawn grids in `app/js/sprites.js`. The textures are extracted from Dad's own installed
Minecraft client jar into `app/assets/mc/`. Nothing here is part of the shipped game: with the art mode off, or the
folder absent, the game is unchanged: hand mode draws exactly the same pictures as before the mob pictures were added.

## Licensing note (read this)
The textures are Mojang's. They are used **locally, from the parent's own install**, for the family's own use.
They must **never be committed, pushed, shared or published**. `app/assets/mc/` is in `.gitignore`; the extractor
refuses to write into the repo unless git ignores the target (`git check-ignore`). Before any commit or push of this
repo, confirm `git status` shows nothing under `app/assets/mc/`. The code (extractor, `mctextures.js`, the mapping
JSON) contains no Mojang assets and is safe to commit.

## Files
| File | Role |
|---|---|
| `tools/extract_mc_textures.py` | reads the jar, writes `app/assets/mc/**` and `manifest.json` |
| `app/js/mctextures_map.json` | contract: every sprite id is either in `entries` (real texture) or `unmapped` (hand-drawn on purpose, with a reason) |
| `app/js/mctextures.js` | loads the manifest, preloads images, `getTexture(id)`, the saved art mode |
| `tests/test_extract_mc_textures.py`, `tests/js/mctextures.test.mjs` | tests (no jar needed; the compositor is tested on a tiny synthetic texture) |

## Running the tool
```
python3 tools/extract_mc_textures.py                      # default jar: ~/Library/Application Support/minecraft/versions/26.3/26.3.jar
python3 tools/extract_mc_textures.py --jar /path/to/26.4.jar --scale 8 --mob-scale 2   # --mob-scale: pixels per model unit for mobs/
python3 tools/extract_mc_textures.py --contact-sheet /tmp/villagers.png   # also write a sheet to eyeball
```
Needs Python 3 and Pillow. Output is deterministic, so re-runs are idempotent. **After a Minecraft update, re-run it
with the new `--jar`**; `manifest.json` records the jar path, its SHA-256 and the Minecraft version. Any missing jar,
missing texture or unreadable file prints a `FAILED` banner listing every problem and exits non-zero, before anything
is written.

Outputs (under `app/assets/mc/`): `items/*.png` and `blocks/*.png` (16x16, animated textures use their first frame),
`blocks/chest.png` (14x15, cropped from the chest entity texture), `blocks/bed.png` (16x32, top-down),
`villagers/<profession>.png`, `villagers/wandering_trader.png`, `villagers/trader_llama.png` (front views, default 8x
nearest-neighbour), `mobs/<mob>.png` (see below, default 2x), `badges/<tier>.png` (profession-level layer: the little hat badge).

### How the villager front view is made
The 64x64 entity textures are mapped onto the real model boxes (values read from the client's `VillagerModel` class):
head, hat and brim, nose, body, robe, crossed arms (two cuffs plus forearm band, tilted 0.75 rad forward), legs. An
orthographic front-view rasteriser samples each texel with nearest-neighbour. Layers are drawn as the game does:
`villager.png`, then `type/plains.png`, then `profession/<p>.png`, with a shared depth buffer (later layer wins ties)
and hat visibility from each layer's `.mcmeta` (`none`/`partial`/`full`; brim only when `full`).

### Mob pictures (`mobs/<mob>.png`)
Every mob craft word (21 of them, the table below) shows the real mob in real mode instead of a spawn egg; hand mode keeps the
spawn-egg stand-ins and hand-drawn art. Each picture is composed from the mob's
entity texture(s) in the jar with the same rasteriser, extended with a camera (`view_matrix(yaw, pitch)`: yaw 0 front,
90 side with the mob facing left; pitch looks down), nested model parts (`compose_parts`: pivots and rotations compose as the
game's pose stack does) and no back-face culling (the game's `entityCutoutNoCull`: the chicken's legs are 1px lines
on a box's back faces). Background is transparent and the picture is cropped to the mob; `--mob-scale` (default 2) sets
pixels per model unit, so the app can upscale by whole numbers (`spriteImage`, box 12x12 sprite pixels).
The boxes, pivots and UV offsets in `MOBS` (tools/extract_mc_textures.py) were read from the 26.3 client's model
classes (`createBodyLayer` of PigModel, CowModel, ... via `javap`); a texture whose size is not the layout the boxes
were read for, an unknown mob name or a missing texture is a FAILED line and a non-zero exit (nothing is written).
After a Minecraft update that changes a model, the size check is the tripwire: re-read the class.

| Craft word (sprite id) | Mob key | View | Variant and layers |
|---|---|---|---|
| PIG (`pig`) | pig | side | temperate pig |
| BAT (`bat`) | bat | front | wings spread (the rest pose) |
| PUP (`pup`) | pup | side | tame wolf + red collar overlay (the baby wolf's stubby tail read as a fifth leg) |
| HEN (`hen`) | hen | 3/4 | temperate chicken |
| CHICK (`chick`) | chick | 3/4 from above | temperate baby chicken (flat legs and wings need the raised view) |
| FOX (`fox`) | fox | side | red fox |
| FROG (`frog`) | frog | 3/4 from above | temperate (orange) frog, no tongue or croaking sac |
| SQUID (`squid`) | squid | front | the eyes are on its front face |
| FISH (`fish`) | cod | side | cod (replaces the old `item/cod` icon for `fish`) |
| MULE (`mule`) | mule | side | mule (donkey model, long ears, no chests) |
| SLIME (`slime`) | slime | front | core with face under the translucent shell |
| BLAZE (`blaze`) | blaze | front | head and the three rod rings |
| GOAT (`goat`) | goat | side | goat |
| SHEEP (`sheep`) | sheep | side | white sheep: skin + `sheep_wool.png` fur layer |
| BEE (`bee`) | bee | 3/4 from above | calm bee (flat wings) |
| COW (`cow`) | cow | side | temperate cow |
| RABBIT (`rabbit`) | rabbit | 3/4 | brown rabbit |
| PANDA (`panda`) | panda | side | classic panda |
| CAMEL (`camel`) | camel | side | camel |
| PIGLIN (`piglin`) | piglin | front | piglin on the player body plan, ears at 30 degrees |
| HOGLIN (`hoglin`) | hoglin | 3/4 from above | hoglin, shows face and tusks |

`CHICK` and `BLAZE` used to share the sprite ids `hen` and `torch`; `craft_words.json` now names them `chick` and `blaze`
(stand-ins `hen` and `torch` in `villagelogic.js`, so hand mode draws exactly what it did). The server only stores the
sprite string. A saved treasure entry that still says `torch` or `hen` keeps drawing the torch or the hen.

## Contracts
- `manifest.json`: `{"v":1,"source_jar","jar_sha256","minecraft_version","files":{rel:{w,h,sha256}},"sprites":{spriteId:rel}}`.
- `mctextures_map.json`: `{"v":1,"entries":{id:{kind,...}},"unmapped":{id:reason}}`; kinds: `item`/`block` (`jar` path
  under `textures/`), `villager` (`profession`), `trader`, `llama`, `badge` (`tier`), `composite` (`name`: chest, bed), `mob` (`mob`: a key of `MOBS`; the output is `mobs/<mob>.png`).
- Every id in `SPRITE_NAMES` must be in exactly one of `entries`/`unmapped`; `tests/js/mctextures.test.mjs` enforces it,
  so adding a sprite means classifying it. An id in `entries` may also be a key of `STAND_IN` (the mobs: frog, goat, bee, ...):
  a **real-only** picture with no hand-drawn grid. `resolveSprite` returns such an id as itself when real mode has it mapped
  (otherwise its stand-in, the spawn egg), and `spriteSize` gives it the 12x12 box of the spawn egg it replaces
  (`REAL_ONLY_BOX`, `isRealOnly` in `sprites.js`) so layouts do not move.
- Optional `tint: [r,g,b]` on an `item`/`block` entry multiplies the texture (the jar's leaves and vine are grey; the
  game tints them by biome). The tinted file is written as `<name>_tinted.png`, never over the plain texture. Used by
  `leaf` and `vine` with the default foliage green `[72,181,24]`.
- **Crafting Table pictures (2026-10-21).** A craft word drawn through a `STAND_IN` must have its own real picture, or
  real mode shows the stand-in's texture instead (STICK showed the fishing rod). `tests/js/mctextures.test.mjs` enforces
  this; `STAND_IN_OK` there is empty. BOAT has its own id `oak_boat` (real mode: the oak boat item texture; hand mode: the hand-drawn `boat` through a stand-in). SHIP uses the hand-drawn `boat` sailing sprite in both modes (`boat` is `unmapped` on purpose, the parent 2026-10-21), like `pup`/`bed`/`mud`/`raft`.
  FLAG uses its own hand-drawn `flag` sprite (the jar has no flat banner texture; the stand-in `banner` -> `rug` showed a rug), in
  `unmapped` on purpose like `pup`/`bed`/`mud`/`raft`.
  Words whose real picture was too small or unclear at Crafting Table size (`pup`, `bed`, `mud`, `raft`) are in
  `unmapped` on purpose, so both modes draw the hand-drawn picture. MILK, ROCKET and BUCKET have their own ids
  (`milk`, `rocket`, `bucket`) so each shows the right item.

## Modes (no silent fallback)
`createTextures({mode})`: `"off"` returns `null` for everything (hand-drawn art). `"real"`: a mapped id whose texture
is missing makes `load()` reject and `getTexture()` throw `McTextureError`; an id listed in `unmapped` returns `null`
so the caller draws the hand-drawn sprite deliberately (`textures.unmapped(SPRITE_NAMES)` lists them for Dad; each has
a reason); an id in neither list throws.

## Art mode (wired)
- **The setting**: Dad's settings screen has an **Art** row: "hand" (default) or "real". It is saved in the browser's
  `localStorage` key `reading_village_art_mode` (not in `progress.json`: the server validates `progress.settings` strictly, and the
  textures exist only on this machine). "real" is offered only when `app/assets/mc/manifest.json` is served; otherwise the
  row says the textures are not installed. Switching loads every texture first (`configureTextures`) and saves the mode only
  if that worked; with "real" on, the settings screen lists every sprite that stays hand-drawn on purpose with its reason
  (`textures.unmapped(SPRITE_NAMES)`).
- **Boot**: `main.js` awaits `configureTextures(mode)`. A saved "real" with a missing or incomplete manifest/texture is a
  loud "Could not start" screen naming the sprite id, never a silent hand-drawn game. `/?art=hand` resets the saved mode.
- **Drawing**: `sprites.js` `spriteImage(name, swap)` is what `drawSprite`, `drawSpriteFit` and `spriteElement` draw: in
  "real" mode a mapped id is its texture fitted to the sprite's logical box (`spriteSize`, the hand-drawn grid, so layouts
  never move) at `REAL_SCALE` (10) times that size, integer upscale when it fits, bottom-centre aligned, no smoothing; the
  recolour `swap` does not apply to real textures. `drawSprite`/`spriteElement` size by `spriteSize * scale`, not by the
  hi-res canvas. An unmapped id is its hand-drawn canvas. Real canvases are cached per texture image.
- **`spriteCanvas` stays hand-drawn on purpose**: `scenes.js` slices it by logical pixel (poses, the bed blanket, props
  drawn at 1 canvas px = 1 sprite px), so a hi-res canvas would break the story scenes. Story scenes therefore draw their
  actors and props from the grids and use real textures only through `drawSprite` (coal/iron/... icons).
- **Villagers** keep the shared 14x24 logical box; the 120x216 real front view fits it at scale 1 (bottom-aligned).
- **Badges** (level icons) use recognisable items instead of the 2x3-pixel profession-level layer: stone = stone block,
  iron/gold = ingot, emerald = emerald, diamond = diamond (`mctextures_map.json`; the `badge` extractor kind is still
  supported but no longer mapped).
- **The classification** (`mctextures_map.json`) covers every id in `SPRITE_NAMES` (a test enforces it). Unmapped on purpose:
  the characters and the mobs that are not craft words (hero, dad, creeper, duck, gold_pig), story props and scenery (stink,
  tree, sun, moon, cloud, crown, hat, hut, bun, sock, pot, pan, nut, junk, bag, rug, bathtub, catnip, pit), effects (steam,
  splash_big, magic_portal, x_mark), `chest_open` (only the closed chest has a clean texture) and `villager_locked` (a
  silhouette). The `emerald` id is the emerald ORE block, like coal/iron/gold/diamond. Wallet, price, Sell and inventory-count icons use `emerald_item`, `diamond_item`, `gold_item`, `iron_item`, `coal_item` (`itemSprite()` in sprites.js): the same grids as the ores in hand mode, the item textures (emerald, diamond, ingots, coal) in real mode.
- Never serve or copy `app/assets/mc/` outside this machine (no deploy step, no export).
- Tests: `tests/js/sprites.test.mjs` (both modes, canvas = `spriteSize * REAL_SCALE`), `tests/js/mctextures.test.mjs`
  (art setting, manifest check), `tests/test_ui_village.py` `ArtMode` (settings, listing, loud failure; the texture files
  are faked with `page.route`, so no Mojang files are needed).
