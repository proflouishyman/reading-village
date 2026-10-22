"""Minecraft bridge for the reading game: config, rolls, delivery ledger, console transport, delivery worker.

Python stdlib only. Contract: docs/design.md "Villager shop and Magic Chest".

Rules this module lives by (loud failure):
  * a bad config is a ConfigError naming the field; nothing is defaulted except the documented optional ones;
  * a delivery is marked "delivered" only after the server log confirmed every insert AND a read-back of the
    chest showed the items (ids, counts, enchantments);
  * every failure is stored on the ledger entry (last_error, with the raw log evidence) and shown by
    GET /api/minecraft; nothing is skipped silently.

Loot tables are INLINE in `loot insert` (no datapack). Decision, tested on the Paper 26.3 copy: inline tables work
for plain items, enchantments, stored enchantments, potions and player heads, and a bad item, enchantment or level is
refused loudly ("Failed to parse structure"), so a datapack (needs files on disk, /reload, a pack format to track)
buys nothing. They work only with the 26.x schema (`modifier` + `type`, NOT the older `functions` + `function`); the
older keys are accepted without error and silently ignored, so every delivery is also verified by reading the chest
back. There is no runtime fallback to a datapack.

Contents: config validation, village rules (reading points, level, bells: all DERIVED, never stored), rolls, the
delivery ledger, log parsing, the console transport, the chest/insert bridge and the delivery worker.
"""
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# --- Contract constants -----------------------------------------------------------------------------
CONFIG_VERSION = 1
LEDGER_VERSION = 1
CHEST_SLOTS = 27
MAX_STACK_COUNT = 64
ITEM_ID = re.compile(r"minecraft:[a-z0-9_]+")
ENCH_ID = re.compile(r"minecraft:[a-z0-9_]+")
PLAYER_NAME = re.compile(r"[A-Za-z0-9_.]{1,32}")  # Java names and Bedrock ".gamertag" forms
SCREEN_NAME = re.compile(r"[A-Za-z0-9_.-]+")
ENTRY_ID = re.compile(r"[a-z0-9_]{1,32}")
CRAFT_WORD = re.compile(r"[A-Z]{3,10}")  # mirrors server.py CRAFT_WORD (phonics ladder words are 3 to 10 letters)
SOURCE_KINDS = ("shop", "surprise", "craft", "unlock")  # what created the treasure a delivery carries
STATUSES = ("pending", "delivered", "failed")
SURPRISE_KEYS = ("story_first", "streak10", "adventure_done")  # each names ONE tier
REPLAY_TIERS_KEY = "story_replay_tiers"  # a list of tier names: replay N gets the tier at index min(N-1, len-1)
POINT_KEYS = ("word", "story_first", "letter_mastered")
EARN_KEYS = ("word_emerald", "story_first_emerald", "story_replay_emerald", "craft_emerald")
PRIVATE_OVERRIDE_KEYS = ("player",)  # the only config keys a gitignored overrides file may set
MAX_ATTEMPTS = 2  # first try + one retry, then "failed"
POLL_SECONDS = 15
REPLY_TIMEOUT = 8.0
ALL_FULL_PROBLEM = "All Magic Chests are full"
INVENTORY_KEYS = ("coal", "iron", "gold", "diamond", "wood", "stone", "emerald")  # mirrors server.py
POTION_ITEMS = ("minecraft:tipped_arrow", "minecraft:potion", "minecraft:splash_potion", "minecraft:lingering_potion")
# Items whose stack size is 1: a count of N takes N chest slots and Minecraft answers "Dropped N items" (not
# "Dropped N [Name]"). Found by inserting every configured item on the Paper 26.3 copy; tests/test_minecraft.py
# fails if an entry's slot use is not what this list predicts (checked live by the end-to-end run).
UNSTACKABLE = ("minecraft:writable_book", "minecraft:potion", "minecraft:splash_potion", "minecraft:lingering_potion",
               "minecraft:rabbit_stew", "minecraft:cake", "minecraft:water_bucket")
REQUIRES_VALUES = ("all_professions",)  # the only allowed profession.requires value
PAY_CHOICES = ("bell", "emeralds")
# Every `sprite` named in the config must be one of these: the frontend draws exactly this vocabulary in sprites.js
# (a test checks the config against this list; the frontend checks its sprites against it). Nearest picture wins:
# e.g. every sword uses "sword", every spawn egg "spawn_egg".
ITEM_SPRITES = (
    # existing in sprites.js
    "pickaxe", "bow", "map", "bed", "bell", "rod", "boat", "torch", "diamond", "emerald", "chest", "wood", "stone",
    # tools, weapons, armour
    "sword", "axe", "shovel", "hoe", "crossbow", "arrow", "trident", "shield", "helmet", "chestplate", "leggings",
    "boots", "horse_armor", "elytra", "totem", "netherite", "bucket", "shears",
    # books, paper, decoration
    "book", "enchanted_book", "bookshelf", "name_tag", "banner", "painting", "wool", "saddle", "bundle", "lantern",
    # food and farm
    "bread", "cookie", "cake", "pie", "carrot", "meat", "fish", "golden_apple", "apple",
    # magic and minerals
    "bottle", "potion", "ender_pearl", "glowstone", "redstone", "quartz", "terracotta", "dripstone", "brick",
    # nature (wandering trader)
    "sapling", "flower", "coral", "lichen", "nautilus", "ice", "pumpkin", "sea_pickle", "fish_bucket", "sniffer_egg",
    "music_disc", "heart_of_sea", "key",
    # real-creature pictures
    "spawn_egg",
)
JOB_BLOCK_SPRITES = ("lectern", "blast_furnace", "grindstone", "smithing_table", "composter", "fletching_table",
                     "brewing_stand", "cartography_table", "loom", "smoker", "barrel", "stonecutter", "cauldron",
                     "llama")  # llama = the Wandering Trader's plot


class ConfigError(ValueError):
    """The config is invalid. The message names the field."""


class LedgerError(ValueError):
    """The ledger file is invalid (or an update named something that does not exist)."""


class McError(RuntimeError):
    """A Minecraft command or its confirmation failed; the message carries the raw log evidence."""


class VerifyError(McError):
    """Inserts were confirmed but the chest read-back disagrees. Not retried: a retry would duplicate items."""


class AllFull(McError):
    """No chest has room and no further candidate spot is usable."""


# --- Config -----------------------------------------------------------------------------------------
def _cfg_check(cond, field, msg):
    if not cond:
        raise ConfigError(f"{field}: {msg}")


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _keys(obj, field, required, optional=()):
    _cfg_check(isinstance(obj, dict), field, "must be an object")
    for k in required:
        _cfg_check(k in obj, f"{field}.{k}", "is required")
    for k in obj:
        _cfg_check(k in required or k in optional, f"{field}.{k}", "unknown key")


def _check_cell(c, field):
    _keys(c, field, ("x", "y", "z"))
    for k in "xyz":
        _cfg_check(_is_int(c[k]), f"{field}.{k}", "must be an integer")


def validate_item_entry(e, field):
    """One item entry: {item, count?, enchantments?, stored_enchantments?, profile?, potion?}. Count missing reads as 1."""
    _keys(e, field, ("item",), ("count", "enchantments", "stored_enchantments", "profile", "potion"))
    _cfg_check(isinstance(e["item"], str) and ITEM_ID.fullmatch(e["item"]), f"{field}.item",
               "must look like minecraft:some_item")
    if "count" in e:
        _cfg_check(_is_int(e["count"]) and 1 <= e["count"] <= MAX_STACK_COUNT, f"{field}.count",
                   f"must be an integer 1..{MAX_STACK_COUNT}")
    for k in ("enchantments", "stored_enchantments"):
        if k in e:
            d = e[k]
            _cfg_check(isinstance(d, dict) and d, f"{field}.{k}", "must be a non-empty object {enchantment: level}")
            for name, lvl in d.items():
                _cfg_check(ENCH_ID.fullmatch(name) is not None, f"{field}.{k}.{name}", "must look like minecraft:name")
                _cfg_check(_is_int(lvl) and 1 <= lvl <= 255, f"{field}.{k}.{name}", "level must be an integer 1..255")
    if "potion" in e:
        _cfg_check(e["item"] in POTION_ITEMS, f"{field}.potion", f"only allowed on {list(POTION_ITEMS)}")
        _cfg_check(isinstance(e["potion"], str) and ITEM_ID.fullmatch(e["potion"]) is not None, f"{field}.potion",
                   "must look like minecraft:swiftness")
    if "profile" in e:
        _cfg_check(e["item"] == "minecraft:player_head", f"{field}.profile", "only allowed on minecraft:player_head")
        _cfg_check(isinstance(e["profile"], str) and re.fullmatch(r"[A-Za-z0-9_]{1,16}", e["profile"]) is not None,
                   f"{field}.profile", "must be a Minecraft player name (1-16 letters, digits, underscore)")


