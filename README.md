<div align="center">

<!-- Keep whatever logo path the repo currently uses -->
<img src="assets/logo.png" width="88" alt="RoadTrip Navigator" />

# RoadTrip Navigator

**An AI agent skill that turns "start + days" into a road trip you can actually drive.**

English · [简体中文](README.zh.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Claude Code + 16 agents](https://img.shields.io/badge/works%20with-Claude%20Code%20%2B%2016%20agents-blue.svg)](INSTALL.md)
[![No API keys required](https://img.shields.io/badge/API%20keys-none%20required-brightgreen.svg)](#how-it-works)
[![Try it in your browser](https://img.shields.io/badge/web%20version-roadtripskill.dev-orange.svg)](https://roadtripskill.dev)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-blueviolet.svg)](CONTRIBUTING.md)

</div>

<!-- TODO: 30–45s demo per launch checklist: install → prompt → itinerary streams out → one edit → web version outro -->

<div align="center">
    <img src="assets/demo.gif" />
</div>

A North American road trip is won or lost in the car, not at the airport: how far do we drive today, where do we sleep, will the charge last, is the pass even open? RoadTrip Navigator plans around exactly those questions, then hands you the answer as **a single HTML file** — a map-first, day-by-day itinerary that opens on your phone with no signal.

See a finished trip before you install:


[Southwest loop, 7 days](https://roadtripskill.dev/api/sample?name=sw) · [Sunnyvale → Lake Tahoe, 3 days](https://roadtripskill.dev/api/sample?name=tahoe) · [Seattle → Vancouver EV, 4 days](https://roadtripskill.dev/api/sample?name=pnw) · [Chicago loop, 5 days](https://roadtripskill.dev/api/sample?name=chicago)

Or skip the install entirely: the free web version at **[roadtripskill.dev](https://roadtripskill.dev)** plans the same trips in your browser.

## Quick start

Two commands in Claude Code, no API keys:

```
/plugin marketplace add Waybox-AI/roadtrip-skill
/plugin install roadtrip-navigator@roadtrip-skill
```

Then ask in plain English:

> Plan a 7-day Southwest national-parks loop from Las Vegas — 2 adults, gas SUV, September.

The skill activates on its own when it spots a road-trip request. Prefer to be explicit? There's a slash command that forces the same workflow:

```
/roadtrip from Las Vegas, 7 days, 2 adults, gas SUV, Southwest loop
```

Refine the plan the way you'd talk to a friend: "add a winery stop," "we're bringing the dog," "make day 4 shorter."

<details>
<summary><b>Other ways to install</b> — Codex, Cursor, and any agent that speaks the open SKILL.md standard</summary>

```
npx skills add Waybox-AI/roadtrip-skill
```

See [INSTALL.md](INSTALL.md) for manual setup and per-agent notes.
</details>

## What it checks that a chatbot won't

Most AI trip planners hand you a wishlist of attractions. The wishlist falls apart around day two. This fixes the five places where it breaks:

| | Generic AI itinerary | RoadTrip Navigator |
| --- | --- | --- |
| **Daily driving** | A pile of stops | Route sliced into days under a sane drive limit — overnight towns picked, arrive-before-dark and gate-hours checks on each day |
| **Reservations** | "Book early!" | A countdown with exact book-by dates on the right system (Recreation.gov / ReserveCalifornia / Parks Canada) — campgrounds open ~6 months out, in-park lodges ~13 |
| **Fuel / EV range** | Ignored | Warnings on long empty stretches; for EVs, a leg-by-leg state-of-charge simulation with winter derate |
| **Seasons** | Generic weather advice | Closure-aware routing — winter passes like Going-to-the-Sun, Tioga, and Trail Ridge; wildfire and snow reroutes |
| **Borders & time zones** | Arrival times that don't add up | Time-zone-corrected arrivals; US–CA–MX document, insurance, and crossing checklists |

Everything lands in one offline-friendly HTML file: a Leaflet / OpenStreetMap route map with numbered stops (each with a one-tap Google or Apple Maps link), a day-by-day timeline, the reservation countdown, and a budget in which every figure is graded **verified / reference / estimate** — so you know exactly what to double-check.

## Features

- **Plan or verify.** Start from scratch ("plan it for me" — start, region, days), or paste an itinerary you already have and let it stress-test the drive times, bookings, and closures.
- **Route comparison.** When two routes are viable, you get an A/B table — miles, days, drive intensity, best season, cost — with the recommendation flagged.
- **EV mode.** A per-leg charging corridor: state of charge, suggested charge-to levels, charger power, and an optional winter-range derate.
- **Cross-border module.** Per-crossing documents and customs notes, insurance rules (US policies work in Canada, not in Mexico), and mi/°F/USD ⇄ km/°C/CAD switching.
- **Reliability grading.** Every number is tagged verified, reference, or estimate. No confident nonsense.
- **Zero keys, works offline.** Each data client falls back to web search when it has no key, and the map degrades gracefully with no network at all.

## How it works

```
request ──► scripts/helper.py ──► 7-step workflow (SKILL.md)
              (slots, mode,        ├─ route + daily segmentation
               region)             ├─ parallel research (tools/, web search)
                                   ├─ reservation countdown
                                   └─ graded budget
                                        │
                        tripData.json ──┴──► assets/generate.py ──► trip.html
```

- **Data and view stay separate.** Everything lands in `tripData.json`; `generate.py` injects it into `assets/template.html`. Edit the JSON, re-render, done.
- **Research fans out.** Sub-agents hit official and free APIs first (NPS, NWS, Recreation.gov, Open Charge Map), with web search as the fallback.

Poke at it locally:

```bash
python3 assets/generate.py assets/tripData.example.json -o trip.html   # render the Southwest sample
python3 scripts/helper.py "from Las Vegas, 7 days, 2 adults, gas, southwest loop"
python3 tools/charging_client.py --corridor                            # EV state-of-charge sim
```

<details>
<summary><b>Optional API keys</b> — all optional; without them, clients fall back to web search</summary>

| Variable | Used for | Free key |
| --- | --- | --- |
| `NPS_API_KEY` | National-park info | [nps.gov/subjects/developer](https://www.nps.gov/subjects/developer/) |
| `OCM_API_KEY` | EV chargers | [openchargemap.org](https://openchargemap.org) |
| `OPENWEATHER_API_KEY` | Weather fallback | [openweathermap.org](https://openweathermap.org) |

NWS weather, OSRM routing, OpenStreetMap tiles, and Recreation.gov links need no key at all.
</details>

## What it won't do (on purpose)

No live fuel or electricity prices, no live charger occupancy or campground availability, no minute-by-minute traffic, and no turn-by-turn navigation — for those it points you to the official app, Recreation.gov, or the nav of your choice. There's also no bulk GPX/KML export: in testing, batch waypoint imports could route drivers onto seasonally closed roads, so every stop gets its own one-tap maps link instead. Each itinerary ships with a reminder to confirm the critical details against official sources.

## Project layout

```
.claude-plugin/    Plugin + marketplace manifests (Claude Code)
SKILL.md           Entry point: triggers, plan/verify modes, the 7-step workflow
reference.md       tripData schema, reliability grading, tool routing
AGENTS.md          Technical rules + worked prompts — plan, verify, EV, cross-border
assets/            generate.py, template.html, three demo trips
scripts/helper.py  Slot filling, mode and region detection, route comparison
tools/             One client per data source, each with a web-search fallback
```

If you're learning to write agent skills, this repo doubles as a worked example — start with [SKILL.md](SKILL.md).

## FAQ

**Why not just ask Claude or ChatGPT directly?**
For inspiration, absolutely do. But a raw prompt won't cap your daily driving, check pass closures, compute booking windows, or simulate charge state — and you can't hand a chat transcript to the person in the passenger seat.

**Is it safe to install a third-party skill?**
Fair question: skills can execute code in your environment, so only install ones you can read. This one is MIT-licensed, runs without keys, and phones nothing home — audit it first; that's what the license is for.

**I found a mistake in a plan.**
Please [open an issue](https://github.com/Waybox-AI/roadtrip-skill/issues). Route bugs — a wrong closure date, a bad booking window — are the most valuable reports we get, and they usually ship as data fixes within a release or two.

## Contributing

Issues and PRs welcome — add a region theme, a state DOT's closure data, a new `tools/` client, or a sample itinerary. The skill runs with no keys, so it's easy to hack on.

## 📄 License

[MIT](LICENSE) © yang-hong

---

<div align="center">
<sub>Built by <a href="https://waybox.ai">Waybox</a> — we also make OMO, an in-car AI companion. RoadTrip Navigator plans the trip; OMO rides along.</sub>
</div>
