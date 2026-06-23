# Install — RoadTrip Navigator skill

## Requirements

- **Python 3.8+** (standard library only — no `pip install` needed to run).
- **Node.js** (optional) — only for the JS syntax self-check in `node -e`.
- An agent with a **web-search tool** (Claude Code / Codex / Cursor). The clients
  in `tools/` fall back to "search this" instructions when live APIs aren't
  reachable, and the agent runs those searches.
- Network access is **optional**: with no network and no API keys the skill still
  produces a full itinerary HTML (research falls back to web search / estimates).

## Install in Claude Code (plugin marketplace)

Two commands — no clone, no API key:

```text
/plugin marketplace add Waybox-AI/roadtrip-skill
/plugin install roadtrip-navigator@roadtrip-skill
```

## Install manually as an Agent Skill

Or copy/symlink the skill into your agent's skills directory so it can discover
`SKILL.md`:

```bash
git clone https://github.com/Waybox-AI/roadtrip-skill

# project-level
mkdir -p .claude/skills
cp -r roadtrip-skill .claude/skills/roadtrip-navigator

# or user-level
cp -r roadtrip-skill ~/.claude/skills/roadtrip-navigator
```

The agent loads the skill when a request matches the `read-when` triggers in
`SKILL.md` (road trip, self drive, 自驾, national park, EV road trip, …).

## Optional API keys (better data, never required)

Set as environment variables. Without them, each client returns a graceful
fallback rather than failing.

| Variable | Used by | Get it from | Cost |
|----------|---------|-------------|------|
| `NPS_API_KEY` | `tools/parks_client.py` | https://www.nps.gov/subjects/developer/ | free |
| `OCM_API_KEY` | `tools/charging_client.py` | https://openchargemap.org/site/develop/api | free |
| `OPENWEATHER_API_KEY` | `tools/weather_client.py` (fallback) | https://openweathermap.org/api | free tier |

No key needed for: **NWS** weather (`api.weather.gov`, US), **OSRM** routing
(public demo), **OpenStreetMap** map tiles (Leaflet), **Recreation.gov** links.

```bash
export NPS_API_KEY=...        # optional
export OCM_API_KEY=...        # optional
export OPENWEATHER_API_KEY=...# optional
```

## Verify the install

```bash
# 1) Renderer + bundled demo (should print "Wrote ... 7 days")
python3 assets/generate.py assets/tripData.example.json -o assets/preview.html

# 2) Open the result
open assets/preview.html        # macOS
xdg-open assets/preview.html    # Linux

# 3) Slot parser
python3 scripts/helper.py "from Las Vegas, 7 days, 2 adults, gas, southwest loop"

# 4) Tool clients (all should print JSON, falling back if offline)
for f in tools/*.py; do echo "== $f =="; python3 "$f" >/dev/null && echo ok; done
```

## Files

```
roadtrip-navigator/
├── SKILL.md                 entry: triggers, two modes, 7-step workflow
├── reference.md             tripData schema, reliability grading, tool routing
├── examples.md              worked prompts (light/heavy/EV/cross-border)
├── INSTALL.md               this file
├── assets/
│   ├── template.html        single-file HTML renderer (Leaflet + timeline)
│   ├── generate.py          tripData.json → HTML
│   ├── tripData.example.json Southwest 7-day demo data
│   ├── preview.html         rendered Southwest demo
│   ├── tripData.tahoe.json  Sunnyvale→Tahoe 3-day demo data
│   ├── preview-tahoe.html   rendered Tahoe demo
│   ├── tripData.pnw.json    Seattle→Vancouver EV cross-border demo data
│   └── preview-pnw.html     rendered PNW demo (route compare + border + EV)
├── scripts/
│   └── helper.py            parsing, mode/region detection, compare_routes()
└── tools/                   per-source clients (each with a web-search fallback)
    ├── web_search.py        universal fallback payload builder
    ├── routing_client.py    OSRM route distance/time + haversine fallback
    ├── parks_client.py      NPS API + reservation countdown
    ├── weather_client.py    NWS forecast by lat/lng
    ├── charging_client.py   Open Charge Map + EV leg check + corridor() SoC sim
    ├── border_client.py     US↔CA↔MX documents/insurance/units checklist
    ├── fuel_client.py       fuel / charging cost estimator
    └── lodging_client.py    lodging search links + reference pricing
```
