# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This is **not a running application** — it is a **Claude Code plugin / agent skill** ("RoadTrip Navigator"). The deliverable is `SKILL.md` (the workflow an agent follows) plus a set of small, dependency-light Python helpers in `scripts/`, `tools/`, and `assets/` that the agent shells out to while planning a road trip. The final artifact a user receives is a single self-contained `trip.html` file.

When editing, remember the two audiences:
- **The agent** reads `SKILL.md` / `reference.md` / `examples.md` as instructions. These are the "source code" of the skill's behavior — keep them accurate; they are load-bearing, not docs.
- **The Python** is glue the agent calls. It must run with **zero required API keys** and **no third-party pip packages** (stdlib only — `urllib`, `json`, `re`, `math`). Do not add runtime dependencies.

## Commands

Use `python3` (there is no `python` on the standard dev machine).

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

# Exercise the helper / clients standalone (each has a __main__ demo)
python3 scripts/helper.py "from Las Vegas, 7 days, 2 adults, gas, southwest loop"
python3 scripts/helper.py --compare              # route-comparison demo
python3 tools/charging_client.py --corridor      # EV state-of-charge sim demo
python3 tools/routing_client.py 36.17,-115.14 37.30,-113.03
```

CI (`.github/workflows/ci-cd.yml`): runs pytest on 3.12, then a PR-agent code review, then a Feishu notification. Run the tests locally after any code change (per the project convention) — the Python must stay green.

## Architecture

### Data / view separation (the central design rule)
Planning never emits HTML directly. It emits **one `tripData.json`** conforming to the schema in `reference.md §1`. Then:

```
tripData.json ──► assets/generate.py ──► (injects into) assets/template.html ──► trip.html
```

`generate.py` replaces the literal token `__TRIP_DATA__` inside a `<script>` in `template.html`. All view logic lives in the browser (Leaflet map + timeline + budget); Python only validates and injects. This means data is **editable and re-renderable** — change the JSON, re-run `generate.py`. If you change the schema, you must touch **both** the producing code and `template.html`'s reader, and update `reference.md`.

- `generate.py` validation is **intentionally non-fatal**: it emits `[warn]` lines and still writes a usable page from partial data. Preserve that — don't turn warnings into hard errors.
- The only hard failure is a missing `__TRIP_DATA__` token. There's also a `syntax_check` that re-parses the injected JSON.
- Injection escapes `</script>` and `<!--` to prevent breaking out of the script element — keep that if you touch `build_html`.

### The tool-client contract (`tools/*.py`)
Every client targets a **free/official API first, then falls back to a structured web-search instruction** — it never crashes on a missing key or a network failure. The fallback shape comes from `tools/web_search.py:fallback(reason, queries, sources)` returning `{"source": "fallback", ...}`. The agent (which has its own web-search tool) is expected to execute those queries. When adding or editing a client:
- Return plain dicts/lists; include `"source"` so callers know provenance.
- Read keys from env vars only (`NPS_API_KEY`, `OCM_API_KEY`, `OPENWEATHER_API_KEY`); degrade to `fallback(...)` when absent or on any exception. NWS, OSRM, and OSM tiles need no key.
- Each file has a dual import guard (`from web_search import ...` / `except ImportError: from tools.web_search import ...`) so it works both as a script and as a package import. `tests/conftest.py` puts the repo root on `sys.path`.

Notable non-trivial logic:
- `tools/charging_client.py:corridor()` — leg-by-leg EV state-of-charge simulation (linear range model, winter derate, per-stop recommended charge-to). Powers the `evPlan` schema section.
- `tools/routing_client.py` — OSRM driving distance/time, falling back to haversine × road-winding factor.
- `scripts/helper.py` — regex slot-filling from the user's request; detects **entry mode** (light "plan it" vs. heavy "verify my route"), **region theme**, vehicle, days, party, dates. Output is *hints*, not authoritative parsing. Also hosts `compare_routes()` / `drive_intensity()` for the `routeOptions` section.
- `scripts/routes.py` — proposes two candidate routes; used by an external webapp that mounts this repo's `scripts/` on `sys.path`, so keep its public API (`plan_routes`, `demo_routes`, `payload_to_text`, `extract_json`, `haversine_km`) stable.

### The skill workflow
`SKILL.md` defines a 7-step flow (slot-fill → route → **daily driving segmentation** → parallel sub-agent research → reservation countdown → graded budget → render HTML). The daily-segmentation and reservation-countdown steps are the skill's reason to exist — they're what a generic "list of attractions" answer misses. `reference.md` is the companion: schema, the reliability-grading rules (`verified`/`reference`/`estimate`), the tool-routing table, and seasonal closure data. Keep `SKILL.md`, `reference.md`, and the actual Python behavior in sync — a workflow step that references a script/flag that no longer exists is a real bug.

## Conventions

- **Units:** miles / °F / MPG / USD by default; switch to km/°C/local currency on Canadian/Mexican legs (the `crossBorder` module encodes this).
- **Honesty boundaries** (see `SKILL.md`): never fabricate live fuel prices, live charger occupancy, minute-level traffic, or live campground availability. Point to the official app instead. Every generated page carries a disclaimer.
- Sample/demo assets (`assets/tripData.*.json` + matching `preview*.html`) double as fixtures and living documentation of the schema — update them when the schema changes.
