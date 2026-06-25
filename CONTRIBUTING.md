# Contributing to RoadTrip Navigator

Thank you for your interest in contributing! This document covers everything
you need to get your changes reviewed and merged.

## Table of Contents

- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Running the tests](#running-the-tests)
- [Project structure](#project-structure)
- [Contribution types](#contribution-types)
  - [Bug reports](#bug-reports)
  - [Adding a sample trip](#adding-a-sample-trip)
  - [Modifying a tool client](#modifying-a-tool-client)
  - [Editing planning logic](#editing-planning-logic)
- [Pull request process](#pull-request-process)
- [Code style](#code-style)
- [License](#license)

---

## Ways to contribute

| Type | Where to start |
|---|---|
| Found a bug | Open an issue with steps to reproduce |
| Wrong data / outdated prices | Open an issue or PR with the corrected value |
| New sample trip | See [Adding a sample trip](#adding-a-sample-trip) |
| New tool client | Open an issue first to discuss scope |
| Docs / translations | PR directly against `README.md` or `README.zh.md` |
| Planning logic (`SKILL.md`) | Open an issue first — planning changes affect every route |

---

## Development setup

No build step, no virtual environment required for the core skill. Python 3.8+
and the standard library are all you need.

```bash
git clone https://github.com/Waybox-AI/roadtrip-skill
cd roadtrip-skill
```

**Verify the install works before making changes:**

```bash
# Renderer + bundled demo (should print "Wrote … 7 days")
python3 assets/generate.py assets/tripData.example.json -o /tmp/preview.html

# Slot parser
python3 scripts/helper.py "from Las Vegas, 7 days, 2 adults, gas, southwest loop"

# All tool clients (each should print JSON or a graceful fallback)
for f in tools/*.py; do echo "== $f =="; python3 "$f" > /dev/null && echo ok; done
```

**Optional API keys** (better data, never required to run or test):

```bash
export NPS_API_KEY=...            # https://www.nps.gov/subjects/developer/
export OCM_API_KEY=...            # https://openchargemap.org/site/develop/api
export OPENWEATHER_API_KEY=...    # https://openweathermap.org/api
```

---

## Running the tests

```bash
python -m pytest tests/ -v
```

The suite uses only the standard library plus `pytest` — install it with:

```bash
pip install pytest
```

All tests must pass before you open a PR. If you add a new feature or fix a
bug, add a corresponding test.

---

## Project structure

```
roadtrip-navigator/
├── SKILL.md          Agent entry point: triggers, two modes, 7-step workflow
├── reference.md      tripData schema, reliability grading, tool routing table
├── examples.md       Worked prompts (light / heavy / EV / cross-border)
├── assets/
│   ├── generate.py           tripData JSON → single-file HTML itinerary
│   ├── template.html         Leaflet map + timeline renderer
│   └── tripData.*.json       Curated sample itineraries
├── scripts/
│   └── helper.py             Slot parser, region detection, route comparison
├── tools/                    Per-source API clients (each with search fallback)
│   ├── routing_client.py
│   ├── parks_client.py
│   ├── weather_client.py
│   ├── charging_client.py
│   ├── border_client.py
│   ├── fuel_client.py
│   └── lodging_client.py
└── tests/
    ├── test_generate.py
    ├── test_helper.py
    ├── test_routing_client.py
    ├── test_parks_client.py
    ├── test_charging_client.py
    └── integration/
```

---

## Contribution types

### Bug reports

Open a [GitHub issue](https://github.com/Waybox-AI/roadtrip-skill/issues) with:

- What you did (the prompt or code path)
- What you expected
- What actually happened (paste the full error or the wrong output)
- Python version and OS

### Adding a sample trip

Sample trips live in `assets/tripData.*.json` and follow the schema defined in
`reference.md`. A good sample trip:

- Covers a region or route not already represented
- Is accurate — verify driving distances, overnight locations, and must-book
  items before submitting
- Includes at least 3 days and realistic `budget`, `lodging`, and
  `bookingCountdown` sections
- Renders correctly: run `python3 assets/generate.py assets/tripData.yours.json`
  and open the output HTML to check the map and timeline

Name the file `tripData.<short-slug>.json` (e.g. `tripData.rockies.json`).

### Modifying a tool client

Each file in `tools/` handles one data source. Every client must:

1. Return a **graceful fallback** (never raise) when the API is offline or the
   key is missing — the agent must keep running without network access
2. Include a `if __name__ == "__main__":` block that exercises the main code
   path so `python3 tools/your_client.py` is a quick smoke test
3. Add or update tests in `tests/`

### Editing planning logic

`SKILL.md` and `reference.md` drive every route the agent produces. Changes
here affect all users, so:

- Open an issue describing the problem and your proposed fix before writing code
- Keep `reference.md` consistent with any schema changes in `generate.py`
- Update `examples.md` if new behaviour is best shown with a worked prompt

---

## Pull request process

1. **Fork** the repo and create a branch from `main`:
   ```bash
   git checkout -b fix/description-of-change
   ```

2. **Make your changes** and run the full test suite:
   ```bash
   python -m pytest tests/ -v
   ```

3. **Open a PR** against `main`. Use a short, descriptive title
   (e.g. `feat: add Rockies sample trip` or `fix: charging fallback returns empty list on timeout`).
   In the PR description, explain *why* the change is needed, not just *what* changed.

4. A maintainer will review within a few days. Please respond to review comments
   promptly and push follow-up commits to the same branch — do not close and
   re-open the PR.

5. Once approved, a maintainer will merge with a squash commit.

---

## Code style

- **Python 3.8+ stdlib only** for `assets/`, `scripts/`, and `tools/` — do not
  add third-party dependencies to the core skill
- `pytest` is the only dev dependency (for `tests/`)
- Follow the style of the surrounding file — 4-space indent, single quotes
  where the file uses them
- No linter is enforced, but keep lines under 100 characters where practical

---

## License

By contributing, you agree that your changes will be licensed under the
[MIT License](LICENSE) that covers this project.