def slots_needed(items):
    """Chest slots a list of item entries occupies: 1 per entry, or `count` for an unstackable item."""
    return sum(e.get("count", 1) if e["item"] in UNSTACKABLE else 1 for e in items)


def expand_items(items):
    """The entries a delivery actually inserts, one `loot insert` each: an unstackable item with count N becomes N
    entries of count 1. Found on the Paper 26.3 copy: `loot insert` of 3 potions with a potion_contents component
    delivers 3 PLAIN potions (the component is lost when the stack is split), and the 'Dropped 3 items' reply does
    not reveal it. One insert per unstackable item keeps its components. Deterministic, so the ledger's `inserted`
    resume index (counted in expanded entries) stays valid."""
    out = []
    for e in items:
        if e["item"] in UNSTACKABLE and e.get("count", 1) > 1:
            out += [{**e, "count": 1} for _ in range(e["count"])]
        else:
            out.append(e)
    return out


def validate_items(items, field):
    _cfg_check(isinstance(items, list) and items, field, "must be a non-empty list of item entries")
    _cfg_check(len(items) <= CHEST_SLOTS, field, f"at most {CHEST_SLOTS} entries")
    for i, e in enumerate(items):
        validate_item_entry(e, f"{field}[{i}]")
    _cfg_check(slots_needed(items) <= CHEST_SLOTS, field, f"needs more than {CHEST_SLOTS} chest slots")


def validate_offer(o, f, n_levels, seen_ids):
    """One village offer: {id,label,sprite,price,min_level,items}. Offer ids are unique across all professions."""
    _keys(o, f, ("id", "label", "sprite", "price", "min_level", "items"))
    _cfg_check(isinstance(o["id"], str) and ENTRY_ID.fullmatch(o["id"]) is not None, f"{f}.id",
               "must be 1-32 chars a-z 0-9 _")
    _cfg_check(o["id"] not in seen_ids, f"{f}.id", "duplicate offer id")
    seen_ids.add(o["id"])
    _cfg_check(isinstance(o["label"], str) and o["label"] != "", f"{f}.label", "must be a non-empty string")
    _cfg_check(o["sprite"] in ITEM_SPRITES, f"{f}.sprite", f"must be one of the sprite vocabulary {list(ITEM_SPRITES)}")
    _cfg_check(_is_int(o["price"]) and 1 <= o["price"] <= 100000, f"{f}.price", "must be an integer >= 1 (emeralds)")
    _cfg_check(_is_int(o["min_level"]) and 0 <= o["min_level"] < n_levels, f"{f}.min_level",
               f"must be an integer 0..{n_levels - 1} (an index into village.levels)")
    validate_items(o["items"], f"{f}.items")


def validate_promotions(pr, field):
    """village.promotions = {"spent_thresholds": [ints >= 1, strictly increasing], "then_every": int >= 1}: the child earns
    one villager promotion each time his total emeralds spent crosses a threshold, then one more per `then_every`."""
    _keys(pr, field, ("spent_thresholds", "then_every"))
    th = pr["spent_thresholds"]
    _cfg_check(isinstance(th, list) and th and all(_is_int(t) and t >= 1 for t in th), f"{field}.spent_thresholds",
               "must be a non-empty list of integers >= 1")
    _cfg_check(all(th[i] < th[i + 1] for i in range(len(th) - 1)), f"{field}.spent_thresholds", "must strictly increase")
    _cfg_check(_is_int(pr["then_every"]) and pr["then_every"] >= 1, f"{field}.then_every", "must be an integer >= 1")


def validate_village(v):
    """The village block: professions (with their offers), levels, point weights, bell rate."""
    _keys(v, "village", ("professions", "levels", "points", "bell_every_points", "promotions"))
    validate_promotions(v["promotions"], "village.promotions")
    lv = v["levels"]
    _keys(lv, "village.levels", ("names", "thresholds"))
    names, th = lv["names"], lv["thresholds"]
    _cfg_check(isinstance(names, list) and names and all(isinstance(n, str) and n for n in names),
               "village.levels.names", "must be a non-empty list of non-empty strings")
    _cfg_check(isinstance(th, list) and len(th) == len(names) and all(_is_int(t) for t in th),
               "village.levels.thresholds", "must be a list of integers, one per level name")
    _cfg_check(th[0] == 0 and all(th[i] < th[i + 1] for i in range(len(th) - 1)), "village.levels.thresholds",
               "must start at 0 and strictly increase")
    _keys(v["points"], "village.points", POINT_KEYS)
    for k in POINT_KEYS:
        _cfg_check(_is_int(v["points"][k]) and 0 <= v["points"][k] <= 1000, f"village.points.{k}",
                   "must be an integer 0..1000")
    _cfg_check(_is_int(v["bell_every_points"]) and v["bell_every_points"] >= 1, "village.bell_every_points",
               "must be an integer >= 1")
    profs = v["professions"]
    _cfg_check(isinstance(profs, list) and profs, "village.professions", "must be a non-empty list")
    pids, offer_ids = set(), set()
    for i, p in enumerate(profs):
        f = f"village.professions[{i}]"
        _keys(p, f, ("id", "name", "job_block_sprite", "unlock_emeralds", "offers"),
              ("job_block_item", "unlock_items", "requires"))
        _cfg_check(isinstance(p["id"], str) and ENTRY_ID.fullmatch(p["id"]) is not None, f"{f}.id",
                   "must be 1-32 chars a-z 0-9 _")
        _cfg_check(p["id"] not in pids, f"{f}.id", "duplicate profession id")
        pids.add(p["id"])
        _cfg_check(isinstance(p["name"], str) and p["name"] != "", f"{f}.name", "must be a non-empty string")
        _cfg_check(p["job_block_sprite"] in JOB_BLOCK_SPRITES, f"{f}.job_block_sprite",
                   f"must be one of {list(JOB_BLOCK_SPRITES)}")
        _cfg_check(_is_int(p["unlock_emeralds"]) and 1 <= p["unlock_emeralds"] <= 100000, f"{f}.unlock_emeralds",
                   "must be an integer >= 1")
        _cfg_check(("job_block_item" in p) != ("unlock_items" in p), f,
                   "needs exactly one of job_block_item (villager egg + that block) or unlock_items (explicit list)")
        if "job_block_item" in p:
            _cfg_check(isinstance(p["job_block_item"], str) and ITEM_ID.fullmatch(p["job_block_item"]) is not None,
                       f"{f}.job_block_item", "must look like minecraft:lectern")
        if "unlock_items" in p:
            validate_items(p["unlock_items"], f"{f}.unlock_items")
        if "requires" in p:
            _cfg_check(p["requires"] in REQUIRES_VALUES, f"{f}.requires", f"must be one of {list(REQUIRES_VALUES)}")
        _cfg_check(isinstance(p["offers"], list) and p["offers"], f"{f}.offers", "must be a non-empty list")
        for j, o in enumerate(p["offers"]):
            validate_offer(o, f"{f}.offers[{j}]", len(names), offer_ids)


