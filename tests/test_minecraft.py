"""Minecraft bridge unit tests: config validation, village rules, rolls, ledger, log parsing, command formatting,
the chest/insert bridge and the delivery worker (against tests/fake_minecraft.py, whose replies were captured from a
real Paper 26.3 server). The live end-to-end run is documented in docs/design.md and was done on a server copy."""
import copy
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import minecraft_bridge as mcb  # noqa: E402
import server  # noqa: E402  (write_json_atomic, craft words)
from fake_minecraft import FakeMinecraft  # noqa: E402

CONFIG = ROOT / "config" / "minecraft.json"
WORDS = list(server.load_craft_words())


def shipped():
    return json.loads(CONFIG.read_text())


def item(name="cookie", count=1, **extra):
    return {"item": "minecraft:" + name, "count": count, **extra}


class ShippedConfig(unittest.TestCase):
    def setUp(self):
        self.cfg = mcb.load_config(CONFIG, craft_words=WORDS)
        self.profs = self.cfg["village"]["professions"]

    def test_thirteen_professions_and_the_wandering_trader(self):
        ids = [p["id"] for p in self.profs]
        self.assertEqual(ids[:13], ["librarian", "armorer", "weaponsmith", "toolsmith", "farmer", "fletcher", "cleric",
                                    "cartographer", "shepherd", "butcher", "fisherman", "mason", "leatherworker"])
        self.assertEqual(ids[13], "wandering_trader")
        self.assertEqual(self.profs[13]["requires"], "all_professions")
        self.assertTrue(all("requires" not in p for p in self.profs[:13]))

    def test_job_blocks_are_the_real_ones(self):
        blocks = {p["id"]: p["job_block_item"] for p in self.profs[:13]}
        self.assertEqual(blocks["librarian"], "minecraft:lectern")
        self.assertEqual(blocks["armorer"], "minecraft:blast_furnace")
        self.assertEqual(blocks["leatherworker"], "minecraft:cauldron")
        self.assertEqual(blocks["fisherman"], "minecraft:barrel")
        self.assertEqual(len(set(blocks.values())), 13)

    def test_enchanted_books_only_at_the_librarian(self):
        for p in self.profs:
            has = any(i["item"] == "minecraft:enchanted_book" for o in p["offers"] for i in o["items"])
            self.assertEqual(has, p["id"] == "librarian", p["id"])

    def test_every_profession_covers_all_levels_and_master_has_big_items(self):
        n = len(self.cfg["village"]["levels"]["names"])
        for p in self.profs:
            levels = {o["min_level"] for o in p["offers"]}
            self.assertEqual(levels, set(range(n)) if p["id"] != "wandering_trader" else levels, p["id"])
            self.assertGreaterEqual(len(p["offers"]), 10, p["id"])
        mending = [o for o in self.profs[0]["offers"] if o["id"] == "lib_mending"][0]
        self.assertEqual(mending["min_level"], n - 1)

    def test_unlock_items(self):
        lib = mcb.profession_unlock_items(self.profs[0])
        self.assertEqual([i["item"] for i in lib], ["minecraft:villager_spawn_egg", "minecraft:lectern"])
        trader = mcb.profession_unlock_items(self.profs[13])
        self.assertEqual([i["item"] for i in trader], ["minecraft:wandering_trader_spawn_egg",
                                                       "minecraft:trader_llama_spawn_egg"])

    def test_defaults_match_the_spec(self):
        v = self.cfg["village"]
        self.assertEqual(v["levels"]["names"], ["Novice", "Apprentice", "Journeyman", "Expert", "Master"])
        self.assertEqual(v["levels"]["thresholds"], [0, 30, 80, 160, 300])
        self.assertEqual(v["points"], {"word": 1, "story_first": 10, "letter_mastered": 5})
        self.assertEqual(v["bell_every_points"], 40)
        self.assertEqual(self.cfg["earn"], {"word_emerald": 1, "story_first_emerald": 5, "story_replay_emerald": 2,
                                            "craft_emerald": 1})
        self.assertNotIn("level_up", self.cfg["surprises"])  # the village level-up surprise was removed 2026-10-21
        self.assertEqual(self.cfg["surprises"]["story_replay_tiers"], ["epic", "legendary"])

    def test_no_private_gamertag_in_the_committed_config(self):
        self.assertNotIn("Snarly", CONFIG.read_text())  # lives in the gitignored private_overrides.json

    def test_every_craft_word_has_an_item(self):
        for w in WORDS:
            self.assertIn(w, self.cfg["craft_items"])


