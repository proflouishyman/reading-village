# Playing away from home (web copy + emailed progress file)

The child can play away from home (`away_label` in `config/family.json`, for example "Mom's house") in a browser, from a public GitHub Pages site. The home computer ("Dad's Mac" below: the grown-up labelled `home_grown_up`) stays the one real
record. The web copy starts from a **snapshot** of the child's status that Dad's Mac publishes. Play there is saved
in that browser, and a big **Send to Dad** button downloads one **export file** that the helper emails to Dad. Dad imports
it on the Mac, which replays it into the real record (surprises, levels, emeralds, history), and then republishes
the snapshot.

Nothing on Dad's Mac accepts connections from outside. Publishing is an ordinary outbound `git push`.

This file is the **contract** for the four parts: the static run mode, the snapshot, the export file and the import.
Shapes are exact. Every reader validates and fails loudly on a mismatch (no coercion, no defaults).

## 1. Static run mode (client)

- `app/js/runmode.js` exports `STATIC` (boolean). In the repo it is `export const STATIC = false;`. The publish tool
  overwrites it in the built copy with `export const STATIC = true;`. Nothing else switches modes.
- With `STATIC`, `api.js` routes every call to `app/js/offline.js` instead of `fetch`. The offline backend keeps the
  same contract: it returns the same reply shapes, and on failure throws `ApiError(message, status)`.
- **All app URLs are relative** (`css/style.css`, `js/main.js`, `data/…`, `../fonts/…` in CSS, `./` for "home").
  This works both from `python3 server.py` at `/` and from `https://YOUR-GITHUB-USER.github.io/YOUR-REPO/`.
  API paths are still written `/api/...` in `api.js`, but they never reach the network in static mode.

### Offline backend (`app/js/offline.js`)

- **Boot**: it fetches `snapshot.json` (relative). A failure is a loud fatal error ("Could not load the child's
  status from the website"). It reads `localStorage["cv_offline_v1"]` (the **local state**, §1.1). If storage throws
  or is unavailable, it shows a loud fatal error: this browser cannot keep progress. Play is not allowed without
  storage.
- **Routes**:

| Call | Offline answer |
|---|---|
| GET `/api/progress` | `local.progress` |
| PUT `/api/progress` | It rejects a stale `rev` (409, same text as the server). It also rejects any change to `village` or `treasure` (400 "`<key>`: is owned by the server…"). It drops `cause`, stores the progress with `rev+1`, and returns it. |
| POST `/api/event` | It checks the event against the same per-type field table as the server (port `EVENT_FIELDS`; an unknown or missing field is 400) and appends it to `local.events`. Reply: `{ok:true}` plus `game_level_ups:[{game,level}]` when the event's game newly reaches a level ≥2. "Newly" means not reached by `deriveLevels(snapshot.events + local.events before this one)` and not already in `local.celebrated`. No `treasure` (surprises are rolled at Dad's on import). |
| GET `/api/events` | `snapshot.events.concat(local.events)` |
| GET `/api/village` | `snapshot.village`, with `wallet` replaced by `local.progress.inventory` |
| GET `/api/treasure` | `snapshot.treasure`, with `enabled:false`, `server_running:false`, `problem:"Sending happens at Dad's house"` |
| GET `/api/minecraft` | `{enabled:false, worker_running:false, server_running:false, pending:[], failed:[], recent:[], chests:[], problem:"Minecraft is at Dad's house"}` |
| GET `/api/history[?kind=]` | `snapshot.history`, filtered by kind like the server does |
| POST unlock / promote / buy / trade / send, `/api/reset` | 409 `{error:"That happens at Dad's house"}`. The UI must not offer these (below), so reaching one is a bug and shows loudly. |

- **UI in static mode**:
  - **Village**: a read-only view with a friendly line, "The shop opens at Dad's house. Your emeralds are safe."
    Buttons are shown disabled, never hidden-and-failing.
  - **Treasure**: Send is disabled, with the line "Sending to Minecraft happens at Dad's house."
  - **Settings and Home**: no Dashboard link and no Reset.
  - **Save banner**: the text in static mode says "Ask a grown-up to reload the page" instead of naming
    `python3 server.py`.
- **Send to Dad** (static mode only):
  - Home shows a big, unmissable button: "📨 Send to Dad", with "N new things to send" or "All sent ✓ (last sent
    <time>)".
  - After `session_end` (Finish) and after `adventure_done`, a full-screen prompt offers the same button.
  - Clicking it downloads the export (§3) as `reading-village-YYYY-MM-DD-HHMM.json`. The page then shows
    instructions in large text: "Attach this file (in your Downloads folder) to an email to Dad." It records
    `local.last_export {at, events, progress_fp}` (§1.1).
  - Local state is **not** cleared: exports are cumulative since the base snapshot.

