# AGENTS.md — Universal Rulebook

Vendor-agnostic technical rules for working in this repo. Applies to any AI agent or
human. For product/domain background see [CONTEXT.md](CONTEXT.md).

## Hard constraints

- **Python 3.8+ standard library only** for `assets/`, `scripts/`, and `tools/`. **No
  third-party pip packages** at runtime (`urllib`, `json`, `re`, `math`, …). Do **not**
  add runtime dependencies. `pytest` is the *only* dev dependency, used solely by
  `tests/`.
- **Zero required API keys.** Everything must run and test with no keys and no network.
  Keys (`NPS_API_KEY`, `OCM_API_KEY`, `OPENWEATHER_API_KEY`) are read from env vars
  only and are strictly optional upgrades.
- Use `python3` (there is no `python` on the standard dev machine).

## Commands

```bash
# One-time: venv + test dependency (only pytest is needed)
python3 -m venv .venv && . .venv/bin/activate && pip install pytest

# Run the full test suite (CI runs exactly this)
python3 -m pytest tests/ -v

# Run a single test file / test
python3 -m pytest tests/test_generate.py -v
python3 -m pytest tests/test_helper.py -k drive_intensity -v

# Render a tripData JSON into the single-file HTML (the core output step)
python3 assets/generate.py assets/tripData.example.json -o trip.html

# Exercise helpers / clients standalone (each has a __main__ demo)
python3 scripts/helper.py "from Las Vegas, 7 days, 2 adults, gas, southwest loop"
python3 scripts/helper.py --compare
python3 tools/charging_client.py --corridor
python3 tools/routing_client.py 36.17,-115.14 37.30,-113.03

# Render the other bundled demo trips
python3 assets/generate.py assets/tripData.tahoe.json -o assets/preview-tahoe.html
python3 assets/generate.py assets/tripData.pnw.json   -o assets/preview-pnw.html

# Probe other data sources directly
python3 tools/border_client.py US MX --rental
python3 tools/parks_client.py --countdown 2026-09-12
python3 tools/charging_client.py --leg 165 280
```

Run the tests locally after **any** code change and report the result; add a matching
test in `tests/` for new clients/features — the Python must stay green. CI
(`.github/workflows/ci-cd.yml`) runs a lychee link check (markdown links) that gates
pytest on 3.12, then a PR-agent review, then a Feishu notification.

## Installing manually (outside the plugin marketplace)

The README's Quick start covers the common case (`/plugin marketplace add` +
`/plugin install`). To install by hand — e.g. to track a branch, or for an
agent that doesn't support the marketplace — copy or symlink the repo into an
agent's skills directory so it can discover `SKILL.md`:

```bash
git clone https://github.com/Waybox-AI/roadtrip-skill
mkdir -p .claude/skills                                   # project-level
cp -r roadtrip-skill .claude/skills/roadtrip-navigator
# or ~/.claude/skills/roadtrip-navigator for user-level
```

The agent loads the skill when a request matches the `read-when` triggers in
`SKILL.md` (road trip, self drive, 自驾, national park, EV road trip, …). No
API keys are required to run it. An agent using the skill needs a
**web-search tool** — `tools/*` fall back to search-query instructions when
live APIs aren't reachable — and network access itself is optional: with
none at all, the skill still produces a full itinerary from fallbacks and
estimates. Node.js is optional too, useful only for an ad hoc `node -e` JS
sanity check when debugging `template.html` — nothing in the repo requires it.

### Optional API keys

Without these, each client returns a graceful fallback rather than failing.

| Variable | Used by | Get it from |
|----------|---------|-------------|
| `NPS_API_KEY` | `tools/parks_client.py` | nps.gov/subjects/developer |
| `OCM_API_KEY` | `tools/charging_client.py` | openchargemap.org/site/develop/api |
| `OPENWEATHER_API_KEY` | `tools/weather_client.py` (fallback) | openweathermap.org/api |

No key needed for **NWS** weather, **OSRM** routing, **OpenStreetMap** tiles,
or **Recreation.gov** links.

### Verify a fresh checkout