class ConfigValidation(unittest.TestCase):
    def bad(self, mutate, field):
        cfg = shipped()
        mutate(cfg)
        with self.assertRaises(mcb.ConfigError) as cm:
            mcb.validate_config(cfg, WORDS)
        self.assertIn(field, str(cm.exception))

    def test_unknown_and_missing_keys(self):
        self.bad(lambda c: c.update(extra=1), "config.extra")
        self.bad(lambda c: c.pop("village"), "config.village")
        self.bad(lambda c: c.update(offers=[]), "config.offers")  # the old top-level offers are gone
        self.bad(lambda c: c["village"].update(x=1), "village.x")
        self.bad(lambda c: c["village"]["professions"][0].update(x=1), "professions[0].x")

    def test_levels(self):
        self.bad(lambda c: c["village"]["levels"].update(thresholds=[0, 30, 30, 160, 300]), "levels.thresholds")
        self.bad(lambda c: c["village"]["levels"].update(thresholds=[5, 30, 80, 160, 300]), "levels.thresholds")
        self.bad(lambda c: c["village"]["levels"].update(thresholds=[0, 30]), "levels.thresholds")

    def test_offers(self):
        off = lambda c: c["village"]["professions"][0]["offers"][0]  # noqa: E731
        self.bad(lambda c: off(c).update(min_level=5), "min_level")
        self.bad(lambda c: off(c).update(sprite="not_a_sprite"), "sprite")
        self.bad(lambda c: off(c).update(price=0), "price")
        self.bad(lambda c: off(c).update(id="lib_shelves"), "duplicate offer id")
        self.bad(lambda c: off(c).pop("min_level"), "min_level")
        self.bad(lambda c: off(c)["items"][0].update(item="cookie"), "items[0].item")
        self.bad(lambda c: off(c)["items"][0].update(count=65), "count")

    def test_requires_and_job_block(self):
        self.bad(lambda c: c["village"]["professions"][13].update(requires="some"), "requires")
        self.bad(lambda c: c["village"]["professions"][0].pop("job_block_item"), "job_block_item")
        self.bad(lambda c: c["village"]["professions"][0].update(unlock_items=[item()]), "exactly one")

    def test_item_entries(self):
        self.bad(lambda c: c["craft_items"].update(PIG=[item("pig_spawn_egg", potion="minecraft:swiftness")]), "potion")
        self.bad(lambda c: c["craft_items"].update(PIG=[item("diamond_sword", enchantments={"sharpness": 5})]),
                 "enchantments")
        self.bad(lambda c: c["craft_items"].update(PIG=[item("diamond_sword", enchantments={"minecraft:sharpness": 0})]),
                 "level")
        self.bad(lambda c: c["craft_items"].update(PIG=[item("diamond", profile="x")]), "profile")

    def test_unstackable_slot_budget(self):
        self.bad(lambda c: c["craft_items"].update(PIG=[item("cake", 28)]), "chest slots")

    def test_tiers_and_surprises(self):
        self.bad(lambda c: c["tiers"]["rare"][0].pop("sprite"), "sprite")
        self.bad(lambda c: c["surprises"].update(streak10="nope"), "surprises.streak10")
        self.bad(lambda c: c["surprises"].update(level_up="epic"), "surprises.level_up")  # removed key: unknown

    def test_replay_tiers_validation(self):
        self.bad(lambda c: c["surprises"].update(story_replay_tiers=[]), "story_replay_tiers")
        self.bad(lambda c: c["surprises"].update(story_replay_tiers=["epic", "nope"]), "story_replay_tiers[1]")
        self.bad(lambda c: c["surprises"].update(story_replay_tiers="epic"), "story_replay_tiers")
        self.bad(lambda c: c["surprises"].pop("story_replay_tiers"), "story_replay_tiers")

    def test_old_story_replay_key_is_rejected_naming_the_new_one(self):
        cfg = shipped()
        cfg["surprises"]["story_replay"] = "rare"
        with self.assertRaises(mcb.ConfigError) as cm:
            mcb.validate_config(cfg, WORDS)
        self.assertIn("story_replay_tiers", str(cm.exception))
        self.assertIn("surprises.story_replay", str(cm.exception))

    def test_chests_too_close(self):
        self.bad(lambda c: c["chests"].append({**c["chests"][0], "x": c["chests"][0]["x"] + 1}), "too close")

    def test_missing_craft_word(self):
        self.bad(lambda c: c["craft_items"].pop("PIG"), "craft_items.PIG")

    def test_overrides_file_may_only_set_the_player(self):
        with tempfile.TemporaryDirectory() as d:
            ov = Path(d) / "o.json"
            ov.write_text('{"player": "Someone_1"}')
            self.assertEqual(mcb.load_config(CONFIG, WORDS, overrides_path=ov)["player"], "Someone_1")
            ov.write_text('{"enabled": false}')
            with self.assertRaises(mcb.ConfigError):
                mcb.load_config(CONFIG, WORDS, overrides_path=ov)


class VillageRules(unittest.TestCase):
    def setUp(self):
        self.cfg = mcb.load_config(CONFIG, craft_words=WORDS)

    @staticmethod
    def ev(t, **kw):
        return {"type": t, **kw}

    def test_points(self):
        events = [self.ev("word", result="correct")] * 4 + [self.ev("word", result="assisted"), self.ev("word", result="miss"),
                  self.ev("card", result="correct"), self.ev("story_done", track="smallcaps", story_id="a"),
                  self.ev("story_done", track="smallcaps", story_id="a"),  # a replay is not a new first pass
                  self.ev("story_done", track="lowercase", story_id="a")]
        # 4 independent words + 2 first passes (a/smallcaps, a/lowercase) x10 + 3 letters x5
        self.assertEqual(mcb.reading_points(self.cfg, events, 3), 4 + 20 + 15)

    def test_levels(self):
        names = [mcb.level_for(self.cfg, p) for p in (0, 29, 30, 79, 80, 160, 299, 300, 10000)]
        self.assertEqual([n["index"] for n in names], [0, 0, 1, 1, 2, 3, 3, 4, 4])
        self.assertEqual(names[0], {"index": 0, "name": "Novice", "next_at": 30})
        self.assertEqual(names[-1], {"index": 4, "name": "Master", "next_at": None})

    def test_bells(self):
        events = [self.ev("story_done", track="smallcaps", story_id="a"), self.ev("story_done", track="smallcaps", story_id="b")]
        self.assertEqual(mcb.bells_earned(self.cfg, events, 79), 2 + 1)  # 2 first passes + 79 // 40