def validate_config(cfg, craft_words=None):
    """Strictly validate a loaded config dict. craft_words (optional list) must all have a craft_items entry."""
    _keys(cfg, "config", ("v", "enabled", "mc_dir", "screen_session", "player", "chests", "earn", "trades",
                          "craft_items", "tiers", "surprises", "village"), ("forbidden", "shrine"))
    _cfg_check(cfg["v"] == CONFIG_VERSION and _is_int(cfg["v"]), "v", f"must be the integer {CONFIG_VERSION}")
    _cfg_check(isinstance(cfg["enabled"], bool), "enabled", "must be true or false")
    _cfg_check(isinstance(cfg["mc_dir"], str) and cfg["mc_dir"] != "", "mc_dir", "must be a non-empty string")
    _cfg_check(isinstance(cfg["screen_session"], str) and SCREEN_NAME.fullmatch(cfg["screen_session"]) is not None,
               "screen_session", "must be letters, digits, . _ -")
    _cfg_check(isinstance(cfg["player"], str) and PLAYER_NAME.fullmatch(cfg["player"]) is not None, "player",
               "must be a Minecraft player name")

    chests = cfg["chests"]
    _cfg_check(isinstance(chests, list) and chests, "chests", "must be a non-empty list of {x,y,z}")
    for i, c in enumerate(chests):
        _keys(c, f"chests[{i}]", ("x", "y", "z"))
        for k in "xyz":
            _cfg_check(_is_int(c[k]), f"chests[{i}].{k}", "must be an integer")
        _cfg_check(-64 <= c["y"] <= 319, f"chests[{i}].y", "must be -64..319")
    for i in range(len(chests)):
        for j in range(i):
            d = max(abs(chests[i][k] - chests[j][k]) for k in "xyz")
            _cfg_check(d >= 3, f"chests[{i}]", f"too close to chests[{j}] (spots must be at least 3 blocks apart)")

    # forbidden (optional, default []): cells nothing may ever be built or decorated on (the world spawn point). Each
    # entry also protects the cell above it (a player stands there). shrine (optional): the cell of chest 1 that the
    # shrine in tools/shrine_blocks.json is built around; when present config.chests must be exactly the shrine's spots
    # (checked by tools/shrine.py and tests/test_shrine.py).
    fb = cfg.get("forbidden", [])
    _cfg_check(isinstance(fb, list), "forbidden", "must be a list of {x,y,z}")
    for i, c in enumerate(fb):
        _check_cell(c, f"forbidden[{i}]")
    if "shrine" in cfg:
        _check_cell(cfg["shrine"], "shrine")
    for i, c in enumerate(chests):
        for j, fc in enumerate(cfg.get("forbidden", [])):
            _cfg_check(not (c["x"] == fc["x"] and c["z"] == fc["z"] and c["y"] in (fc["y"], fc["y"] + 1)),
                       f"chests[{i}]", f"is on forbidden[{j}] (the spawn point must stay clear)")

    _keys(cfg["earn"], "earn", EARN_KEYS)
    for k in EARN_KEYS:
        _cfg_check(_is_int(cfg["earn"][k]) and 0 <= cfg["earn"][k] <= 1000, f"earn.{k}", "must be an integer 0..1000")

    ids = set()
    _cfg_check(isinstance(cfg["trades"], list), "trades", "must be a list")
    for i, t in enumerate(cfg["trades"]):
        f = f"trades[{i}]"
        _keys(t, f, ("id", "give", "get"))
        _cfg_check(isinstance(t["id"], str) and ENTRY_ID.fullmatch(t["id"]) is not None, f"{f}.id",
                   "must be 1-32 chars a-z 0-9 _")
        _cfg_check(t["id"] not in ids, f"{f}.id", "duplicate trade id")
        ids.add(t["id"])
        for side in ("give", "get"):
            d = t[side]
            _cfg_check(isinstance(d, dict) and d, f"{f}.{side}", "must be a non-empty object {resource: amount}")
            for k, n in d.items():
                _cfg_check(k in INVENTORY_KEYS, f"{f}.{side}.{k}", f"must be one of {list(INVENTORY_KEYS)}")
                _cfg_check(_is_int(n) and 1 <= n <= 10000, f"{f}.{side}.{k}", "must be an integer 1..10000")
        _cfg_check(not set(t["give"]) & set(t["get"]), f, "give and get must not share a resource")

    validate_village(cfg["village"])

    ci = cfg["craft_items"]
    _cfg_check(isinstance(ci, dict), "craft_items", "must be an object {WORD: [items]}")
    for w, items in ci.items():
        _cfg_check(CRAFT_WORD.fullmatch(w) is not None, f"craft_items.{w}", "key must be a 3 to 10 letter capital word")
        validate_items(items, f"craft_items.{w}")
    for w in craft_words or []:
        _cfg_check(w in ci, f"craft_items.{w}", "missing: every word in app/data/craft_words.json needs a real item")

    tiers = cfg["tiers"]
    _cfg_check(isinstance(tiers, dict) and tiers, "tiers", "must be a non-empty object {name: [rolls]}")
    for name, rolls in tiers.items():
        _cfg_check(isinstance(name, str) and ENTRY_ID.fullmatch(name) is not None, f"tiers.{name}", "bad tier name")
        _cfg_check(isinstance(rolls, list) and rolls, f"tiers.{name}", "must be a non-empty list")
        for i, r in enumerate(rolls):
            f = f"tiers.{name}[{i}]"
            _keys(r, f, ("weight", "label", "sprite", "items"))
            _cfg_check(_is_int(r["weight"]) and r["weight"] >= 1, f"{f}.weight", "must be an integer >= 1")
            _cfg_check(isinstance(r["label"], str) and r["label"] != "", f"{f}.label", "must be a non-empty string")
            _cfg_check(r["sprite"] in ITEM_SPRITES, f"{f}.sprite",
                       f"must be one of the sprite vocabulary {list(ITEM_SPRITES)}")
            validate_items(r["items"], f"{f}.items")

    sur = cfg["surprises"]
    # The old single-tier key was replaced (breaking change): refuse it loudly rather than ignore or translate it.
    _cfg_check(not (isinstance(sur, dict) and "story_replay" in sur), "surprises.story_replay",
               f"was replaced by surprises.{REPLAY_TIERS_KEY} (a list of tier names, e.g. [\"epic\", \"legendary\"]; "
               "replay N gets entry N, the last entry repeats)")
    _keys(sur, "surprises", SURPRISE_KEYS + (REPLAY_TIERS_KEY,))
    for k in SURPRISE_KEYS:
        _cfg_check(sur[k] in tiers, f"surprises.{k}", f"must name a tier in {sorted(tiers)}")
    rt = sur[REPLAY_TIERS_KEY]
    _cfg_check(isinstance(rt, list) and rt, f"surprises.{REPLAY_TIERS_KEY}", "must be a non-empty list of tier names")
    for i, t in enumerate(rt):
        _cfg_check(isinstance(t, str) and t in tiers, f"surprises.{REPLAY_TIERS_KEY}[{i}]",
                   f"must name a tier in {sorted(tiers)}")


def load_config(path, craft_words=None, overrides_path=None):
    """Read, apply the optional gitignored overrides file, and validate. Raises ConfigError (file errors included).

    The overrides file (default: private_overrides.json next to the config) may set only PRIVATE_OVERRIDE_KEYS;
    it exists so the child's gamertag never has to be committed to a public repo. mc_dir is returned with ~ expanded.
    """
    path = Path(path)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"{path}: cannot read as JSON ({e})") from None
    ov = Path(overrides_path) if overrides_path else path.parent / "private_overrides.json"
    if ov.exists():
        try:
            over = json.loads(ov.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"{ov}: cannot read as JSON ({e})") from None
        _cfg_check(isinstance(over, dict), str(ov), "must be an object")
        for k in over:
            _cfg_check(k in PRIVATE_OVERRIDE_KEYS, f"{ov.name}.{k}", f"not overridable (allowed: {list(PRIVATE_OVERRIDE_KEYS)})")
        if isinstance(cfg, dict):
            cfg = {**cfg, **over}
    validate_config(cfg, craft_words)
    cfg = dict(cfg)
    cfg["mc_dir"] = str(Path(cfg["mc_dir"]).expanduser())
    return cfg


def normalize_item(e):
    """A deep copy of an item entry with count filled in (missing count = 1)."""
    out = json.loads(json.dumps(e))
    out.setdefault("count", 1)
    return out


def humanize_item(item_id):
    """minecraft:pig_spawn_egg -> 'Pig Spawn Egg'."""
    return item_id.split(":", 1)[1].replace("_", " ").title()


def describe_items(items):
    """Child/Dad readable label for a list of item entries: 'Glowstone x4 + Sunflower'."""
    parts = []
    for e in items:
        n = e.get("count", 1)
        name = f"{e['profile']}'s Head" if "profile" in e else humanize_item(e["item"])
        parts.append(name + (f" x{n}" if n > 1 else ""))
    return " + ".join(parts)


def replay_tier(cfg, n):
    """Tier name for the Nth replay (n >= 1) of a story: surprises.story_replay_tiers[min(n-1, len-1)]."""
    if not _is_int(n) or n < 1:
        raise ValueError(f"replay number must be an integer >= 1 (got {n!r})")
    tiers = cfg["surprises"][REPLAY_TIERS_KEY]
    return tiers[min(n - 1, len(tiers) - 1)]


def roll_tier(cfg, tier, rng):
    """Weighted pick from cfg['tiers'][tier]. rng is a random.Random (seedable in tests).
    Returns {"label": str, "sprite": str, "items": [normalized item entries]}."""
    rolls = cfg["tiers"][tier]
    pick = rng.choices(rolls, weights=[r["weight"] for r in rolls], k=1)[0]
    return {"label": pick["label"], "sprite": pick["sprite"], "items": [normalize_item(e) for e in pick["items"]]}