```bash
python3 assets/generate.py assets/tripData.example.json -o assets/preview.html
open assets/preview.html        # macOS; xdg-open on Linux
for f in tools/*.py; do echo "== $f =="; python3 "$f" >/dev/null && echo ok; done
```

## Orientation map

New here? Read this section first — it's the fastest way to build a mental model.

### The pipeline (data flows one direction)

```
user request
  └─ scripts/helper.py      slot-fill + entry-mode/region detection (hints, not truth)
       └─ tools/*.py         fetch each data concern (route, parks, weather, EV, …)
            └─ tripData.json  the ONE canonical data object (schema: reference.md §1)
                 └─ assets/generate.py   inject into the __TRIP_DATA__ token
                      └─ assets/template.html   Leaflet map + timeline + budget (all view logic)
                           └─ trip.html   the single self-contained file the user receives
```

Planning never emits HTML — it only produces `tripData.json`. Everything downstream
is deterministic rendering. (See "Data / view separation" below.)

### File → role

| File | One-line job |
|------|--------------|
| `SKILL.md` | The 7-step workflow the agent follows. Load-bearing "source code" of behavior. |
| `reference.md` | Companion spec: schema (§1), reliability grades (§2), tool-routing table (§3), drive limits (§4), seasonal closures (§5). |
| `scripts/helper.py` | Regex slot-filling from the user's request; entry-mode + region detection; `compare_routes()` / `drive_intensity()`. Output is *hints*. |
| `scripts/routes.py` | Two candidate routes for the **external webapp** (live model call or offline sample fallback). Not used by the skill workflow. |
| `tools/*.py` | One data client per concern (routing, parks, weather, charging, fuel, lodging, border). Free/official API first, else a web-search `fallback(...)`. Never crash. |
| `tools/web_search.py` | Defines the `fallback(reason, queries, sources)` shape every client degrades to. |
| `assets/generate.py` | Validates (non-fatally) and injects `tripData.json` into `template.html` → `trip.html`. |
| `assets/template.html` | The browser view: map, day timeline, budget. All view logic lives here. |
| `assets/tripData.*.json` + `preview*.html` | Sample trips — double as test fixtures and living schema docs. |
| `tests/` | pytest suite (stdlib + pytest only). CI runs exactly this. |

### "I need to… → start here"

| Task | Where to start | Don't forget |
|------|----------------|--------------|
| Change the tripData schema | producing Python **+** `template.html` reader **+** `reference.md §1` | update the sample `tripData.*.json` too |
| Add a new data source | new `tools/<x>_client.py` | follow the client contract, add a `tests/` file |
| Change how requests are parsed | `scripts/helper.py` | it emits hints, not authoritative parsing |
| Add a sample trip | `assets/tripData.<name>.json` + matching `preview*.html` | wire keyword match in `routes.demo_routes()` if webapp should pick it |
| Edit the rendered page | `assets/template.html` (+ `generate.py` if injection changes) | keep the `__TRIP_DATA__` escaping |
| Change the workflow itself | `SKILL.md` | keep `SKILL.md` / `reference.md` / Python in sync |

## Architecture rules

### Data / view separation (the central design rule)
Planning never emits HTML directly. It emits **one `tripData.json`** (schema in
`reference.md §1`), then:

```
tripData.json ──► assets/generate.py ──► (injects into) assets/template.html ──► trip.html
```

`generate.py` replaces the literal token `__TRIP_DATA__` inside a `<script>` in
`template.html`. All view logic lives in the browser (Leaflet map + timeline + budget);
Python only validates and injects. If you change the schema, you must touch **both** the
producing code and `template.html`'s reader, **and** update `reference.md`.

- `generate.py` validation is **intentionally non-fatal**: it emits `[warn]` lines and
  still writes a usable page from partial data. **Preserve this** — do not turn warnings
  into hard errors.
- The only hard failure is a missing `__TRIP_DATA__` token. A `syntax_check` re-parses
  the injected JSON.
- Injection escapes `</script>` and `<!--` to prevent breaking out of the script
  element — keep that if you touch `build_html`.

