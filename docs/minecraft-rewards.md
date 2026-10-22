# Minecraft rewards: how reading reaches a real Minecraft world (optional)

**Status: matches the code.** This whole side is optional and off by default (`config/minecraft.json` has `"enabled": false`).
The coordinates, chest spots, `mc_dir`, `screen_session` and player name in that file are **example values**: replace them with
ones that suit your world (the installer's `--survey-only` helps you choose a site).

In the author's world the shrine was built and the Magic Necklace worked on Java. Still unconfirmed:
- The necklace's **crouch** trigger on Bedrock (a tablet) is not confirmed yet.
- 48 item names have no real picture yet; the game draws stand-ins (the dashboard lists them).
- Mini-game level-up screens appear at the end of a stage, the adventure, or on Home, not in the middle of a word.

## 1. The big picture

1. The child reads in the game and earns emeralds, Village Bells and reading points.
2. Reading points earn Village Bells (a bell unlocks a villager).
3. The child unlocks villagers and buys real Minecraft items from them with emeralds. Spending emeralds earns **promotions**: each one lets them pick a villager to move up a level (Novice up to Master), which opens that villager's better trades.
4. Bought items, surprise drops and crafted items all go into their **Treasure Pile** in the game.
5. **The child chooses what to send** and presses Send. Only then does it travel to the **Magic Chest** in their real Minecraft world, even when the child is offline.

Nothing is sent automatically. Items the child has not chosen stay "kept" in the pile.

## 2. What the child earns

| For | The child gets |
|---|---|
| Each word (correct or helped) | 1 emerald, plus wood or stone as before |
| First time through a story | 5 emeralds, 1 Village Bell, 10 reading points, a surprise |
| Replaying a story (including a letter swap-in read) | 2 emeralds, a surprise that gets better each time: 1st replay epic, 2nd and later legendary |
| Each craft at the Crafting Table | 1 emerald, plus the real item (section 5) |
| Every 40 reading points | 1 more Village Bell |
| Each independent correct word | 1 reading point (helped words and misses earn none) |
| Each letter mastered beyond the starting 2 | 5 reading points |

Points and bells are worked out fresh from their history each time; none is stored. (Reading points used to make a shared village level; they no longer do.)

The child can sell wood, stone, coal, iron, gold and diamonds at the "Sell to the village" stall: 10 wood, 10 stone, 5 coal, 3 iron or 2 gold each give 1 emerald; 1 diamond gives 2. All numbers live in the config (section 7).

## 3. The village

**The village** replaces the old Build tile on Home, and a **Treasure Pile** tile sits beside it. Build is still there as the last stage of "Start today's adventure".

- There are 13 villagers, each with a real job-site block: librarian (lectern), armorer (blast furnace), weaponsmith (grindstone), toolsmith (smithing table), farmer (composter), fletcher (fletching table), cleric (brewing stand), cartographer (cartography table), shepherd (loom), butcher (smoker), fisherman (barrel), mason (stonecutter), leatherworker (cauldron).
- Locked villagers appear as "?" plots.
- **Their first villager is free, and the child chooses which.** After that the child picks the next one and how to pay: one Village Bell, or emeralds (15 for farmer, shepherd, butcher, fisherman; 20 for librarian, fletcher, cartographer, mason; 25 for armorer, weaponsmith, toolsmith, cleric; 30 for leatherworker).
- Unlocking puts a villager spawn egg and that job-site block in the Treasure Pile.
- The **Wandering Trader** shows as a silhouette until all 13 are unlocked. It costs 50 emeralds or a bell, and gives a trader egg plus 2 trader llama eggs. The trader sells 23 offers (saplings, music discs, sniffer eggs and so on).
- Enchanted books are sold only by the librarian. There are 188 offers in all.

**Villager levels** are Novice, Apprentice, Journeyman, Expert, Master, and each villager has their own. They come from **spending emeralds**, not from reading. Every time their total emeralds spent reaches 10, 25, 45, 70 and 100, and then every 40 more, the child earns one **promotion** (the village shows a yellow "Promotion ready!" banner and "Spend 6 more emeralds for a promotion"). The child chooses which unlocked villager to promote one level, confirms, and sees "The Armorer is now Apprentice!" with "New trades!". The server never promotes anyone by itself, and a promotion can go to a villager again until the child is Master. Each offer has a minimum level for ITS villager; ones the child cannot reach yet are grey with "Reach Apprentice!" (or the level it needs). Expensive gear and Mending need Expert or Master. The total counts emeralds spent on purchases and on emerald unlocks (not bells, not selling) since the last "Reset progress". There is no longer a celebration or surprise for a shared village level; ones already in the pile stay.

## 4. The Magic Chest and the the village shrine

- Built by the install tool (see "Where things are", section 13); coordinates here are the example values from `config/minecraft.json`. It stands in a small **pagoda shrine** built around it, at **100 68 100** (example values; use your own world's coordinates): a stone platform, dark-oak pillars, a two-level red-and-dark-oak roof, hanging lanterns, glowing sea lanterns in the floor, amethyst, and a **beacon** in the forecourt whose purple beam can be seen from far away. A sign at the entrance says "the village". Another `village_name` sign stands on a free cell next to the world spawn point (never on it). Magic Chest 1 is in the middle, named "Magic Chest" with a floating label.
- When the child presses Send, the game server types commands into the running Minecraft server and reads the result back to check each item arrived (it compares the chest with how it looked before the delivery began, so a late answer from Minecraft can never put an item in twice). An item shows "on the way" until confirmed, then "in your chest".
- The chunk stays loaded, so delivery works while the child is offline. A sparkle and a level-up sound play at the chest.
- **Chest full:** the game places "Magic Chest 2" at the next spot in the config list (9 spots, all inside the shrine hall, 3 blocks apart), and so on. If all are full, sends wait and the dashboard shows "PROBLEM: All Magic Chests are full". Nothing is thrown away.
- **Minecraft server off:** sends wait (not an error) and go in once the server is up. The dashboard shows "Server: NOT running (sends wait until it is up)".
- Each send happens once only. An item can never be delivered twice.
- Nothing is ever built on the world spawn point (it is listed under `forbidden` in the config).

## 5. Surprise drops and crafted creatures

The game server rolls the prize, so the game can show exactly what it was ("A surprise for your Treasure Pile!"). Each tier has about a dozen possible prizes (rare, epic and the new legendary: netherite armor and tool sets, elytra, totems, enchanted golden apples, beacon and nether stars, heart of the sea and conduit, shulker boxes, a stack of 64 diamonds, tridents, a power bow, a netherite block).

| Moment | Tier |
|---|---|
| First pass through a story | epic |
| Replaying a story, 1st time | epic |
| Replaying a story, 2nd time and every time after | legendary |
| 10 independent correct words in a row (every 10th) in one session | rare |
| Finishing today's adventure (once per session and adventure) | epic |
| New level in a minigame (Crafting, Word Blocks, Letter Mine, Bridge Match), once per game and level (section 5a) | rare |

**Replays and how to change the tiers.** A replay is any finished re-read of a story: the same track again, the plain lowercase story after its first pass, or a letter swap-in read (each one counts, and they all count toward the same story's replay number). Which tier a replay gets is the list `surprises.story_replay_tiers` in `config/minecraft.json`; replay 1 uses the first entry, replay 2 the second, and the last entry repeats forever. The shipped list is `["epic", "legendary"]`. For example `["rare", "epic", "legendary"]` makes the first replay rare, the second epic and every later one legendary; `["legendary"]` makes every replay legendary. Each name must be a tier in `tiers`. The old `story_replay` setting no longer exists: the game refuses to start if it is still there and tells you to use `story_replay_tiers`. The Treasure Pile history shows each prize's source, for example `story_replay:swap:gold-pig:replay2:legendary`. Edit the file, restart the game; prizes already in the pile do not change.

Crafting gives a real item, and there are 63 craft words (see "Levels", section 5a). A few examples: PIG a pig spawn egg, HEN a chicken egg, FOX a fox egg, BAT a bat egg, PUP a wolf egg, BED a red bed, SUN 4 glowstone and a sunflower, DAD Daddy's player head, FROG a frog egg, CAKE a cake, GOAT a goat egg. The full list is `craft_items` in `config/minecraft.json`.

## 5a. Levels (how the child moves up)

Each of the four games has its own level: Crafting Table, Word Blocks, Letter Mine and Bridge Match. A level is just "how hard the words or cards are right now". The child sees it under the game's title, for example "Level 2: blends" and "7 of 8 right at level 2". There are no timers, and the child can never lose a level.

**What the levels are**

| Level | Crafting Table and Word Blocks | Examples |
|---|---|---|
| 1 | short vowel words | PIG, BED, QUIT |
| 2 | blends | FROG, NEST, MILK, BANK |
| 3 | digraphs (SH, CH, TH, CK) | FISH, SHIP, DUCK |
| 4 | silent e | CAKE, BONE, SLIME |
| 5 | vowel teams | GOAT, SHEEP, SNOW, MOON, BOOK |
| 6 | two syllables | RABBIT, PANDA, ROCKET |

A few rules about the word lists: QU counts as one unit from level 1 (QUIT). Words ending in NK (BANK, PINK) are treated as blends at level 2. Level 5 includes both sounds of OW (snow, cow) and of OO (moon, book). Level 6 uses only simple closed syllables, so no TURTLE, CANDLE or CANDY. The Crafting Table's grid has one slot per letter, so longer words get a longer grid. Every word at the level can appear: Crafting and Word Blocks are small caps, which do not mirror, so the mirror-prone letters (b, d, p, q, m, w, n, u) need not be introduced first (that rule is for lowercase only), and the spare letters on the Crafting tray can be any letter. Each round is mostly the current level (4 of 5 crafts, 8 of 10 blocks words) plus a review word or two from the level just below; at level 1 it is all level 1. If a level has too few words, the round is topped up with easier ones and Dad's bar says so.

Letter Mine climbs from one letter at a time, to letters mixed, to mirror pairs (b d b d), to everything mixed. Bridge Match climbs from two choices (one letter at a time), to two choices mixed, to three choices, to four.

**Letter Mine and Bridge Match are lowercase-track games.** They practise the letters that get flipped (b/d, p/q, m/w, n/u), and that only happens with lowercase letters; in small caps the child reads them as capitals, which the child already knows. So both stay locked on Home ("Lowercase comes later") until you turn the lowercase track on in the dashboard, and they use only letters that are swapped in along with their partner. Their levels start counting once that track is on. Word Blocks and the Crafting Table are available from the start.

**How the child moves up.** At least 10 tries at a level, with 8 of the last 10 right on their own. A try after a hint ("Let's try again") or a miss does not count as right. A review word mixed into a harder round counts toward its own level, not the harder one, so a level-up takes about two and a half rounds. Levels never go down. Each new level shows a "Crafting level 3!" style screen (at the end of a stage or on Home, never mid-word) and adds one rare surprise to the Treasure Pile, once per game and level. If you reset progress, levels start again at 1 (the history of surprises already sent stays).

**How to override.** In the game, open Settings and find **Levels**: for each game choose "Automatic" (the earned level) or a specific level. The override decides what that game shows and drills; the level the child has earned keeps counting on its own, and surprises still follow the earned level. Choose Automatic to go back. The dashboard's **Levels** panel shows, for each game, the level in force (marked "Dad's override" when set), what it is, and how close the child is to the next one.

**How to change the thresholds.** `app/data/levels.json` holds, per game, the highest level, how many tries to look at (10) and how many must be right (8). Edit it and restart the game.

## 6. What Dad sees

The dashboard has a Minecraft panel at the top, and the Dad bar and Home Dad corner show a status line. A red banner appears when anything needs you.

| Line | Meaning | What to do |
|---|---|---|
| Server: NOT running (sends wait until it is up) | Minecraft is off; sends are queued | `cd <MC_DIR> && ./mc.sh start` |
| PROBLEM: All Magic Chests are full | Every chest spot is full | Empty a chest in game, or add spots to `chests` |
| n DELIVERY FAILED: (shows the reason) | Retried once, still failed; kept for you to see | Read the reason, fix it, ask Claude to retry |
| Delivery worker is NOT running | Game started with the worker off | Restart the game normally (no `--minecraft-worker off`) |
| Minecraft delivery is OFF | `"enabled": false` | Set it to true, restart the game |
| STATUS UNAVAILABLE / MALFORMED | The game could not read its own status | Tell Claude |

## 7. Changing prices, rewards and levels

Edit `config/minecraft.json` and **restart the game after editing**. The file is checked strictly at startup: a typo or unknown key stops the game with a clear error. Prices are in emeralds.

Example, making the first promotion come after 6 emeralds spent and then every 30 after the fifth:

```
"village": { "promotions": { "spent_thresholds": [6, 20, 40, 65, 95], "then_every": 30 } }
```

(`village.levels.thresholds` is now only the informational reading level on Dad's dashboard; it gates nothing.)

Other settings: what each action earns (`earn`), sell prices (`trades`), each villager's `unlock_emeralds` and `offers` (each with `price` and `min_level`), surprise contents (`tiers`), craft items (`craft_items`), and chest spots (`chests`). Past deliveries are never changed by an edit.

The player's gamertag is **not** in this file (the repo may be public). It lives in `config/private_overrides.json`, which is not committed. The committed value is `PlayerName`.

## 8. Installing the shrine on the live server

Only Dad does this, once. The tool builds the shrine, chest 1, the entrance sign and the spawn sign in the live world.

1. **Back up the world first:** `cd <MC_DIR> && ./mc.sh backup`
2. Make sure the server is running: `./mc.sh status` (start it with `./mc.sh start`, never `start.sh`, and wait until the world has loaded).
3. Look before you build: `python3 tools/shrine.py --render ~/Desktop/shrine.png` draws the design (needs the Minecraft jar on this Mac; the picture is for you only, do not publish it).
4. Check the site without building anything: `python3 tools/minecraft_install.py --mc-dir <MC_DIR> --session minecraft --survey-only`
5. Build: the same command without `--survey-only`. (`--session` is the server's screen session; `--config` is optional.) Takes a few minutes: it looks at every block position first.
6. It is safe to run again: it says the shrine marker was found and only fills what is missing.

**Requirement: `spawn-protection=0`** in `server.properties` (in `<MC_DIR>`). Minecraft stops players who are not operators, such as the child, from using blocks near world spawn, and the shrine is close to spawn, so with protection on the child cannot open the Magic Chest. Before building anything the tool reads `server.properties`. If `spawn-protection` is 1 or more it prints **FAILED**, names the radius and the affected positions (the spawn sign always counts, because it stands right beside spawn), and builds nothing. (The protected square is side 2r+1 around spawn; that is the usual Minecraft/Paper rule, assumed rather than checked against Paper's source.) Fix: set `spawn-protection=0`, then `./mc.sh stop` and `./mc.sh start`, and run the installer again. A missing file, a missing key or a non-integer value also fails.

What the survey checks: every block position the shrine will use must be air or a loose plant (grass, ferns, flowers). If anything else is there (rock, a tree, water, a chest that is not ours) the tool prints a **FAILED** banner, lists the blocked positions and builds **nothing**. The spawn point is never touched. The site is the `shrine` position in `config/minecraft.json` (platform at y 67 west of spawn); the chest positions in `chests` must match it (the tool checks). To move the shrine, change `shrine` and `chests` together (`python3 tools/shrine.py --origin X Y Z --chests` prints the list) and survey again.

## 9. Safety

- Back up the world before installing (section 8). The tool does not do it for you.
- The game only adds items to the chest. Nothing is taken out of their Minecraft inventory.
- Spending emeralds in the game is their choice, and the only place the game takes something away.
- Every delivery is recorded in `data/minecraft_deliveries.json` and never deleted.
- Everything the child earns, spends, trades, unlocks, reaches and sends is recorded in `data/rewards_history.jsonl` (see section 11). It is only ever added to; "Reset progress" does not touch it.
- The shrine tool never uses `fill`, never replaces anything but loose plants, and refuses the whole build if a single position is taken.

## 10. Troubleshooting

| Symptom | What to do |
|---|---|
| Magic Chest won't open for the child ("spawn protection") | `spawn-protection` in `<MC_DIR>/server.properties` must be `0` (non-ops can't use blocks near spawn otherwise); set it, then `mc.sh stop` / `mc.sh start`. Fixed 2026-10-20. |
| Item bought but not in the chest | Bought items wait in the pile until the child presses Send. If sent, check the dashboard for "NOT running"; start Minecraft and wait about 15 seconds |
| Chest not there at all, no shrine | The install step has not run (section 8) |
| The installer says FAILED about `spawn-protection` | Set `spawn-protection=0` in `<MC_DIR>/server.properties`, restart Minecraft with `mc.sh stop` / `mc.sh start`, run the installer again. Nothing was built |
| The installer says FAILED and lists blocked positions | Something already stands where the shrine goes. Nothing was built. Move `shrine` (section 8) or clear the spot |
| The beacon has no beam | The iron base or the sky above it is blocked; the installer reports it ("did not activate") |
| "All Magic Chests are full" | Empty a chest, or add more spots to `chests` |
| A delivery shows failed | Read the reason on the dashboard; fix it; ask Claude to retry. The child sees "Dad is checking" |
| Game will not start after config edit | Read the error; it names the bad key. Undo the edit |
| The child cannot afford an item | Dim means emeralds are short; grey means that villager's level is too low (promote them). Nothing is wrong |
| Items appeared twice | Should not happen; tell Claude and share `data/minecraft_deliveries.json` |

## 11. The rewards history (master list)

`data/rewards_history.jsonl` has one line for every change: resources earned, emeralds and bells spent, trades, treasure created, villagers unlocked, villager promotions, treasure sent, deliveries confirmed (with the item list, the chest and the Minecraft log lines that confirmed it) and deliveries that failed. It is written by the game server in the same moment as the change and the change fails if the line cannot be written. It is never edited, trimmed or moved, and survives "Reset progress".

- See it: `http://localhost:8642/api/history` (add `?kind=earn`, `spend`, `trade`, `treasure`, `unlock`, `promote`, `level` (old lines only), `send`, `delivered` or `delivery_failed` to filter); it also shows totals (ever earned per resource, ever sent per item, villagers unlocked, levels).
- Spreadsheet: `http://localhost:8642/api/history.csv` (columns `ts, kind, ref, what, wallet_after`, the last two as JSON text).
- One limit: resources are earned inside the game, so an `earn` line is the net increase per resource in one save, and it names the newest event as the likely cause.

## 12. The Magic Necklace

A Magic Necklace (a glowing, purple-named Heart of the Sea) teleports the child to the shrine from anywhere in the Overworld.

- **Use:** hold it and **crouch for about one second** (Java also: right-click). The child lands at the shrine entrance (100 68 104) facing the chest, with sparkles and a sound.
- **Overworld only** (a red message says so elsewhere). **5 second cooldown.** The necklace is never used up.
- Installed 2026-10-19 as the data pack `reading_village_necklace` in `<MC_DIR>/world/datapacks/` (source in `tools/datapacks/reading_village_necklace/`, mirror in `<MC_DIR>/datapacks/`).
- Confirmed: Tested on Java, works. **Not yet confirmed:** crouch on Bedrock.
- One necklace was put in the Magic Chest for the child.
- Spare necklace (Dad, in game or console): `/loot give @s loot reading_village_necklace:necklace` (insert into a chest: `/loot insert 100 68 100 loot reading_village_necklace:necklace` for Magic Chest 1). Design details are in `docs/design.md`.

## 13. Where things are (example values; yours come from `config/minecraft.json`)

| What | Where |
|---|---|
| Magic Chest 1 (example) | 100 68 100 |
| Beacon (active) | 100 68 109 |
| Entrance sign (the `village_name`) | 99 68 106 (example) |
| Spawn sign (the `village_name`) | 109 65 91 (example) |
| Forbidden spot, e.g. world spawn (left clear; example) | 108 65 90 |
| Necklace arrival point | 100 68 104 |
| World backup before install | `your backup archive from before installing (outside the repo)` |

## 14. Daily routine

1. Start the reading game: `cd <the repo> && python3 server.py`.
2. Start Minecraft: `cd <MC_DIR> && ./mc.sh start` (a background screen session). Do **not** use `start.sh`: the game cannot reach a server started that way.
3. The child plays. The child can press Send at any time; deliveries wait until **both** the game and the Minecraft server are running, then go in. The Minecraft client is opened normally.
4. When finished: `./mc.sh stop`.

## 15. Handy commands

| Want | Command |
|---|---|
| Go to the shrine | `/tp @s 100 68 104` |
| Give a spare necklace | `/loot give @s loot reading_village_necklace:necklace` |
| Server status / back up | `./mc.sh status` / `./mc.sh backup` (in `<MC_DIR>`) |

## 16. Real-texture art mode

Settings, then Art, switches the game to real Minecraft pictures. The textures are extracted locally into the git-ignored `app/assets/mc/` from the parent's own client jar and are never committed. In this mode the Crafting Table shows the real mob for 21 of the craft words (pig, bat, wolf, hen, chick, fox, frog, squid, cod, mule, slime, blaze, goat, sheep, bee, cow, rabbit, panda, camel, piglin, hoglin) instead of a spawn egg; the pictures are built on this Mac from the game's own files. The default hand-drawn mode is unchanged. See `docs/textures.md`.


## 17. Away from home

The child can play away from home through a public website (https://YOUR-GITHUB-USER.github.io/YOUR-REPO/). Your Mac stays the real record. The helper plays, presses "📨 Send to Dad", and emails you the file; you import it. The full contract is [away-from-home.md](away-from-home.md); the helper's own instructions are [away-guide.md](away-guide.md).

### First-time setup (once)

```
python3 tools/publish_web.py --setup
```

This creates the public repo named in `config/web.json` and turns on GitHub Pages. After that, publishing is automatic.

### Importing the helper's file

1. Save the `reading-village-....json` file from the helper's email.
2. Open the Dashboard, find **Import from <away_label>**, choose the file, press **Import this file**.
3. Read the result:
   - `IMPORTED: N new events, M already there, E emeralds added.` plus the surprises and level-ups the child earned. "Already there" are duplicates: events you already hold are skipped, so importing the same play twice is safe.
   - `ALREADY IMPORTED earlier ... Nothing changed.` means that very file was imported before.
   - `HOUSE CELLS SKIPPED (n), Dad's blocks were kept` (red): a house cell where your record and the helper's differ. Yours wins; the rest of the import still went ahead.
   - `IMPORT FAILED, NOTHING WAS CHANGED: ...` (red): the file was damaged or invalid, or it is **older** than one already imported from the same browser (fewer events than before; applying it would subtract play). Nothing was written. Import the newer file instead.

### How the website updates

- Automatically after **Finish session** and after a successful import (in the background; several requests at once become one more run).
- By hand: Dashboard, **away-from-home website** panel, **Update away-from-home website** button.
- The panel shows idle, running, or the time and snapshot of the last good update. A red **WEBSITE UPDATE FAILED** box means **nothing was published**: the site is as it was. Fix the cause named in the box and press Update. "Publishing is switched off" means `config/web.json` has `enabled` false or is broken.
- The helper's browser keeps its own play. It picks up a newer snapshot only once you have imported everything made there.

### The scrub guard

Before anything is pushed, every byte of the site is scanned. The publish fails (nothing pushed) if it finds the gamertag, an email address, an IP address other than 127.0.0.1, `/Users/`, anything under `assets/mc/` (Mojang's textures), `private_overrides`, `dashboard.html`, `render.html`, `.DS_Store`, or a `runmode.js` that is not `STATIC = true`. The public repo holds one commit only, replaced each time.
