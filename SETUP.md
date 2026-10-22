# Make Reading Village yours

This page is for a parent. You do not need to code. You will paste the **interview script** below into Claude Code
(run from this repository's folder), answer some friendly questions, and Claude will personalise the game: your child's
name, a village of your own, characters from your family, and starter stories at the right reading level.

Before you start:

- Install Python 3 and [Claude Code](https://claude.com/claude-code). Open a terminal in this folder.
- Run `python3 server.py` once to see the game as shipped (it opens at http://localhost:8642). It ships with example
  stories about "Sam", "Dad" and "Mama". It will refuse to start if `config/family.json` has a mistake, and it will tell
  you which field.
- Everything about your child stays on your computer (`data/` is gitignored). If you put your copy on GitHub, make it a
  **private** repository, or read the privacy notes at the end of this page first.

## The interview script (paste this into Claude Code)

```
You are helping me personalise this reading game for my child. Read README.md, docs/overview.md and the
docs/family.md and the "Stories" section of docs/design.md first. Then interview me, a few questions at a time (never all
at once), warmly and plainly. Do not write any files until the interview is done and I have said yes to your summary.

Ground rules:
- Failures are loud: if a check fails, show me the failure and fix the cause. Never hide an error or paper over it.
- Keep my child's private details out of anything that could be published. Names go only where config/family.json and
  the stories need them. Never put a surname, school, address, email or gamertag in a committed file.
- Characters are simple pixel cartoons, never portraits. From any photo I give you, describe only hair colour and style,
  clothes and glasses, and match them with the existing hand-drawn sprites in app/js/sprites.js. Do not describe faces,
  skin or bodies, and do not try to reproduce a likeness.

INTERVIEW
1. About my child: first name (or the nickname they like), age or grade, and how they feel about reading.
2. Reading method and place: which approach do they use at school or with a tutor (Orton-Gillingham, a structured literacy
   programme, none)? Which letters and sounds are solid? Which patterns can they decode now (short-vowel CVC words, blends,
   digraphs, silent e, vowel teams)? Which sight words do they know and which trip them up?
3. Letters: should they read small caps first (capital shapes at lowercase size) and move to lowercase later, or go
   straight to lowercase? Which letters do they flip or mix up (b/d, p/q, m/w, n/u)? Which cues does their teacher use?
4. Family: who lives with them, who reads with them (the grown-up who will sit beside them is the "home grown-up"; what
   does the child call them: Mom, Dad, Papa, Nana?), siblings, grandparents, pets. For each person or pet I want a
   first name or title and, if I choose, a line about hair and clothes.
5. Interests: favourite animals, Minecraft things, foods, places, jobs, funny things that happened. These become the story
   topics.
6. Village: what should the village be called ("Sam's Village")? And, if relevant, what do they call the other house where
   they sometimes play (e.g. "Grandma's house")?
7. Rewards: do they get excited by treasure, or do they get frustrated easily? How generous should rewards be (many
   small treats vs a few special ones)?
8. Minecraft: do we run our own Java Paper server, or none? If yes: where is it, what version, Bedrock devices
   (Geyser) or Java only, which player will use the chest? If no, we skip the Minecraft section and leave it off.
9. Another household: will the child play at another house? If yes, we may set up the optional website later.

AFTER THE INTERVIEW
A. Summarise what you heard in 10 lines and wait for my yes.
B. Write config/family.json (child.name, village_name, home_grown_up, away_label). Run `python3 server.py --no-browser`
   to confirm it validates. Fix any error it names.
C. Characters: add simple sprites for the family members and pets I chose, in the existing style, following the sprite
   format in app/js/sprites.js and how scenes use them (docs/design.md, "Composable page art"). Rename the hero
   only through the sprite id "hero"; keep that id.
D. Starter stories: write 4 to 6 short decodable stories (8 to 14 pages, one short sentence per page) starring my child
   (as "who": "hero") and the family and pets I named. Rules: only patterns my child can decode, plus the sight words I
   said are safe; ASCII letters only in page text; lean on the letters they need practice with (set focus_letters);
   avoid words I said trip them up; no scary or failure-shaming plots. Save as stories/<id>.json, add the ids to
   stories/index.json, replacing or keeping the example stories as I prefer. Match the schema in docs/design.md.
E. Check the pictures: for every story run `python3 tools/render_pages.py <story-id>` (needs Playwright). Fix every
   CLIP, OVERLAP or HEADCOVER failure; never raise a limit to pass. Then show me each page's PNG next to its sentence
   and ask me to confirm that every picture matches its sentence and that the people look like my family (as cartoons).
   Fix what I flag, re-render, and ask again.
F. Word lists: adjust app/data/words.json and app/data/craft_words.json only if I asked (level, pattern and focus are
   required fields; the loader validates them). Do not add words my child cannot decode at that level.
G. Settings I can change later on the dashboard: lowercase track on/off, mini-game levels, sound, font.
H. Rewards: set how generous earning is (the `earn` and `surprises` blocks of config/minecraft.json control emerald and
   treasure rates even when Minecraft delivery is off). Explain each number you change in plain words.
I. Run the tests that apply: `python3 -m unittest discover tests` and `node --test tests/js/`. Tell me what failed.
J. Do not commit or publish anything unless I ask. When I ask, first show me the diff and check it for private details.
```

## Optional: real Minecraft rewards

Only if you run your own Java Paper server. Delivery is off by default. In short (full guide:
[docs/minecraft-rewards.md](docs/minecraft-rewards.md)):

1. **Back up your world first** (copy the world folder somewhere safe). Try everything on a copy of the world before the
   real one.
2. Your server directory needs an `mc.sh` helper (`start`, `stop`, `status`, `cmd`, `backup`; `status` must exit 0 when
   running and 3 when stopped) and must run inside a detached `screen` session, because the game types commands into
   that session. Ask Claude to write `mc.sh` for your setup.
3. In `server.properties` set `spawn-protection=0`, then restart. Otherwise a non-operator child cannot open the chest.
4. Edit `config/minecraft.json`: set `mc_dir`, `screen_session`, choose chest and shrine coordinates for your world (the
   shipped numbers are examples), and set `enabled` to `true`. Put the player's gamertag in the gitignored
   `config/private_overrides.json`, never in committed config.
5. Check the site first: `python3 tools/minecraft_install.py --mc-dir <your server dir> --session <screen name> --survey-only`.
   Then build the shrine once (without the flag). It refuses to build if spawn protection would block the chest.

## Optional: real Minecraft pictures

The repository never contains Minecraft textures. To use them, extract them from your own copy:
`python3 tools/extract_mc_textures.py` (needs Pillow), then pick "real" in Settings, Art. The files stay in
`app/assets/mc/`, which is gitignored; never publish them.

## Optional: playing at another house

The game can publish a small website copy that the child plays elsewhere; a **Send** button downloads a file that the
helper emails back, and you import it from the dashboard. It is off until you set `config/web.json` (replace
`YOUR-GITHUB-USER/YOUR-REPO`, set `enabled`) and run `python3 tools/publish_web.py --setup`. Publishing is opt-in, the
site is scanned for private values before anything is pushed, and the repository it creates is public, so only put the
first name and labels from `config/family.json` in it. Give the helper
[docs/away-guide.md](docs/away-guide.md). Contract: [docs/away-from-home.md](docs/away-from-home.md).

## Privacy checklist before you ever push

- `git status` shows nothing under `data/`, `app/assets/mc/` or `config/private_overrides.json`.
- No gamertag, email address, surname, school or address in any committed file, commit message or author email (use
  your host's no-reply address as the commit email).
- The stories contain only first names or nicknames you are happy to share.
- If you are unsure, keep the repository private.