### 1.1 Local state `localStorage["cv_offline_v1"]`

```
{ v: 1,
  device_id: string (crypto.randomUUID, made once, never changed),
  base: { snapshot_id: string, progress: <snapshot.progress at adoption, deep copy> },
  progress: <current full progress, same shape as server progress>,
  events: [<event>, ...]            // events made here since `base`, in order
  celebrated: [{game, level}, ...], // level-ups already shown here
  last_export: null | { at: ISO string, events: int, progress_fp: string } }
// progress_fp = canonical JSON (keys sorted) of the client-owned slice of `progress` as exported (what the file held)
```

- **Adopting a snapshot.** On boot with a fresh browser, it adopts the snapshot: `base = snapshot`,
  `progress = snapshot.progress`, `events = []`.
- **Unsent.** Play here is unsent when events were made since the last export (`events.length - last_export.events`,
  or all of them if never exported) OR the client-owned progress (canonical JSON, `rev` ignored) differs from
  `last_export.progress_fp` (from the base's progress if never exported). A progress change with no event (story
  resume page, a newly introduced letter, a setting) therefore counts: Home shows it as one more "new thing to send"
  and never says "All sent".
- **A newer snapshot is published.** When `snapshot.snapshot_id != base.snapshot_id`, it adopts the new snapshot
  only if nothing local would be lost: (a) no events were made here and the client-owned progress equals the base's;
  or (b) Dad's receipt covers all local events (`snapshot.imported[device_id]` exists with
  `base_snapshot_id == base.snapshot_id` and `events >= events.length`) AND the progress is not unsent (unchanged
  since the last export, or since the base when never exported). Otherwise it keeps the old base and local play, and
  the Home button shows what is unsent. Never merge two bases in the browser; merging happens at Dad's. Known limit:
  the receipt holds only an event count, so two exports with equal counts and different progress cannot be told
  apart; the later one is assumed to be the one emailed.
- **Two tabs**: every write first re-reads storage and compares it with the string this tab last wrote; a mismatch
  means another tab changed it, and the write throws ApiError 409 ("opened in another tab: reload"), which shows the
  PROGRESS NOT SAVED banner. Nothing is overwritten.
- **A write fails** (quota, or storage cleared mid-session): it shows the loud "PROGRESS NOT SAVED" banner.

## 2. Snapshot `snapshot.json` (written by `tools/publish_web.py`)

```
{ format: "reading-village-snapshot", v: 1,
  snapshot_id: string (sha256 of the canonical JSON of the other fields, first 16 hex),
  published_at: ISO string with offset,
  source: { commit: <git HEAD short sha of this repo>, progress_rev: int },
  progress: <GET /api/progress reply>,
  events: <GET /api/events reply>,
  village: <GET /api/village reply>,
  treasure: <GET /api/treasure reply>,
  history: <GET /api/history reply>,
  imported: { <device_id>: { base_snapshot_id: string, events: int }, ... } }   // from data/imports.jsonl
```

- The tool builds these by calling the server's own view functions in-process on `data/`, not over HTTP. It then
  applies a **documented strip list** of fields the web copy does not need (for example delivery/player details in
  history or treasure).
- After that it runs the **scrub guard** (§4).

## 3. Export file (downloaded at the helper's, imported at Dad's)

```
{ format: "reading-village-export", v: 1,
  export_id: string (uuid, new per download),
  device_id: string, created: ISO string with offset,
  base: { snapshot_id: string, progress: <base progress, client-owned keys only> },
  progress: <current progress, client-owned keys only>,
  events: [<event>, ...] }   // all of local.events, cumulative since base
```

**Client-owned keys**: `inventory, active_letters, letter_stats, house, stories, crafted, settings`.

## 4. Scrub guard (publish tool)

Before anything is pushed, every byte of the built site is scanned, and the publish **fails loudly** (non-zero exit,
FAILED banner, nothing pushed) on any of these:

- the gamertag from `config/private_overrides.json` (any case);
- an email address;
- an IPv4 address other than `127.0.0.1`;
- `/Users/`;
- any file under `assets/mc/`;
- `private_overrides`;
- `dashboard.html`, `render.html`, `.DS_Store`;
- a `runmode.js` that is not `STATIC = true`.

