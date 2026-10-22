# Design: The Reading Village Game

Status: v1 built 2026-10-18; the village (villagers, Treasure Pile, Magic Chest shrine, Magic Necklace) added and
installed 2026-10-18/19; phonics-ladder levels for all four mini games, real mob pictures in real-texture mode and the
install tool's spawn-protection check added 2026-10-21. This is the contract the code is built against; see "Implementation decisions (v1)" at the
end for choices made during the build. `docs/architecture.md` is the map of the whole system (components, data
ownership, flows, invariants); this file holds the field-level contracts.

## Family config

`config/family.json` is the one place a parent personalises the game (child name, village name, grown-up label, away label).
The contract is in [family.md](family.md); `server.py` (`load_family_config`) and `app/js/family.js` (`loadFamily`) both enforce it.

## Who and how
- The reader is an early reader who decodes simple CVC words (pig, map) and is learning sight words and the phonics patterns in the ladder below. A parent sets the starting point (levels, tracks) in the game and on the dashboard.
- Mirrors **letters only** (not whole words): **b d p q**, **m w**, **n u**.
- The approach is **Orton-Gillingham** friendly → explicit, multisensory, cumulative, one confusable
  at a time, letter = sound, consistent verbal cues.
- Played on a **Mac** in a browser, **Dad sitting with them**. Dad judges every answer (no speech
  recognition). **~10 minute** sessions.
- Family only. Runs locally; no network, no accounts.

## Confidence rules (non-negotiable)
- No lives, no losing, no timers visible to the child, no red X, no "wrong" sound.
- A miss is recorded silently and the card comes back later. Dad's buttons are
  **"Got it!"** and **"Let's try again"** (shows the cue, then retry; a retry success counts as `assisted`).
- Every session ends on a success: the last card shown is one the child has mastered. That final "victory" card
  offers Dad only "Got it!" (no "Let's try again"), so it can never record a miss.
- Rewards are only ever gained, never lost.

## Two tracks
1. **Small caps track (fluency).** Text where every lowercase letter is shown as a capital shape at
   x-height (ᴘɪɢ style), true capitals stay full size. The child already knows these shapes, so this is
   reading-for-confidence with no mirror risk.
2. **Lowercase track (in parallel).** The same material in ordinary lowercase, plus letter drills on
   the confusable letters.

Every story is read in small caps first; the lowercase pass of a story is only offered once its small-caps pass is done, and only in the lowercase track.

### Small caps rendering
**Everything the child sees is Arial small caps** (Home, stage titles, story-picker titles, Back/Next/The end,
interludes, Build, the match prompt, reward text), in both tracks: in the lowercase track the chrome stays small
caps and only the reading material (cards, choices, cues, story text) changes. This goes through ONE helper,
`setKid` / the `kid` prop of `h()` in `app/js/ui.js` (built on `toSmallCaps`), never ad hoc per screen. The
Dad bar, `.dad-only` text, banners and `dashboard.html` are normal Arial. `tests/test_ui_smallcaps.py` walks the
DOM and fails on any a-z text outside those areas.

Do not rely on `font-variant: small-caps` (fonts synthesize it inconsistently). Render explicitly:
each lowercase char → `<span class="sc">UPPER</span>` with `.sc { font-size: 0.72em; }`; capitals,
digits and punctuation unchanged. One shared JS function `toSmallCaps(text) -> HTML string`, tested.

### Font
Default (F1) is a plain sans stack (`Arial, "Helvetica Neue", Helvetica, sans-serif`) for the game and dashboard; some children prefer another face, so the font is a Settings toggle. OpenDyslexic (npm
`open-dyslexic@1.0.3`; that release is Bitstream Vera–derived and states its licence in its README, copied
to `app/fonts/LICENSE-README.txt`) stays bundled locally in `app/fonts/` as an optional toggle
(`settings.font` is `"system"` (default) or `"opendyslexic"`; button reads "Font: plain (click for
OpenDyslexic)"). Large type: letters on cards ≥ 160px, story text ≥ 48px.

## Session flow (~10 min, Dad-led)
The reader should be fluent in small caps before lowercase work, so lowercase is a **separate track**,
off by default.

**"Start today's adventure" is always the small-caps adventure** (never any lowercase):
1. **Word Blocks** (~2 min): 10 words at their current level (phonics ladder, see "Levels"; level 1 is CVC words), each
   in **small caps only** (every word at the level is usable: the confusable-letter gate is lowercase-only, see "Levels"). Dad judges.
   Each correct word pays a block (wood/stone alternate). "Let's try again" shows **no letter cue** (the cues
   are lowercase): Dad's bar says "Sound it out together, then tap." instead.
2. **Story, small caps**: The child picks any story (a list; unread ones marked "next"). One sentence per
   page with pixel art. Clicking a word marks it "tricky" (logged, no visual penalty, tiny pickaxe icon
   for Dad). An unfinished story resumes at `resume_page`. First finish of a story's small-caps pass pays
   `earn.story_first_emerald` (5 shipped) emeralds; **re-reading a finished story pays `earn.story_replay_emerald`
   (2 shipped) emeralds** and changes no progress. Both rates are in `config/minecraft.json` (see "Who earns what").
3. **Build**: spend what was earned on placing blocks in the child & Dad's house. Build is the last stage of both
   adventures; it is no longer a Home tile (the village and Treasure Pile replaced it).

**Lowercase track** (`settings.lowercase_track` = `"on"`; Home then shows a "Lowercase track" button and a
separate "Plain lowercase story" button):
Swap-in story → Bridge Match → Letter Mine → Build.
- **Swap-in story**: pick any story whose small-caps pass is done. It is rendered at
  `settings.lowercase_percent` (below). It is a replay-style read: it starts at page 0, pays
  `earn.story_replay_emerald` emeralds, changes no story progress, and logs `swap_page` events per page (not
  `story_page`/`story_done`) and one `swap_done` event when the last page is finished. `swap_done` earns a replay
  surprise (see "Replay surprises" under "Villager shop and Magic Chest"); it is not a `story_done`, so it never counts as
  a first pass, a bell or reading points.
- **Plain lowercase story** (its own Home button): the old lowercase pass (first story with small caps
  done and lowercase not, else a re-read). Same emerald/replay rules as small caps (first pass 5 emeralds, replay 2).
- **Bridge Match and Letter Mine drill a mirror letter only when BOTH it and its partner (b/d, p/q, n/u, m/w)
  are swapped in** (replaces the old "swapped-in" gating: each Bridge Match round offers the pair side by
  side, so a half-swapped pair would be unfair). If no active letter qualifies, the stage is skipped with a calm
  "Not yet" screen and no error. This is a deliberate rule, not a fallback. The b/d → p → q → n/u → m/w
  introduction rule still decides which letters are active, and runs only while the track is on. With the
  shipped swap order the pairs complete at 20 letters (77%: n/u), 22 (85%: m/w), 24 (92%: p/q), 26 (100%: b/d).
- **Letter cues and the bed picture appear only here** (Letter Mine, Bridge Match), where lowercase is intended.
- **No finished small-caps story yet** (the swap-in or plain lowercase story has nothing to offer): The child sees a
  calm small-caps message "Read a story in small caps first!" and returns Home; Dad's bar explains why. This is a
  legitimate state, not an error screen.
While the track is off, Bridge Match and Letter Mine show as locked on Home with the note
"Lowercase comes later — Dad will open it." Dad turns the track on/off on the dashboard (confirm dialog
for "on"). The stage lists are `SMALLCAPS_ADVENTURE` and `LOWERCASE_TRACK` in `app/js/constants.js`; the two locked
stages are `LOWERCASE_STAGES` (`["match","mine"]`).

**Why Letter Mine and Bridge Match are lowercase-track drills.** They exist to train the mirror-prone letters (b d p q,
m w, n u), and those confusions are a property of the lowercase shapes: in small caps the letters are capitals the child already
knows, with no mirror risk, so there is nothing to drill there. Both stages show lowercase letters and the lowercase
cues, and the small-caps adventure never shows lowercase. So they are locked until Dad opens the lowercase track, and
they drill only letters that are swapped in (both a letter and its partner). Consequences: their levels (see "Levels")
only advance, and Dad's override for them only matters, once the track is on and a pair is swapped in; with no drilled
letter the stage shows the calm "Not yet" screen and logs nothing. The small-caps path has its own leveled mini games:
Word Blocks and the Crafting Table.

### Letter swap-in
`settings.lowercase_percent` (integer 0..100; Dad's dashboard slider counts **letters, 0 to 26**, one step = one
letter, and saves `lowercase_percent = round(n * 100 / 26)`; never advances automatically). The inverse is
`n = round(26 * percent / 100)`: every n from 0 to 26 round-trips, so each slider step adds exactly one letter
(`percentForCount` / `swapCount` in `app/js/swap.js`, tested). `app/data/swap_order.json` = `{"v":1,"order":[26 unique a-z letters]}` (strictly validated
on load; Dad can edit) sets the order lowercase letters replace small caps: safe distinct letters first,
mirror letters last, one pair at a time. N = round(26 × percent / 100); the first N letters render as plain
lowercase, every other lowercase letter as small caps, real capitals stay capitals. Deterministic, never
random: a letter looks the same everywhere. Pure functions: `toMixedCase` (`app/js/smallcaps.js`),
`swappedLetters` / `nextSwapLetter` / `drillLetters` (`app/js/swap.js`).

Stage descriptions:
- **Letter Mine** (~3 min): flashcards of target letters in lowercase. The child says the sound
  (and a key word). Dad taps Got it / Let's try again. Each card shows a mined ore on success.
- **Bridge Match** (~2 min): match small-caps letter to its lowercase twin (ʙ ↔ b), choosing
  between the target and its mirror partner (b vs d). Correct choice is the only thing that counts, a
  wrong click just wiggles gently and shows the cue.

### Sounds (F2)
Celebration sounds, synthesized with the Web Audio API in `app/js/sounds.js` (no audio files, works offline):
a short **pop** for an ore from a correct card (Letter Mine), a rising **3-note jingle** for a correct word
(Word Blocks), a **fanfare** (~1.5 s) for finishing a story (plus a **sparkle** when it pays an emerald), a soft
**thunk** when a block is placed in Build. **No background music and no sound at all for a miss or a "try
again".** Gentle: master gain 0.25, sine/triangle waves only. `settings.sound` is `"on"` | `"off"`; a missing
value reads as `"on"` (documented default). Dad mutes with a toggle in the Dad bar (every stage), the Home Dad
corner and the dashboard. If the AudioContext cannot start, one note appears in Dad's bar (once, counted); nothing
is thrown at the child.

A small Dad-only session clock in a corner (e.g. "7:40") — muted styling, not a countdown bar.
At 10:00 a gentle "Great mining today!" suggestion appears; Dad can keep going.

Each stage can also be launched on its own from the home screen (Story is the small-caps picker).

## OG letter cues (shown on "Let's try again", spoken by Dad)
- **b**: "**b**at then **b**all" — stick first, then the circle. Bed picture: the word *bed* — b is the
  headboard, d is the footboard.
- **d**: "**d**oughnut then **d**own" — circle first, then the stick. Bed picture.
- **p**: "**p**ush down, then the circle" — stick goes down below the line.
- **q**: "**q**ueen's circle first, then the tail down" — q is almost always with u.
- **m**: "**m**ountains — two humps on top." **w**: "**w**aves at the bottom — w is a valley."
- **n**: "**n**ose — one hump on top." **u**: "**u**p cup — open at the top, holds water."
These live in `app/data/cues.json` so Dad can edit them.

## Introduction order (cumulative, one confusable at a time)
Start with **b vs d** only. Add **p** when b and d are each ≥ 80% over the last 10 tries, then **q**,
then **n/u**, then **m/w**. "Mastered" letters keep appearing ~20% of the time for review. The
current active set and the rule are visible on the Dad dashboard and can be overridden there.

## Rewards (Minecraft flavor)
Reading pays in the currency of the village; the full rules are under "Villager shop and Magic Chest" and
`docs/minecraft-rewards.md`. In short:
- Letter card success → ore (coal → iron → gold → diamond as streaks build within a session).
- Word success (correct or helped) → wood/stone block **and** 1 emerald. First pass of a story → 5 emeralds, 1 Village
  Bell, 10 reading points and a surprise; a replay → 2 emeralds and a surprise that gets better with each replay (epic, then legendary). Each craft → 1 emerald and the real item. A new level in a mini game
  (Crafting Table, Word Blocks, Letter Mine, Bridge Match) → one rare surprise, once per game and level (see "Levels").
  (All emerald rates come from `config/minecraft.json` `earn`.)
- **the village** (Home tile): unlock villagers, buy real Minecraft items with emeralds, sell wood/stone/ore for
  emeralds. **Treasure Pile** (Home tile): everything the child has bought, crafted or been given; the child chooses what to Send to
  the Magic Chest in the real world. Nothing is sent automatically.
