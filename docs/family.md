# Family config (`config/family.json`)

The one place a parent personalises the game. Committed, strict, and read by both `server.py` (startup) and the browser
(`loadFamily` in `app/js/family.js`, at boot, fetching `data/family.json`). A bad file stops startup with a message naming the field: unknown key,
wrong type, empty string or missing required key. There are no fallback values.

```json
{ "v": 1,
  "child": { "name": "Sam" },
  "village_name": "Sam's Village",
  "home_grown_up": "Dad",
  "away_label": "Mom's house" }
```

| Field | Type | Required | Used for |
|---|---|---|---|
| `v` | integer, must be 1 | yes | schema version |
| `child.name` | non-empty string | yes | UI text ("Great job, Sam!"); the only place the child's name lives |
| `village_name` | non-empty string | yes | Home tile, village screen title, shrine signs |
| `home_grown_up` | non-empty string | yes | label of the grown-up corner and of "Send to <home_grown_up>" |
| `away_label` | non-empty string | yes | wording of the away-from-home website copy ("Playing at <away_label>") |

Optional fields added later must be documented here with their default. None exist yet. The hero's sprite id is `hero`
(stories refer to the child as `who: "hero"`); "Dad" and "Mama" in the example stories are example family characters, not
tied to `home_grown_up`. `config/` is not a static root, so the server serves its validated copy at `/data/family.json`, and the website build
(`tools/publish_web.py`) writes it into the site as `data/family.json`. It is therefore public on any published website:
put nothing private in it (a first name and labels only).

Startup failure: `server.py` exits with `FAILED:` and a message naming the file and the field; the browser shows the
"Could not start" banner naming the field. The same rules apply in both.

The example stories (`stories/`) use a child called Sam. Real names belong only in this file and in your own stories.

