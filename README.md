# DotaSense AI

A **read-only** Dota 2 companion: item recommendations, counter analysis, strategy hints and
post-match coaching, with every recommendation explained.

> **Status: Phase 1 done, first versions of Phases 2 to 5.** The live-match screen reads your own
> game through Dota 2 **Game State Integration** (GSI), with hand-written **MOCK scenarios** (clearly
> labeled) for practice. Post-match reports use **real** public match data from OpenDota.
> A Windows installer is built on every push to `main`.

## Windows app

1. Download **DotaSenseAI-Setup.exe** from the
   [latest release](https://github.com/prasetyofauzy1-hash/dota-sense-ai/releases/latest/download/DotaSenseAI-Setup.exe)
   and run it. No admin rights are needed; it installs into `%LOCALAPPDATA%\Programs\DotaSense AI`.
   The installer is not code-signed, so Windows SmartScreen may warn: click **More info → Run anyway**.
2. Open **DotaSense AI** from the Start menu (or the desktop icon). It opens in its own window
   (Microsoft Edge app mode); closing the window quits the app.
3. In **Live Match → Connect Dota 2**, click **Install config into Dota 2**. This writes
   `gamestate_integration_dotasense.cfg` into `dota 2 beta\game\dota\cfg\gamestate_integration\`.
   If Dota 2 is not found, use **Download config file** and copy it there yourself.
4. In Steam: **Dota 2 → Properties → Launch options**, add `-gamestateintegration`.
5. Restart Dota 2 and play a match (or Demo Hero). The sidebar shows **Live GSI: Receiving**.
   Enemy heroes are not in GSI data: pick them in the sidebar as you see them on the scoreboard.

Data (database, GSI token, log `dotasense.log`) lives in `%LOCALAPPDATA%\DotaSenseAI`.
The app listens on `127.0.0.1:47690` for Dota 2 (this PC only); every push must carry the
token written into the config file. Uninstall from **Settings → Apps**; delete the `.cfg` file
above to stop Dota 2 from sending data.

Build it yourself on Windows: `pip install -r requirements.txt pyinstaller`, then
`pyinstaller packaging/windows/dotasense.spec --noconfirm` (app in `dist\DotaSenseAI\`) and
`iscc packaging\windows\dotasense.iss` with [Inno Setup 6](https://jrsoftware.org/isinfo.php).
From source, `python -m app.desktop` runs the same launcher.

## Compliance (strict)

DotaSense AI never reads or writes game memory, injects DLLs, hooks the client, modifies game
files, automates input, buys items, or reveals fog-of-war information. It is not a bot.

* **Live data:** only Valve's Game State Integration (GSI), a documented, read-only HTTP push of
  the player's own game state from the client. It is **on** by default for personal coaching use;
  set `DOTASENSE_LIVE_GSI=false` to turn it off (the receiver then returns HTTP 403). GSI does not
  give players the enemy lineup, so the dashboard takes the visible enemy heroes as **manual input**
  (as seen on the scoreboard).
* **Mock data:** `config/mock_scenarios/*.json` are hand-written practice states in GSI format.
  Each carries `dotasense_mock.is_mock = true` and the UI shows a MOCK banner.

## Run locally (Windows, macOS or Linux)

Requires Python 3.11+.

```bash
git clone https://github.com/prasetyofauzy1-hash/dota-sense-ai.git
cd dota-sense-ai

# Create & activate a virtualenv (use `py -3.11` on Windows or `python3` on macOS/Linux if `python` is older)
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Windows (CMD):        .venv\Scripts\activate.bat
# macOS / Linux:        source .venv/bin/activate

pip install -r requirements.txt

streamlit run app/dashboard.py          # dashboard  -> http://localhost:8501
uvicorn app.main:app --port 47690      # API + live GSI receiver (separate terminal) -> http://localhost:47690/docs
pytest -q                               # tests (run offline)
python -m app.desktop                   # or: both of the above in one window, like the Windows app
```

> **Windows PowerShell note:** If script execution is restricted when activating `.venv`, run commands directly without activating: `.venv\Scripts\python -m pip install -r requirements.txt` and `.venv\Scripts\streamlit run app/dashboard.py`. Set optional environment variables with `$env:DOTASENSE_OFFLINE="true"`.

Optional environment variables:

| Variable | Default | Effect |
|---|---|---|
| `OPENDOTA_API_KEY` | none | Higher OpenDota rate limits (free tier ≈ 60 req/min, 2000/day) |
| `DOTASENSE_OFFLINE` | `false` | Never call OpenDota; rules only |
| `DOTASENSE_DB_PATH` | `./dotasense.db` | SQLite file |
| `OPENAI_API_KEY` | none | Optional LLM rewording of explanations (`app/ai/explanation.py`) |
| `DOTASENSE_LIVE_GSI` | `true` | Accept GSI pushes from Dota 2 |
| `DOTASENSE_GSI_PORT` | `47690` | Port Dota 2 posts to (written into the config file) |
| `DOTASENSE_GSI_TOKEN` | generated | GSI auth token; by default one is generated and kept in the data folder |
| `DOTASENSE_DATA_DIR` | repo root (`%LOCALAPPDATA%\DotaSenseAI` in the Windows app) | Database, token, live state |

## Architecture

```
app/
  dashboard.py          Streamlit UI (dark theme, 7 sections)
  main.py               FastAPI: /health /state /analysis /coach/{match_id} /reports /gsi
  services.py           Glue: provider -> OpenDota data -> engines -> SQLite log
  models.py             Pydantic models (GameState, ItemRecommendation, Threat, ...)
  gsi/parser.py         GSI JSON -> GameState; records missing fields instead of guessing
  gsi/provider.py       MockProvider, LiveGSIProvider (latest push, shared via a JSON file)
  gsi/receiver.py       GSI POST endpoint, token-checked
  gsi/dota_cfg.py       Finds Dota 2 via Steam libraries, writes the GSI config file
  desktop.py            Windows launcher: GSI/API server + dashboard + app window
  data/opendota.py      OpenDota client with SQLite cache
  data/constants.py     Hero/item constants + curated rule tables
  data/snapshot/        Trimmed OpenDota constants (heroes, items, abilities) for offline use
  engine/item_recommender.py   rules + historical item stats (secondary signal only)
  engine/counter_analyzer.py   threat tags per enemy, counter items, matchup win rates
  engine/decision_engine.py    farm/fight, power spike, stance, push/defend, Roshan
  engine/coach.py              post-match report from OpenDota /matches/{id}
  ai/explanation.py            optional LLM rewording, never adds facts
  database/                    SQLite schema: api_cache, game_snapshots, recommendation_log, match_reports
config/mock_scenarios/  MOCK game states
tests/
```

### How recommendations are made
1. **Core build** per hero attribute and game phase (curated heuristic table).
2. **Counter rules:** each enemy gets threat tags (curated for ~60 heroes, otherwise inferred from
   OpenDota roles); each tag maps to counter items, weighted by threat severity.
3. **Hero fit:** e.g. Battle Fury is never suggested to ranged heroes; support items are down-weighted for carries.
4. **History (optional):** OpenDota item purchase share for the hero and phase adds at most +0.3 to the score;
   matchup win rates raise threat severity. Popularity alone never creates a recommendation.
5. Owned items (and their upgrades) are skipped; each result shows reason, benefit, alternative and gold left.

Curated tables are design heuristics, not statistics, and are labeled as such.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation, dashboard, SQLite, mock provider, models | Done |
| 2 | Item engine: rules + historical data | First version (rules + OpenDota popularity). Next: scikit-learn model trained on parsed public matches |
| 3 | Counter intelligence + decisions | First version (rule-based) |
| 4 | Live data | Live GSI on; Windows installer with one-click Dota 2 config |
| 5 | Post-match coach | First version (OpenDota stats, benchmarks, item timings). Next: compare timings with high-MMR players on the same hero |

## Known limitations
* Enemy lineup is manual (GSI only sends your own hero's data).
* Roshan, tower and enemy positions are not available, so those hints are marked **uncertain**.
* Item timings need the match to be **parsed** on OpenDota; otherwise the report says so.
* Hero/item constants are a snapshot (see `app/data/snapshot/meta.json`); refresh when a patch lands.
* The Windows installer is unsigned (SmartScreen warning on first run).

Data: [OpenDota API](https://docs.opendota.com/). Dota 2 is a trademark of Valve Corporation; this project is not affiliated with Valve.
