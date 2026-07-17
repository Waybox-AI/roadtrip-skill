# AGENTS.md — Universal Rulebook

Vendor-agnostic technical rules for working in this repo. Applies to any AI agent or
human. For product/domain background see [CONTEXT.md](CONTEXT.md).

## Branching Rule

- When creating git branches, if current base branch is not default branch (`main`), you should prompt user to specify
  base branch
- When submitting pull request (PR), you should set PR base branch as the current local base branch, instead of the
  browser github's default base branch

## Hard constraints

- **Python 3.8+ standard library only** for `assets/`, `scripts/`, and `tools/`. **No
  third-party pip packages** at runtime (`urllib`, `json`, `re`, `math`, …). Do **not**
  add runtime dependencies. Sole exception: `mcp_server/` depends on the `mcp` SDK
  (declared in `pyproject.toml`) — never let it leak into the other dirs. Dev
  dependencies are `pytest` plus `mcp` for `tests/test_mcp_server.py`, which
  auto-skips when `mcp` is absent so the stdlib+pytest baseline stays green.
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
python3 tools/places_client.py "Zzyzx, CA"   # place-name existence gate ("ABC" → no-match)

# MCP server: serve over stdio / run its tests (the one part that needs the mcp SDK)
pip install -e ".[dev]"                      # mcp SDK + pytest
python3 -m mcp_server.server
python3 -m pytest tests/test_mcp_server.py -v
```

Run the tests locally after **any** code change and report the result; add a matching
test in `tests/` for new clients/features — the Python must stay green. CI
(`.github/workflows/ci-cd.yml`) runs a lychee link check (markdown links) that gates
pytest on 3.12, then a PR-agent review, then a Feishu notification.

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
| `tools/*.py` | One data client per concern (routing, place validation, parks, weather, charging, fuel, lodging, border). Free/official API first, else a web-search `fallback(...)`. Never crash. |
| `tools/web_search.py` | Defines the `fallback(reason, queries, sources)` shape every client degrades to. |
| `assets/generate.py` | Validates (non-fatally) and injects `tripData.json` into `template.html` → `trip.html`. |
| `assets/template.html` | The browser view: map, day timeline, budget. All view logic lives here. |
| `assets/tripData.*.json` + `preview*.html` | Sample trips — double as test fixtures and living schema docs. |
| `mcp_server/` | MCP stdio server: `tools/*` + renderer + planning guide as 14 typed tools for any MCP host (Claude Code / Codex / Gemini CLI). Thin adapter — no planning logic. |
| `pyproject.toml` | Packaging for the `roadtrip-mcp` console script; the wheel vendors the server's runtime files under `mcp_server/_vendor/`. |
| `tests/` | pytest suite (stdlib + pytest only, except `test_mcp_server.py`). CI runs exactly this. |

### "I need to… → start here"

| Task | Where to start | Don't forget |
|------|----------------|--------------|
| Change the tripData schema | producing Python **+** `template.html` reader **+** `reference.md §1` | update the sample `tripData.*.json` too |
| Add a new data source | new `tools/<x>_client.py` | follow the client contract, add a `tests/` file, wrap it in `mcp_server/server.py` (+ schema test, `_TOOLS_GUIDE` entry) |
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
returning `{"source": "fallback", ...}`. When adding or editing a client:
- Return plain dicts/lists; include `"source"` so callers know provenance.
- Read keys from env vars only; degrade to `fallback(...)` when absent or on any
  exception. NWS, OSRM, and OSM tiles need no key.
- Keep the dual import guard (`from web_search import ...` /
  `except ImportError: from tools.web_search import ...`) so the file works both as a
  script and as a package import.
- Include an `if __name__ == "__main__":` smoke-test block, and add/update `tests/`.

### The MCP adapter (`mcp_server/`)
`mcp_server/server.py` exposes the clients, the renderer, and the skill docs over the
Model Context Protocol (stdio). It is a **thin adapter by contract**: input conversion
and delegation only — planning logic and HTTP belong in `tools/`, rendering in
`assets/generate.py`. Tool names are public API for host configs (`claude` / `codex` /
`gemini mcp add`) — change them additively only. Tool docstrings are what non-Claude
models read *instead of* `SKILL.md`, so keep the fallback-contract line and the
`get_planning_guide` pointers intact. File layout resolves via `_ROOT`: repo checkout
or, from an installed wheel, `mcp_server/_vendor/` — if a new file becomes a runtime
dependency of the server, add it to the `force-include` list in `pyproject.toml`.

### Keep the skill sources in sync
`SKILL.md`, `reference.md`, and the actual Python behavior must agree. A workflow step
that references a script/flag that no longer exists is a real bug. `reference.md` holds
the schema, reliability-grading rules, tool-routing table, and seasonal closure data.

### Stable public APIs
- `scripts/routes.py` is mounted on `sys.path` by an external webapp — keep its public
  API stable: `plan_routes`, `demo_routes`, `payload_to_text`, `extract_json`,
  `haversine_km`.
- `scripts/planner.py` is mounted the same way — keep `live_mode`, `generate_trip`,
  `regenerate_day`, `remove_city`, `set_nights`, `revise_stay`, `fix_endpoints`,
  `despread_stops`, `refresh_trip_weather`, `refresh_trip_fuel`,
  `refresh_trip_ev_corridor`, `refresh_trip_routing`, `refresh_trip_countdown`,
  `refresh_trip_lodging_links`, `refresh_trip_border`,
  `refresh_trip_route_options`, `weather_advisories` stable.
- Stay edits (`set_nights` / `revise_stay`) let the model return this stay's `lodging`
  and `bookingCountdown` alongside its `days`; night counts and `booked` stay
  code-owned. Bookings are matched to a stay by city name **or** by a stop name in
  its days (many bookings never name the town).
- **Weather provenance.** `weather_client.forecast()` tries NWS (US) then Open-Meteo
  (global, ~16-day, +precip-prob/wind); `climatology()` gives a seasonal average past
  the forecast window. On a trip day, `weather.source` is `"forecast"` or
  `"climatology"`; an untagged `weather` block is the model's own estimate. Never
  render or reason about a climatology average as if it were a forecast.
- **Post-generation backfill (single source of truth with the agent workflow).**
  After a live generation, `generate_trip` replaces every hard number the
  single-shot model path had to guess with the same `tools/` clients the agent
  workflow uses. In order: `refresh_trip_routing` (per-day miles/time from
  `routing_client`/OSRM, tagged `driveSource: "osrm"`; all-or-nothing, the
  great-circle fallback is never applied), `refresh_trip_fuel(trip, efficiency)`
  (fuel/charging budget line from `fuel_client.gas_cost` / `ev_cost`, tagged
  `source: "fuel_client"`, reliability stays `estimate`),
  `refresh_trip_ev_corridor` (`evPlan` from `charging_client.corridor` using the
  days' `driveMiles` + charge stops — purely computational),
  `refresh_trip_countdown` (bookingCountdown deadlines from
  `parks_client.book_by` release rules, tagged `source: "parks_client"`),
  `refresh_trip_lodging_links` (`lodging[].links` from
  `lodging_client.search_links`), `refresh_trip_border` (`crossBorder` from
  `border_client.trip_section` + `customs_client.personal_exemption`, driven by
  a model-emitted `crossings` structure list), and `refresh_trip_route_options`
  (`routeOptions[]` via `helper.compare_routes` when the webapp passes both
  phase-1 candidates as `payload["routes"]`). Every step is best-effort and
  never raises; existing sections and curated demo trips are left untouched.
- **Weather advisories.** `weather_advisories(trip)` is deterministic (no model
  call): per-day `{severity, source, condition, message}` or None. It only warns
  on days with a provenance tag — never on the model's own estimate — and speaks
  in the future tense for a forecast, in tendencies for a climatology average.
  Advice is a rule/phrase-bank, not AI-generated, so it can't hallucinate.

### `scripts/routes.py` live / offline dual-mode (webapp-only)
`plan_routes()` runs in one of two modes, chosen by `_live_mode()`:
- **Live:** `ANTHROPIC_API_KEY` is set **and** the `anthropic` package is importable →
  one fast model call (`ROADTRIP_MODEL`, default `claude-sonnet-4-6`) proposes two
  candidate routes.
- **Offline:** missing key or missing package → `demo_routes()` fallback: pick a curated
  sample by keyword-matching `start + destination` (e.g. tahoe / pnw, else the default
  example), then derive two variants (Scenic / Highlights) from it.

This is the webapp's Phase-1 step and is **not** part of the agent's `SKILL.md` workflow.
The skill itself is run *by* an LLM, so it never reads `ANTHROPIC_API_KEY` — consistent
with the zero-required-keys constraint above. Keep the offline branch crash-free.

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
