# DotaSense AI

A **read-only** Dota 2 companion: item recommendations, counter analysis, strategy hints and
post-match coaching, with every recommendation explained.

> **Status: Phase 1 done, first versions of Phases 2, 3 and 5.** The live-match screen runs on
> **hand-written MOCK scenarios** (clearly labeled in the UI). Live game integration (Phase 4) is
> **disabled** until its policy status is reviewed. Post-match reports use **real** public match data from OpenDota.

## Compliance (strict)

DotaSense AI never reads or writes game memory, injects DLLs, hooks the client, modifies game
files, automates input, buys items, or reveals fog-of-war information. It is not a bot.

* **Live data:** Valve's Game State Integration (GSI) is a documented, read-only HTTP push from the
  client, but this project does **not** assume GSI is approved for use in live matchmaking. The
  receiver (`app/gsi/receiver.py`) returns HTTP 403 unless `DOTASENSE_LIVE_GSI=true`, and nothing
  in the app turns it on. Also note that GSI does not give players the enemy lineup, so the
  dashboard takes the visible enemy heroes as **manual input** (as seen on the scoreboard).
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
uvicorn app.main:app --reload           # optional API (separate terminal) -> http://localhost:8000/docs
pytest -q                               # tests (run offline)
```

> **Windows PowerShell note:** If script execution is restricted when activating `.venv`, run commands directly without activating: `.venv\Scripts\python -m pip install -r requirements.txt` and `.venv\Scripts\streamlit run app/dashboard.py`. Set optional environment variables with `$env:DOTASENSE_OFFLINE="true"`.

Optional environment variables:

| Variable | Default | Effect |
|---|---|---|
| `OPENDOTA_API_KEY` | none | Higher OpenDota rate limits (free tier ≈ 60 req/min, 2000/day) |
| `DOTASENSE_OFFLINE` | `false` | Never call OpenDota; rules only |
| `DOTASENSE_DB_PATH` | `./dotasense.db` | SQLite file |
| `OPENAI_API_KEY` | none | Optional LLM rewording of explanations (`app/ai/explanation.py`) |
| `DOTASENSE_LIVE_GSI` | `false` | Keep off until the policy review is done |

## Architecture

```
app/
  dashboard.py          Streamlit UI (dark theme, 7 sections)
  main.py               FastAPI: /health /state /analysis /coach/{match_id} /reports /gsi
  services.py           Glue: provider -> OpenDota data -> engines -> SQLite log
  models.py             Pydantic models (GameState, ItemRecommendation, Threat, ...)
  gsi/parser.py         GSI JSON -> GameState; records missing fields instead of guessing
  gsi/provider.py       MockProvider (active), LiveGSIProvider (disabled)
  gsi/receiver.py       GSI POST endpoint, 403 by default
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
| 4 | Live data | Blocked on policy review; receiver built but disabled |
| 5 | Post-match coach | First version (OpenDota stats, benchmarks, item timings). Next: compare timings with high-MMR players on the same hero |

## Known limitations
* The live screen uses mock data only; enemy lineup is manual.
* Roshan, tower and enemy positions are not available, so those hints are marked **uncertain**.
* Item timings need the match to be **parsed** on OpenDota; otherwise the report says so.
* Hero/item constants are a snapshot (see `app/data/snapshot/meta.json`); refresh when a patch lands.
* Streamlit is a browser dashboard, not yet a packaged Windows app (planned: PyInstaller or a native shell).

Data: [OpenDota API](https://docs.opendota.com/). Dota 2 is a trademark of Valve Corporation; this project is not affiliated with Valve.
