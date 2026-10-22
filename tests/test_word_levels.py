"""Word content contract for the phonics ladder (docs/design.md "Phonics ladder"): every word in words.json and
craft_words.json fits the pattern of its level, the confusable-letter gate is computable, and every craft word has
a configured real item and a picture."""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ["cvc", "blend", "digraph", "silent_e", "vowel_team", "two_syllable"]
CONFUSABLE = "bdpqnumw"
VOWELS = "aeiou"
DIGRAPHS = ("sh", "ch", "th", "ck")
TEAMS = ("ai", "ay", "ee", "ea", "oa", "oo", "ow")


def confusables_in(word):
    """Same rule as rules.js confusablesIn: 'qu' counts as q."""
    return [c for c in word.lower().replace("qu", "q") if c in CONFUSABLE]


def eligible(word, active):
    """The confusable gate: a word is usable only when every confusable letter in it is active."""
    return all(c in active for c in confusables_in(word))


def _vowel_groups(w):
    return re.findall(r"[aeiouy]+", w)


def fits(word, pattern):
    """Simple rule check that `word` (any case) is a decodable example of `pattern` (lower patterns are allowed too
    for blends/digraphs only inside their own rule; each pattern is checked on its own rung)."""
    w = word.lower().replace("qu", "q")
    single = len(re.findall(r"[aeiou]", w)) == 1
    if pattern == "cvc":
        return re.fullmatch(r"[^aeiou][aeiou][^aeiouy]", w) is not None
    if pattern == "blend":
        return (single and w[-1] not in "aeiouy" and re.fullmatch(r"[^aeiou]{1,2}[aeiou][^aeiou]{1,3}", w) is not None
                and len(re.match(r"[^aeiou]*", w).group()) + len(re.search(r"[^aeiou]*$", w).group()) >= 3
                and not any(d in w for d in DIGRAPHS))
    if pattern == "digraph":
        return single and w[-1] not in "aeiouy" and any(d in w for d in DIGRAPHS)
    if pattern == "silent_e":
        return re.fullmatch(r"[^aeiou]+[aeiou][^aeiou]+e", w) is not None
    if pattern == "vowel_team":
        return any(t in w for t in TEAMS)
    if pattern == "two_syllable":
        # closed/simple syllables only: no r-controlled vowel, no consonant-le, no soft c (c before e/i/y), no y as a vowel
        if re.search(r"[aeiou]r|[^aeiouy]le$|c[eiy]|y", w):
            return False
        g = _vowel_groups(w)
        return len(g) == 2 and all(len(x) == 1 for x in g) and 5 <= len(w) <= 8
    raise AssertionError(pattern)


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class WordLevels(unittest.TestCase):
    def test_blocks_words_fit_their_level(self):
        d = load("app/data/words.json")
        self.assertEqual(d["v"], 2)
        seen = set()
        for i, w in enumerate(d["words"]):
            at = f"words.json[{i}] {w}"
            self.assertEqual(set(w), {"word", "focus", "level", "pattern"}, at)
            self.assertIn(w["pattern"], PATTERNS, at)
            self.assertEqual(w["level"], PATTERNS.index(w["pattern"]) + 1, at)
            self.assertRegex(w["word"], r"^[a-z]+$", at)
            self.assertNotIn(w["word"], seen, at)
            seen.add(w["word"])
            self.assertTrue(fits(w["word"], w["pattern"]), f"{at}: letters do not fit the pattern")
            self.assertIn(w["focus"], confusables_in(w["word"]), at)
            self.assertNotEqual(w["word"], "into", at)

    def test_blocks_has_twenty_per_level(self):
        words = load("app/data/words.json")["words"]
        for lv in range(1, 7):
            self.assertGreaterEqual(sum(w["level"] == lv for w in words), 20, f"level {lv}")

    def test_removed_words_are_absent_and_replacements_present(self):
        blocks = {w["word"] for w in load("app/data/words.json")["words"]}
        for gone in "bush push pencil candy muddy member number lumber winter zipper pepper hamster hundred turtle wire parrot".split():
            self.assertNotIn(gone, blocks, gone)
        craft = {w["word"] for w in load("app/data/craft_words.json")["words"]}
        items = load("config/minecraft.json")["craft_items"]
        for gone in ("WOLF", "TURTLE", "CANDLE", "PARROT"):
            self.assertNotIn(gone, craft, gone)
            self.assertNotIn(gone, items, gone)
        self.assertIn("mile", blocks)

    def test_level_six_is_closed_simple_syllables_only(self):
        """The doc rule, checked on every shipped level 6 word (fits() enforces it; this names the failure)."""
        bad = [w["word"] for f in ("words", "craft_words") for w in load(f"app/data/{f}.json")["words"]
               if w["level"] == 6 and re.search(r"[aeiou]r|[^aeiouy]le$|c[eiy]|y", w["word"].lower())]
        self.assertEqual(bad, [])

    def test_gate_is_computable(self):
        self.assertEqual(confusables_in("quit"), ["q"])
        self.assertEqual(confusables_in("frog"), [])
        self.assertTrue(eligible("frog", "bd"))
        self.assertFalse(eligible("squid", "bd"))
        self.assertTrue(eligible("squid", "bdpq"))
        self.assertFalse(eligible("plum", "bdp"))  # p, m, u need introducing
        for w in load("app/data/words.json")["words"]:
            self.assertTrue(eligible(w["word"], CONFUSABLE), w)

    def test_craft_words_fit_their_level(self):
        d = load("app/data/craft_words.json")
        self.assertEqual(d["v"], 2)
        seen = set()
        for i, w in enumerate(d["words"]):
            at = f"craft_words.json[{i}] {w}"
            self.assertEqual(set(w), {"word", "level", "pattern", "sprite"}, at)
            self.assertRegex(w["word"], r"^[A-Z]+$", at)
            self.assertNotIn(w["word"], seen, at)
            seen.add(w["word"])
            self.assertEqual(w["level"], PATTERNS.index(w["pattern"]) + 1, at)
            self.assertTrue(fits(w["word"], w["pattern"]), f"{at}: letters do not fit the pattern")
            self.assertIsInstance(eligible(w["word"], "bdpq"), bool)
        for lv in range(1, 7):
            n = sum(w["level"] == lv for w in d["words"])
            self.assertTrue(10 <= n <= 14, f"level {lv} has {n} craft words (want 10-14)")

    def test_every_craft_word_has_items(self):
        words = [w["word"] for w in load("app/data/craft_words.json")["words"]]
        items = load("config/minecraft.json")["craft_items"]
        for w in words:
            self.assertIn(w, items, f"{w} has no craft_items entry")
            self.assertTrue(all(e["item"].startswith("minecraft:") for e in items[w]), w)
        self.assertEqual(sorted(items), sorted(words), "craft_items has entries for words that are not craft words")

    def test_craft_sprites_resolve(self):
        """Every craft sprite is a drawn sprite or has a STAND_IN (resolveSprite), checked in node."""
        words = load("app/data/craft_words.json")["words"]
        js = ("import('./app/js/villagelogic.js').then(async v=>{const s=await import('./app/js/sprites.js');"
              "const bad=[];for(const n of JSON.parse(process.argv[1])){try{v.resolveSprite(n,s.SPRITE_NAMES)}catch(e){bad.push(n)}}"
              "console.log(JSON.stringify(bad))})")
        r = subprocess.run(["node", "-e", js, json.dumps([w["sprite"] for w in words])], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [], "craft sprites with no sprite or stand-in")


if __name__ == "__main__":
    unittest.main()
