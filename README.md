<div align="center">

<img src="assets/readme-hero.png" alt="RoadTrip Navigator" />

# RoadTrip Navigator

**A road trip plan, checked before you drive.**

Plan a route from scratch—or paste the itinerary you already made. RoadTrip Navigator checks the details that decide whether the trip actually works, then turns it into one shareable, offline-friendly itinerary.

English · [简体中文](README.zh.md)

[![CI/CD Status](https://img.shields.io/github/actions/workflow/status/Waybox-AI/roadtrip-skill/ci-cd.yml?branch=main&label=CI/CD&style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/Waybox-AI/roadtrip-skill/actions/workflows/ci-cd.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge)](LICENSE)
[![Claude Code + compatible agents](https://img.shields.io/badge/works%20with-Claude%20Code%20%2B%20compatible%20agents-blue.svg?style=for-the-badge)](INSTALL.md)
[![No API keys required](https://img.shields.io/badge/API%20keys-none%20required-brightgreen.svg?style=for-the-badge)](#install)
[![Try it in your browser](https://img.shields.io/badge/web%20version-roadtripskill.dev-orange.svg?style=for-the-badge)](https://roadtripskill.dev)

</div>

<div align="center">
  <img src="assets/demo.gif" alt="RoadTrip Navigator demo" />
</div>

## Two ways to start

### Plan one

> Plan a 7-day Southwest national-parks loop from Las Vegas—2 adults, gas SUV, September.

RoadTrip Navigator proposes two viable routes, helps you choose, and builds the trip around realistic driving days, overnight stops, bookings, weather, fuel or charging, and seasonal road access.

### Check one

> Here is my itinerary. Tell me what is unrealistic, risky, or missing—and fix it without changing the parts that already work.

Paste day-by-day text, a linked plan, or an itinerary you already drafted. The skill keeps your route as the starting point, stress-tests it, and calls out problems such as:

```text
⚠ Day 3 is about 5.5 hours of driving with a child in the car.
  Suggested fix: overnight in Forks and move the coast stops to Day 4.

⚠ Arrival is after sunset and after the park gate closes.
  Suggested fix: leave 90 minutes earlier or move the hike to tomorrow.

⚠ This mountain pass is normally closed for your travel date.
  Suggested fix: use the winter route and add 42 miles.

⚠ Estimated EV arrival charge is below the trip buffer.
  Suggested fix: add a mid-route DC fast-charge stop.
```

The result is not just a list of recommendations. It is a revised itinerary that explains what passed, what did not, and what still needs confirmation.

## What gets checked

Most AI trip planners are good at inspiration. Road trips fail in the operational details.

| Reality check | Generic AI itinerary | RoadTrip Navigator |
| --- | --- | --- |
| **Daily driving** | A sequence of stops | Routes each day against a realistic drive limit, overnight location, daylight, and gate hours |
| **Place names and routing** | Quietly accepts bad inputs | Validates user-supplied places and backfills per-day distance and drive time from routing tools when available |
| **Weather and seasons** | Generic packing advice | Separates live forecast from climatology, surfaces weather advisories, and flags seasonal closures or reroutes |
| **Reservations** | “Book early” | Builds dated booking tasks on the appropriate system and organizes hotels, restaurants, and attractions |
| **Fuel and EV range** | Usually ignored | Recomputes energy cost, warns about sparse corridors, simulates leg-by-leg state of charge, and can add mid-route fast charging |
| **Borders and time zones** | Arrival times that do not add up | Corrects time-zone effects and adds US–Canada–Mexico document, insurance, customs, and exemption notes |
| **Prices and confidence** | Precise-looking guesses | Labels figures as verified, reference, or estimate; shows prices only when they can be supported |

## One file for the whole car

The final deliverable is a single `trip.html` file built from an editable `tripData.json`.

Open it on a phone. Send it to the passenger seat. Print it. Share it. Re-render it after an edit.

It contains:

- A map-first route with numbered stops.
- One-tap Google Maps and Apple Maps links for each leg.
- A complete daily timeline with weather, meals, activities, lodging, and warnings.
- Booking views for every stay, meal, and attraction—not only the ones with deadlines.
- A route comparison when two viable options exist.
- A budget that updates when the itinerary changes.
- EV charging details and border logistics when relevant.
- Responsive styling, print colors, and a built-in share action.

The itinerary data remains available offline. Network-dependent maps and links degrade gracefully.

See a finished trip before installing:

[Southwest loop, 7 days](https://roadtripskill.dev/api/sample?name=sw) · [Sunnyvale → Lake Tahoe, 3 days](https://roadtripskill.dev/api/sample?name=tahoe) · [Seattle → Vancouver EV, 4 days](https://roadtripskill.dev/api/sample?name=pnw) · [Chicago loop, 5 days](https://roadtripskill.dev/api/sample?name=chicago)

Or use the free browser version at **[roadtripskill.dev](https://roadtripskill.dev)**.

## Change your mind without rebuilding everything

Road trips evolve. Edit the plan in ordinary language:

```text
Make Day 4 shorter.
Remove Monterey and reconnect the route.
Stay two nights in Banff.
Rewrite the Lake Tahoe stay around a quieter hotel.
Add a mid-route charging stop.
Refresh the weather and budget.
```

The planning layer can update affected days and then refresh derived sections such as mileage, weather, fuel cost, EV corridor, booking countdown, lodging links, border information, and route comparison.

## Designed to show its work

“Checked” does not mean “guaranteed.” It means the itinerary has been run through explicit feasibility checks and its remaining uncertainty is visible.

- **Official and free sources first.** Routing, parks, weather, charging, border, and lodging helpers prefer official or open sources and fall back to structured web research.
- **Source-aware weather.** A short-range forecast is not presented as the same thing as a historical climate average.
- **Reliability grading.** Numbers are marked `verified`, `reference`, or `estimate` so you know what to trust and what to recheck.
- **Best-effort backfill.** Hard numbers such as daily route distance, energy cost, EV corridor, booking dates, lodging links, border notes, and route comparisons are refreshed by deterministic tools when possible.
- **Clear limits.** Every itinerary reminds you to confirm critical details with official sources before departure.

North America is the deepest-supported region. For China-domestic itineraries, localized output includes CNY budgets and Ctrip lodging links where supported.

## Install

### Claude Code

```text
/plugin marketplace add Waybox-AI/roadtrip-skill
/plugin install roadtrip-navigator@roadtrip-skill
```

Then ask for a road trip in ordinary language. The skill activates automatically; `/roadtrip` is available when you want to invoke it explicitly.

### Codex, Cursor, and other SKILL.md-compatible agents

```bash
npx skills add Waybox-AI/roadtrip-skill
```

See [INSTALL.md](INSTALL.md) for per-agent and manual installation notes.

### MCP server

The routing, weather, park, charging, border, lodging, place-validation, and rendering tools are also available as a 14-tool MCP server for Codex, Gemini CLI, Claude Code, and other MCP hosts.

```bash
# OpenAI Codex CLI
codex mcp add roadtrip -- uvx --from git+https://github.com/Waybox-AI/roadtrip-skill roadtrip-mcp

# Google Gemini CLI
gemini mcp add roadtrip uvx --from git+https://github.com/Waybox-AI/roadtrip-skill roadtrip-mcp

# Claude Code
claude mcp add roadtrip -- uvx --from git+https://github.com/Waybox-AI/roadtrip-skill roadtrip-mcp
```

The skill carries the planning discipline; the MCP server carries the typed execution tools. See [mcp_server/README.md](mcp_server/README.md).

## How it works

```text
request or existing itinerary
        │
        ▼
scripts/helper.py ── mode, required inputs, region hints
        │
        ▼
SKILL.md workflow ── plan or verify ── research and feasibility checks
        │
        ▼
tripData.json ── structured itinerary and reliability metadata
        │
        ▼
assets/generate.py + assets/template.html
        │
        ▼
trip.html ── map, timeline, bookings, budget, warnings, share and print
```

Planning data and presentation stay separate: edit the JSON, render again, and keep the final page deterministic.

## What it deliberately does not do

RoadTrip Navigator does not promise:

- Live fuel or electricity prices.
- Live charger occupancy.
- Live campground, hotel, or ticket availability.
- Minute-by-minute traffic.
- Booking or payment on your behalf.
- Turn-by-turn navigation.

It also avoids whole-route GPX/KML export. Batch waypoint imports can route travelers onto seasonally closed roads or start from the wrong origin, so each stop gets its own navigation link instead.

Use the itinerary to prepare and to spot problems. Confirm critical closures, reservations, vehicle requirements, and same-day conditions with official sources before driving.

## Project layout

```text
.claude-plugin/    Claude Code plugin and marketplace manifests
SKILL.md           Plan/check modes and the seven-step workflow
reference.md       tripData schema, reliability grades, drive limits, tool routing
scripts/           Input parsing, planning, editing, route comparison, and backfills
tools/             Routing, weather, parks, EV, fuel, lodging, places, borders, customs
assets/            HTML generator, template, and sample trips
mcp_server/        The same helpers and renderer exposed as 14 typed MCP tools
tests/             Offline-first behavior and rendering tests
```

If you are learning to build agent skills, start with [SKILL.md](SKILL.md), then read [AGENTS.md](AGENTS.md) and [reference.md](reference.md).

## Contributing

Issues and pull requests are welcome. Useful contributions include regional closure knowledge, reservation rules, new official data clients, sample trips, and reports of itineraries that failed a real-world check.

Found a bad closure date, booking window, route, or charging assumption? [Open an issue](https://github.com/Waybox-AI/roadtrip-skill/issues). Those reports improve the checks for everyone.

## License

[MIT](LICENSE) © yang-hong

---

<div align="center">
<sub>Built by <a href="https://waybox.ai">Waybox</a>, maker of OMO, an in-car AI companion. RoadTrip Navigator checks the trip before departure; OMO rides along.</sub>
</div>