# --- Village rules (everything here is DERIVED from events + progress; nothing is stored) -----------
def first_story_passes(events):
    """Number of distinct (track, story_id) pairs with a story_done event: 'first story passes'."""
    return len({(e["track"], e["story_id"]) for e in events if e["type"] == "story_done"})


def reading_points(cfg, events, letters_mastered):
    """Reading points = independent correct words x w + first story passes x s + letters mastered x l
    (weights from village.points). Independent = a `word` event with result "correct" (assisted and miss earn none)."""
    w = cfg["village"]["points"]
    words = sum(1 for e in events if e["type"] == "word" and e["result"] == "correct")
    return words * w["word"] + first_story_passes(events) * w["story_first"] + letters_mastered * w["letter_mastered"]


def level_for(cfg, points):
    """{"index","name","next_at"} for a point total; next_at is the next threshold or None at the top level."""
    lv = cfg["village"]["levels"]
    idx = max(i for i, t in enumerate(lv["thresholds"]) if points >= t)
    nxt = lv["thresholds"][idx + 1] if idx + 1 < len(lv["thresholds"]) else None
    return {"index": idx, "name": lv["names"][idx], "next_at": nxt}


def bells_earned(cfg, events, points):
    """Village Bells earned: 1 per first story pass + 1 per bell_every_points reading points."""
    return first_story_passes(events) + points // cfg["village"]["bell_every_points"]


def promotions_earned(cfg, spent):
    """Promotions earned by `spent` emeralds in total: one per village.promotions.spent_thresholds entry reached, then
    one more per then_every emeralds beyond the last threshold."""
    pr = cfg["village"]["promotions"]
    th = pr["spent_thresholds"]
    n = sum(1 for t in th if spent >= t)
    return n + (spent - th[-1]) // pr["then_every"] if spent >= th[-1] else n


