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

## Units convention

Miles / °F / MPG / USD by default; switch to km / °C / local currency on
Canadian/Mexican legs (encoded by the `crossBorder` module) and note the change.
