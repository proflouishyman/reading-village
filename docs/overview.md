# Overview

A Minecraft-themed reading game kit for an early reader, played on the parent's computer with a grown-up beside the
child. Full contract: `docs/design.md`. How the parts fit together: `docs/architecture.md`.

In the docs, "the child" is whoever plays, and "Dad" is the example label of the grown-up corner. Both come from
`config/family.json` (child name, `home_grown_up`); your family's wording replaces them on screen. "Dad", "Mama" and the hero
(sprite id `hero`) are example characters in the shipped stories.

## Personalisation: `config/family.json`

The one file a parent edits to make the game theirs. Both `server.py` and the browser validate it at startup and refuse to
run on an unknown key, a wrong type or a missing required key, naming the field (loud failure, no defaults).
Shape and rules: `docs/family.md`. Beyond this file, a family changes stories
(`stories/`), word lists (`app/data/`) and, optionally, the Minecraft config. `SETUP.md` walks through it with Claude Code.

## What the game is

- Played on a computer in a browser with a grown-up beside the child, about ten minutes a day.
- The grown-up judges answers (no speech recognition): Got it / Let's try again buttons live in a small grown-up bar.
- Track 1: small caps (capital shapes at lowercase size). Track 2: lowercase, in parallel (off until the grown-up turns it on).
  Every story is read first in small caps, then lowercase. The method is Orton-Gillingham friendly: explicit, cumulative,
  one confusable pair at a time.
- Four mini games: Word Blocks and the Crafting Table (small caps, on Home from the start), and Letter Mine and Bridge Match
  (mirror-letter drills; lowercase-track drills, so they stay locked until the grown-up turns the lowercase track on).
- Every mini game has levels that rise by themselves (at least 10 tries at a level with 8 of the last 10 right unaided).
  Word Blocks and the Crafting Table climb a six-step phonics ladder (short vowels, blends, digraphs, silent e, vowel teams,
  two syllables); each new level earns a rare surprise. The dashboard shows them and Settings can override them.
- Theme: Minecraft. The hand-drawn pixel art is the default; an optional, local-only art mode draws real Minecraft textures
  from the parent's own install (never committed or shared; `docs/textures.md`).
- Reading earns emeralds, Village Bells and surprise treasure. The child unlocks villagers, buys Minecraft items, collects them
  in a Treasure Pile and chooses what to Send. Delivery into a real Minecraft world (a Magic Chest in a pagoda shrine, on a
  Paper server the family runs) is optional and off by default.
- Progress is saved locally in `data/` (gitignored) and shown on the grown-up dashboard. Saves are rev-checked, so the
  game and the dashboard can be open together without overwriting each other. Failures are loud (a banner, never a
  silent fallback), and nothing is granted, sent or delivered twice.
- Everything the child sees is Arial small caps by default; synthesized success-only sounds (mute in the grown-up bar).

## Systems
- `docs/architecture.md`: the map. Components, data ownership, key flows (reading turn, level-up, unlock, buy, Send and
  delivery, failures, reset, necklace, shrine install, real textures, mini-game levels), invariants, where to change things.
- `docs/minecraft-rewards.md`: The parent guide to the optional Minecraft side: what the child earns, the village, levels,
  the shrine, the necklace, daily routine, troubleshooting.
- `docs/textures.md`: the optional local real-texture art mode and its licensing rules.
- `docs/family.md`: the `config/family.json` contract (child name, village name, grown-up and away labels).
- `docs/design.md`: the contract: tracks, session flow, events, progress, API, stories, page art, the phonics
  ladder and levels, Crafting Table, village and delivery details, rewards history, install tool, data pack.
- `docs/away-from-home.md`: the contract for the optional away-from-home website copy, export and import;
  `docs/away-guide.md`: plain-language instructions for the helper at the other house.
- `SOLUTIONS.md`: the bug-fix log (root cause and fix). `CHANGELOG.md`: releases.

## Layout
- `server.py`: local stdlib server, JSON API and the delivery worker thread.
- `minecraft_bridge.py`: Minecraft config validation, village rules (points, level, bells), the delivery ledger and
  rewards history classes, the console transport (screen session + `logs/latest.log`) and the delivery worker.
- `config/`: `family.json` (personalisation, committed), `minecraft.json` (prices, levels, offers, surprises, chest spots,
  shrine; example values; delivery off by default), `web.json` (website publishing; off by default) and
  `private_overrides.json` (private values only; gitignored).
- `app/`: the game (`index.html`) and dashboard (`dashboard.html`); logic in `app/js/` (screens in
  `app/js/screens/`), editable word lists (phonics ladder), cues, swap order, craft words and level thresholds (`levels.json`)
  in `app/data/`. `app/assets/mc/` holds local real textures (gitignored).
- `stories/`: story JSON (source of truth) and `index.json`.
- `tools/`: `minecraft_install.py`, `shrine.py`, `shrine_blocks.json`, `shrine_render.py` (the shrine),
  `extract_mc_textures.py` (real textures), `render_pages.py` and `caption_pages.py` (story picture review),
  `datapacks/` (the Magic Necklace data pack), `publish_web.py` (away-from-home website).
- `data/`: The child's private record (gitignored): progress, events, deliveries ledger, rewards history, treasure
  counter, reset archives.
- `tests/`: `python3 -m unittest discover tests`, `node --test tests/js/`. The Python run includes Playwright UI tests.