- **Build** (last stage of "Start today's adventure"): a pixel-grid house for the child & Dad; each earned block is placed
  by clicking a grid cell. The house persists between sessions and grows (walls → roof → door → torches → pig pen).
  Decorations unlock one per finished story pass and cost an emerald each.
- **Art.** Hand-drawn pixel art is the default (original, no Mojang assets, drawn from small char-grid arrays in
  `sprites.js`): The child, Dad, a pig, a green blocky "creeper", a bat, a hen, a fox, a duck, a stinky fish, a chest,
  torch, ores, blocks, villagers. An optional local-only **real-texture mode** (Settings, Art) draws real Minecraft
  textures from Dad's own install instead for villagers, items and blocks, plus 21 real mob pictures for the craft words
  (composed from the mob's entity texture in the jar and shown instead of a spawn egg); the extracted files are gitignored
  and never committed (`docs/textures.md`). Hand mode is unchanged. The child, Dad, the other mobs (creeper, duck, gold pig),
  story props and effects stay hand-drawn in both modes.

## Data and persistence
Local Python stdlib server (`server.py`, no dependencies) serves `app/` and a tiny JSON API.
Data lives in `data/` (gitignored — it is the child's private record).

### `data/events.jsonl` — append-only log, one JSON object per line
| field | type | req | notes |
|---|---|---|---|
| `v` | int | yes | schema version, `1` |
| `ts` | string | yes | ISO-8601 local time with offset |
| `session_id` | string | yes | set at session start |
| `type` | enum | yes | `session_start`, `session_end`, `card`, `match`, `word`, `story_page`, `swap_page`, `swap_done`, `story_done`, `tricky_word`, `block_placed`, `craft`, `adventure_done` |
| `level` | int 1..99 | optional on card/match/word/craft | the game level in force when the attempt was made (see "Levels"); missing counts as 1; above the game's `max` in `app/data/levels.json` is a 400 |
| `track` | enum | for card/word/story_*/craft | `smallcaps` or `lowercase` (`swap_page` and `swap_done` require `lowercase`; `craft` requires `smallcaps`) |
| `item` | string | for card/match/word/tricky_word/craft | the letter or word shown (`card`/`match`: one of the 8 drill letters b d p q m w n u; `craft`: the crafted word, 3 to 10 capital letters) |
| `result` | enum | for card/match/word/craft | `correct`, `assisted` (right after a retry/cue), `miss` (`craft` allows only `correct` or `assisted`) |
| `chosen` | string | match only | what the child clicked |
| `story_id` | string | story_* / swap_page / swap_done / tricky_word | |
| `page` | int | story_page / swap_page | 0-based |
| `percent` | int 0..100 | swap_page and swap_done (required), tricky_word (optional, set during swap-in) | `lowercase_percent` at the time |
| `cell` | [int,int] | block_placed | grid x,y |
| `block` | string | block_placed | block kind |
| `adventure` | enum | adventure_done | `smallcaps` or `lowercase`: which "Start today's adventure" sequence was finished |

### `data/progress.json` — current state (rewritten atomically: temp file + rename)
```json
{ "v": 1, "rev": 0,
  "active_letters": ["b","d"],
  "letter_stats": { "b": {"recent": ["correct","miss", "..."], "total_correct": 0, "total_tries": 0} },
  "inventory": { "coal": 0, "iron": 0, "gold": 0, "diamond": 0, "wood": 0, "stone": 0, "emerald": 0 },
  "house": [ {"x":0,"y":0,"block":"stone"} ],
  "stories": { "gold-pig": {"smallcaps_done": false, "lowercase_done": false, "resume_page": 0} },
  "settings": { "font": "system", "lowercase_track": "off", "lowercase_percent": 0, "sound": "on", "level_override": { "craft": 3 } },
  "crafted": { "PIG": 2 },
  "village": { "unlocked": ["librarian"], "bells_spent": 0, "emeralds_spent": 12, "levels": { "librarian": 1 } },
  "treasure": [ { "tid": "t000001", "label": "Name Tags", "sprite": "name_tag", "items": [{"item":"minecraft:name_tag","count":2}],
                 "source": {"kind":"shop","ref":"lib_nametag"}, "status": "kept" } ] }
```
`rev` is an integer >= 0 that the server bumps on every save (optimistic concurrency, below); a file without it
reads as `0` (documented default). `settings.sound` is `"on"` | `"off"`; a file without it reads as `"on"`. `settings.level_override` is optional, `{game: level}` (see "Levels"); missing = none.
`settings.lowercase_track` is `"off"` | `"on"` and `settings.lowercase_percent` an integer 0..100; both are
optional: a file without them reads as `"off"` / `0` (documented defaults); any other value is a 400. `crafted` is optional: an object `{WORD: count}` (key 3 to 10 capital letters, count integer >= 1); a file without it reads as `{}` (documented default), any other shape is a 400. `village` and `treasure` are optional and **server-owned** (see "Villager shop and Magic Chest"): missing reads as `{"unlocked":[],"bells_spent":0}` / `[]`; `PUT /api/progress` must carry them unchanged (400 otherwise). `village.emeralds_spent` (integer >= 0, total emeralds spent in this progress era) and `village.levels` (`{profession id: 0..top}`, only unlocked villagers, missing = Novice) are optional for older files; a fresh or just-reset progress carries `0` / `{}` explicitly (see "Villager promotions"). `recent` holds the last 10 results. If the file is missing on first run, the server creates the default.

### API
- `GET /api/progress` → progress.json, **validated first** (an invalid file is HTTP 500 with a clear message, never
  served); a missing `rev` is returned as `0`.
- `PUT /api/progress` → the body must carry `rev` (the rev it was based on; missing = 400). Compare-and-write under
  one lock: **409** if `rev` differs from the saved rev, otherwise validate, write atomically with `rev + 1`, and
  return the saved progress.
- `POST /api/event` → validate one event, append to events.jsonl
- `POST /api/reset` → archive progress and events, write fresh progress (see "Settings")
- `GET /api/events` → all events (for dashboard), each line validated with the same validator as POST. The first
  bad line is HTTP 500 naming its line number and field (e.g. `events.jsonl line 3: ts: is required`); nothing is
  skipped, and the dashboard shows it loudly.

Validation is strict on the server: unknown `type`, missing required field, wrong type → HTTP 400
with a message naming the field. **Never coerce, never default a bad field.**

### Concurrent saves (rev)
Game tab(s) and the dashboard can be open at once. Every client save goes through ONE queue (`app/js/savequeue.js`,
used by `store.js` in both pages), so a page never has two PUTs in flight. On a **409** the client GETs fresh
progress, **re-applies the same mutate function once**, and PUTs again. Re-applying is correct, not a fallback:
a mutation is a function of state ("add one wood", "set sound"), so applying it to newer state keeps the other
window's changes and ours. A second 409 in a row locks with the PROGRESS NOT SAVED banner. A mutate function may
return `SKIP` (`false`) meaning "nothing to do": nothing is saved or logged (Build uses this, checking the cell and
the block count against the state it is applied to, so a double-click places one block and logs one
`block_placed`). Progress is saved first, then the event, so a skipped mutation leaves no event behind.

### Loud failure
If any save fails (server down, 400, 500), the app shows a big unmissable banner to Dad:
"PROGRESS NOT SAVED — <reason>" and stops awarding until resolved. No silent localStorage fallback.
The server logs every 4xx/5xx to stderr. A corrupt `progress.json` makes the server refuse to start
with a clear message (it does not overwrite it).

## Settings
A "⚙ Settings" button sits in the Dad corner on Home and in the stage Dad bar (`app/js/screens/settings.js`).
From a stage it leaves the stage by the usual quit path, then Home shows Settings instead of itself. The screen is
Dad-facing normal text (inside `.dad-only`): Font, Sound and Lowercase-track toggles (the font and lowercase-track
buttons live in `settings.js` and Home reuses the font one; the dashboard keeps its own copies), a link to the dashboard,
a **Levels** block (one select per game: Automatic, or Dad's override level; see "Levels"), an **Art** row (see "Art mode" in docs/textures.md: hand-drawn or real Minecraft textures; "real" is offered only when
`app/assets/mc/manifest.json` is served, and the list of pictures that stay hand-drawn is shown with it), and
**Reset progress…**, which is enabled only after Dad types `RESET`.
- `POST /api/reset` with body exactly `{"confirm":"RESET"}` (anything else is 400). Under the write lock it MOVES
  `progress.json` and `events.jsonl` into `data/archive/<YYYYMMDD-HHMMSS>/` (a `-2`, `-3` suffix if that name exists),
  writes fresh default progress and returns `{"archived_to": "<path>"}`. Nothing is deleted; on a failure the moved
  files are put back and the answer is 500 with a message. The fresh progress carries `rev` = old rev + 1, so a
  second tab still holding the old state gets a 409 rather than overwriting the reset.
- The client ends the open session (so the archived log is complete), posts the reset, reloads progress through the
  store (`loadProgress`), and shows the archive path to Dad. No session is open afterwards: the next stage starts a new one.
- **Progress row (the child):** Word Blocks, Letter Mine and Bridge Match show one small block icon per card in the
  stage plus "n / total" (small caps). Done = filled, current = highlighted. A miss looks exactly like a success;
  a re-queued card adds a pip. The victory card is counted as the last pip up front; if the final card was a clean
  success there is no victory card and the row ends one pip shorter, all filled. `stageLayout(...).setProgress(done, total)`.

## Dad dashboard (`/dashboard.html`)
- Per letter: accuracy over last 10 / all time, trend per session, assisted vs independent.
- Which confusion pairs the child mixes up (from `match` events: target vs chosen).
- Tricky words list with counts. Stories finished per track. Session history with durations.
- **Small-caps fluency** panel: per small-caps story pass (per session and story) the date, pages, minutes
  (first to last page tap), seconds per page (minutes / (pages - 1); the time before the first tap is not
  logged), tricky-word taps and taps per 10 pages; plus Word Blocks small-caps accuracy over the last 20
  words (independent-correct share) with a per-session trend. No readiness threshold: Dad decides.
- **Letter swap-in** panel: letter slider (0 to 26, one letter per step; saved as a percent) with the exact lowercase letters and the
  next letter to come; swap-in fluency per percent (seconds per page, tricky taps per 10 pages).
- **Minecraft** panel (first, full width): delivery status, waiting and failed sends (table with the error), any problem,
  the village (reading points, bells, promotions earned/used/waiting with the emeralds spent, each villager's level) and the pile by state. A failed delivery, a server problem, a missing
  worker with sends waiting, or an unreachable endpoint is a RED banner (the panel turns red); it is never a quiet line.
  Also lists the item pictures that are still stand-ins (see Frontend below).
- **Rewards history** panel (second): totals (ever earned per resource, ever delivered per item, villagers unlocked, levels
  reached), the full chronological list (oldest first, scrollable, with the wallet after each line) and **Download CSV**
  (`/api/history.csv`). A history that cannot be read or fails validation is a RED banner, never a partial list.
- **Levels** panel: per mini game the level in force (`n of max`, with "Dad's override; earned k" when overridden), its name and the
  count toward the next level (see "Levels"). The override itself is set in Settings.
- Controls: turn the lowercase track on/off, change active letters, sound on/off, reset nothing destructive without a typed confirmation.

## Stories
`stories/<id>.json`, the source of truth for the app (served at `/stories/`):
```json
{ "v": 1, "id": "gold-pig", "title": "Sam and the Gold Pig", "subtitle": "A Minecraft Tale",
  "focus_letters": ["b","d"],
  "pages": [ {"text": "Sam had a map.", "art": "map"} ] }
```
`stories/index.json` is exactly `{"v":1,"stories":[ids]}`, in reading order (anything else is a loud error). `art` names a scene key the app knows how to draw
(unknown key → loud error on load, not a blank). Page text may use only ASCII letters a-z: any other letter
(é, ß, ﬁ ...) is a loud validation error. Curly quotes and apostrophes (‘ ’ “ ”), dashes and ellipses are not
letters and are allowed exactly as written (not normalised); the tricky-word tap treats ’ as '. A token with no
letter in it is shown but is not tappable.
Scene keys (`SCENE_KEYS` in `app/js/scenes.js`, 30): title map hill cave dark torch bat creeper run boom pool
wall chest hat king rock bed dig pup web sun night boat river house end hen fox duck fish. The last four
are animal scenes: `hen` (hen on the grass by a hut, the child watching), `fox` (fox on a log with a bun, Dad
pointing), `duck` (duck in a bathtub on a hilltop), `fish` (the child and Dad on the boat, a stinky fish on a line). Example stories star the hero and Dad, decodable CVC words +
early sight words, heavy on the focus letters.

### Composable page art
A page's `art` is either a scene key (string, above) or an object (composed in `app/js/scenes.js`, validated by
`checkArt`, which `validateStory` calls; an unknown name is a loud error naming story file, page and field, e.g.
`stories/x.json: pages[3].art.fx "laser" is not a known fx (known: ...)`):
```json
{"bg": "cave", "actors": [{"who": "hero", "x": 30, "pose": "run", "flip": false, "scale": 1}],
 "props": [{"what": "creeper", "x": 70, "y": "ground"}], "fx": "boom"}
```
- `bg` (required): grass hill cave dark_cave night river sea inside_house sandpit hilltop sunset pond wall sky. `sky` is open sky with a few clouds, no ground band and `ground` at the very bottom (106), for flying scenes: use `y:"ground"` for the broom and `sit_on` riders at scale about 0.85 so they are big.
- `actors` (optional list, drawn in order): `who` any sprite name in `sprites.js`; `x` 0-100 (percent of the width,
  so it means the same at any canvas size); optional `pose` (default stand), `flip` (mirror; default faces right),
  `scale` (multiplier of the sprite's default size, 0 < n <= 4, default 1).
- Poses: stand run jump sit fall upside_down hug hide sleep lying up in sit_on dig (the last five: see "Engine vocabulary"). They are canvas transforms of the existing sprite, not
  new art. `hug` needs exactly two (or an even number of) actors with pose hug: each pair is moved to meet at its
  midpoint. `hide` needs a ground prop: the actor moves to the nearest one's edge (half behind it) and the prop is
  drawn in front.
- `props` (optional list): `what` any sprite name; `x` 0-100; optional `y`: `ground` (default, feet on the floor),
  `air` (hanging near the top), `water` (floating; the bg must be river, sea or pond), `held` (in the hand of the
  nearest actor, on the side it faces; needs an actor), `head` (worn: sits ON the head of the nearest actor by `x`, overlapping it by a third of its own height, centred on
  heads that are off-centre (hen, pig, fox, duck, pup) and mirrored by `flip`; for Dad's `hat`, a `crown`, the Creeper or the hen; the
  actor must be upright: stand run jump sit hug hide, else a loud error). Example: `{"what": "hat", "x": 50, "y": "head"}`
  next to `{"who": "dad", "x": 50}`.
  Prop sprites added for this: hat mud hut bun sock rod pot map bow pan nut web raft log bell junk, plus `gold_pig` (pig, recoloured gold).
  More story sprites (any of them can be an actor or prop): chest_open pit bag rug bathtub steam catnip sand x_mark splash_big. `boat`, `web` (spider web) and `bun` (jam bun) were redrawn at their old sizes. `splash_big` is a sprite (a tall water crown); the `splash` fx is unchanged.
  **Forest, pirate and witch sprites (2026-10-21).** Characters (actors, scale 4, `HANDS` set): `pirate` (10x17, striped shirt, red bandana, eye patch, beard), `witch` (10x18, friendly neighbour: purple hat baked in, ginger hair, green dress). Animals: `owl bunny deer polly` (a parrot) `black_cat`. Props: scenery `pine berry_bush mushroom tent campfire` (with the existing `tree`, `log`); pirate `pirate_hat` (worn, `y:"head"`), `pirate_flag` and `flag` (held by the pole or on the ground), `spyglass` (held, raised to the eye), `plank`; witch `witch_hat` (worn), `broom` (held upright, or ridden: `sit_on` it), `flask` (potion bottle). Reused as they are: `cauldron`, `chest`, `chest_open`, `gold`, `map`, `boat`. All are hand-drawn (`unmapped`). `flag` is also the FLAG craft word's picture in both art modes.
- `fx` (optional): boom splash sneeze hiss sparkle mud_splat zzz stink tap. It needs at least one actor or prop.
  `sneeze` and `zzz` appear at the first actor's head; every other effect at the first prop, else the first actor.
  `boom` replaces that thing (the blast is drawn in its place and it is not drawn).
- Clipping guard: `artBoxes(art, width, height)` (`app/js/scenes.js`, pure) returns each drawn actor's, prop's and
  effect's (`kind: "fx"`, text included) bounding box (poses included, so a falling actor counts) and `clip`, the
  fraction of it outside the frame. `tools/render_pages.py` fails (non-zero, listing `story/page/element`) when any
  `clip` is above 5%. Scene-key art is not checked. Overlap guard: see "Engine vocabulary".
- **Engine vocabulary (E2).** All fields below are optional, validated strictly (unknown names, ids, relations and
  placements that cannot work throw `ArtError` naming story, page and field; `checkArt` also lays the art out once, so
  this happens when the story loads).
  - **References.** Actors and props may have `id` (lowercase letters, digits, `_`; unique in the art). Every field that
    points at another thing (`in`, `on`, `by`, `near`, `line_to`) takes an `id`, or a sprite name that is unique among
    the art's actors and props (two clouds need ids: an ambiguous name is a loud error).
  - **Actor fields:** `id`, `in` (the container prop, for pose `in`, or the `bed` for `lying`), `on` (what the child sits on,
    for `sit_on`). Each is an error on any other pose.
  - **Props:** `y` gains `"on"`; fields `id`, `by` (the actor holding/wearing it, for `held`/`head`; default the
    nearest actor by `x`), `on` (for `y: "on"`: a prop, or an actor's head), `angle` (degrees -180..180, held only),
    `scale` (0 < n <= 4), `line_to` (a held `rod` only: draws a line from the rod tip to the top of the target).
    - `held`: the prop is drawn IN the hand (the hand pixel of the sprite, through the pose), rotated about its grip,
      on the side the actor faces; a skin-coloured hand pixel is drawn over the grip. Tool angles (`TOOLS` in
      scenes.js): pickaxe 35 (digging: 100), torch 15, rod 0 (as drawn), pan -15 and mirrored so the handle is in the
      hand; other props are held by their centre. `angle` overrides. One held prop per actor (loud error otherwise).
      A rod with `line_to` is drawn without its baked hanging line.
    - `head` (worn), `on`: a sock on Dad's hat is `{"what":"hat","y":"head","id":"hat1"}` plus
      `{"what":"sock","y":"on","on":"hat1"}`; a crown on the pig is `{"what":"crown","y":"head","by":"pig"}` or
      `{"what":"crown","y":"on","on":"pig"}`. Several props per actor are fine (one hand, any number worn/stacked).
  - **Poses** (actor `pose`): `lying` (horizontal, head left; mirrored by flip; centred on x, lying on the ground; with
    `in: "bed"` the bed is drawn behind them, their head on the pillow, and the blanket in front from the shoulders on;
    the bed prop's x/scale decide where and how long: The child must fit), `up` (airborne: top of the actor 6px from the top
    of the frame, a ground shadow and streaks; fully inside the frame), `in` (needs `in`: the container prop, `ground`
    or `water`, e.g. pit, bathtub, boat, is drawn in FRONT of them and covers the lower part of their body; their `x` must be
    inside the container, a loud error gives the allowed x), `sit_on` (needs `on`: sits on the top of that actor or
    prop, both visible; `x` must be over it), `dig` (needs a held tool by them: leaned in, the tool angled down, dirt
    bits at its tip), `run` (existing; now with motion lines behind), `hug` (existing pair pose; the pair now overlaps
    by the arms only).
  - **`fx`** is now a name (as before), an object `{"fx": name, "near": ref, ...}`, or a list of either. `near` anchors
    any effect to the named thing (default as before). Text: `{"fx":"text","text":"QUACK!","near":"duck"}`; `text` is
    letters, digits, space and `! ? . , ' -` (<= 40 chars); optional `style` `burst` (default, a spiky yellow burst) or
    `say` (a white speech bubble with a tail to the speaker's head, wrapped at 100px); `side` `above` (default) | `left` |
    `right`; `size` 5-24 logical px (default 11 burst, 7 say; the engine may use a smaller size, see Text placement). It is drawn in bold Arial small caps (lowercase letters
    as capitals at 0.72, like the rest of the game) and the engine clamps it inside the frame. `sneeze` (ACHOO!) and
    `hiss` (HISS) now use the same lettering. A page with text draws its canvas at 4x (`HI_RES`) so the letters are
    crisp; other pages stay 192x108. The string `"text"` is an error (it needs the object form).
  - **Text placement (never over a head).** A `say` bubble or `text` burst (also the sneeze and hiss words) never covers
    an actor's head. The head box of each actor (`headRect` in scenes.js: `HEAD_BOX` / `HEAD` / `HEAD_ROWS`, through the
    pose, united with any worn hat or prop `on` the head) is avoided, the speaker's own and the neighbours'. Order, fully
    deterministic: the requested `side` (default above), above, above raised over a neighbour's head, the side with more
    room, the other side, the same sides below head level; if none is clear the size drops one step (to 5 for `say`, 6 for
    a burst) and all places are tried again. The tail points at the head box edge, never into the face. If nothing is clear
    at any size the least-covering place is drawn and the HEADCOVER guard fails it. A bubble may still cover a prop or a
    body: keep a key prop away from the bubble, or give it a `side`.
  - **Guards** (`tools/render_pages.py`, all exit non-zero listing `story/page/element`): HEADCOVER (`artBubbleHeadHits`
    in scenes.js) fails a bubble whose body overlaps an actor's head box by more than 0.5 logical px. CLIP covers actors, props
    and effects/text (a boom cloud counts; sparkle is clamped by the engine). OVERLAP (`artOverlaps(art, limit=0.2)`
    in scenes.js): two actors, or an actor and a non-held prop, whose boxes share more than 20% of the smaller box
    fail unless the art declares the relation: held, `head`, `on`, `in`, `sit_on`, lying in a bed, `hide`, `hug`. Prop
    against prop is not checked. A boom's target (not drawn) is not counted. A summary line gives pages failing per guard.
- `findRepeatedArt(story)` (`app/js/stories.js`) lists consecutive pages with identical art. It is an authoring
  check for the tools only; the app never calls it.
- Review tools (dev only): `python3 tools/render_pages.py STORY_ID [--out DIR]` starts the server on a free port with a
  temp data dir and renders every page at 800x450 via the dev-only `app/render.html?story=ID` (not linked from the
  game) to `DIR/<story>_<page:02d>.png` plus `DIR/<story>_pages.json` `[{page,text,png}]`.
  `python3 tools/caption_pages.py DIR STORY_ID` captions each PNG with local Ollama (`qwen3-vl:8b-instruct-q4_K_M`)
  from the picture alone (the model is never shown the sentence) into `DIR/<story>_captions.json`
  `[{page,text,caption}]`; one retry per image, then a FAILED banner and a non-zero exit. Compare caption to text to
  find pictures that do not match the story.

## Phonics ladder: word lists (content contract)
Six levels, each may also use any pattern from a lower level. `level` is always `1 + index of pattern` in the order below; a mismatch is a loud validation error.

| Level | `pattern` | Rule checked by `tests/test_word_levels.py` |
|---|---|---|
| 1 | `cvc` | consonant, one short vowel, consonant (`qu` counts as one consonant unit from level 1: QUIT, QUIZ) |
| 2 | `blend` | one vowel; an initial and/or final consonant cluster (CCVC / CVCC: FROG, NEST, MILK); no digraph. `-nk` (BANK, PINK) is treated as a blend here. SQUID stays at level 2 on purpose: it is s + the `qu` unit + id, an initial cluster (`qu` itself is allowed from level 1) |
| 3 | `digraph` | one vowel and one of sh, ch, th, ck (FISH, SHIP, DUCK, CHICK, BATH) |
| 4 | `silent_e` | consonant(s), one vowel, consonant(s), final e (CAKE, BONE, MULE, SLIME) |
| 5 | `vowel_team` | contains ai, ay, ee, ea, oa, oo or ow (GOAT, SHEEP, BOAT, BEE, SNOW). Level 5 includes **both** sounds of `ow` (snow / cow) and of `oo` (moon / book); the ladder does not separate them |
| 6 | `two_syllable` | exactly two syllables, single-letter vowel nuclei, **closed/simple syllables only**: no r-controlled vowel (so no TURTLE, PARROT, WINTER), no consonant-le (CANDLE), no soft c, no y as a vowel (CANDY). RABBIT, PANDA, ROCKET |

- **`app/data/words.json` (Word Blocks)** = `{"v":2,"words":[{"word","focus","level","pattern"}]}` (v2 replaced the bare v1 list; the four fields are all required, `word` lowercase, unique, never "into"). `focus` is a confusable letter in the word (the most recently introduced one: order b d p q n u m w). `focus` is `null` only for a word with no confusable letter: **the validator (`validateWords` in `data.js`) allows that and this doc now matches it**; the shipped list has none (words without any b/d/p/q/m/w/n/u are simply not in it, and `tests/test_word_levels.py` checks every shipped word has a confusable focus). The existing 92 words are level 1. The confusable gate (every b/d/p/q/m/w/n/u in the word must be active) applies only to LOWERCASE presentations (lowercase track, swap-in pages, Letter Mine, Bridge Match; `rules.js` `eligibleWords`). Word Blocks and the Crafting Table are small caps, whose shapes do not mirror, so they use every word at the level.
- **`app/data/craft_words.json` (Crafting Table)** = `{"v":2,"words":[{"word","level","pattern","sprite"}]}`; `word` is 3 to 7 capitals, unique, every word a real Minecraft thing so crafting delivers the real item; 10 to 14 words per level (at least 10, checked by test). **The craft grid has one slot per letter (not 3 wide).** `sprite` is a drawn sprite or a `STAND_IN` name (`villagelogic.js`; `resolveSprite`), so animals without hand-drawn art show the spawn egg.
- **`config/minecraft.json` `craft_items`** has an entry for every craft word (spawn eggs for animals). Each item id was checked on a copy of the server by inserting it into a test chest and reading it back (2026-10-21, Paper 26.3). `crab_spawn_egg` and `duck_spawn_egg` do not exist in 26.3, so CRAB and DUCK are not craft words. **Added 2026-10-21:** MAP, MUD, BLOCK and ROCKET use ids already present elsewhere in the config (`minecraft:map`, `minecraft:mud`, `minecraft:quartz_block`, `minecraft:firework_rocket`); **GOLD (`minecraft:gold_ingot`) and RAFT (`minecraft:bamboo_raft`) are new ids that have NOT been insert-tested** on the server copy yet. WOLF, TURTLE, CANDLE and PARROT were removed with their entries.

Craft words shipped (level: words):
- 1 (cvc): PIG BAT BED PUP HEN FOX SUN DAD MAP MUD
- 2 (blend): FROG SQUID PLANK FLINT SAND NEST MILK FLAG GOLD RAFT
- 3 (digraph): FISH SHIP CHEST STICK BRICK CLOCK SHELL PICK CHICK BLOCK
- 4 (silent_e): CAKE BONE MULE SLIME BLAZE STONE VINE GATE NOTE HIVE TUBE
- 5 (vowel_team): GOAT SHEEP BOAT BEE SNOW COW TREE COAL BOOK RAIL WOOL LEAF
- 6 (two_syllable): RABBIT PANDA CAMEL PIGLIN HOGLIN BUCKET PUMPKIN CACTUS HELMET ROCKET

Word Blocks words per level: 1: 92, 2: 52, 3: 54, 4: 51, 5: 60, 6: 29 (at least 20 each). See `app/data/words.json` for the lists.

## Levels (all four minigames)
Crafting Table, Word Blocks, Letter Mine and Bridge Match each have levels. A level is **derived from events, never
stored**: the same events always give the same level, so nothing can drift and a reset (which archives the events) starts
again at level 1.

**Rule** (`app/js/levels.js` `deriveLevels`/`step`, mirrored by `server.py` `derive_levels`; keep the two in sync).
Per game, level = 1 + the number of consecutive level-ups earned. Walk the game's events in order; an event counts only
when its `level` equals the current derived level (no `level` = 1). After each counted event, if there have been at least
`window` attempts at this level and at least `need` of the last `window` are `correct`, the level goes up and the count
restarts. `assisted` and `miss` are never independent. Never demotes. No level-up beyond `max`.
Event type to game: `craft` -> craft, `word` -> blocks, `card` -> mine, `match` -> match. Letter Mine and Bridge Match are
lowercase-track drills (locked until the lowercase track is on, see "Letter swap-in" above), so their levels start counting
only once Dad has opened that track.

**`app/data/levels.json`** (both client and server read it; validated strictly, any problem fails the page / server start):
`{"v":1,"games":{"craft":{"max":6,"window":10,"need":8},"blocks":{...},"mine":{...},"match":{...}}}`. All four games are
required, no other keys, integers >= 1, `need <= window`, `max` at most the number of levels the game defines. Shipped:
craft 6, blocks 6, mine 4, match 4 (all window 10, need 8).

**Events** `craft`, `word`, `card`, `match` gain an optional integer `level` (1..99 on any event; the server also rejects a
value above the game's `max`: 400 `level: must be at most N for type T (levels.json)`). The level is fixed at the START of a round (`roundLevel`), never re-read at attempt time, so a level-up in the middle of a round does
not retag the rest of it. Letter Mine and Bridge Match send the round's level (Dad's override if set, else the derived level).
Crafting Table and Word Blocks send each word's OWN level (`entry.level`), so a level-1 word mixed into a level-2 round carries
`level: 1` and never counts toward level 2: a level-up needs 8 of 10 independent answers on words AT that level
(`derive_levels` ignores events whose level is not the current derived level, so client and server agree). Old events without it count as level 1.

**Dad override**: `progress.settings.level_override` is optional, `{game: level}` with game one of `craft blocks mine match`
and level an integer 1..99 (server: and at most the game's `max`, 400 otherwise); missing = no override. The override wins for
what is shown and drilled; the derived level keeps counting on its own (events made under an override carry the overridden
level, or in craft/blocks the word's own level, and so count toward the derived level only when it equals it). Set it in Settings > Levels (one select per game; "Automatic" deletes the key).

**Level-up reward.** When an accepted event takes a game to a new level, the server creates one **rare** surprise treasure
(tier `rare` of `config/minecraft.json`; source kind `surprise`, `source.ref` = `minigame_level:<game>:<level>`), exactly once
per game and level ever (a ref already in the pile is skipped; a retried event finds its treasure by event key like every
other surprise). If several levels were reached at once (old data), each missing level gets its own. The history gets the
usual `treasure` line (no new history kind; the ref names the level). The `POST /api/event` reply gains optional
`game_level_ups: [{game, level}]`. The client queues them and shows, at the next calm moment, a
celebration screen "Crafting level 3!" ("Word Blocks", "Letter Mine", "Bridge Match") with the existing fanfare and "A
surprise is waiting in your Treasure Pile!". Data from before levels existed counts as level 1 events, so the first new event
can award the level that history already earned.

**On screen (the child, small caps).** Under the stage title: `Level 2: blends` and `7 of 8 right at level 2` (independent
answers among the last 10 at the derived level; `top level` at max; `level chosen by Dad` under an override). Updated after
every attempt (`stageLayout(...).setLevel(title, sub)`, `makeTracker` in `levels.js`).

**Craft and Word Blocks: which words.** Level 1: the least-practised level-1 words (all 5 craft words, all 10 Word Blocks
words). Level L > 1: **80% at level L and 20% review from level L-1** (`levels.js` `pickAtLevel`, `reviewCount`): craft 4 + 1
of 5, Word Blocks 8 + 2 of 10. Each group is least-practised first (craft: `progress.crafted` counts, ties in file order; blocks:
word events on file, ties random). The review words come from level L-1 only; if L-1 has too few they come from the next level
down. The round opens on a review word and, with two, closes on one. **No confusable-letter gate here:** Crafting Table and Word
Blocks are small caps, so every word at the level is usable and craft tray distractors may be any letter (the gate stays fully
in force for the lowercase track, swap-in pages, Letter Mine and Bridge Match). If level L has too few words the round is topped
up with easier ones and Dad's bar says so; if the list has nothing at or below the level the screen fails loudly. A level-up
counts only words AT the level (a review word counts toward its own level), so 8 of the last 10 takes about 2.5 rounds of 4.
Level names: 1 short vowel words, 2 blends, 3 digraphs, 4 silent e, 5 vowel teams, 6 two syllables.
The craft grid has one slot per letter (up to 10; slots shrink to fit the screen); the tray is the word plus 2 spare letters.

**Letter Mine levels** (cards judged by Dad as before; only the deck order changes; the cue, victory card and "Got it!"
rules are untouched). 1 *one letter at a time*: runs of three of the same letter. 2 *letters mixed*: the original
review-weighted mix. 3 *mirror pairs*: a letter and its mirror partner alternate (b d b d, then p q p q), only pairs with both
letters drilled. 4 *everything mixed*: every drilled letter shuffled, never the same twice in a row. Max 4.

**Bridge Match levels** (a wrong click still only wiggles and shows the cue; a miss stays silent). 1 *two choices, one letter
at a time*: target and its mirror partner, targets in runs of four. 2 *two choices, mixed*: the original deck. 3 *three
choices*: adds one other drilled letter. 4 *four choices*: adds two others, targets shuffled. The mirror partner is always among
the choices, extra choices come only from letters already drilled, and a drill set too small to fill the choices offers fewer
(never an undrilled letter). Max 4.

**Never**: timers, losing, loud misses, a demotion, or a level the child did not earn showing as earned.

**Dad dashboard**: a "Levels" panel, per game the level in force (`n of max`, with "Dad's override; earned k" when overridden),
what it is, and `x of 8 right (n tries at level L; needs 10)` or `top level`.

Tests: `tests/js/levels.test.mjs`, `tests/test_levels.py` (derivation, event field, override, once-only surprise, retry),
`tests/test_ui_levels.py` (Playwright: crafting levels up with fixture words, level line on every screen, Dad override,
dashboard panel).

## Crafting Table
A mini game (Home tile "Crafting Table", `app/js/screens/craft.js`; Dad's pick). The child sees a picture (an existing
sprite), Dad says the word, and the child taps small-caps letter blocks into a crafting grid (**variable length: one slot per letter of the word**, 3 to 7 shipped) in order. The tray
holds the word's letters plus 2 distractor letters (`CRAFT_DISTRACTORS`; **any letter**: small caps does not mirror, so
there is no confusable-letter gate), shuffled deterministically from the word's
index in `craft_words.json` (`trayFor(word, index)`; no `Math.random`; the first three blocks are never already in order).
- **No miss.** A wrong block wiggles in place (it never leaves the tray), with no sound and no colour. Each word then
  completes normally; the attempt is logged as `assisted` if any wrong block was tapped, else `correct`.
- **Craft!** The button is disabled until all slots are full, then glows. Pressing it (once; a double-click counts
  once) plays the existing jingle, pops the item sprite out, logs the event and adds the word to `progress.crafted`.
- **Round:** 5 words (`CRAFT_WORDS_PER_ROUND`) for the current level (see "Levels": `pickRound`, 4 at the level + 1 review from the level below, least-crafted first, no confusable gate), the usual
  progress row (`setProgress`), then a success screen ("You crafted five things!", the number word derived from the round length by `roundTitle`). Dad's Got it / Try again buttons are hidden.
- **Collection chest:** a button on the craft screen toggles a chest view: every craftable word, its sprite and count
  (`WORD xN`), or a "?" if not crafted yet, and "n / total" in the title.
- **Words:** `app/data/craft_words.json` (v2) and the phonics ladder, see "Phonics ladder: word lists" and "Levels". The grid has one slot
  per letter (`word.length`; 3 to 7 shipped, the validator allows 3 to 10; the CSS variable `--n` shrinks slots to fit the screen).
  `validateCraftWords` throws naming file, entry and field on anything else (an unknown sprite is a loud error, not a blank).
- **Event** `{type:"craft", item: WORD, result: "correct"|"assisted", track:"smallcaps", level?: int}`: the server requires
  these (item = 3 to 10 capitals; `miss` and `lowercase` are 400).
- **`progress.crafted`**: optional object `{WORD: count}` (count integer >= 1, key 3 to 10 capitals). A file without it reads
  as `{}` (documented default; `craftedOf` in craft.js). Any other shape is a 400.
- **Not in "Start today's adventure":** adding a stage there is not trivial (it lengthens the ~10 minute session and
  changes the interlude chain the tests walk), so it is a Home tile only. `SMALLCAPS_ADVENTURE` is unchanged.
- **Dashboard:** `craftStats(events)` in `stats.js` returns `{total, assisted, independentShare, words:[{word,n,assisted}]}`
  or `null`; the "Small-caps fluency" panel in `dashboard.js` shows a "Crafting" line (total crafts, share
  without help, most-crafted words), or "No crafting yet." when `null`.

## Villager shop and Magic Chest
Reading earns things in the real Minecraft world (the family's own Paper server). Rewards for kids/Dad:
`docs/minecraft-rewards.md`. Code: `minecraft_bridge.py` (config, village rules, ledger, transport, bridge, worker),
`server.py` (API, treasure creation), `tools/minecraft_install.py`, config `config/minecraft.json`.

**Flow.** The child earns emeralds, Village Bells and reading points -> unlocks villagers and buys items -> everything the child
gets (purchases, crafted creatures, surprise drops, mini-game level-up drops, villager kits) lands in the **Treasure Pile**
(`progress.treasure`, status `kept`) -> on the Send screen the child picks treasures -> `POST /api/treasure/send` creates one
delivery per tid -> the delivery worker puts it in the Magic Chest in the real world. Nothing is ever delivered
automatically; unsent treasure stays `kept` forever.

### Who earns what, and where (client vs server)
Inventory (`progress.inventory`) is **client-owned**: the game changes it inside its `commitUntilSaved` mutate
function and saves with `PUT /api/progress`, exactly like wood and ore. The server prices and checks everything that
spends it (shop, unlock). The client earns as follows (values come from `GET /api/village` `earn`, read once at boot by `loadVillageRates`):
| Where (app/js) | Earns (as built) |
|---|---|
| `screens/blocks.js` `record` (word, correct or assisted) | +1 wood/stone and `+earn.word_emerald` emerald (a miss earns nothing) |
| `screens/story.js` `advance` first pass | `+earn.story_first_emerald` (5) |
| `screens/story.js` `advance` replay (and swap-in reads) | `+earn.story_replay_emerald` (2) emeralds |
| `screens/craft.js` craft | `+earn.craft_emerald` emerald, in the same mutate as `crafted[WORD]` |
| `screens/mine.js` (lowercase cards) | ore, unchanged |
| `screens/build.js` | spends 1 wood/stone (or 1 emerald for a decoration) per block placed |
The server grants **no** emeralds itself (a second source would double count). Bells and reading points are never
stored: they are derived on every request from `events.jsonl` (+ `progress.active_letters`). Villager levels and the
emeralds-spent total ARE stored, server-owned (see "Villager promotions").

### Derived values
- **Reading points** = independent correct `word` events x `village.points.word` + first story passes x `story_first`
  + letters mastered x `letter_mastered`. A *first story pass* is a distinct (track, story_id) with a `story_done`
  event. *Letters mastered* = `len(active_letters)` minus the 2 starting letters (`INITIAL_LETTERS`). Assisted words,
  misses, cards and matches earn no points. Defaults 1 / 10 / 5.
- **Reading level** = highest `village.levels` index whose threshold is <= points (defaults Novice 0, Apprentice 30,
  Journeyman 80, Expert 160, Master 300). `next_at` is the next threshold, `null` at the top. Since 2026-10-21 this is
  informational only (Dad's dashboard): it no longer gates trades, earns no surprise and is not shown to the child.
- **Bells** earned = first story passes + points // `bell_every_points` (40); available = earned - `village.bells_spent`.

### Events the frontend must send
Unchanged: `craft`, `story_done` (first pass vs replay is decided by the server from earlier events), `word`, `card`,
`match`. **New:** `adventure_done` `{adventure: "smallcaps"|"lowercase"}` when the "Start today's adventure" sequence
finishes (once per session and adventure earns an `adventure_done` surprise). Surprises are decided by the server
when an accepted event arrives (`event_rewards` in server.py).
**Replay surprises.** Replay number N of a story is DERIVED from `events.jsonl` (never stored): `replay_count` in server.py
counts the earlier `story_done` events for that story whose track already had a `story_done` (the first pass of each track is
not a replay) plus every earlier `swap_done`, across tracks, and the new event is replay `count + 1`. With the shipped
`story_replay_tiers: ["epic", "legendary"]` replay 1 is epic and replay 2 and every later one is legendary (the last entry
repeats). The treasure's `source.ref` is `story_replay:<track>:<story_id>:replay<N>:<tier>` (`<track>` is `swap` for a swap-in
read), so the history line "Treasure: ... (surprise: ref)" shows the replay number and tier. A retry of the same event finds
its treasure by event key and creates nothing twice (the existing idempotency, see `event_key`); a swap-in read that logs
`swap_done` twice (two finished reads) is two replays. The swap-in client logs `swap_done` through the same commit as its
emeralds, exactly as `story_done` does.
| Event | Treasure created |
|---|---|
| `craft` | the word's real item (`craft_items`), sprite = the word's sprite |
| `story_done` first pass (first for its story + track) | surprise `story_first` |
| `story_done` replay, or `swap_done` (a finished letter swap-in read) | replay surprise: tier `surprises.story_replay_tiers[min(N-1, len-1)]` for replay number N of that story |
| `card`/`match`/`word` correct, 10th, 20th... independent correct in a row in one session (an assisted or miss breaks it) | surprise `streak10` |
| `adventure_done` | surprise `adventure_done` (once per session + adventure) |
| *(removed 2026-10-21)* the shared reading-points village level-up | no surprise any more; existing `level:<n>` treasure stays in the pile |
| `craft`/`word`/`card`/`match` after which that game's derived level is higher (see "Levels") | a **rare** surprise (`LEVEL_SURPRISE_TIER`), once per game and level, `source.ref == "minigame_level:<game>:<level>"` |
`POST /api/event` stays `{"ok": true}` and gains optional `"treasure": [{"label","sprite"}]` for newly created treasure
and `"game_level_ups": [{"game","level"}]` for mini-game levels. (`level_up` is gone; a client that still receives one throws.) Because the server bumps `rev` when it adds treasure, the
client's next save may get one 409 (the existing refetch-and-reapply handles it); a client may also GET `/api/progress`.
A reset archives the pile; treasure ids never restart: `next_tid` takes the next number from the persisted counter
`data/treasure_counter.json` (`{"v":1,"last":N}`, written before the id is handed out, untouched by a reset; a missing file
is seeded once from the pile, the ledger and every `data/archive/*/progress.json`; a corrupt one is a loud 500 and is never
overwritten), and keeps it above the pile and the ledger refs as well.
**Event retries are idempotent.** The treasure is saved before the event line is appended, so a failed append (500) can be
followed by the client's retry of the same event. Each treasure an event creates therefore carries the optional field
`event` = `"<events already on file>:<sha256[:16] of the event>"` (`event_key`); a retry finds its entries by that key,
creates nothing again, returns the same `treasure` extras and then appends the event line. Not covered: a retry
after the append succeeded (a lost response) is a new event; the client sends no event id.

### API
- `GET /api/village` -> `{"enabled","wallet":{inventory},"points","level":{"index","name","next_at"},
  "levels":{"names","thresholds"},"bells":{"earned","spent","available"},"promotions":{"earned","used","available","spent",
  "next_at"},"first_free":bool,"professions":[{"id","name","job_block_sprite","unlock_emeralds","requires":null|"all_professions",
  "unlocked","can_unlock","level":int,"level_name","can_promote":bool,"offers":[{"id","label","sprite","price","min_level",
  "items","locked"}]}],"trades":[{"id","give","get"}],"earn":{...},"rev"}`.
  `level`/`levels.thresholds` are the old reading level (informational, see "Derived values"); `levels.names` names the
  villager levels. `locked` = THAT villager's `level` is below `min_level` ("Reach Apprentice!"); `can_unlock` = not yet
  unlocked and its requirement met (the Wandering Trader needs all 13 others). `level`/`level_name` are 0/"Novice" for a
  villager who is not unlocked; `can_promote` = unlocked, below the top level and `promotions.available > 0`.
- `POST /api/village/unlock {"profession","pay":"bell"|"emeralds"}` -> 200 `{"village":<GET shape>,"wallet","treasure":<entry>,"rev"}`.
  The first unlock is free whatever `pay` is. Later: `bell` needs one available bell (adds 1 to `bells_spent`),
  `emeralds` costs `unlock_emeralds`. 400 bad body / unknown / already unlocked; 409 no bell, not enough emeralds,
  trader requirement unmet. Treasure: villager spawn egg + job-site block (trader: wandering trader egg + 2 trader llama eggs).
- `POST /api/shop/buy {"offer_id"}` -> 200 `{"wallet","treasure":<entry>,"rev"}`; 400 unknown offer or extra fields;
  409 villager not unlocked, THAT villager's level too low, or not enough emeralds. Wallet, treasure and the
  emeralds-spent counter are saved in one write.
- `POST /api/village/promote {"profession"}` -> 200 `{"village":<GET shape>,"wallet","profession":{"id","name","level",
  "level_name"},"rev"}` (the new level). 400 bad body or unknown profession; 409 villager not unlocked, already at the top
  level (Master), or no promotion available. Checked and saved under the write lock: a double tap earns one promotion.
- `POST /api/shop/trade {"trade_id"}` -> 200 `{"wallet","rev"}` (sell resources for emeralds); 400 / 409 as above.
- `GET /api/treasure` -> `{"treasure":[{tid,label,sprite,items,source,status,"state","delivery"}],"enabled","server_running","problem","rev"}`.
  `state`: `kept` | `on_the_way` (delivery pending) | `in_chest` | `failed`; `delivery` = `{id,status,attempts,last_error,delivered_ts,chest}` or null.
- `POST /api/treasure/send {"tids":[...]}` -> 200 `{"treasure":[...with state],"deliveries":[...],"rev"}`. 400 bad body
  / repeated / unknown tid; 409 any tid already sent or delivery disabled. Nothing changes unless every tid is valid.
  All tids are marked `sent` in one progress write, then one delivery per tid is created (ledger `source.ref` = tid,
  `source.kind` = the treasure's kind: shop|surprise|craft|unlock). If creating a delivery fails the marks are rolled
  back; if that fails too the error says so. A tid with a delivery can never get a second one (the ledger refuses).
  At startup a tid marked `sent` without a delivery (crash between the two writes) gets its delivery and a RECOVERED line.
- `GET /api/minecraft` -> `{"enabled","worker_running","server_running","pending","failed","recent"(last 10 delivered),"chests","problem"}`.
  `problem` is e.g. "All Magic Chests are full" or "d000012 FAILED: ...". `worker_running` is false for a temp `--data-dir`.
- `PUT /api/progress` rejects (400) a body whose `village` or `treasure` differs from the stored value (checked after the rev check, so a stale save is still a 409). A PUT may carry one optional extra field, `cause` = the full event the save belongs to (validated like `POST /api/event`, a bad one is a 400, never stored in progress.json); `savequeue.js` sends the event it is about to post, because progress is saved BEFORE the event. When a save RAISES a resource (the client grants wood/stone/emeralds itself) the server writes an `earn` history line first, and one `spend` line per resource it LOWERS (building spends wood/stone/emeralds) (see "Rewards history"). The client builds the event ONCE per commit: a retry after a failed save re-posts the identical event, so its idempotency key (event_key) matches.
- `GET /api/history[?kind=K]`, `GET /api/history.csv[?kind=K]`: see "Rewards history".
- Spending emeralds is a deliberate exception to "rewards are only ever gained".

### Villager promotions
Villager levels are **per villager** and keyed to **emeralds spent**, never to reading. Novice, Apprentice, Journeyman,
Expert, Master (`village.levels.names`; `min_level` of an offer is an index into them). The child earns a **promotion**
each time their total emeralds spent crosses a threshold and **chooses** which one villager moves up one level; the server
never promotes anyone by itself and never promotes every villager.
- **Ladder** (`village.promotions`, validated: thresholds strictly increase): `earned = #thresholds reached`, plus one more per
  `then_every` emeralds beyond the last threshold. Shipped `spent_thresholds [10,25,45,70,100]`, `then_every 40`, so 54 spent = 3
  earned, 100 = 5, 140 = 6, 180 = 7. `next_at` is the spent total where the next one lands (the ladder never ends).
  `available = earned - used`, `used = sum(progress.village.levels)`. `used > earned` is corrupt data: `GET /api/village` is a 500.
- **Spent total** = `progress.village.emeralds_spent`, a **server-owned counter** incremented in the SAME atomic progress
  write as the wallet change, by shop buys (`offer.price`) and emerald unlocks (`unlock_emeralds`); bell unlocks and sells spend
  no emeralds, and the first unlock is free. Why a counter and not a sum over `rewards_history.jsonl`: the history is
  append-only across resets and a history line is written BEFORE the progress save, so a failed save would leave a spend line
  for emeralds never taken; the counter cannot disagree with the wallet, "Reset progress" zeroes it for free (the fresh
  progress carries `emeralds_spent: 0`, `levels: {}`), and it is idempotent (a refused buy changes nothing). The client
  never sends it (a PUT that changes `village` is a 400).
- **Older files** (no `emeralds_spent`): derived ONCE from the history: the sum of `spend` lines with `resource: emerald` whose
  `ts` is at or after the newest `data/archive/<YYYYMMDD-HHMMSS>` stamp (the last reset, local time; no archive = all), then the
  next spend or promotion writes the counter back. For example, 54 emeralds spent gives 3 promotions, all available. Unlocked villagers with no `levels` entry are Novice.
- **Gating**: `shop_buy` compares `offer.min_level` with THAT villager's level (409 "needs the Armorer to be Journeyman ...").
  Reading points still give bells (bells still unlock villagers) but no longer gate anything.
- **Removed**: the shared village level-up surprise (`level:<n>` treasure, the `level_up` event extra, the "Your village is now
  ..." celebration, new `level` history lines). Existing treasure and history lines stay.
- Tests: `tests/test_promotions.py` (ladder math, counter, promote 200/400/409, double tap, per-villager gating, reset, history
  line + CSV, older-file derivation, corrupt data), `tests/js/villagelogic.test.mjs`, `tests/js/historylogic.test.mjs`,
  `tests/test_ui_village.py` `Promotions` (picker, confirm, celebration; `VILLAGE_SHOTS=<dir>` saves screenshots).

### Config: `config/minecraft.json` (strict; any unknown key, bad id, bad sprite, bad level is a startup error naming the field)
`{v:1, enabled, mc_dir, screen_session, player, chests:[{x,y,z}...], forbidden?:[{x,y,z}...], shrine?:{x,y,z}, earn:{word_emerald, story_first_emerald,
story_replay_emerald, craft_emerald}, trades:[{id,give,get}], craft_items:{WORD:[items]}, tiers:{name:[{weight,label,sprite,items}]},
surprises:{story_first,streak10,adventure_done,level_up: tier name; story_replay_tiers: [tier name, ...] (non-empty; replay N uses entry min(N-1, len-1))},
village:{levels:{names,thresholds}, points:{word,story_first,letter_mastered}, bell_every_points,
promotions:{spent_thresholds:[int >= 1, strictly increasing, non-empty], then_every:int >= 1},
professions:[{id,name,job_block_sprite,unlock_emeralds,job_block_item | unlock_items,requires?,offers:[{id,label,sprite,price,min_level,items}]}]}}`.
`forbidden` (optional, default `[]`): cells nothing is ever built or decorated on, each also protecting the cell above it; the
shipped config lists an example forbidden point `108 65 90` (the bridge never decorates or places a chest there; the install tool
also refuses unless the spawn read from `level.dat` is listed). `shrine` (optional): the cell of chest 1 the shrine is built
around; `chests` must then be exactly the shrine's chest spots (`tools/shrine.py --chests` prints them; the install tool and
`tests/test_shrine.py` check it). A chest on a forbidden cell is a config error.
Item entry: `{item:"minecraft:x", count?(1..64), enchantments?, stored_enchantments?, profile? (player_head), potion? (potion/tipped_arrow items)}`.
Shipped: the 13 professions (librarian, armorer, weaponsmith, toolsmith, farmer, fletcher, cleric, cartographer,
shepherd, butcher, fisherman, mason, leatherworker) and `wandering_trader` (`requires: all_professions`, `unlock_items`);
188 offers, enchanted books only at the librarian. The committed `player` is a placeholder: the real gamertag goes in
the gitignored `config/private_overrides.json` (`{"player": "..."}`; only `player` may be overridden). The worker
delivers by coordinates and does not use it today. Edit and restart; sprites must come from `ITEM_SPRITES` /
`JOB_BLOCK_SPRITES` in minecraft_bridge.py (the frontend draws that vocabulary).

### Delivery ledger: `data/minecraft_deliveries.json`
`{"v":1,"deliveries":[{id:"d000001", created_ts, source:{kind,ref}, label, items, status:"pending"|"delivered"|"failed",
attempts, last_error, delivered_ts, chest:{x,y,z}|null, inserted?, baseline?, confirmed?, pending?}]}`. Never deleted; atomic writes; validated on
every read (a bad file raises and is never overwritten). `inserted` (optional, default 0) = how many *expanded* item
entries are already confirmed in the chest (resume point). `baseline` (optional, absent on old entries) =
`{slots, totals:{item id: count}, raw}`, the chest's contents as read BEFORE the delivery's first attempt; it is saved
together with `chest` and is the starting point of every read-back of that delivery, however many retries it takes.
`confirmed` (optional; absent = each inserted entry counts as its own count) = list of the `Dropped N` counts the game printed for
the confirmed entries, exactly `inserted` long. `pending` (optional, null when none) = `{index, mark:[log inode, byte offset]}`: the
one insert that was sent and not yet confirmed, and where in `logs/latest.log` its reply would appear; written BEFORE the command is sent.

### Delivery worker (thread; `--minecraft-worker auto|on|off`, auto = real data dir only)
Transport: console commands through the screen session (like `mc.sh cmd`); every reply is read from NEW lines of
`<mc_dir>/logs/latest.log` ("System chat: ..."). No RCON. Poll 15 s, one delivery at a time, oldest first.
Per delivery: forceload the chunk; chest 1.. in config order: a Magic Chest (CustomName starts "Magic Chest") with
free slots >= slots needed is used; a free spot (air or loose plants, no fluid, solid ground below) gets the next chest
("Magic Chest 2", decorated, labelled); none left -> stays pending, `problem` = "All Magic Chests are full" (no
attempt counted). Each item is one inline `loot insert`; the reply must be exactly "Dropped N [Item]"/"Dropped N items"
(N = wanted; "Dropped 0 items" = chest full, loot discarded), then the chest is **read back** and ids, counts,
enchantments, potions and profiles must have grown by exactly what was sent. Only then `delivered` (+ particles and the
level-up sound at the chest). **Retries reconcile, never re-insert blindly:** a `Dropped` reply that arrives after the 8 s
timeout leaves the insert in the chest but `inserted` not advanced. The retry reconciles the ONE pending insert against the
delivery's own records, not against the chest baseline alone: `delta` = what the chest gained since `baseline` minus the
`confirmed` counts, and "reply" = a `Dropped <count>` line in the log after `pending.mark`. Only two cases are clear: no delta
and no reply (it never landed: insert it) and delta exactly the pending entry plus a reply (it landed: counted, evidence line
"reconciled by read-back and log"). Everything else (the child took items out, put a matching item in, a reply but no items,
items but no reply, a partial drop, a rotated log) is ambiguous: `VerifyError` with the evidence (delta, reply, chest contents),
NOTHING is inserted, and the delivery is marked failed loudly rather than silently short or doubled. The final read-back always runs against the
baseline (also when nothing was left to insert), so a duplicate or a missing item is a loud `VerifyError`. An old entry with
inserted items but no baseline fails loudly (check that chest by hand). Server off -> pending, not an error ("waiting for
Minecraft"); one grace pass after the worker first sees the server up, whether it was down before or its state was still
unknown (the world may still be loading). The worker writes the `delivered` / `delivery_failed` history line BEFORE it
changes the ledger entry; if that write fails the entry stays pending and the next pass reconciles (nothing is inserted
twice). The write is idempotent per delivery: a `delivered` line (or a `delivery_failed` line with the same error) already on
file is not written again, so a ledger write that failed after the line cannot produce a duplicate. Other failure: one retry, then `failed` with the raw evidence in
`last_error`; a read-back mismatch fails at once (never retried: items may already be in the chest).
**Inline loot table, not a datapack** (decided by testing on the Paper 26.3 copy): inline tables work for plain items,
enchantments, stored enchantments, potions and player heads, and bad input is refused loudly ("Failed to parse
structure"), so a datapack would need files, /reload and a pack format to track for no gain. They need the 26.x schema
(`modifier`/`type`; the old `functions`/`function` is accepted and silently ignored - hence the read-back).
Facts found live: unstackable items (potions, cake, rabbit stew, buckets, writable book: `UNSTACKABLE`) reply "Dropped N
items" and take N slots; and a stack of N>1 loses its components when split (3 potions came out plain), so each is
inserted as its own `loot insert` (`expand_items`).

### Frontend: The village, shop, Treasure Pile (`app/js`)
- **Home**: the Build tile is replaced by **the village** and **Treasure Pile** tiles (Build stays as the last stage of
  "Start today's adventure"; the code and its tests stay). Village and Pile open **no session** (browsing is not reading).
  The Dad corner shows the Minecraft status (`mcstatus.js`, plain text, red when something needs Dad).
- **Earning** (rates read once at boot from `GET /api/village` `earn` via `loadVillageRates`; a missing rate throws, never
  guessed): `blocks.js` word (correct or assisted) +wood/stone **and** +`word_emerald`; `story.js` first pass
  +`story_first_emerald`, replay +`story_replay_emerald` (emerald, no longer wood); `craft.js` +`craft_emerald` in the same
  save as `crafted[WORD]`. `STORY_PASS_REWARD`/`REPLAY_REWARD` are gone. After `adventure_done` events: `runSequence` sends
  `{type:"adventure_done", adventure:"smallcaps"|"lowercase"}` once the last stage is done.
- **Event replies**: `savequeue.js` passes every accepted event's reply to `onEvent` (`surprise.js`): new `treasure` shows
  the "A surprise for your Treasure Pile!" toast (never blocks) and the client refreshes progress (the server bumped rev);
  `game_level_ups` are queued and celebrated at the next calm moment (between stages, after the adventure, on Home).
  A malformed reply, or a `level_up` (gone), throws. The client never writes `progress.village` / `treasure`:
  after every server-side change (unlock, buy, sell, send) it reloads progress with `loadProgress`.
- **Village screen** (`screens/village.js`): "Spend N more emeralds for a promotion" + bells + emeralds; a yellow
  **Promotion ready!** banner (x available) when `promotions.available > 0` and some villager can be promoted; their villagers
  at their job-site blocks, each with ITS OWN level badge and name; a "?" plot (with the job-site block and the name) for each villager the child can unlock; the Wandering
  Trader as a locked silhouette "Unlock every villager to meet me!" until all 13 are unlocked; "Sell to the village" and
  "Treasure Pile" (red number = unsent treasure). **Unlock picker**: tapping a "?" shows who it is; the first is free
  (one big button), later the child chooses **a bell** or **emeralds** (dim and disabled when the child cannot, never scolded).
  **Villager screen**: the villager's own level badge; offers as picture cards with price; not enough emeralds = dimmed,
  villager level too low = greyed with "Reach Apprentice!" (that villager's level names); a tap opens a Buy!/Not now confirm (a 6-year-old must not spend by accident); the server prices
  everything. **Sell stall**: one tap per trade.
- **Treasure Pile + Send** (`screens/treasure.js`): every treasure as a card (picture, label, x count). The child taps cards to
  choose (Choose all / none, "n chosen"); **Send!** first POSTs `/api/treasure/send`, and only after the server accepted it
  the portal scene plays (items fly in one by one, sparkles, sound) and ends "Sent to your Magic Chest!". A refused send is
  a red **SEND FAILED** overlay and never the success text. Sent treasure moves to "Already sent" with "on the way" ->
  "in your chest" (polled every 4 s) or "Dad is checking" (failed). With Minecraft off, sends stay "on the way".
- **No double sends**: every POSTing button on the Village screen goes through `act` (village.js): a synchronous `busy`
  flag ignores any further tap, and every button on the screen is disabled until the request resolves and the screen
  re-renders. The Send! button has the same guard (`sending`). One tap pair = one request (tests: `DoubleTap`).
- **Promotion flow**: the banner opens a picker of the villagers who can be promoted (unlocked, below Master; each shows
  "Novice -> Apprentice"); tapping one asks "Make the Armorer Apprentice?" (Yes! / Not now); Yes POSTs `/api/village/promote`
  (through `act`, so a double tap is one request), plays the fanfare and shows "The Armorer is now Apprentice!" with
  "New trades!" (pictures of the offers that level opened) and "See what they sell" / "Back to the village". The reply is
  validated (`validatePromoteReply`, and it must agree with the village it carries).
- **Level badges** come from the server: `badgesFor(levels.names)` gives one badge sprite per level name
  (`LEVEL_BADGE`: novice/apprentice/journeyman/expert/master). A level without a badge is a loud error at validation, not a
  blank icon; the number of levels is the server's, not the client's.
- **Treasure Book** (`screens/book.js`, from the "Treasure Book" button on the pile): everything the child has ever earned and
  sent, newest first, small caps with pictures (a row per earn / treasure / unlock / level / promote / send / delivered line; spend,
  trade and failures are Dad's and are not shown), 60 rows at a time with "Show more". It reads `GET /api/history`.
- **Rewards history contract (frontend)**: `GET /api/history` (optional `?kind=`) is `{v:1, kind:null|string, count, lines,
  totals}`: `lines` = the lines of `data/rewards_history.jsonl`, oldest first (filtered by `kind`), `count` = their number,
  `totals` = `{earned, spent, sent, delivered, unlocked:[ids], levels:[indexes]}` over the whole file. Each line is
  `{v:1, ts, kind, what, wallet_after:{...}|null, ref}`. `historylogic.js` validates the reply and every line (unknown
  fields, an unknown kind, a count that does not match, a missing `what` field all throw naming the field; tests
  `tests/js/historylogic.test.mjs`). The `what` fields the client reads: earn `{resources:{res:n}, last_event|null}`, spend
  `{resource, amount, on}`, trade `{trade_id, give, get}`, treasure `{tid,label,items,source:{kind,ref}}`, unlock
  `{profession,name,paid:free|bell|emeralds}`, level `{index,name,points}`, promote `{profession,name,from_level,level,
  level_name,spent}`, send `{tids,items}`, delivered
  `{delivery,tid,label,items,chest:{x,y,z},log:[string]}`, delivery_failed `{delivery,tid,error}`. `GET /api/history.csv`
  is linked from the dashboard, not parsed.
- **Treasure Book pictures**: treasure/send/delivered lines carry no sprite, so a picture is the pile entry's sprite for
  that tid (`GET /api/treasure`), else the sprite named like the first item (`minecraft:diamond` -> `diamond`), else a chest
  placeholder. Placeholders are counted and shown to Dad on the book page (a reset archives the pile, so old tids are
  legitimately missing from it); they are never silent.
- **Art mode**: `main.js` calls `configureTextures` at boot with Dad's saved art mode (localStorage `reading_village_art_mode`,
  `hand` default); `sprites.js` draws mapped sprites from real textures in `real` mode (docs/textures.md), including the 21 mob
  pictures of the craft words (`mobs/<mob>.png`, drawn in the 12x12 sprite-pixel box of the spawn egg they replace). `chick` and
  `blaze` are their own sprite ids (stand-ins `hen` and `torch` in `STAND_IN`), so hand mode draws exactly what it did.
- **Sprites**: `villagelogic.js` `resolveSprite`: a server sprite name is drawn by its own sprite, else by an explicit
  `STAND_IN` (documented, counted, listed on the dashboard), else it throws. `sprites.js` lacks 48 names of the server
  vocabulary (counted from the shipped config on 2026-10-19; the dashboard lists the live set) (sword, helmet, bread, coral, ...), so those use stand-ins until real art is drawn; a test fails when a
  stand-in's name gets its own sprite (remove it then).
- **Boundaries**: every GET reply (`/api/village`, `/api/treasure`, the event extras, `/api/minecraft`) is validated in
  `villagelogic.js` / `mcstatus.js` and throws naming the field. Failures in a village action show the loud overlay.
- Tests: `tests/js/villagelogic.test.mjs`, `historylogic.test.mjs`, `savequeue.test.mjs` (onEvent), `tests/test_ui_village.py`.

### Rewards history: `data/rewards_history.jsonl`
Append-only master list of everything earned, spent and sent. Never rewritten, trimmed or moved: "Reset progress" archives
`progress.json` and `events.jsonl` only, and the new life continues the same file. One JSON line per change, written by the
request that makes the change BEFORE it returns success; if the write fails the request fails (500) and changes nothing (except `send`, whose line is written after the send is durable)
(for earn/spend/trade/unlock the line is written first, so if the progress write then fails there is one line for a change that did not land; its `ref`
names it; `send` and `delivered` follow the rules in their rows). Every line, validated on write and on read (a bad line is a loud 500 naming its number):
`{"v":1,"ts":ISO,"kind":K,"what":{...},"wallet_after":{inventory}|null,"ref":str}`.
| kind | written by | `what` | `ref` |
|---|---|---|---|
| `earn` | `PUT /api/progress` that raises a resource (the client grants resources) | `{"resources":{res:n>0},"last_event":{type,ts,session_id,...}|null}`: net increase per resource per save; `last_event` = the event the client sent with the save as `cause` (the event that earned it; null for a progress-only save, never guessed from the events on file; the field keeps its name) | `progress_rev:<new rev>` |
| `spend` | buy, unlock; and a `PUT /api/progress` that lowers a resource (building) | `{"resource":"emerald"|"bell"|"wood"|...,"amount":n,"on":label}` (+ `"offer_id"` for a buy); for a PUT `on` = the cause's type and block/item (`block_placed torch`), or `the game (no event named)` | offer id / profession id / `progress_rev:<new rev>` |
| `trade` | sell | `{"trade_id","give":{},"get":{}}` | trade id |
| `treasure` | any treasure created (event, buy, unlock) | `{"tid","label","items","source":{kind,ref}}` | tid |
| `unlock` | unlock | `{"profession","name","paid":"free"|"bell"|"emeralds"}` | profession id |
| `level` | *(no longer written since 2026-10-21; old lines stay)* an event that reached a new shared village level | `{"index","name","points"}` | `level:<index>` |
| `promote` | `POST /api/village/promote` | `{"profession","name","from_level","level" (= from_level + 1),"level_name","spent" (total emeralds spent at that moment)}` | profession id |
| `send` | `POST /api/treasure/send`, written LAST (after the marks are saved and the deliveries exist, so a rolled-back send leaves no line; if the write then fails the 500 says the send DID happen) | `{"tids":[...],"items":[every item of every tid]}` | tids joined by `,` |
| `delivered` | delivery worker, after the read-back | `{"delivery","tid","label","items","chest":{x,y,z},"log":[the log lines that confirmed each insert, or "reconciled by read-back ..."]}` | tid |
| `delivery_failed` | delivery worker | `{"delivery","tid","error"}` | tid |
`wallet_after` = the inventory after the change for earn/spend/trade/unlock/treasure-from-buy, else null.
`GET /api/history[?kind=K]` -> `{"v":1,"kind":K|null,"count":n,"lines":[...chronological, filtered],"totals":{"earned":{res:n},
"spent":{res:n},"sent":{item id:n},"delivered":{item id:n},"unlocked":[profession ids],"levels":[indexes]}}`; totals always
cover the whole file. `GET /api/history.csv[?kind=K]` -> `text/csv`, header `ts,kind,ref,what,wallet_after` (the last two
are JSON strings). An unknown `kind` or any other query parameter is a 400. Limits: earn lines are the NET change per
resource per save (a save that also spends the same resource shows the difference); a retry after a lost response writes
its lines again (no client event id).

### Install tool and the shrine
`python3 tools/minecraft_install.py --mc-dir DIR --session NAME [--config PATH] [--survey-only]` (server must be running;
idempotent) builds the **the village shrine** (spec Addenda 5 and 6): a pagoda (9x9 hall on an 11x11 platform, dark-oak
pillars and rails, two-tier dark-oak/crimson roof with a finial and end rod, hanging lanterns and soul lanterns, sea
lanterns and glowstone in the floor, amethyst, a forecourt with a **beacon** on a flush 3x3 iron base and purple glass above
it; the roof leaves the beacon column open) around Magic Chest 1, plus an entrance sign (the `village_name`), Magic Chest 1 with
its floating label, and a standing `village_name` sign on a free cell next to the world spawn (never on it, facing it).
Everything is Bedrock-safe vanilla blocks. The design is DATA: `tools/shrine_blocks.json` (boxes and cells relative to chest 1,
nine chest spots 3 apart inside the hall, beacon, sign, foundation rule, clear volumes); `tools/shrine.py` expands, surveys
and builds; `tools/shrine_render.py` draws an isometric PNG with the local real textures (`python3 tools/shrine.py --render
OUT.png`, never committed). Order, all before any block is placed: config `chests` must equal the shrine's spots; config
`forbidden` must contain the spawn read (read-only) from `<mc-dir>/world/level.dat`; `server.properties` `spawn-protection` must not
cover the build (`check_spawn_protection`, below); then EVERY target cell is surveyed (one
`execute if blocks` column test per air column, else cell by cell): only air or a replaceable plant (short_grass, tall_grass,
fern, large_fern, dead_bush, flowers) is acceptable, foundations must be air or such a plant down to the first solid block (liquid, or no
ground within 6, refuses); one blocked cell refuses the whole build, lists the blocked cells (stops listing after 80) and
places nothing. The build is `setblock ... keep` per air cell; a surveyed PLANT cell (in the shrine or in a foundation column) is written as
`execute if block <cell> <that plant> run setblock <cell> <block> replace` (the survey records which plant, or `#minecraft:flowers`), so a
block placed there after the survey is never overwritten: the guard fails and the build stops with an error naming the cell;
there is no `fill`.
A marker armor stand (tag `reading_village_shrine`, created first) makes a re-run repair only what is missing; on a re-run
cells holding the intended block, chests and the lanterns/amethyst the worker adds beside overflow chests are accepted.
It then places chest 1 and the label, verifies the beacon (`Levels` >= 1) and prints a report; FAILED banner + exit 1 on any
problem. The chunks under the shrine are forceloaded. Config `shrine` = the cell of chest 1 (site chosen from a survey near
example origin: 100 68 100, platform y 67); a different world needs a new origin and `chests` (`--chests`).

**Spawn protection (the Magic Chest must be usable by non-ops).** With `spawn-protection` above 0, Minecraft stops players who are not
operators (the child) from using blocks, so from opening a chest, inside a square of side `2r+1` (x and z, any y) around world spawn.
The shrine is near spawn, so the install tool reads `<mc-dir>/server.properties` first (`read_spawn_protection`): a missing file, a
missing `spawn-protection` key or a non-integer or negative value is a loud failure. It then refuses (FAILED banner, exit 1, nothing
built) whenever the radius is 1 or more: it lists any shrine or chest cells inside the square (`spawn_protected`) and, because the spawn
sign always stands within 2 cells of spawn, treats the sign as affected for every radius >= 1. The square rule is the vanilla/Paper one,
assumed and not verified against Paper's source offline. **Requirement: `spawn-protection=0`** in `server.properties`, then
`./mc.sh stop` and `./mc.sh start`. Set it in `server.properties` and restart.

### Magic Necklace data pack
Source `tools/datapacks/reading_village_necklace/` (installed 2026-10-19 in `<mc>/world/datapacks/`, mirror `<mc>/datapacks/`; pack format 121). Files: `pack.mcmeta`; `data/minecraft/tags/function/{load,tick}.json`; functions `load` (creates objectives), `tick` (counts down `cn_cd`, runs `player` for everyone), `player` (per-player sneak logic), `use` (Java right-click path), `go` (effects, `tp @s 100 68 104 180 0`, sets cooldown); predicate `sneaking`; advancement `use` (`consume_item` on custom_data `{reading_village_necklace:1b}`, rewards function `use`); loot table `necklace`.
- Objectives: `cn_sneak` = consecutive ticks sneaking while holding it (teleports at 20, about 1 s; reset by any break); `cn_cd` = cooldown ticks left (set to 100 = 5 s). Overworld only.
- Item: `heart_of_the_sea` with components `custom_name`, `lore`, `enchantment_glint_override`, `custom_data {reading_village_necklace:true}`, `max_stack_size 1`, `consumable` (0.2 s, no animation) and `use_remainder` (a copy of itself) so a right-click never consumes it; `player` restores the full item from the loot table if a remainder copy lacks `use_remainder`.
- 26.x schema gotchas found: predicates use `"type"` (not `"condition"`); loot tables use `"modifier"` and `"type"` for item modifiers (not `"functions"`/`"function"`); console lines longer than about 1 KB are silently dropped, so long commands must be split or shortened.
- Confirmed on Java; Bedrock crouch not yet confirmed.

### Tests
`tests/test_shrine.py` (shrine data rules, survey-then-build safety, idempotence, spawn sign, render) against an in-memory
world, `tests/test_minecraft.py` (config, rules, rolls, ledger, log parsing, commands, bridge and worker against
`tests/fake_minecraft.py`, whose replies were captured from the real server) and `tests/test_minecraft_api.py` (village,
unlock, shop, treasure, send, events, PUT guards).

## Away from home (static copy, export, import)

The contract (static run mode, offline backend, `snapshot.json`, export file, scrub guard, import, publishing) is [away-from-home.md](away-from-home.md). Do not duplicate its shapes here. Summary of what it adds to this document's contracts:

- **Run mode.** `STATIC` in `app/js/runmode.js` (false in the repo, true in the published copy) routes `api.js` to `app/js/offline.js`. Same reply shapes, same `ApiError(message, status)`.
- **Events.** `accept_event(srv, ev)` in `server.py` is the body of `POST /api/event`; import calls it per new event in file order, so surprises, streaks and level-up surprises behave exactly as live play. Offline, events are validated against the same field table and kept in the browser until sent.
- **Client-owned progress keys** (the only ones an export carries): `inventory, active_letters, letter_stats, house, stories, crafted, settings`. `village` and `treasure` stay server-owned.
- **New API routes** (Dad's Mac only; never reachable from the static copy):
  - `POST /api/import` <export JSON> -> `{ok, already_imported, events_new, duplicates, treasure, game_level_ups, house_conflicts, emeralds_added, rev}`; 400 names the bad field or event index and changes nothing.
  - `GET /api/web` -> `{state: idle|running|ok|failed|disabled, at, snapshot_id, error, enabled, auto}`.
  - `POST /api/web/publish` -> start a publish now (409 when publishing is disabled).
- **New files.** `data/imports.jsonl` (one receipt per import), `config/web.json`, `build/` (gitignored), `snapshot.json` in the published site.

## Run
```
python3 server.py                                   # opens http://localhost:8642
python3 server.py --port 9000 --no-browser
python3 server.py --data-dir /tmp/x                 # temp data: the delivery worker stays off (never touches the real world)
python3 server.py --minecraft-worker on|off|auto    # auto (default) = worker only for the real data/ dir
python3 server.py --minecraft-config PATH --minecraft-poll SECONDS
```
Dad's dashboard: `http://localhost:8642/dashboard.html`. The server binds `127.0.0.1` and `::1` (both or it exits).
A bad `config/minecraft.json` exits with `FAILED: invalid Minecraft config ...`. For Minecraft deliveries the server
must be running too: `cd <MC_DIR> && ./mc.sh start` (a screen session; not `start.sh`).

## Tests
- `python3 -m unittest discover tests`: `test_server.py` (validation, rev, atomic write, corrupt-file refusal, reset),
  `test_minecraft.py` (config, rules, rolls, ledger, log parsing, commands, bridge and worker against
  `tests/fake_minecraft.py`), `test_minecraft_api.py` (village, unlock, shop, treasure, send, events, PUT guards),
  `test_shrine.py` (shrine data, survey-then-build safety, idempotence, spawn sign, render),
  `test_extract_mc_textures.py` (no jar needed; includes the mob compositor), `test_levels.py` (derivation, event field, override,
  once-only surprise, retry), `test_word_levels.py` (the phonics-ladder rules over every shipped word list), `test_ui_levels.py`
  (Playwright: levels on every screen, Dad override, dashboard panel), `test_ui_smallcaps.py` and `test_ui_village.py` (Playwright: small-caps
  DOM walk, no Word Blocks cue, victory card, Build double-click, village, Treasure Pile, art mode with faked textures).
- `node --test tests/js/`: `toSmallCaps`, letter-introduction and reward rules, story validation, scene engine and
  boxes, swap/slider maths, the save queue (fake server), sounds (fake AudioContext), `villagelogic`, `historylogic`,
  `mctextures`, `sprites`, `stats`, `craft`, `constants`, `levels`.
- Live end-to-end checks of the delivery worker should be run on a copy of the world first.

## Contract changes
- **2026-10-21 (villager promotions, breaking):** villager levels are per villager and keyed to emeralds spent (see "Villager
  promotions"). `config/minecraft.json` `village` gains required `promotions {spent_thresholds, then_every}`.
  `progress.village` gains optional server-owned `emeralds_spent` and `levels` (fresh progress carries `0` / `{}`).
  `GET /api/village` gains `promotions {earned, used, available, spent, next_at}` and per profession `level`, `level_name`,
  `can_promote`; `offers[].locked` now compares the villager's own level. New `POST /api/village/promote`. New history kind
  `promote` (`{profession,name,from_level,level,level_name,spent}`). `POST /api/event` no longer returns `level_up` and the
  server no longer creates `level:<n>` surprises or `level` history lines (`event_rewards` now returns the entry list only);
  `surprises.level_up` is removed from the config and from `SURPRISE_KEYS` (a config still carrying it is rejected). Consumers updated: `villagelogic.js` (`validateVillage`,
  `validatePromoteReply`, `levelFraction` removed), `surprise.js`, `village.js`, `dashboard.js`, `historylogic.js`, `api.js`.
- **2026-10-21 (word mix):** the confusable-letter gate now applies only to lowercase presentations; Crafting Table and Word Blocks
  (small caps) use every word at the level, and craft tray distractors may be any letter. Round mix is 80% at the level + 20%
  review from level L-1 (4+1 of 5 craft, 8+2 of 10 blocks; was 2 easier words from any lower level). Signatures changed:
  `pickAtLevel(items, level, n, {rng})` (option `lowerN` removed; new export `reviewCount`), `pickRound(words, crafted, level, n)`
  (no `active`), `trayFor(word, index, distractors)` (no `active`), `pickBlocksWords(words, practised, level, n, rng)` (no `active`).
  Data files and events are unchanged.
- **2026-10-21 (real mob pictures, install check):** craft words `CHICK` and `BLAZE` now name sprite ids `chick` and `blaze` (were `hen` and
  `torch`; `STAND_IN` keeps hand mode identical, and a saved treasure entry with the old sprite string keeps drawing the old picture).
  `mctextures_map.json` gains the `mob` entry kind and 21 mob entries; `manifest.json` gains `mobs/<mob>.png` files (docs/textures.md).
  The install tool gains the `spawn-protection` check (a new refusal, no format change); `spawn-protection=0` is now a documented requirement.
- **2026-10-21 (levels):** new `app/data/levels.json` (`{"v":1,"games":{craft,blocks,mine,match:{max,window,need}}}`). Events `craft`/`word`/`card`/`match`
  gain an optional `level` int (1..99; above the game's `max` is a 400; missing = 1). `progress.settings.level_override`
  (optional `{game: level}`) is validated on save (400 on an unknown game or a level outside 1..max). `POST /api/event` replies
  may carry `game_level_ups: [{game, level}]`; a level-up creates a rare `surprise` treasure with ref
  `minigame_level:<game>:<level>` (once per game and level). `craft` item, `progress.crafted` keys and `craft_items` keys are
  3 to 10 capitals (were exactly 3; `server.py` and `minecraft_bridge.py` `CRAFT_WORD`). `app/data/craft_words.json` is
  `{"v":2,...}` and `app/data/words.json` is `{"v":2,...}` (phonics ladder, see "Phonics ladder: word lists"); `server.py`
  refuses to start on any other version. `rules.js` `eligibleWords` no longer tests `focus` separately (every confusable in the
  word must be active; the focus is one of them). New `app/js/levels.js`; `validateCraftWords` and `pickRound` changed shape
  (`pickRound(words, crafted, active, level, n)` returns `{round, short}`).
- **2026-10-18:** `settings.lowercase_track` (`"off"`|`"on"`, default off), `settings.lowercase_percent`
  (int 0..100, default 0) added to progress.json, both optional on read. New event type `swap_page`
  (story_page fields plus required int `percent`; `track` is `"lowercase"`); `tricky_word` gains optional
  `percent`. New data file `app/data/swap_order.json`. Default `settings.font` is now `"system"`.
- **2026-10-18:** four scene keys added (`hen`, `fox`, `duck`, `fish`; 26 → 30) and sprites `hen`, `fox`,
  `duck`, `fish`, `stink`. Additive: no existing key, field or file format changed; the animal story pages
  now use the new `art` keys.

- **2026-10-18 (review fixes):** `progress.json` gains integer `rev` (optional on read, missing = 0). `PUT
  /api/progress` must carry `rev` and answers 409 on a mismatch; the response and `GET` carry the new rev.
  `settings.sound` (`"on"`|`"off"`, missing = `"on"`) added. `settings.lowercase_percent` stays 0..100 but is now
  set from a 0..26 letter slider as `round(n*100/26)`. Bridge Match / Letter Mine drill a mirror letter only when it
  and its partner are both swapped in. `GET /api/progress` and `GET /api/events` validate and return 500 on
  invalid data. Events: `swap_page` requires `track` `"lowercase"`; `card`/`match` `item` must be one of the 8
  drill letters. Story page text: ASCII letters only. `write_json_atomic` fsyncs the parent directory after the
  rename. New files `app/js/sounds.js`, `soundui.js`, `savequeue.js`.

- **2026-10-18 (page art):** a page's `art` may now also be a composable object (see "Composable page art"). Additive:
  string scene keys are unchanged. New files `app/render.html`, `app/js/renderpage.js` (dev-only), `tools/render_pages.py`,
  `tools/caption_pages.py`; `findRepeatedArt` added to `stories.js`. `stories/gold-pig.json` pages 0 and 20 use object art.

- **2026-10-18 (page-art engine, E2):** composable art gains `id`, actor `in`/`on`, prop `by`/`on`/`angle`/`scale`/`line_to`,
  prop `y` `"on"`, poses `lying up in sit_on dig`, `fx` as an object/list with `fx:"text"` (see "Engine vocabulary").
  Behaviour changes: a `held` prop is now drawn in the hand (it used to float beside the actor); `sneeze`/`hiss` letter
  in Arial small caps; `artBoxes` also returns effects (`kind: "fx"`); new `artOverlaps`; `render_pages.py` has the
  OVERLAP guard and its CLIP guard covers effects. Pages with text draw a 768x432 canvas (`HI_RES`). Existing art stays valid.

- **2026-10-18 (settings):** new endpoint `POST /api/reset`; archive directory `data/archive/<stamp>/`. No existing field, event or file format changed. New file `app/js/screens/settings.js`; `stageLayout` gains `setProgress` and a Settings gear.

- **2026-10-18 (Crafting Table):** new event type `craft` (`track` `"smallcaps"`, `item` 3 capitals, `result` `correct`|`assisted`);
  `progress.json` gains optional `crafted` (`{WORD: count}`, missing = `{}`); new file `app/data/craft_words.json`, new screen
  `app/js/screens/craft.js`, `craftStats` in `stats.js`, constants `CRAFT_WORDS_PER_ROUND`/`CRAFT_DISTRACTORS`. Additive: no existing field or event changed.

- **2026-10-18 (history, shrine, review fixes):** new file `data/rewards_history.jsonl`, new file `data/treasure_counter.json`,
  new endpoints `GET /api/history`, `GET /api/history.csv`. Optional additions only: treasure entries may carry `event`;
  ledger deliveries may carry `baseline`; config may carry `forbidden` and `shrine` (and `chests` now lists the shrine's
  spots). New files `tools/shrine.py`, `tools/shrine_render.py`, `tools/shrine_blocks.json`. `POST /api/event` keeps its
  reply shape. Behaviour: the delivery worker's first pass after it first sees the server up is a grace pass (also when the
  previous state was unknown); `Bridge.deliver` verifies against the persisted baseline.
- **2026-10-18 (review fixes 2):** optional `cause` field on `PUT /api/progress` (an event; never stored); `earn`/`spend` history
  lines now come from it; new `spend` resources (wood, stone, ...) from client saves; optional ledger fields `confirmed` and
  `pending`; `savequeue.js` builds the event once per commit; new sprite ids `coal_item`, `iron_item`, `gold_item`,
  `diamond_item`, `emerald_item` (same art as the ore sprites in hand mode, item textures in real mode; `itemSprite()`);
  the shrine writes plant cells with a guarded `execute if block ... run setblock`.
- **2026-10-18 (Villager shop / Magic Chest):** new event type `adventure_done` (`adventure`); `progress.json` gains optional
  server-owned `village` and `treasure` (missing = defaults; `PUT` must not change them); new endpoints `GET /api/village`,
  `POST /api/village/unlock`, `POST /api/shop/buy`, `POST /api/shop/trade`, `GET /api/treasure`, `POST /api/treasure/send`,
  `GET /api/minecraft`; `POST /api/event` response gains optional `treasure` and `level_up`; new data file
  `data/minecraft_deliveries.json`, config `config/minecraft.json` (+ gitignored `config/private_overrides.json`),
  `minecraft_bridge.py`, `tools/minecraft_install.py`. The client earns emeralds (see "Who earns what"); the earlier
  single-shop / automatic-delivery design (`GET /api/shop`, top-level `offers`, purchase deliveries) never shipped and
  is superseded by the village and the Treasure Pile.
- **2026-10-19 (Magic Necklace):** new data pack `tools/datapacks/reading_village_necklace/` (scoreboard objectives `cn_sneak`, `cn_cd`; function tags `load`/`tick`). Additive: no game API, config or data-file change. Installed in the real world; see "Magic Necklace data pack".
- **2026-10-19 (replay tiers, legendary):** BREAKING config change: `surprises.story_replay` (one tier name) is replaced by
  `surprises.story_replay_tiers` (non-empty list of tier names; replay N gets entry `min(N-1, len-1)`); the old key is
  rejected at startup with a message naming the new one. New tier `legendary` in `tiers`. New event type `swap_done`
  (`track` `"lowercase"`, `story_id`, `percent`) logged by the swap-in read when its last page is finished; it earns a replay
  surprise and counts as nothing else (no first pass, bell or points). Replay surprises' treasure `source.ref` is now
  `story_replay:<track>:<story_id>:replay<N>:<tier>` (`<track>` is `swap` for swap-in; was `story_replay:<track>:<story_id>`);
  existing treasure keeps its old ref and nothing parses it.

## Implementation decisions (v1)
- **Retry flow:** "Let's try again" shows the cue and logs nothing. "Got it!" after a cue logs
  `assisted`. A second "try again" logs `miss` and re-queues the card ~3 cards later (once).
  Each stage ends on a repeat of a card the child got right.
- **Match events:** one per click. Wrong click → `miss` with `chosen`; right click after a miss →
  `assisted`. They feed `letter_stats`; `match` events carry no `track`. `tricky_word` may carry `track`.
- **Strictness:** the server rejects unknown fields on events and progress.
- **Mastery:** the ≥80%-of-last-10 rule counts only independent `correct`, needs 10 tries first, is
  checked at session start, and only ever adds letters.
- **Rewards:** ore climbs with streak (assisted → coal); each correct small-caps word pays wood/stone (and, since the
  village was added, an emerald); the first finish of a story pass pays `earn.story_first_emerald` and a replay
  `earn.story_replay_emerald` (v1 paid 1 emerald and 0; superseded, see "Villager shop and Magic Chest"); each
  finished pass unlocks one decoration (door, torch, pig, bed, chest), 1 emerald each. Build grid 12×8 — size and
  block list are duplicated in `server.py` and `app/js/rules.js`, so change both.
- **Word eligibility:** a word is used only when every b/d/p/q/m/w/n/u in it is active ("qu" counts
  as q). Word list: `app/data/words.json` (6 levels, see "Phonics ladder: word lists").
- **Sessions:** `session_end` is logged by "Finish session" or completing the adventure; a closed tab
  shows as "not closed" on the dashboard, timed to its last event.
- **Victory card:** picked from items the child got right independently this stage (the most recent one); Dad sees only
  "Got it!", recorded as `correct`. Only if the child got nothing right on their own is the first card used, and then "Got it!"
  is recorded as `assisted`. Bridge Match's victory round never records a wrong click.
- **Home during a save:** once Dad has tapped Home the stage is over; a save still in flight does not bring up the
  story-done screen afterwards.
- **Not in v1:** destructive reset controls on the dashboard.