## 5. Import (Dad's Mac): `POST /api/import` with the export JSON as the body

All or nothing, under `write_lock`:

1. **Validate the whole file first.** Check the exact shape (§3); `format`/`v`; validate every event with
   `validate_event` plus the level cap; check that `progress` and `base.progress` have exactly the client-owned
   keys. Any problem → 400 naming the field (or the event index), and **nothing changes**.
2. **Event dedupe**: `key = sha256(json.dumps(ev, sort_keys=True))` over the events already in `events.jsonl`.
   Events already present are counted as duplicates and skipped. New events go **in file order** through
   `accept_event(srv, ev)`, which is the body of `POST /api/event` factored into a function (that handler then calls
   it too), so surprises, streaks, level-up surprises and history work exactly as live play.
   **Older export refused**: for the same `(device_id, base.snapshot_id)`, an export with fewer events than the last
   receipt's `events_total` is 400 ("older than an export already imported; nothing changed"): exports are
   cumulative, so applying it would subtract play. Craft words with no configured item are also rejected in
   validation, before anything is written.
3. **Progress merge**: prev = the progress from the last import receipt for the same `(device_id,
   base.snapshot_id)`, else `base.progress`.
   - `inventory`, `crafted`: add `(export − prev)` per key. A result below 0 → 400, nothing changes.
   - `letter_stats`, `stories`: per sub-key, take the export's value where it differs from prev.
   - `active_letters`: the union, keeping server order and then adding new letters.
   - `house`: append the cells the export added beyond prev. A cell Dad's record already holds with a different block
     is **not** an error: Dad's block is kept, the cell is skipped and listed in the reply as
     `house_conflicts:[{x,y,dads,moms}]` (shown loudly on the Dashboard); the rest of the import goes ahead. (An error
     here would block every later cumulative export from that base for good.)
   - `settings`: ignored (Dad's settings win).
   - Then `validate_progress` on the result, `record_client_changes(srv, current, merged, None)` (earn/spend
     history), and save with rev+1.
4. **Receipt**: append to `data/imports.jsonl`
   `{v:1, ts, export_id, device_id, base_snapshot_id, events_total: len(events), events_new, duplicates, progress: <export progress>}`.
   - A failed import restores its files, but `rewards_history.jsonl` is only trimmed back to its saved start (keeping
     any `delivered` / `delivery_failed` line the delivery worker appended meanwhile), never rewritten wholesale.
   - Re-importing the same `export_id` → 200 `{already_imported:true, ...counts from the receipt}`, and nothing
     changes.
5. **Reply 200**: `{ok:true, already_imported:false, events_new, duplicates, treasure:[{label,sprite}], game_level_ups, house_conflicts, emeralds_added, rev}`.
6. **Publish**: after a successful import, the server republishes the snapshot (§6).

## 6. Publishing (`tools/publish_web.py` + server hook)

- `config/web.json`:
  `{ "enabled": true, "auto": true, "repo": "YOUR-GITHUB-USER/YOUR-REPO", "branch": "main", "work_dir": "build/web-repo" }`
  (`build/` is gitignored). The site also gets the repo-root `stories/*.json` (top level only) as `stories/`.
- `python3 tools/publish_web.py [--no-push] [--setup]`. `--setup` creates the public repo and enables Pages once.
- The publish steps:
  1. Build the site in `build/web/`: `app/` minus `assets/mc/`, `dashboard.html`, `render.html`,
     `js/dashboard.js`, `js/renderpage.js`, `.DS_Store`.
  2. Set `runmode.js` to `STATIC = true` and write `snapshot.json`.
  3. Run the scrub guard.
  4. Copy into `work_dir` as **one orphan commit** and force-push it, so the public repo never accumulates
     history of the child's data.
  5. Print the page URL.
- Function contract: `build_and_publish(root: Path, data_dir: Path, push: bool = True) -> dict {ok: True,
  snapshot_id, url, pushed: bool, files: int}`. It raises `PublishError(message)` on any failure.
- **Server hook**: when `web.json` has `enabled` and `auto`, the server runs `build_and_publish` in a background
  thread (one at a time; requests that arrive meanwhile coalesce into one more run) after a `session_end` event and
  after an import.
- **Status**: the result is kept in `srv.web_status = {state: "idle"|"running"|"ok"|"failed", at, snapshot_id,
  error}` and returned by `GET /api/web`. `POST /api/web/publish` starts a publish now.
- The Dashboard shows the status, with a loud red box on `failed`, and a "Update away-from-home website" button.