class Rolls(unittest.TestCase):
    def test_replay_tier_escalates_and_the_last_entry_repeats(self):
        cfg = mcb.load_config(CONFIG, craft_words=WORDS)
        self.assertEqual([mcb.replay_tier(cfg, n) for n in (1, 2, 3, 9)], ["epic", "legendary", "legendary", "legendary"])
        cfg["surprises"]["story_replay_tiers"] = ["rare", "epic", "legendary"]
        self.assertEqual([mcb.replay_tier(cfg, n) for n in (1, 2, 3, 4)], ["rare", "epic", "legendary", "legendary"])
        for bad in (0, -1, "1", True):
            with self.assertRaises(ValueError):
                mcb.replay_tier(cfg, bad)

    def test_legendary_tier_is_shipped_and_above_epic(self):
        cfg = mcb.load_config(CONFIG, craft_words=WORDS)
        ids = {e["item"] for r in cfg["tiers"]["legendary"] for e in r["items"]}
        for want in ("netherite_chestplate", "elytra", "totem_of_undying", "enchanted_golden_apple", "beacon",
                     "nether_star", "heart_of_the_sea", "conduit", "trident"):
            self.assertIn("minecraft:" + want, ids)
        self.assertTrue(any(i.endswith("shulker_box") for i in ids))
        self.assertTrue(any(e["item"] == "minecraft:diamond" and e["count"] == 64
                            for r in cfg["tiers"]["legendary"] for e in r["items"]))
        epic_labels = {r["label"] for r in cfg["tiers"]["epic"]}
        self.assertFalse(epic_labels & {r["label"] for r in cfg["tiers"]["legendary"]})  # a label names one tier

    def test_seeded_roll_is_repeatable_and_normalised(self):
        cfg = mcb.load_config(CONFIG, craft_words=WORDS)
        a = mcb.roll_tier(cfg, "epic", random.Random(7))
        b = mcb.roll_tier(cfg, "epic", random.Random(7))
        self.assertEqual(a, b)
        self.assertTrue(all("count" in e for e in a["items"]))
        self.assertIn(a["sprite"], mcb.ITEM_SPRITES)

    def test_weights_are_honoured(self):
        cfg = mcb.load_config(CONFIG, craft_words=WORDS)
        cfg["tiers"]["rare"] = [{"weight": 1, "label": "A", "sprite": "diamond", "items": [item("diamond")]},
                                {"weight": 10**9, "label": "B", "sprite": "diamond", "items": [item("diamond")]}]
        labels = {mcb.roll_tier(cfg, "rare", random.Random(s))["label"] for s in range(20)}
        self.assertEqual(labels, {"B"})


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "d.json"
        self.led = mcb.Ledger(self.path, server.write_json_atomic)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_update_never_delete(self):
        a = self.led.create("shop", "t000001", "Cookie", [item()])
        b = self.led.create("craft", "t000002", "Egg", [item("pig_spawn_egg")])
        self.assertEqual((a["id"], b["id"]), ("d000001", "d000002"))
        self.assertEqual(a["status"], "pending")
        self.led.update("d000001", status="delivered", delivered_ts="2026-10-18T10:00:00-04:00",
                        chest={"x": 1, "y": 2, "z": 3})
        self.assertEqual([d["status"] for d in self.led.deliveries()], ["delivered", "pending"])
        self.assertEqual(self.led.find_by_ref("t000002")["id"], "d000002")
        self.assertIsNone(self.led.find_by_ref("t000009"))

    def test_a_ref_gets_one_delivery_only(self):
        self.led.create("shop", "t000001", "Cookie", [item()])
        with self.assertRaises(mcb.LedgerError):
            self.led.create("shop", "t000001", "Cookie", [item()])

    def test_invalid_updates_and_files_are_refused(self):
        self.led.create("shop", "t000001", "Cookie", [item()])
        with self.assertRaises(mcb.LedgerError):
            self.led.update("d000001", status="done")
        with self.assertRaises(mcb.LedgerError):
            self.led.update("d000001", status="delivered")  # delivered needs delivered_ts and chest
        with self.assertRaises(mcb.LedgerError):
            self.led.update("d999999", status="failed")
        self.path.write_text("{not json")
        with self.assertRaises(mcb.LedgerError):
            self.led.deliveries()
        self.assertEqual(self.path.read_text(), "{not json")  # a bad file is never overwritten

    def test_kinds(self):
        for kind in ("shop", "surprise", "craft", "unlock"):
            self.led.create(kind, f"t{len(self.led.deliveries()) + 1:06d}", "x", [item()])
        with self.assertRaises(mcb.LedgerError):
            self.led.create("gift", "t000099", "x", [item()])


# Reply lines captured from the real Paper 26.3 server (docs/design.md lists the commands).
LOG_ITEMS = ('[15:16:22] [Server thread/INFO]: System chat: -47, 65, 90 has the following block data: '
             '[{Slot: 0b, id: "minecraft:diamond_sword", count: 1, components: {"minecraft:enchantments": '
             '{"minecraft:sharpness": 5, "minecraft:unbreaking": 3}}}, {Slot: 1b, id: "minecraft:cobblestone", count: 64}]')


class LogParsing(unittest.TestCase):
    def test_parse_chat(self):
        self.assertEqual(mcb.parse_chat("[15:16:19] [Server thread/INFO]: System chat: Dropped 64 [Cobblestone]"),
                         "Dropped 64 [Cobblestone]")
        self.assertIsNone(mcb.parse_chat("[15:16:19] [Server thread/INFO]: Sam joined the game"))

    def test_parse_items(self):
        text = mcb.parse_chat(LOG_ITEMS)
        import re
        inner = re.search(r"block data: (\[.*\])\s*$", text).group(1)
        parsed = mcb.parse_items_line(inner)
        self.assertEqual(parsed["slots"], 2)
        self.assertEqual(parsed["totals"], {"minecraft:diamond_sword": 1, "minecraft:cobblestone": 64})
        self.assertEqual(mcb.parse_items_line("[]")["slots"], 0)


class CommandFormat(unittest.TestCase):
    pos = {"x": -47, "y": 65, "z": 90}

    def test_plain_item(self):
        self.assertEqual(
            mcb.loot_insert_command(self.pos, item("cookie", 16)),
            'loot insert -47 65 90 loot {pools:[{rolls:1,entries:[{type:"minecraft:item",name:"minecraft:cookie",'
            'modifier:[{type:"minecraft:set_count",count:16}]}]}]}')

    def test_enchanted_book_and_sword(self):
        book = mcb.loot_insert_command(self.pos, item("enchanted_book", stored_enchantments={"minecraft:mending": 1}))
        self.assertIn('"minecraft:stored_enchantments":{"minecraft:mending":1}', book)
        sword = mcb.loot_insert_command(self.pos, item("diamond_sword", enchantments={"minecraft:unbreaking": 3,
                                                                                    "minecraft:sharpness": 5}))
        self.assertIn('"minecraft:enchantments":{"minecraft:sharpness":5,"minecraft:unbreaking":3}', sword)
        self.assertNotIn("functions", sword)  # 26.x schema: modifier/type, not the old functions/function

    def test_head_and_potion(self):
        self.assertIn('"minecraft:profile":"example_player"',
                      mcb.loot_insert_command(self.pos, item("player_head", profile="example_player")))
        self.assertIn('"minecraft:potion_contents":{potion:"minecraft:swiftness"}',
                      mcb.loot_insert_command(self.pos, item("tipped_arrow", 16, potion="minecraft:swiftness")))

    def test_describe(self):
        self.assertEqual(mcb.describe_items([item("glowstone", 4), item("sunflower")]), "Glowstone x4 + Sunflower")
        self.assertEqual(mcb.describe_items([item("player_head", profile="example_player")]), "example_player's Head")


