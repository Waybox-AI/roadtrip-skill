# CONTEXT.md — Domain Knowledge

Product vision, problem framing, and domain terminology for **RoadTrip Navigator**.
For technical/build rules see [AGENTS.md](AGENTS.md); for model-specific prompting
see [CLAUDE.md](CLAUDE.md) / [GEMINI.md](GEMINI.md).

## What this is

RoadTrip Navigator is **not a running application** — it is a **Claude Code plugin /
agent skill**. The deliverable is `SKILL.md` (the workflow an agent follows) plus
small, dependency-light Python helpers the agent shells out to while planning. The
final artifact a user receives is a single self-contained **`trip.html`** file.

Two audiences share this repo:
- **The agent** reads `SKILL.md`, `reference.md`, and `examples.md` as *instructions*
  — these are the load-bearing "source code" of the skill's behavior.
- **The Python** (`scripts/`, `tools/`, `assets/`) is glue the agent calls.

## The problem it solves

North American road trips revolve around the **car**, not flights: *how many hours do
we drive today, where do we sleep, will we make it on the fuel/charge we have, and is
the road even open.* Generic "AI trip planners" hand back a wishlist of attractions and
skip exactly these executable questions. This skill exists to answer them.

## Value proposition — the five things that make it more than a list

These are where pure-model answers fail and where the skill earns its keep:

1. **Daily driving segmentation (the core).** Slice the whole route into days under a
   sane daily drive limit, place an overnight at each segment end, and *validate* each
   day (drive ≤ limit, arrive before dark, no closed gate, fatigue buffer). The
   road-trip equivalent of connection-checking.
2. **Reservation countdown.** Work backwards from departure into a "book by" to-do
   list — campgrounds (~6 months out), timed-entry permits (days), in-park lodges (up
   to ~13 months) — on the *right* system (Recreation.gov / ReserveCalifornia / Parks
   Canada).
3. **Fuel / charge planning.** Gas: flag long empty stretches. EV: a per-leg charging
   corridor against the vehicle's range with a winter-derate option.
4. **Seasonal road conditions & closures.** Winter passes (Going-to-the-Sun, Tioga,
   Trail Ridge), wildfire/snow/hurricane season → down-rank or reroute and say so.
5. **Timezones & borders.** Timezone-corrected arrivals; US↔CA↔MX documents /
   insurance / customs / wait-time checklist.

## Positioning (how this wins)

- **Tagline:** *"An AI agent skill that turns 'start + days' into a road trip you can
  actually drive."* Think of it as a **compiler from an idea to a drivable itinerary** —
  the depth is in feasibility checking, not attraction discovery.
- It is deliberately **not** a better Roadtrippers/Wanderlog (consumer apps with live
  data and booking flows) and **not** a broader generic travel-planner skill. The moat
  is the five feasibility concerns above, plus: zero-key trial, offline single-file
  output, MIT + honesty boundaries, reliability grading, and the SKILL.md open
  standard (Claude Code plus other compatible agent tools).
- The **single-file `trip.html` is the shareable artifact** — every generated trip is
  something users forward to co-travelers or post publicly. Output polish is part of
  the product, not cosmetics.
- The biggest real-world alternative is *just asking ChatGPT/Claude directly*. The
  answer to that is executability (drive-time sanity, closures, book-by dates, SoC
  simulation) — never "more attractions".

## Product structure — two channels, one brand

- **The skill (this repo)** — for users of Claude Code and other SKILL.md-compatible
  agents. Two-command install, zero API keys.
- **The web version (roadtripskill.dev)** — no-install browser generation for
  non-developers; early access, free for now. This is the "external webapp" that
  imports `scripts/routes.py` (see [DEVELOPMENT.md](DEVELOPMENT.md)) — another reason
  that module's public API stays stable.
- Parent brand: **Waybox** (waybox.ai, maker of the in-car AI companion OMO) — hence
  the `Waybox-AI` GitHub org. The driving-scenario narrative is shared across products.

## Who uses this

- **Developers** — Claude Code power users collecting skills, and devs studying
  SKILL.md engineering. The repo doubles as a teaching artifact (7-step workflow,
  data/view separation, reliability grading), so docs quality *is* product quality.
- **Coding road-trippers** — tech workers planning national-park / cross-state / EV
  trips. They validate the skill on real trips and share the generated HTML.
- **Mass-market travelers** — reach the product through the web version only; they
  never see this repo.

## Vision: region-by-region expansion

The long-term product is a **driving-feasibility copilot for any region**, with
destinations opened as data matures. Live today: North America (US/CA/MX). Roadmap
candidates (order undecided): Europe/Alps, Australia/NZ, Japan. The three universal
pain classes (scarce bookings, energy/range, seasonal closures) hold everywhere, but
each region has different "dirty details" to encode:

| Region | Scarce bookings | Energy | Roads / rules |
|--------|----------------|--------|---------------|
| Europe | hot campgrounds, Dolomites parking quotas | fragmented charging networks per country | Alpine pass closures, Italian ZTL zones, AT/CH vignettes |
| AUS/NZ | state park systems (NPWS etc.) | outback stretches with no services | dusk wildlife, one-lane bridges, wet-season roads |
| Japan | Mt. Fuji access control, mountain parking | ETC toll costs (often underestimated) | IDP / license-translation rules, winter mountain closures |

## Domain terminology

- **Entry mode** — *Light* ("plan it for me" from start + region + days) vs. *Heavy*
  ("verify my route" from a pasted/linked itinerary). Detected up front by
  `scripts/helper.py`.
- **tripData.json** — the single canonical data object (schema in `reference.md §1`)
  that all planning emits. The view is rendered from it, never the reverse.
- **Reliability grading** — every figure is tagged **verified** / **reference (~)** /
  **estimate (≈)** so users know what to trust.
- **Daily drive limit** — the pacing constraint (relaxed adults ≤ 4–5h; with
  kids/seniors ≤ 3–4h; user-adjustable) that segmentation slices against.
- **bookingCountdown[]** — the reservation to-do list rendered at the top of the page.
- **routeOptions[]** — multi-route A-vs-B comparison (miles, days, drive intensity,
  best season, cost) with the chosen route flagged.
- **crossBorder** — per-crossing checklist. Key asymmetry it encodes: US insurance is
  usually valid in **Canada** but **never in Mexico** (buy Mexican insurance).
- **evPlan** — leg-by-leg EV state-of-charge simulation with recommended charge-to
  levels and flagged legs that won't make the buffer.
- **America the Beautiful** — the US national-parks annual pass the budget weighs
  against per-park entry fees.

## Honesty boundaries (product promise)

The skill deliberately does **not** promise: exact live fuel/electricity prices, live
charger occupancy, minute-level traffic, live campground availability, or replacing
turn-by-turn navigation. For these it points the user to the official app /
Recreation.gov / their nav app. Every generated page carries a disclaimer that it is
AI-assembled and may be out of date — verify with official sources before departure.

Also deliberate: **no whole-route export to a nav app and no GPX/KML.** Batch waypoint
import has (in similar projects) routed users onto seasonally closed roads, and origin
parameters start from the wrong place. Instead, every stop carries its own Google/Apple
Maps deep link for leg-by-leg navigation. Treat this as a design decision to preserve,
not a missing feature.

## Units convention

Miles / °F / MPG / USD by default; switch to km / °C / local currency on
Canadian/Mexican legs (encoded by the `crossBorder` module) and note the change.