### The tool-client contract (`tools/*.py`)
Every client targets a **free/official API first, then falls back to a structured
web-search instruction** — it never crashes on a missing key or network failure. The
fallback shape comes from `tools/web_search.py:fallback(reason, queries, sources)`
returning `{"source": "fallback", ...}`. One file per concern:
- `web_search.py` — universal fallback payload builder
- `routing_client.py` — OSRM distance/time + haversine fallback
- `parks_client.py` — NPS API + reservation countdown
- `weather_client.py` — NWS forecast by lat/lng
- `charging_client.py` — Open Charge Map + EV leg check + `corridor()` SoC sim
- `border_client.py` — US↔CA↔MX documents/insurance/units checklist
- `fuel_client.py` — fuel / charging cost estimator
- `lodging_client.py` — lodging search links + reference pricing

When adding or editing a client:
- Return plain dicts/lists; include `"source"` so callers know provenance.
- Read keys from env vars only; degrade to `fallback(...)` when absent or on any
  exception. NWS, OSRM, and OSM tiles need no key.
- Keep the dual import guard (`from web_search import ...` /
  `except ImportError: from tools.web_search import ...`) so the file works both as a
  script and as a package import.
- Include an `if __name__ == "__main__":` smoke-test block, and add/update `tests/`.

### Keep the skill sources in sync
`SKILL.md`, `reference.md`, and the actual Python behavior must agree. A workflow step
that references a script/flag that no longer exists is a real bug. `reference.md` holds
the schema, reliability-grading rules, tool-routing table, and seasonal closure data.

### Two consumers of this repo
The same code is used by two very different callers. Keeping them straight avoids a
whole class of mistakes.

| | **Agent skill** | **External webapp** |
|---|---|---|
| Who runs it | an LLM agent (e.g. Claude Code) | a normal web server |
| Entry point | `SKILL.md` (read as instructions) | imports `scripts/routes.py` |
| Where the "intelligence" comes from | the LLM itself, reasoning through `SKILL.md` | a Claude API call |
| Uses `scripts/routes.py`? | no — uses `scripts/helper.py` | yes — calls `plan_routes()` |
| Needs `ANTHROPIC_API_KEY`? | **no** | **yes** (else falls back to samples) |

The agent skill is run *by* an LLM, so it never needs to "call" a model — and
therefore never reads `ANTHROPIC_API_KEY`. That key belongs entirely to the webapp
path, consistent with the zero-required-keys constraint above.

### Stable public APIs
- `scripts/routes.py` is mounted on `sys.path` by an external webapp — keep its public
  API stable: `plan_routes`, `demo_routes`, `payload_to_text`, `extract_json`,
  `haversine_km`.

### `scripts/routes.py` live / offline dual-mode (webapp-only)
`plan_routes()` runs in one of two modes, chosen by `_live_mode()` (`scripts/routes.py:41`):
- **Live:** `ANTHROPIC_API_KEY` is set **and** the `anthropic` package is importable →
  one fast model call (`ROADTRIP_MODEL`, default `claude-sonnet-4-6`) proposes two
  candidate routes.
- **Offline:** missing key or missing package → `demo_routes()` (`scripts/routes.py:253`)
  fallback: pick a curated sample by keyword-matching `start + destination`, then
  derive two variants (`Scenic` = every stop, `Highlights` = every other stop) from it.

Curated samples the offline path selects from (`assets/`):

| Keyword match (in `start + destination`) | Sample file |
|---|---|
| `tahoe`, `sacramento`, `sierra` | `tripData.tahoe.json` |
| `vancouver`, `canada`, `whistler`, `seattle`, `bc` | `tripData.pnw.json` |
| `chicago`, `illinois`, `indiana`, `oak park` | `tripData.chicago.json` ⚠️ missing — see Known issues |
| (anything else — default) | `tripData.example.json` |

This is the webapp's Phase-1 step and is **not** part of the agent's `SKILL.md` workflow
— do not wire `ANTHROPIC_API_KEY` or `scripts/routes.py` into the skill. Keep the
offline branch crash-free.

## Worked examples

Illustrative prompt → agent-flow walkthroughs, one per notable path through the
workflow. Adapt these, don't follow them verbatim.

### Light mode — plan it for me
> "Plan a 7-day road trip from Las Vegas through the Southwest national parks
> for 2 adults in mid-September. Renting a gas SUV, want a loop back to Vegas."