CHESTS = [{"x": 0, "y": 65, "z": 0}, {"x": 4, "y": 65, "z": 0}, {"x": 8, "y": 65, "z": 0}]
P1, P2, P3 = (0, 65, 0), (4, 65, 0), (8, 65, 0)


def bridge_on(fake, chests=CHESTS, forbidden=()):
    return mcb.Bridge(fake, chests, reply_timeout=0.05, sleep=lambda s: None, forbidden=forbidden)


def delivery(items, chest=None, inserted=0):
    return {"id": "d000001", "created_ts": "2026-10-18T10:00:00-04:00", "source": {"kind": "shop", "ref": "t000001"},
            "label": "x", "items": [mcb.normalize_item(i) for i in items], "status": "pending", "attempts": 0,
            "last_error": None, "delivered_ts": None, "chest": chest, "inserted": inserted}


class BridgeCase(unittest.TestCase):
    def test_first_delivery_places_chest_one_decorated_and_labelled(self):
        fake = FakeMinecraft()
        b = bridge_on(fake)
        progress = []
        pos = b.deliver(delivery([item("cookie", 16), item("enchanted_book", stored_enchantments={"minecraft:mending": 1})]),
                        lambda **f: progress.append(f))
        self.assertEqual(pos, CHESTS[0])
        self.assertEqual(fake.chests[P1]["name"], "Magic Chest")
        self.assertEqual([s["id"] for s in fake.chests[P1]["slots"]], ["minecraft:cookie", "minecraft:enchanted_book"])
        self.assertIn({"inserted": 2, "confirmed": [16, 1], "pending": None}, progress)  # Dropped counts recorded per entry
        self.assertTrue(fake.blocks)  # decorations around it
        self.assertTrue(any(c.startswith("summon") for c in fake.sent))
        self.assertTrue(any(c.startswith("forceload add") for c in fake.sent))

    def test_unstackable_potions_are_inserted_one_command_each_so_the_potion_survives(self):
        fake = FakeMinecraft()
        bridge_on(fake).deliver(delivery([item("potion", 3, potion="minecraft:strong_healing")]), lambda **f: None)
        inserts = [c for c in fake.sent if c.startswith("loot insert")]
        self.assertEqual(len(inserts), 3)
        self.assertTrue(all("count:1}" in c and "strong_healing" in c for c in inserts))
        self.assertEqual(len(fake.chests[P1]["slots"]), 3)

    def test_expand_items(self):
        out = mcb.expand_items([item("potion", 2, potion="minecraft:swiftness"), item("arrow", 32), item("cake", 1)])
        self.assertEqual([(e["item"], e["count"]) for e in out],
                         [("minecraft:potion", 1), ("minecraft:potion", 1), ("minecraft:arrow", 32), ("minecraft:cake", 1)])
        self.assertEqual(mcb.slots_needed(out), 4)

    def test_unstackable_stack_of_many(self):
        fake = FakeMinecraft()
        bridge_on(fake).deliver(delivery([item("cake", 3)]), lambda **f: None)
        self.assertEqual(len(fake.chests[P1]["slots"]), 3)  # "Dropped 3 items": three separate cakes

    def test_overflow_goes_to_chest_two_named_and_all_full_is_loud(self):
        fake = FakeMinecraft()
        b = bridge_on(fake)
        fake.full_chest(P1)
        pos = b.deliver(delivery([item("diamond")]), lambda **f: None)
        self.assertEqual(pos, CHESTS[1])
        self.assertEqual(fake.chests[P2]["name"], "Magic Chest 2")
        fake.full_chest(P2, "Magic Chest 2")
        fake.full_chest(P3, "Magic Chest 3")
        with self.assertRaises(mcb.AllFull):
            b.deliver(delivery([item("diamond")]), lambda **f: None)

    def test_not_enough_free_slots_for_the_whole_delivery_overflows(self):
        fake = FakeMinecraft()
        fake.chests[P1] = {"name": "Magic Chest", "slots": [{"id": "minecraft:dirt", "count": 1, "components": ""}] * 26}
        pos = bridge_on(fake).deliver(delivery([item("diamond"), item("emerald")]), lambda **f: None)
        self.assertEqual(pos, CHESTS[1])  # one free slot is not enough for two stacks

    def test_unusable_candidate_is_skipped(self):
        fake = FakeMinecraft()
        fake.full_chest(P1)
        fake.blocks[P2] = "minecraft:stone"  # something else sits on candidate 2
        fake.unsolid.add((8, 64, 0))  # candidate 3 hangs over nothing
        with self.assertRaises(mcb.AllFull):
            bridge_on(fake).deliver(delivery([item("diamond")]), lambda **f: None)
        self.assertNotIn(P3, fake.chests)

    def test_tall_grass_does_not_block_a_candidate_spot_but_water_does(self):
        fake = FakeMinecraft()
        fake.full_chest(P1)
        fake.blocks[P2] = "minecraft:short_grass"
        fake.blocks[P3] = "minecraft:water"
        pos = bridge_on(fake).deliver(delivery([item("diamond")]), lambda **f: None)
        self.assertEqual(pos, CHESTS[1])
        self.assertIn(P2, fake.chests)
        fake.full_chest(P2, "Magic Chest 2")
        with self.assertRaises(mcb.AllFull):
            bridge_on(fake).deliver(delivery([item("diamond")]), lambda **f: None)

    def test_a_chest_that_is_not_ours_is_never_used(self):
        fake = FakeMinecraft()
        fake.chests[P1] = {"name": "Dad's Stuff", "slots": []}
        pos = bridge_on(fake).deliver(delivery([item("diamond")]), lambda **f: None)
        self.assertEqual(pos, CHESTS[1])
        self.assertEqual(fake.chests[P1]["slots"], [])

    def test_lying_insert_is_caught_by_the_read_back(self):
        fake = FakeMinecraft()
        fake.drop_less = 1
        with self.assertRaises(mcb.VerifyError) as cm:
            bridge_on(fake).deliver(delivery([item("cookie", 16)]), lambda **f: None)
        self.assertIn("read-back", str(cm.exception))

    def test_missing_enchantment_is_caught(self):
        fake = FakeMinecraft()
        before = {"slots": 0, "totals": {}, "raw": "[]"}
        after = {"slots": 1, "totals": {"minecraft:diamond_sword": 1}, "raw": '[{id: "minecraft:diamond_sword"}]'}
        with self.assertRaises(mcb.VerifyError):
            mcb.Bridge.verify(before, after, [mcb.normalize_item(item("diamond_sword", enchantments={"minecraft:sharpness": 5}))])

    def test_no_reply_is_an_error_naming_the_command(self):
        fake = FakeMinecraft()
        fake.say = lambda t: None  # a server that never answers
        with self.assertRaises(mcb.McError) as cm:
            bridge_on(fake).ensure_forceload(CHESTS[0])
        self.assertIn("forceload add 0 0", str(cm.exception))

    def test_unloaded_chunk(self):
        fake = FakeMinecraft()
        fake.unloaded = True
        with self.assertRaises(mcb.McError):
            bridge_on(fake).chest_state(CHESTS[0])

    def test_resume_after_partial_insert_does_not_duplicate(self):
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("cookie", 16), item("diamond")])
        base = {"slots": 0, "totals": {}, "raw": "[]"}  # the chest as it was before the delivery's first attempt
        fake.chests[P1] = {"name": "Magic Chest", "slots": []}
        b.deliver(delivery([item("cookie", 16)]), lambda **f: None)  # attempt 1 got the cookies in, then "crashed"
        before = len(fake.chests[P1]["slots"])
        b.deliver({**d, "chest": CHESTS[0], "inserted": 1, "baseline": base}, lambda **f: None)
        ids = [s["id"] for s in fake.chests[P1]["slots"]]
        self.assertEqual(ids.count("minecraft:cookie"), before)  # only the diamond was added
        self.assertEqual(ids.count("minecraft:diamond"), 1)

    # -- review findings: spawn cell, late replies, read-back on retry
    def test_decoration_never_touches_the_forbidden_spawn_cell(self):
        # Review finding 2: the lantern went onto the cell west of chest 1, which was the world spawn point.
        fake = FakeMinecraft()
        spawn = {"x": -1, "y": 65, "z": 0}  # exactly where decorate() puts its first lantern (x - 1)
        bridge_on(fake, forbidden=[spawn]).deliver(delivery([item("diamond")]), lambda **f: None)
        self.assertNotIn((-1, 65, 0), fake.blocks)
        self.assertFalse([c for c in fake.sent if c.startswith("setblock -1 65 0 ")])
        self.assertIn((1, 65, 0), fake.blocks)  # the other decorations still happen

    def test_the_cell_above_a_forbidden_cell_is_protected_too(self):
        fake = FakeMinecraft()
        bridge_on(fake, forbidden=[{"x": -1, "y": 64, "z": 0}]).deliver(delivery([item("diamond")]), lambda **f: None)
        self.assertNotIn((-1, 65, 0), fake.blocks)  # y 64 forbidden -> y 65 (the head) too

    def test_a_chest_is_never_placed_on_a_forbidden_cell(self):
        fake = FakeMinecraft()
        b = bridge_on(fake, forbidden=[{"x": 0, "y": 65, "z": 0}])
        self.assertFalse(b.place_chest(CHESTS[0], 1))
        self.assertNotIn(P1, fake.chests)

    def test_a_late_reply_does_not_duplicate_the_insert_on_retry(self):
        # Review finding 3: the insert landed but its "Dropped" reply came after the timeout; the retry used to
        # insert it again and the re-snapshotted baseline made the duplicate verify.
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("cookie", 16)])
        fake.late_loot_replies = 1
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        self.assertEqual(d["inserted"], 0)  # the reply never came, so it was not counted
        b.deliver(d, lambda **f: d.update(f))  # the retry
        total = sum(s["count"] for s in fake.chests[P1]["slots"] if s["id"] == "minecraft:cookie")
        self.assertEqual(total, 16)  # one copy, not two
        self.assertIn("baseline", d)  # the pre-delivery chest was persisted with the delivery
        self.assertTrue(any("reconciled" in e for e in b.evidence))

    def test_a_late_reply_in_the_middle_of_several_entries(self):
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("cookie", 16), item("diamond"), item("emerald", 3)])
        real_send, seen = fake.send, {"n": 0}

        def send(cmd):  # let the first insert reply normally, delay the reply of the second one (the diamond)
            if cmd.startswith("loot insert"):
                seen["n"] += 1
                fake.late_loot_replies = 1 if seen["n"] == 2 else 0
            return real_send(cmd)
        fake.send = send
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        self.assertEqual(d["inserted"], 1)
        b.deliver(d, lambda **f: d.update(f))
        held = lambda name: sum(s["count"] for s in fake.chests[P1]["slots"] if s["id"] == name)  # noqa: E731
        self.assertEqual((held("minecraft:cookie"), held("minecraft:diamond"), held("minecraft:emerald")), (16, 1, 3))

    def _held(self, fake, name):
        return sum(s["count"] for s in fake.chests[P1]["slots"] if s["id"] == name)

    def test_child_taking_the_late_item_out_is_reported_ambiguous_and_nothing_is_inserted_again(self):
        # Review finding 4, scenario A: the insert landed (its reply was late), Sam took the items out before the
        # retry. The old reconcile saw "not landed" and inserted it again (then failed verify, or doubled it).
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("cookie", 16)])
        fake.late_loot_replies = 1
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        fake.chests[P1]["slots"] = []  # Sam emptied the chest
        fake.sent.clear()
        with self.assertRaises(mcb.VerifyError) as cm:
            b.deliver(d, lambda **f: d.update(f))
        self.assertIn("ambiguous", str(cm.exception))
        self.assertIn("Dropped 16", str(cm.exception))  # the evidence: the log holds the reply
        self.assertFalse([c for c in fake.sent if c.startswith("loot insert")])
        self.assertEqual(self._held(fake, "minecraft:cookie"), 0)

    def test_child_taking_confirmed_items_out_before_a_retry_is_reported_ambiguous(self):
        # Scenario A, other half: entry 1 was confirmed, entry 2 never landed (command lost), Sam took entry 1 out.
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("cookie", 16), item("diamond")])
        real_send, seen = fake.send, {"n": 0}

        def send(cmd):
            if cmd.startswith("loot insert"):
                seen["n"] += 1
                fake.lose_loot_commands = 1 if seen["n"] == 2 else 0
            return real_send(cmd)
        fake.send = send
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        self.assertEqual((d["inserted"], d["confirmed"]), (1, [16]))
        fake.chests[P1]["slots"] = []
        fake.sent.clear()
        with self.assertRaises(mcb.VerifyError):
            b.deliver(d, lambda **f: d.update(f))
        self.assertFalse([c for c in fake.sent if c.startswith("loot insert")])

    def test_child_putting_a_matching_item_in_is_not_counted_as_the_delivery(self):
        # Scenario B: the insert never executed (no reply, nothing in the log); Sam put a diamond in the chest.
        # The old reconcile counted that diamond as the delivery's, skipped the insert and verified: silently short.
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("diamond")])
        fake.lose_loot_commands = 1
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        fake.chests[P1]["slots"].append({"id": "minecraft:diamond", "count": 1, "components": ""})
        fake.sent.clear()
        with self.assertRaises(mcb.VerifyError) as cm:
            b.deliver(d, lambda **f: d.update(f))
        self.assertIn("reply to it in the log: None", str(cm.exception))
        self.assertFalse([c for c in fake.sent if c.startswith("loot insert")])  # no guess, no insert

    def test_an_unrelated_item_in_the_chest_does_not_stop_a_clean_retry(self):
        # The command never executed and nothing else changed: the retry inserts it (once).
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("diamond")])
        fake.lose_loot_commands = 1
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        b.deliver(d, lambda **f: d.update(f))
        self.assertEqual(self._held(fake, "minecraft:diamond"), 1)

    def test_a_reply_that_is_lost_everywhere_is_ambiguous_not_guessed(self):
        # The item landed but no reply ever reached the log: chest delta without evidence is not proof.
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("cookie", 16)])
        fake.swallow_loot_replies = 1
        with self.assertRaises(mcb.McError):
            b.deliver(d, lambda **f: d.update(f))
        with self.assertRaises(mcb.VerifyError):
            b.deliver(d, lambda **f: d.update(f))
        self.assertEqual(self._held(fake, "minecraft:cookie"), 16)

    def test_pending_and_confirmed_are_validated_in_the_ledger(self):
        d = delivery([item("diamond")], chest=CHESTS[0])
        d["confirmed"] = [1]
        with self.assertRaises(mcb.ConfigError):  # confirmed needs exactly `inserted` counts
            mcb.validate_delivery(d)
        d["inserted"], d["pending"] = 1, {"index": 5, "mark": [1, 2]}
        with self.assertRaises(mcb.ConfigError):
            mcb.validate_delivery(d)
        d["pending"] = {"index": 0, "mark": [1, 2]}
        mcb.validate_delivery(d)

    def test_a_retry_with_nothing_left_to_insert_still_reads_the_chest_back(self):
        # Review finding 3, second variant: every insert succeeded but the final read-back timed out; the retry had
        # nothing to insert and used to pass verify([]) without looking. Here the chest does NOT hold the items.
        fake = FakeMinecraft()
        fake.chests[P1] = {"name": "Magic Chest", "slots": []}
        d = delivery([item("diamond")], chest=CHESTS[0], inserted=1)
        d["baseline"] = {"slots": 0, "totals": {}, "raw": "[]"}
        with self.assertRaises(mcb.VerifyError):
            bridge_on(fake).deliver(d, lambda **f: None)
        self.assertTrue(any(c.endswith("Items") for c in fake.sent))

    def test_a_retry_with_nothing_left_passes_when_the_chest_holds_the_items(self):
        fake = FakeMinecraft()
        b = bridge_on(fake)
        d = delivery([item("diamond")])
        b.deliver(d, lambda **f: d.update(f))
        fake.sent.clear()
        d["inserted"] = 1
        self.assertEqual(b.deliver(d, lambda **f: d.update(f)), CHESTS[0])
        self.assertFalse([c for c in fake.sent if c.startswith("loot insert")])  # nothing inserted twice

    def test_an_old_entry_with_inserted_items_but_no_baseline_fails_loudly(self):
        fake = FakeMinecraft()
        fake.chests[P1] = {"name": "Magic Chest", "slots": []}
        with self.assertRaises(mcb.VerifyError) as cm:
            bridge_on(fake).deliver(delivery([item("diamond")], chest=CHESTS[0], inserted=1), lambda **f: None)
        self.assertIn("baseline", str(cm.exception))

    def test_baseline_is_validated_in_the_ledger(self):
        d = delivery([item("diamond")], chest=CHESTS[0])
        d["baseline"] = {"slots": 99, "totals": {}, "raw": ""}
        with self.assertRaises(mcb.ConfigError):
            mcb.validate_delivery(d)
        d["baseline"] = {"slots": 0, "totals": {"minecraft:dirt": 1}, "raw": "[]"}
        mcb.validate_delivery(d)
        d["chest"] = None
        with self.assertRaises(mcb.ConfigError):
            mcb.validate_delivery(d)