def next_promotion_at(cfg, spent):
    """The total emeralds spent at which the NEXT promotion is earned (always a number: the ladder never ends)."""
    pr = cfg["village"]["promotions"]
    th = pr["spent_thresholds"]
    for t in th:
        if spent < t:
            return t
    return th[-1] + ((spent - th[-1]) // pr["then_every"] + 1) * pr["then_every"]


def profession_unlock_items(prof):
    """What unlocking a profession puts in the Treasure Pile: its explicit unlock_items, else a villager spawn egg
    and the job-site block."""
    if "unlock_items" in prof:
        return [normalize_item(e) for e in prof["unlock_items"]]
    return [normalize_item({"item": "minecraft:villager_spawn_egg"}), normalize_item({"item": prof["job_block_item"]})]


# --- Ledger -----------------------------------------------------------------------------------------
def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_delivery(d, field="delivery"):
    _keys(d, field, ("id", "created_ts", "source", "label", "items", "status", "attempts", "last_error",
                     "delivered_ts", "chest"), ("inserted", "baseline", "confirmed", "pending"))
    _cfg_check(isinstance(d["id"], str) and re.fullmatch(r"d\d{6,}", d["id"]) is not None, f"{field}.id", "bad id")
    _cfg_check(isinstance(d["created_ts"], str), f"{field}.created_ts", "must be an ISO string")
    try:
        datetime.fromisoformat(d["created_ts"])
    except ValueError:
        raise LedgerError(f"{field}.created_ts: not ISO-8601") from None
    _keys(d["source"], f"{field}.source", ("kind", "ref"))
    _cfg_check(d["source"]["kind"] in SOURCE_KINDS, f"{field}.source.kind", f"must be one of {list(SOURCE_KINDS)}")
    _cfg_check(isinstance(d["source"]["ref"], str), f"{field}.source.ref", "must be a string")
    _cfg_check(isinstance(d["label"], str) and d["label"] != "", f"{field}.label", "must be a non-empty string")
    validate_items(d["items"], f"{field}.items")
    _cfg_check(d["status"] in STATUSES, f"{field}.status", f"must be one of {list(STATUSES)}")
    _cfg_check(_is_int(d["attempts"]) and d["attempts"] >= 0, f"{field}.attempts", "must be an integer >= 0")
    _cfg_check(d["last_error"] is None or isinstance(d["last_error"], str), f"{field}.last_error", "string or null")
    _cfg_check(d["delivered_ts"] is None or isinstance(d["delivered_ts"], str), f"{field}.delivered_ts", "string or null")
    if d["chest"] is not None:
        _keys(d["chest"], f"{field}.chest", ("x", "y", "z"))
        for k in "xyz":
            _cfg_check(_is_int(d["chest"][k]), f"{field}.chest.{k}", "must be an integer")
    if "inserted" in d:  # optional, default 0: how many item entries are already in the chest (resume point)
        _cfg_check(_is_int(d["inserted"]) and 0 <= d["inserted"] <= len(expand_items(d["items"])), f"{field}.inserted",
                   "must be an integer 0..len(expanded items)")
    if "confirmed" in d:  # optional (absent on older entries: then each inserted entry counts as its own count)
        c = d["confirmed"]
        _cfg_check(isinstance(c, list) and all(_is_int(n) and n >= 1 for n in c), f"{field}.confirmed",
                   "must be a list of integers >= 1 (the `Dropped N` count of each confirmed entry)")
        _cfg_check(len(c) == d.get("inserted", 0), f"{field}.confirmed", "must have exactly `inserted` counts")
    if "pending" in d and d["pending"] is not None:  # the one insert that was sent but not yet confirmed
        p = d["pending"]
        _keys(p, f"{field}.pending", ("index", "mark"))
        _cfg_check(_is_int(p["index"]) and 0 <= p["index"] < len(expand_items(d["items"])), f"{field}.pending.index",
                   "must be an entry index")
        _cfg_check(isinstance(p["mark"], list) and len(p["mark"]) == 2 and all(_is_int(n) and n >= 0 for n in p["mark"]),
                   f"{field}.pending.mark", "must be [log id, log offset]")
    if "baseline" in d:  # optional (absent on entries from before it existed): the chest as it was BEFORE attempt 1
        b = d["baseline"]
        _keys(b, f"{field}.baseline", ("slots", "totals", "raw"))
        _cfg_check(_is_int(b["slots"]) and 0 <= b["slots"] <= CHEST_SLOTS, f"{field}.baseline.slots",
                   f"must be an integer 0..{CHEST_SLOTS}")
        _cfg_check(isinstance(b["totals"], dict) and all(isinstance(k, str) and _is_int(v) and v >= 0
                                                          for k, v in b["totals"].items()),
                   f"{field}.baseline.totals", "must be {item id: count}")
        _cfg_check(isinstance(b["raw"], str), f"{field}.baseline.raw", "must be a string")
        _cfg_check(d["chest"] is not None, f"{field}.baseline", "needs a chest (the baseline belongs to it)")
    if d["status"] == "delivered":
        _cfg_check(d["delivered_ts"] is not None and d["chest"] is not None, field,
                   "a delivered entry needs delivered_ts and chest")


def validate_ledger(led):
    _keys(led, "ledger", ("v", "deliveries"))
    _cfg_check(led["v"] == LEDGER_VERSION and _is_int(led["v"]), "ledger.v", f"must be the integer {LEDGER_VERSION}")
    _cfg_check(isinstance(led["deliveries"], list), "ledger.deliveries", "must be a list")
    seen = set()
    for i, d in enumerate(led["deliveries"]):
        validate_delivery(d, f"ledger.deliveries[{i}]")
        _cfg_check(d["id"] not in seen, f"ledger.deliveries[{i}].id", "duplicate id")
        seen.add(d["id"])


class Ledger:
    """data/minecraft_deliveries.json. Entries are never deleted. All access goes through one lock; writes are
    atomic via the injected `writer` (server.write_json_atomic). Every read validates the file; a bad file raises
    LedgerError and is never overwritten."""

    def __init__(self, path, writer):
        self.path = Path(path)
        self._write = writer
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists():
            return {"v": LEDGER_VERSION, "deliveries": []}
        try:
            led = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise LedgerError(f"{self.path}: cannot read ({e})") from None
        try:
            validate_ledger(led)
        except ConfigError as e:
            raise LedgerError(f"{self.path}: {e}") from None
        return led

    def deliveries(self):
        with self.lock:
            return self._read()["deliveries"]

    def find_by_ref(self, ref):
        """The delivery whose source.ref is `ref` (a treasure id), or None. A tid has at most one delivery."""
        with self.lock:
            hits = [d for d in self._read()["deliveries"] if d["source"]["ref"] == ref]
        if len(hits) > 1:
            raise LedgerError(f"{len(hits)} deliveries share source.ref {ref}; a treasure id may be delivered once")
        return hits[0] if hits else None

    def create(self, kind, ref, label, items):
        """Append a pending delivery and return it. items are normalized copies. `ref` is the treasure id and must
        not already have a delivery (a treasure is never sent twice)."""
        with self.lock:
            led = self._read()
            if any(d["source"]["ref"] == ref for d in led["deliveries"]):
                raise LedgerError(f"{ref} already has a delivery; refusing to create a second")
            n = 1 + max((int(d["id"][1:]) for d in led["deliveries"]), default=0)
            d = {"id": f"d{n:06d}", "created_ts": _now_iso(), "source": {"kind": kind, "ref": ref}, "label": label,
                 "items": [normalize_item(e) for e in items], "status": "pending", "attempts": 0, "last_error": None,
                 "delivered_ts": None, "chest": None, "inserted": 0}
            try:
                validate_delivery(d)
            except ConfigError as e:
                raise LedgerError(f"refusing to create an invalid delivery: {e}") from None
            led["deliveries"].append(d)
            self._write(self.path, led)
            return d

    def update(self, delivery_id, **fields):
        """Merge fields into one entry (validated) and persist. Returns the new entry."""
        with self.lock:
            led = self._read()
            for d in led["deliveries"]:
                if d["id"] == delivery_id:
                    d.update(fields)
                    try:
                        validate_delivery(d)
                    except ConfigError as e:
                        raise LedgerError(f"refusing invalid update of {delivery_id}: {e}") from None
                    self._write(self.path, led)
                    return d
            raise LedgerError(f"no delivery {delivery_id}")


# --- History: data/rewards_history.jsonl (append-only master list of everything earned, spent and sent) ---
HISTORY_VERSION = 1
HISTORY_KINDS = ("earn", "spend", "trade", "treasure", "unlock", "level", "promote", "send", "delivered", "delivery_failed")
HISTORY_CSV_COLUMNS = ("ts", "kind", "ref", "what", "wallet_after")


class HistoryError(ValueError):
    """The history file is invalid or a line could not be written. The request that needed it fails."""


def validate_history_line(l, field="history line"):
    """{"v":1,"ts":ISO,"kind":HISTORY_KINDS,"what":{...},"wallet_after":{inventory}|null,"ref":str}; all required."""
    _keys(l, field, ("v", "ts", "kind", "what", "wallet_after", "ref"))
    _cfg_check(l["v"] == HISTORY_VERSION and _is_int(l["v"]), f"{field}.v", f"must be the integer {HISTORY_VERSION}")
    _cfg_check(isinstance(l["ts"], str), f"{field}.ts", "must be an ISO string")
    try:
        datetime.fromisoformat(l["ts"])
    except ValueError:
        raise ConfigError(f"{field}.ts: not ISO-8601") from None
    _cfg_check(l["kind"] in HISTORY_KINDS, f"{field}.kind", f"must be one of {list(HISTORY_KINDS)}")
    _cfg_check(isinstance(l["what"], dict), f"{field}.what", "must be an object")
    _cfg_check(isinstance(l["ref"], str), f"{field}.ref", "must be a string")
    w = l["wallet_after"]
    if w is not None:
        _keys(w, f"{field}.wallet_after", INVENTORY_KEYS)
        for k in INVENTORY_KEYS:
            _cfg_check(_is_int(w[k]) and w[k] >= 0, f"{field}.wallet_after.{k}", "must be an integer >= 0")


class History:
    """data/rewards_history.jsonl: one JSON line per change, only ever appended (never rewritten, trimmed or moved;
    "Reset progress" leaves it alone). append() validates, writes and fsyncs, and raises HistoryError if it could not:
    the caller must then fail its request. Safe from several threads (the server and the delivery worker)."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def append(self, kind, what, ref, wallet_after=None):
        line = {"v": HISTORY_VERSION, "ts": _now_iso(), "kind": kind, "what": what, "wallet_after": wallet_after,
                "ref": ref}
        try:
            validate_history_line(line)
            text = json.dumps(line)
        except (ConfigError, TypeError, ValueError) as e:
            raise HistoryError(f"refusing to write an invalid history line ({e})") from None
        with self.lock:
            try:
                if self.path.exists() and self.path.stat().st_size:
                    with open(self.path, "rb") as f:
                        f.seek(-1, os.SEEK_END)
                        if f.read(1) != b"\n":
                            raise HistoryError(f"{self.path} does not end with a newline (a torn write?); not appending")
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                raise HistoryError(f"could not write {self.path}: {e}") from None
        return line

    def read(self, kind=None):
        """Every line, validated; the first bad line raises HistoryError naming its number. kind filters."""
        if kind is not None and kind not in HISTORY_KINDS:
            raise HistoryError(f"kind: must be one of {list(HISTORY_KINDS)}")
        with self.lock:
            if not self.path.exists():
                return []
            try:
                raw = self.path.read_text(encoding="utf-8").splitlines()
            except OSError as e:
                raise HistoryError(f"could not read {self.path}: {e}") from None
        out = []
        for n, text in enumerate(raw, 1):
            try:
                line = json.loads(text)
                validate_history_line(line)
            except (ValueError, ConfigError) as e:
                raise HistoryError(f"{self.path} line {n}: {e}") from None
            if kind is None or line["kind"] == kind:
                out.append(line)
        return out


def history_totals(lines):
    """Totals over history lines: {"earned":{resource:n},"spent":{resource:n},"sent":{item id:n},"delivered":{item id:n},
    "unlocked":[profession ids in order],"levels":[indexes reached]}. `sent` counts items of every send line,
    `delivered` the items of every delivery the game confirmed."""
    earned, spent, sent, delivered, unlocked, levels = {}, {}, {}, {}, [], []

    def add(into, key, n):
        into[key] = into.get(key, 0) + n
    for l in lines:
        w, k = l["what"], l["kind"]
        if k == "earn":
            for r, n in w["resources"].items():
                add(earned, r, n)
        elif k == "spend":
            add(spent, w["resource"], w["amount"])
        elif k == "send":
            for it in w["items"]:
                add(sent, it["item"], it.get("count", 1))
        elif k == "delivered":
            for it in w["items"]:
                add(delivered, it["item"], it.get("count", 1))
        elif k == "unlock":
            unlocked.append(w["profession"])
        elif k == "level":
            levels.append(w["index"])
    return {"earned": earned, "spent": spent, "sent": sent, "delivered": delivered, "unlocked": unlocked,
            "levels": levels}


def history_csv(lines):
    """The history as CSV text (header HISTORY_CSV_COLUMNS; what and wallet_after are JSON strings)."""
    import csv
    import io
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(HISTORY_CSV_COLUMNS)
    for l in lines:
        wr.writerow([l["ts"], l["kind"], l["ref"], json.dumps(l["what"], sort_keys=True),
                     "" if l["wallet_after"] is None else json.dumps(l["wallet_after"], sort_keys=True)])
    return buf.getvalue()


# --- Log parsing ------------------------------------------------------------------------------------
_CHAT = re.compile(r"System chat: (.*)$")
_SLOT = re.compile(r'Slot: (\d+)b, id: "([^"]+)", count: (\d+)')


def parse_chat(line):
    """The message text of a console 'System chat:' log line, or None for any other line."""
    m = _CHAT.search(line)
    return m.group(1) if m else None


def parse_items_line(text):
    """Parse the reply to `data get block X Y Z Items` into {"slots": n, "totals": {id: count}, "raw": text}."""
    slots, totals = 0, {}
    for _slot, item_id, count in _SLOT.findall(text):
        slots += 1
        totals[item_id] = totals.get(item_id, 0) + int(count)
    return {"slots": slots, "totals": totals, "raw": text}


# --- Command formatting -----------------------------------------------------------------------------
def snbt_components(e):
    """Item-component SNBT for set_components, or None when the entry has none."""
    parts = []
    for key, comp in (("enchantments", "minecraft:enchantments"), ("stored_enchantments", "minecraft:stored_enchantments")):
        if key in e:
            inner = ",".join(f'"{n}":{lvl}' for n, lvl in sorted(e[key].items()))
            parts.append(f'"{comp}":{{{inner}}}')
    if "profile" in e:
        parts.append(f'"minecraft:profile":"{e["profile"]}"')
    if "potion" in e:
        parts.append(f'"minecraft:potion_contents":{{potion:"{e["potion"]}"}}')
    return "{" + ",".join(parts) + "}" if parts else None


def loot_insert_command(pos, e):
    """The `loot insert` console line for one item entry (inline loot table, 26.x schema)."""
    mods = [f'{{type:"minecraft:set_count",count:{e.get("count", 1)}}}']
    comps = snbt_components(e)
    if comps:
        mods.append(f'{{type:"minecraft:set_components",components:{comps}}}')
    table = ('{pools:[{rolls:1,entries:[{type:"minecraft:item",name:"%s",modifier:[%s]}]}]}'
             % (e["item"], ",".join(mods)))
    return f"loot insert {pos['x']} {pos['y']} {pos['z']} loot {table}"


def _pos(p):
    return f"{p['x']} {p['y']} {p['z']}"


def forbidden_set(cells):
    """The explicit set of (x, y, z) positions nothing may be built or decorated on: every config `forbidden` cell
    (the world spawn point) and the cell above it, where the player's head is."""
    out = set()
    for c in cells or ():
        out.add((c["x"], c["y"], c["z"]))
        out.add((c["x"], c["y"] + 1, c["z"]))
    return out


# --- Transport --------------------------------------------------------------------------------------
class ScreenTransport:
    """Sends console lines through the server's screen session (like mc.sh) and reads NEW lines of
    <mc_dir>/logs/latest.log after a remembered byte offset. No RCON, no network port."""

    def __init__(self, mc_dir, session):
        self.mc_dir = Path(mc_dir)
        self.session = session
        self.log = self.mc_dir / "logs" / "latest.log"
        self._ino = None
        self._off = 0
        self._partial = b""

    def server_running(self):
        """True / False via `<mc_dir>/mc.sh status` (exit 0 running, 3 not running). Anything else raises McError."""
        script = self.mc_dir / "mc.sh"
        if not script.exists():
            raise McError(f"{script} not found")
        r = subprocess.run([str(script), "status"], capture_output=True, text=True, timeout=30,
                           env={**os.environ, "MC_SESSION": self.session})
        if r.returncode == 3:
            return False
        if r.returncode != 0:
            raise McError(f"mc.sh status failed (exit {r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
        if "(screen)" not in r.stdout:
            raise McError("Minecraft is running outside a screen session, so commands cannot be sent: " + r.stdout.strip())
        return True

    def _stat(self):
        try:
            st = self.log.stat()
        except OSError as e:
            raise McError(f"cannot read {self.log}: {e}") from None
        return st

    def skip_to_end(self):
        """Forget everything already in the log (so old lines can never answer a new command)."""
        st = self._stat()
        self._ino, self._off, self._partial = st.st_ino, st.st_size, b""

    def new_lines(self):
        """Complete log lines written since the last call. A different inode (log rotated on restart) restarts at 0."""
        st = self._stat()
        if self._ino != st.st_ino or st.st_size < self._off:
            self._ino, self._off, self._partial = st.st_ino, 0, b""
        with open(self.log, "rb") as f:
            f.seek(self._off)
            data = f.read()
        self._off += len(data)
        data = self._partial + data
        *whole, self._partial = data.split(b"\n")
        return [ln.decode("utf-8", "replace") for ln in whole]

    def log_mark(self):
        """A position in the log, [inode, byte offset] (JSON-able; stored in the delivery before an insert is sent)."""
        st = self._stat()
        return [st.st_ino, st.st_size]

    def chat_since(self, mark):
        """The 'System chat' texts written after `mark`. A different log file (rotated by a restart) means the
        evidence is gone: McError, never an empty answer."""
        st = self._stat()
        if st.st_ino != mark[0] or st.st_size < mark[1]:
            raise McError(f"{self.log} was replaced since the insert was sent (server restarted?); its reply cannot be checked")
        with open(self.log, "rb") as f:
            f.seek(mark[1])
            data = f.read().decode("utf-8", "replace")
        return [t for t in (parse_chat(ln) for ln in data.split("\n")) if t is not None]

    def send(self, cmd):
        r = subprocess.run(["screen", "-S", self.session, "-p", "0", "-X", "stuff", cmd + "\r"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            raise McError(f"could not send to screen session '{self.session}': {r.stderr.strip() or r.stdout.strip()}")


# --- Bridge (what to say to Minecraft) --------------------------------------------------------------
class Bridge:
    """Command/confirmation logic on top of a transport (ScreenTransport, or a fake in tests)."""

    def __init__(self, transport, chests, reply_timeout=REPLY_TIMEOUT, clock=time.monotonic, sleep=time.sleep,
                 log=None, forbidden=()):
        self.t = transport
        self.chests = chests
        self.forbidden = forbidden_set(forbidden)  # (x, y, z) cells that are never built on (see forbidden_set)
        self.evidence = []  # log lines that confirmed the inserts of the delivery in progress (for the history)
        self.known = set()  # (x, y, z) of Magic Chests seen or placed by this bridge
        self.log = log or (lambda m: None)
        self.reply_timeout = reply_timeout
        self._clock, self._sleep = clock, sleep

    # -- one command, one confirmed reply
    def ask(self, cmd, expect):
        """Send cmd; wait for a 'System chat' line matching one of expect {name: regex}. Returns (name, match).
        Unrelated lines are ignored; no matching reply in time raises McError listing everything seen."""
        self.t.skip_to_end()
        self.t.send(cmd)
        seen = []
        deadline = self._clock() + self.reply_timeout
        while True:
            for ln in self.t.new_lines():
                text = parse_chat(ln)
                if text is None:
                    continue
                seen.append(text)
                for name, rx in expect.items():
                    m = re.search(rx, text)
                    if m:
                        return name, m
            if self._clock() >= deadline:
                raise McError(f"no expected reply to '{cmd[:160]}' within {self.reply_timeout:g}s; "
                              f"console said: {seen or 'nothing'}")
            self._sleep(0.05)

    def fire(self, cmd):
        """Send a cosmetic command without waiting for (or caring about) its reply."""
        self.t.send(cmd)

    # -- chunk / chest inspection
    def ensure_forceload(self, pos):
        name, _ = self.ask(f"forceload add {pos['x']} {pos['z']}",
                           {"ok": r"Marked chunk|No chunks were marked for force loading"})
        return name

    def _test(self, cmd):
        """Run an `execute if/unless ...` test: True on 'Test passed', False on 'Test failed'."""
        name, _ = self.ask(cmd, {"yes": r"^Test passed", "no": r"^Test failed", "unloaded": r"not loaded"})
        if name == "unloaded":
            raise McError(f"chunk not loaded for: {cmd}")
        return name == "yes"

    def test(self, cmd):
        """Public form of _test: run an `execute if/unless ...` line, True on 'Test passed', False on 'Test failed'."""
        return self._test(cmd)

    def is_free(self, pos):
        """True when the spot holds only air or a loose plant/snow cover (the tag #minecraft:replaceable) and no
        fluid. Found on the copy: candidate spots in a real world often hold tall grass, which is not `air`."""
        p = _pos(pos)
        return (self._test(f"execute if block {p} #minecraft:replaceable")
                and not self._test(f"execute if block {p} minecraft:water")
                and not self._test(f"execute if block {p} minecraft:lava"))

    def chest_state(self, pos):
        """One of 'ours' (a Magic Chest), 'air' (free: air or loose plants), 'other' (anything else there)."""
        p = _pos(pos)
        if self._test(f"execute if block {p} minecraft:chest"):
            name, m = self.ask(f"data get block {p} CustomName",
                               {"named": r'text: "([^"]*)"', "unnamed": r"Found no elements"})
            return "ours" if name == "named" and m.group(1).startswith("Magic Chest") else "other"
        return "air" if self.is_free(pos) else "other"

    def snapshot(self, pos):
        """Parsed contents of the chest at pos: {"slots","totals","raw"}."""
        name, m = self.ask(f"data get block {_pos(pos)} Items",
                           {"items": r"block data: (\[.*\])\s*$", "none": r"not a block entity|not loaded"})
        if name != "items":
            raise McError(f"{_pos(pos)} is not a readable chest")
        return parse_items_line(m.group(1))

    # -- placing and dressing a chest
    def place_chest(self, pos, number):
        """Place chest number `number` (1-based) at pos if the spot is free (air or loose plants) and the block below
        is solid.
        Returns True if placed, False if the spot is unusable (caller moves on to the next candidate)."""
        p = _pos(pos)
        below = f"{pos['x']} {pos['y'] - 1} {pos['z']}"
        if (pos["x"], pos["y"], pos["z"]) in self.forbidden or not self.is_free(pos):
            return False
        if not self._test(f"execute unless block {below} #minecraft:replaceable"):
            return False
        title = "Magic Chest" if number == 1 else f"Magic Chest {number}"
        self.ask(f'setblock {p} minecraft:chest[facing=south,type=single]'
                 f'{{CustomName:{{text:"{title}",color:"gold",bold:true}}}} replace',
                 {"ok": r"Changed the block"})
        return True

    def decorate(self, pos):
        """Amethyst clusters and lanterns on free ground around the chest. Only ever fills air ('keep'); returns
        how many blocks were placed. Cosmetic: a spot that is not free is simply left alone."""
        x, y, z = pos["x"], pos["y"], pos["z"]
        spots = [(x - 1, z, "lantern[hanging=false]"), (x + 1, z, "lantern[hanging=false]"),
                 (x, z - 1, "amethyst_cluster[facing=up]"), (x - 1, z - 1, "amethyst_cluster[facing=up]"),
                 (x + 1, z - 1, "amethyst_cluster[facing=up]"), (x - 1, z + 1, "amethyst_cluster[facing=up]"),
                 (x + 1, z + 1, "amethyst_cluster[facing=up]")]
        placed = 0
        for sx, sz, block in spots:
            if (sx, y, sz) in self.forbidden:
                continue  # the spawn point (or the cell under a player's head) is never decorated
            if not self._test(f"execute unless block {sx} {y - 1} {sz} #minecraft:replaceable"):
                continue  # no solid ground there
            name, _ = self.ask(f"setblock {sx} {y} {sz} minecraft:{block} keep",
                               {"yes": r"Changed the block", "no": r"Could not set the block"})
            placed += name == "yes"
        return placed

    def ensure_label(self, pos, number):
        """One invisible marker armor stand floating above the chest, tagged magic_chest_label. Idempotent.
        Returns True when it was created, False when one already existed."""
        x, y, z = pos["x"], pos["y"], pos["z"]
        found, _ = self.ask(
            f"execute if entity @e[type=minecraft:armor_stand,tag=magic_chest_label,x={x},y={y},z={z},distance=..3]",
            {"yes": r"^Test passed", "no": r"^Test failed"})
        if found == "yes":
            return False
        title = "Magic Chest" if number == 1 else f"Magic Chest {number}"
        self.ask(f'summon minecraft:armor_stand {x + 0.5} {y + 1.4} {z + 0.5} {{Invisible:1b,Marker:1b,NoGravity:1b,'
                 f'CustomNameVisible:1b,CustomName:{{text:"{title}",color:"gold"}},Tags:["magic_chest_label"]}}',
                 {"ok": r"Summoned new"})
        return True

    def magic(self, pos):
        """Particle burst and level-up sound at the chest. Cosmetic: replies are not checked."""
        x, y, z = pos["x"], pos["y"], pos["z"]
        self.fire(f"particle minecraft:enchant {x + 0.5} {y + 1.2} {z + 0.5} 0.4 0.4 0.4 0.6 80")
        self.fire(f"particle minecraft:happy_villager {x + 0.5} {y + 1.2} {z + 0.5} 0.5 0.5 0.5 0 25")
        self.fire(f"playsound minecraft:entity.player.levelup block @a {x} {y} {z} 1 1")

    # -- choosing a chest
    def pick_chest(self, need):
        """The first Magic Chest with >= need free slots; places the next candidate chest if none has room.
        Raises AllFull when every candidate is full or unusable. Returns (pos, number, snapshot)."""
        for i, pos in enumerate(self.chests):
            self.ensure_forceload(pos)
            state = self.chest_state(pos)
            if state == "ours":
                self.known.add((pos["x"], pos["y"], pos["z"]))
                snap = self.snapshot(pos)
                if CHEST_SLOTS - snap["slots"] >= need:
                    return pos, i + 1, snap
                self.log(f"chest {i + 1} at {_pos(pos)} has {CHEST_SLOTS - snap['slots']} free slots, need {need}")
            elif state == "air":
                if self.place_chest(pos, i + 1):
                    self.known.add((pos["x"], pos["y"], pos["z"]))
                    self.log(f"placed Magic Chest {i + 1} at {_pos(pos)}")
                    self.decorate(pos)
                    self.ensure_label(pos, i + 1)
                    return pos, i + 1, self.snapshot(pos)
                self.log(f"candidate {i + 1} at {_pos(pos)} is unusable (air above solid ground required)")
            else:
                self.log(f"candidate {i + 1} at {_pos(pos)} is occupied by something that is not a Magic Chest")
        raise AllFull(ALL_FULL_PROBLEM)

    # -- delivering
    def insert_items(self, pos, items, start, on_pending):
        """Insert items[start:], yielding (new `inserted` count, the `Dropped N` count the game confirmed) after each
        insert. Before each command is sent on_pending(pending={index, mark}) persists where in the console log the
        reply would appear, so a retry can tell a late reply from no reply (see Bridge._resolve_pending)."""
        for i in range(start, len(items)):
            e = items[i]
            want = e.get("count", 1)
            on_pending(pending={"index": i, "mark": self.t.log_mark()})
            name, m = self.ask(loot_insert_command(pos, e),
                               {"dropped": r"^Dropped (\d+) (?:\[(.*)\]|items)", "notcontainer": r"is not a container",
                                "unloaded": r"not loaded", "zero": r"^Dropped 0 items",
                                "parse": r"^Failed to parse"})
            if name != "dropped":
                raise McError(f"insert of {e['item']} at {_pos(pos)} failed: {m.string}")
            got = int(m.group(1))
            if got != want:
                raise McError(f"insert of {e['item']} x{want}: Minecraft reported {m.group(0)!r} "
                              f"(chest full? loot discarded)")
            self.evidence.append(m.string)
            yield i + 1, got

    @staticmethod
    def verify(before, after, items):
        """Compare chest snapshots: every delivered id's total grew by exactly the delivered count, and each
        enchantment / profile token appears at least as often as delivered. Raises VerifyError."""
        want = {}
        tokens = {}
        for e in items:
            want[e["item"]] = want.get(e["item"], 0) + e.get("count", 1)
            for key in ("enchantments", "stored_enchantments"):
                for n, lvl in e.get(key, {}).items():
                    t = f'"{n}": {lvl}'
                    tokens[t] = tokens.get(t, 0) + 1
            if "profile" in e:
                t = f'name: "{e["profile"]}"'
                tokens[t] = tokens.get(t, 0) + 1
            if "potion" in e:
                t = f'potion: "{e["potion"]}"'
                tokens[t] = tokens.get(t, 0) + 1
        for item_id, n in want.items():
            grew = after["totals"].get(item_id, 0) - before["totals"].get(item_id, 0)
            if grew != n:
                raise VerifyError(f"read-back: {item_id} grew by {grew}, expected {n}; chest now: {after['raw'][:600]}")
        for t, n in tokens.items():
            grew = after["raw"].count(t) - before["raw"].count(t)
            if grew < n:
                raise VerifyError(f"read-back: expected {n} more of {t} in the chest, saw {grew}; "
                                  f"chest now: {after['raw'][:600]}")

    def _resolve_pending(self, base, now, items, start, confirmed, pending):
        """Decide what a retry may do about the one insert that was sent but never confirmed (`pending`).
        Returns the resume index: `start` (insert it) or `start + 1` (it landed; its late `Dropped` reply is in the
        log). Never inserts anything itself.

        Facts: the chest's change since the delivery's baseline minus what this delivery's own confirmed inserts
        account for (`delta`), and whether the log holds a `Dropped <count>` reply to the pending command. Only two
        combinations are unambiguous: no delta and no reply (it never landed: insert it) and delta exactly the pending
        entry plus a reply (it landed). Anything else (items taken out, a matching item put in by someone else, a
        reply but no items, items but no reply, a partial drop) cannot be told apart from a double or a short
        delivery, so it raises VerifyError with the evidence and the delivery is marked failed; nothing is inserted."""
        gained = {k: now["totals"].get(k, 0) - base["totals"].get(k, 0) for k in {*now["totals"], *base["totals"]}}
        for e, n in zip(items[:start], confirmed):
            gained[e["item"]] = gained.get(e["item"], 0) - n
        delta = {k: v for k, v in gained.items() if v}
        e = items[start] if pending is not None and start < len(items) else None
        if pending is not None and pending["index"] != start:
            raise VerifyError(f"pending insert is entry {pending['index']} but the delivery resumes at {start}; "
                              f"check the chest by hand")
        replied = None
        if e is not None:
            try:
                texts = self.t.chat_since(pending["mark"])
            except McError as ex:
                raise VerifyError(f"cannot tell whether entry {start + 1} ({e['item']} x{e.get('count', 1)}) landed: "
                                  f"{ex}; chest delta {delta}; check the chest by hand") from None
            want = e.get("count", 1)
            replied = next((t for t in texts if re.match(rf"Dropped {want} (?:\[|items)", t)), None)
        which = f"; pending entry {start + 1} is {e['item']} x{e.get('count', 1)}" if e else ""
        evidence = (f"chest changed by {delta or 'nothing'} beyond the {start} confirmed entries{which}; "
                    f"reply to it in the log: {replied!r}; chest now: {now['raw'][:600]}")
        if not delta and replied is None:
            return start
        if e is not None and replied is not None and delta == {e["item"]: e.get("count", 1)}:
            self.evidence.append(f"reconciled by read-back and log: entry {start + 1} ({e['item']} x{e.get('count', 1)}) "
                                 f"landed, its late reply was {replied!r}; not inserted again")
            confirmed.append(e.get("count", 1))
            return start + 1
        raise VerifyError(f"ambiguous read-back, nothing was inserted: {evidence}")

    def deliver(self, d, on_progress):
        """Deliver ledger entry d (a dict). on_progress(**fields) persists {chest, baseline, inserted, confirmed,
        pending}. Returns the chest position. Raises AllFull / McError / VerifyError.

        The verify baseline is the chest as it was BEFORE the delivery's first attempt, persisted with the delivery
        (`baseline`), together with the `Dropped N` count of every confirmed entry (`confirmed`) and, while an
        insert is in flight, where its reply would appear in the log (`pending`). A retry reconciles against those
        (Bridge._resolve_pending), not against the baseline alone, so a chest that someone else changed is reported
        as ambiguous instead of being miscounted. The read-back at the end always runs, even with nothing left to
        insert."""
        items, start = expand_items(d["items"]), d.get("inserted", 0)  # `inserted` counts expanded entries
        confirmed = list(d["confirmed"]) if "confirmed" in d else [e.get("count", 1) for e in items[:start]]
        self.evidence = []
        base = d.get("baseline")
        if d["chest"] is not None and base is not None:
            pos = d["chest"]  # a retry: the chest and its pre-delivery contents were recorded by attempt 1
            self.ensure_forceload(pos)
        else:
            if d["chest"] is not None and start > 0:
                raise VerifyError(f"delivery {d['id']} has {start} entries inserted into {_pos(d['chest'])} but no "
                                  f"recorded baseline (made before baselines existed); check that chest by hand")
            pos, _number, snap = self.pick_chest(slots_needed(items))
            base = {"slots": snap["slots"], "totals": snap["totals"], "raw": snap["raw"]}
            start, confirmed = 0, []
            on_progress(chest=pos, baseline=base, inserted=0, confirmed=[], pending=None)
        now = self.snapshot(pos)
        landed = self._resolve_pending(base, now, items, start, confirmed, d.get("pending"))
        if landed != start or d.get("pending") is not None:
            start = landed
            on_progress(inserted=start, confirmed=list(confirmed), pending=None)
        for n, dropped in self.insert_items(pos, items, start, on_progress):
            confirmed.append(dropped)
            on_progress(inserted=n, confirmed=list(confirmed), pending=None)
        self.verify(base, self.snapshot(pos), items)
        return pos


# --- Worker -----------------------------------------------------------------------------------------
class DeliveryWorker:
    """Background thread: every POLL_SECONDS deliver pending ledger entries in creation order, one at a time.

    State read by GET /api/minecraft: server_running (None until the first check), problem (str|None).
    A thread-level crash never goes silent: it is stored in `problem`, printed to stderr, and the loop continues.
    """

    def __init__(self, cfg, ledger, bridge, server_check, poll=POLL_SECONDS, log=None, history=None):
        self.cfg, self.ledger, self.bridge = cfg, ledger, bridge
        self.history = history  # a History: "delivered" / "delivery_failed" lines are written BEFORE the ledger changes
        self.server_check = server_check
        self.poll = poll
        self.log = log or (lambda m: sys.stderr.write(f"[minecraft] {m}\n"))
        self.server_running = None
        self.problem = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="minecraft-delivery", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001 - must not die silently; reported via problem + stderr
                self.problem = f"delivery worker error: {type(e).__name__}: {e}"
                self.log(self.problem)
            self._stop.wait(self.poll)

    def run_once(self):
        """One pass: check the server, then deliver pending entries oldest first until none is left or one blocks."""
        running = self.server_check()
        was, self.server_running = self.server_running, running
        if not running:
            return  # waiting for Minecraft is not an error; the entries stay pending
        if was is not True:
            # Just started, or the first look after the worker itself started (was None: it may have been started
            # while Minecraft was still loading): `mc.sh status` says running while the world is still loading, and
            # commands answer "An unexpected error occurred" (seen on the copy, it burned a delivery attempt).
            # Skip one pass.
            self.log("Minecraft is up; delivering on the next pass")
            return
        while True:
            pending = [d for d in self.ledger.deliveries() if d["status"] == "pending"]
            if not pending:
                self.problem = None
                return
            if not self._deliver_one(pending[0]):
                return

    def _deliver_one(self, d):
        """Returns True when the caller may move on to the next entry."""
        did = d["id"]
        try:
            pos = self.bridge.deliver(d, lambda **f: self.ledger.update(did, **f))
        except AllFull:
            self.problem = ALL_FULL_PROBLEM
            self.log(f"{did}: {ALL_FULL_PROBLEM}; staying pending")
            return False
        except VerifyError as e:
            self._history("delivery_failed", {"delivery": did, "tid": d["source"]["ref"], "error": str(e)}, d)
            self.ledger.update(did, status="failed", attempts=d["attempts"] + 1, last_error=str(e))
            self.log(f"{did}: FAILED (not retried, items may already be in the chest): {e}")
            return True
        except McError as e:
            attempts = d["attempts"] + 1
            failed = attempts >= MAX_ATTEMPTS
            if failed:
                self._history("delivery_failed", {"delivery": did, "tid": d["source"]["ref"], "error": str(e)}, d)
            self.ledger.update(did, status="failed" if failed else "pending", attempts=attempts, last_error=str(e))
            self.log(f"{did}: attempt {attempts} failed ({'failed' if failed else 'pending'}): {e}")
            if failed:
                self.problem = f"{did} FAILED: {e}"
            return failed  # a failed entry never blocks the next one; a pending one is retried on the next poll
        now = _now_iso()
        self._history("delivered", {"delivery": did, "tid": d["source"]["ref"], "label": d["label"],
                                    "items": [normalize_item(e) for e in d["items"]],
                                    "chest": {"x": pos["x"], "y": pos["y"], "z": pos["z"]},
                                    "log": list(self.bridge.evidence)}, d)
        self.ledger.update(did, status="delivered", delivered_ts=now, chest=pos, last_error=None,
                           attempts=d["attempts"] + 1, inserted=len(expand_items(d["items"])))
        self.log(f"{did}: delivered {d['label']!r} to chest at {_pos(pos)}")
        self.bridge.magic(pos)
        self.problem = None
        return True

    def _history(self, kind, what, d):
        """Write the history line for delivery d before its ledger entry changes; a failed write raises (the worker
        records it as its problem and the entry stays as it was, so the next pass retries). Idempotent per delivery:
        if the ledger write after a line fails, the next pass reaches this point again and must not write a second
        identical line, so a `delivered` line for this delivery, or a `delivery_failed` line with the same error,
        that is already on file is not written again."""
        if self.history is None:
            return
        for l in self.history.read(kind):
            w = l["what"]
            if w.get("delivery") == what["delivery"] and (kind == "delivered" or w.get("error") == what.get("error")):
                return
        self.history.append(kind, what, d["source"]["ref"])

    def status(self):
        """Snapshot for GET /api/minecraft (ledger-derived lists are added by the caller)."""
        return {"server_running": bool(self.server_running), "problem": self.problem}


def build_worker(cfg, ledger, poll=POLL_SECONDS, history=None):
    """The real worker for a validated config: screen transport + bridge + status check."""
    transport = ScreenTransport(cfg["mc_dir"], cfg["screen_session"])
    worker = DeliveryWorker(cfg, ledger, None, transport.server_running, poll=poll, history=history)
    worker.bridge = Bridge(transport, cfg["chests"], log=worker.log, forbidden=cfg.get("forbidden", []))
    return worker


def make_rng(seed=None):
    return random.Random(seed)
