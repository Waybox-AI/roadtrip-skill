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
```

Run the tests locally after **any** code change — the Python must stay green. CI
(`.github/workflows/ci-cd.yml`) runs pytest on 3.12, then a PR-agent review, then a
Feishu notification.

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

### Keep the skill sources in sync
`SKILL.md`, `reference.md`, and the actual Python behavior must agree. A workflow step
that references a script/flag that no longer exists is a real bug. `reference.md` holds
the schema, reliability-grading rules, tool-routing table, and seasonal closure data.

### Stable public APIs
- `scripts/routes.py` is mounted on `sys.path` by an external webapp — keep its public
  API stable: `plan_routes`, `demo_routes`, `payload_to_text`, `extract_json`,
  `haversine_km`.

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