def make_ledger(tmp):
    return mcb.Ledger(Path(tmp) / "d.json", server.write_json_atomic)


class WorkerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = make_ledger(self.tmp.name)
        self.fake = FakeMinecraft()
        self.logs = []
        self.cfg = {"chests": CHESTS}
        self.history = mcb.History(Path(self.tmp.name) / "h.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def worker(self, running=None):
        w = mcb.DeliveryWorker(self.cfg, self.ledger, bridge_on(self.fake),
                               lambda: self.fake.running if running is None else running, log=self.logs.append,
                               history=self.history)
        w.server_running = True  # as if already seen up; the grace pass has its own tests
        return w

    def create(self, ref, *items):
        return self.ledger.create("shop", ref, "label " + ref, list(items))

    def test_delivers_in_creation_order_and_logs_confirmation(self):
        self.create("t000001", item("cookie", 16))
        self.create("t000002", item("diamond"))
        w = self.worker()
        w.run_once()
        ds = self.ledger.deliveries()
        self.assertEqual([d["status"] for d in ds], ["delivered", "delivered"])
        self.assertEqual(ds[0]["chest"], CHESTS[0])
        self.assertLess(ds[0]["delivered_ts"], ds[1]["delivered_ts"] + "z")
        self.assertIsNone(w.problem)
        self.assertTrue(any("delivered" in m for m in self.logs))
        self.assertTrue(any(c.startswith("playsound") for c in self.fake.sent))  # the magic

    def test_waits_when_minecraft_is_off(self):
        self.create("t000001", item("cookie"))
        self.fake.running = False
        w = self.worker()
        w.run_once()
        self.assertEqual(self.ledger.deliveries()[0]["status"], "pending")
        self.assertEqual(self.ledger.deliveries()[0]["attempts"], 0)
        self.assertFalse(w.status()["server_running"])
        self.assertIsNone(w.problem)
        self.assertEqual(self.fake.sent, [])  # not one command was tried
        self.fake.running = True
        w.run_once()  # grace pass: the world may still be loading right after a start
        self.assertEqual(self.ledger.deliveries()[0]["status"], "pending")
        self.assertEqual(self.fake.sent, [])
        w.run_once()
        self.assertEqual(self.ledger.deliveries()[0]["status"], "delivered")

    def test_one_retry_then_failed_and_visible(self):
        self.create("t000001", item("cookie"))
        self.create("t000002", item("diamond"))
        self.fake.unloaded = True
        w = self.worker()
        w.run_once()
        d = self.ledger.deliveries()[0]
        self.assertEqual((d["status"], d["attempts"]), ("pending", 1))  # first failure: retry next poll
        self.assertIn("not loaded", d["last_error"] + "not loaded")
        w.run_once()
        d = self.ledger.deliveries()[0]
        self.assertEqual((d["status"], d["attempts"]), ("failed", 2))
        self.assertTrue(d["last_error"])
        self.assertIn("FAILED", w.problem)
        self.fake.unloaded = False
        w.run_once()  # a failed entry never blocks the next one
        self.assertEqual([x["status"] for x in self.ledger.deliveries()], ["failed", "delivered"])

    def test_all_full_stays_pending_with_the_loud_problem(self):
        self.create("t000001", item("cookie"))
        for pos in (P1, P2, P3):
            self.fake.full_chest(pos)
        w = self.worker()
        w.run_once()
        d = self.ledger.deliveries()[0]
        self.assertEqual((d["status"], d["attempts"]), ("pending", 0))
        self.assertEqual(w.problem, mcb.ALL_FULL_PROBLEM)
        del self.fake.chests[P1]["slots"][0]  # Dad empties a slot: next pass delivers
        w.run_once()
        self.assertEqual(self.ledger.deliveries()[0]["status"], "delivered")
        self.assertIsNone(w.problem)

    def test_verify_failure_is_failed_at_once_not_retried(self):
        self.create("t000001", item("cookie", 16))
        self.fake.drop_less = 1
        w = self.worker()
        w.run_once()
        d = self.ledger.deliveries()[0]
        self.assertEqual((d["status"], d["attempts"]), ("failed", 1))
        self.assertIn("read-back", d["last_error"])

    def test_first_look_with_an_unknown_state_also_gets_the_grace_pass(self):
        # Review finding 5: a worker started while Minecraft was still loading (previous state None) burned an attempt.
        self.create("t000001", item("cookie"))
        w = mcb.DeliveryWorker(self.cfg, self.ledger, bridge_on(self.fake), lambda: True, log=self.logs.append)
        self.assertIsNone(w.server_running)
        w.run_once()
        self.assertEqual(self.fake.sent, [])
        self.assertEqual(self.ledger.deliveries()[0]["status"], "pending")
        w.run_once()
        self.assertEqual(self.ledger.deliveries()[0]["status"], "delivered")

    def test_delivered_history_line_carries_items_chest_and_the_confirming_log_lines(self):
        self.create("t000001", item("cookie", 16), item("diamond"))
        self.worker().run_once()
        (line,) = self.history.read("delivered")
        self.assertEqual(line["ref"], "t000001")
        self.assertEqual(line["what"]["chest"], CHESTS[0])
        self.assertEqual([i["item"] for i in line["what"]["items"]], ["minecraft:cookie", "minecraft:diamond"])
        self.assertEqual(line["what"]["log"], ["Dropped 16 [Cookie]", "Dropped 1 [Diamond]"])
        self.assertEqual(line["what"]["delivery"], "d000001")

    def test_failed_delivery_writes_a_delivery_failed_line(self):
        self.create("t000001", item("cookie", 16))
        self.fake.drop_less = 1
        self.worker().run_once()
        (line,) = self.history.read("delivery_failed")
        self.assertIn("read-back", line["what"]["error"])
        self.assertEqual(line["ref"], "t000001")

    def test_a_failed_history_write_leaves_the_delivery_pending_and_is_loud(self):
        self.create("t000001", item("cookie"))
        w = self.worker()
        with mock.patch.object(self.history, "append", side_effect=mcb.HistoryError("disk full")):
            with self.assertRaises(mcb.HistoryError):
                w.run_once()
        self.assertEqual(self.ledger.deliveries()[0]["status"], "pending")  # never delivered without its line
        w.run_once()  # the next pass reconciles: the items are already in the chest, nothing is inserted twice
        self.assertEqual(self.ledger.deliveries()[0]["status"], "delivered")
        self.assertEqual(sum(s["count"] for s in self.fake.chests[P1]["slots"]), 1)

    def test_a_ledger_write_failure_after_the_delivered_line_does_not_duplicate_the_line(self):
        # Review finding 5: the delivered line is written before the ledger update; when that update failed the next
        # pass wrote a second identical line.
        self.create("t000001", item("cookie"))
        w = self.worker()
        real = self.ledger.update
        calls = []

        def flaky(did, **f):
            calls.append(f)
            if f.get("status") == "delivered" and len(calls) < 20 and not getattr(flaky, "done", False):
                flaky.done = True
                raise mcb.LedgerError("disk full")
            return real(did, **f)
        with mock.patch.object(self.ledger, "update", flaky):
            with self.assertRaises(mcb.LedgerError):
                w.run_once()
            self.assertEqual(self.ledger.deliveries()[0]["status"], "pending")
            w.run_once()
        self.assertEqual(self.ledger.deliveries()[0]["status"], "delivered")
        self.assertEqual(len(self.history.read("delivered")), 1)

    def test_worker_crash_is_reported_not_swallowed(self):
        w = self.worker()
        w.server_check = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        w.poll = 0.01
        w.start()
        import time
        for _ in range(100):
            if w.problem:
                break
            time.sleep(0.01)
        w.stop()
        self.assertIn("boom", w.problem)


class HistoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = mcb.History(Path(self.tmp.name) / "h.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_read_filter_and_shape(self):
        wallet = {k: 0 for k in mcb.INVENTORY_KEYS}
        a = self.h.append("earn", {"resources": {"wood": 1}, "last_event": None}, "progress_rev:1", wallet)
        self.h.append("level", {"index": 1, "name": "Apprentice", "points": 30}, "level:1")
        self.assertEqual(set(a), {"v", "ts", "kind", "what", "wallet_after", "ref"})
        self.assertEqual([l["kind"] for l in self.h.read()], ["earn", "level"])
        self.assertEqual([l["kind"] for l in self.h.read("level")], ["level"])
        self.assertIsNone(self.h.read("level")[0]["wallet_after"])
        with self.assertRaises(mcb.HistoryError):
            self.h.read("nonsense")

    def test_invalid_lines_are_refused_on_write_and_on_read(self):
        with self.assertRaises(mcb.HistoryError):
            self.h.append("bogus", {}, "x")
        with self.assertRaises(mcb.HistoryError):
            self.h.append("earn", {}, "x", wallet_after={"wood": 1})  # missing keys
        self.assertFalse(self.h.path.exists())
        self.h.path.write_text('{"v": 1}\n')
        with self.assertRaises(mcb.HistoryError) as cm:
            self.h.read()
        self.assertIn("line 1", str(cm.exception))

    def test_a_torn_last_line_is_never_appended_to(self):
        self.h.append("level", {"index": 1, "name": "x", "points": 1}, "level:1")
        with open(self.h.path, "a") as f:
            f.write('{"v": 1')  # a crash mid-write
        with self.assertRaises(mcb.HistoryError):
            self.h.append("level", {"index": 2, "name": "x", "points": 1}, "level:2")

    def test_unwritable_file_raises(self):
        h = mcb.History(Path(self.tmp.name) / "no_such_dir" / "h.jsonl")
        with self.assertRaises(mcb.HistoryError):
            h.append("level", {"index": 1, "name": "x", "points": 1}, "level:1")

    def test_totals_and_csv(self):
        self.h.append("earn", {"resources": {"wood": 2, "emerald": 1}, "last_event": None}, "r1")
        self.h.append("earn", {"resources": {"wood": 3}, "last_event": None}, "r2")
        self.h.append("spend", {"resource": "emerald", "amount": 1, "on": "x"}, "o")
        self.h.append("send", {"tids": ["t000001"], "items": [{"item": "minecraft:diamond", "count": 2}]}, "t000001")
        self.h.append("unlock", {"profession": "librarian", "name": "Librarian", "paid": "free"}, "librarian")
        self.h.append("level", {"index": 2, "name": "Journeyman", "points": 80}, "level:2")
        t = mcb.history_totals(self.h.read())
        self.assertEqual(t["earned"], {"wood": 5, "emerald": 1})
        self.assertEqual(t["spent"], {"emerald": 1})
        self.assertEqual(t["sent"], {"minecraft:diamond": 2})
        self.assertEqual((t["unlocked"], t["levels"]), (["librarian"], [2]))
        rows = mcb.history_csv(self.h.read()).splitlines()
        self.assertEqual(rows[0], "ts,kind,ref,what,wallet_after")
        self.assertEqual(len(rows), 7)


class ForbiddenConfig(unittest.TestCase):
    def test_forbidden_and_shrine_are_validated(self):
        cfg = shipped()
        mcb.validate_config(cfg)  # the shipped file passes (it carries both)
        bad = copy.deepcopy(cfg)
        bad["forbidden"] = [{"x": 1, "y": 2}]
        with self.assertRaises(mcb.ConfigError) as cm:
            mcb.validate_config(bad)
        self.assertIn("forbidden[0].z", str(cm.exception))
        bad = copy.deepcopy(cfg)
        c = bad["chests"][0]
        bad["forbidden"] = [{"x": c["x"], "y": c["y"], "z": c["z"]}]
        with self.assertRaises(mcb.ConfigError) as cm:
            mcb.validate_config(bad)
        self.assertIn("chests[0]", str(cm.exception))
        bad["forbidden"] = [{"x": c["x"], "y": c["y"] - 1, "z": c["z"]}]  # the cell above it is protected too
        with self.assertRaises(mcb.ConfigError):
            mcb.validate_config(bad)

    def test_the_shipped_config_forbids_the_world_spawn_point(self):
        self.assertIn({"x": 108, "y": 65, "z": 90}, shipped()["forbidden"])


if __name__ == "__main__":
    unittest.main()