`scripts/helper.py` → mode=light, region=desert, all slots present. Draft two
route candidates and let the user pick (e.g. "Grand Circle Classic" ≈1,180 mi
vs. "Fast Loop" ≈820 mi), segment into days under the drive limit, run
parallel research (weather, lodging, fuel, park passes), build the
reservation countdown (timed-entry tours ~T-30d, in-park lodges ~T-13mo),
grade the budget, then emit `tripData.json` + `trip.html`. See
`assets/preview.html` for this exact trip rendered.

### Heavy mode — verify my route
> "Here's my plan, can you check it and make a page? Day 1: Seattle → Port
> Angeles. Day 2: Olympic NP. Day 3: → Forks → coast. Day 4: → Seattle. 4 days,
> 2 adults + 1 kid, gas, late October."

`helper.py` detects mode=heavy from multiple "Day N" lines. Parse their days
into the schema instead of re-planning; verify each leg against the
with-kids drive limit, ferry logistics, and daylight; fill gaps (fuel stops,
weather, lodging); flag seasonal closures (e.g. a mountain road that closes on
snow days) with an alternative; call out anything that didn't check out (e.g.
"Day 3 as written is ~5.5h driving with a kid — suggest splitting").

### EV corridor
> "EV road trip, Tesla-ish ~280 mi range, San Francisco to LA via Highway 1, 3
> days, couple."

Run `tools/charging_client.corridor(legs, 280, winter_derate=0.25)` for a
per-leg state-of-charge table with recommended charge-to levels, written to
`evPlan` — sparse stretches (e.g. Big Sur) surface as a low-arrival-SoC
warning. `fuel_client.ev_cost(...)` feeds the budget. See
`assets/preview-pnw.html` for a rendered EV corridor.

### Cross-border
> "Seattle to Banff and Jasper, 6 days, 2 adults, gas."

`crossBorder=true` → `tools/border_client.trip_section([("US","CA",rental),
("CA","US",rental)])` builds a per-crossing documents/insurance/customs/
unit-switch checklist. Switch to km/°C/CAD on the Canadian legs. Use Parks
Canada (not Recreation.gov) for reservations. Key asymmetry the tool encodes:
US insurance usually works in Canada, but Mexico always requires buying local
insurance. See `assets/preview-pnw.html` for a rendered cross-border + EV +
route-comparison page.

## Known issues

### Offline `demo_routes()` crashes on Chicago-area input
`demo_routes()` maps `chicago` / `illinois` / `indiana` / `oak park` to
`tripData.chicago.json` (`scripts/routes.py:261-262`), **but that sample file does not
exist** in `assets/` (only `tripData.example.json`, `tripData.pnw.json`, and
`tripData.tahoe.json` are present).

- **Effect:** in offline mode, any Chicago-area `start`/`destination` hits
  `open(... "tripData.chicago.json")` and raises `FileNotFoundError`, which violates
  the "offline branch must never crash" contract above.
- **Repro:**
  ```python
  from scripts.routes import demo_routes
  demo_routes({"start": "Chicago, IL", "destination": "Indiana Dunes"})
  # -> FileNotFoundError: ... tripData.chicago.json
  ```
- **Fix options (pick one):** add a real `assets/tripData.chicago.json` sample (plus
  its `preview*.html`); remove the `chicago` branch so Chicago-area input falls
  through to the default `tripData.example.json`; or make the file load defensive —
  fall back to `tripData.example.json` if the chosen sample is missing.

## Conventions

- **Units:** miles / °F / MPG / USD by default; km / °C / local currency on
  Canadian/Mexican legs (`crossBorder` encodes this).
- **Honesty boundaries:** never fabricate live fuel prices, live charger occupancy,
  minute-level traffic, or live campground availability. Point to the official app
  instead. Every generated page carries a disclaimer.
- Sample/demo assets (`assets/tripData.*.json` + matching `preview*.html`) double as
  fixtures and living schema documentation — update them when the schema changes.
- Follow the surrounding file's style: 4-space indent, single quotes where the file
  uses them, lines under ~100 chars where practical. No linter is enforced.
- **Be terse and technical when reporting work.** No sycophantic preambles or
  restating the task — state what changed and the verification command you ran.
