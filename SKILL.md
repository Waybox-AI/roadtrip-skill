---
name: roadtrip-navigator
description: >
  Generate North American road-trip itineraries as a map-first, offline-friendly
  single-file HTML page. Plans around daily driving segments, overnight stops,
  fuel/EV-charging, national-park reservations (Recreation.gov / NPS), seasonal
  road closures, and timezone/border crossings — for executable, decision-ready
  trips. Two entry modes: give a start + region/destination + days and it plans
  the whole route, or hand it an existing route and it verifies, fills gaps, and
  produces the page.
read-when: >
  road trip, self drive, 自驾, 公路旅行, national park, scenic drive, RV trip,
  EV road trip, Southwest loop, route 66, drive itinerary, campground, 自驾路线,
  租车自驾, 环线, road trip planner, US/Canada drive, park reservation
---

# RoadTrip Navigator

Turn **"start + days"** or **"an existing route"** into a road trip you can
actually drive: paced into days, with overnight stops, fuel/charging, park
reservations, seasonal road risks, and a map-first single-file HTML page.

North American road trips revolve around the **car**, not flights: *how many
hours do we drive today, where do we sleep, will we make it on the fuel/charge
we have, and is the road even open.* That focus is what this skill adds on top
of a generic "list of attractions."

## When to use

Use this skill whenever the request is about driving a multi-stop trip in the
US / Canada / Mexico (see `read-when` triggers). If the user only wants a single
city guide or a flight itinerary, this is not the right skill.

## Two entry modes

Detect the mode up front (see `scripts/helper.py` for the heuristic):

- **Light mode (plan it for me):** user gives a start, a rough region or
  destination, day count, and party/vehicle. → Run the full 7-step workflow,
  designing the route yourself.
- **Heavy mode (verify my route):** user pastes/links/screenshots an existing
  route. → Skip route invention. Parse their route into the schema, then
  *verify and fill gaps*: driving segmentation, overnight realism, fuel/charge
  coverage, reservation countdown, seasonal closures, and produce the page.

When unsure which mode, ask one short question. Otherwise infer and proceed.

## The five things that make this more than a list

These are where pure-model answers fail and where this skill earns its keep:

1. **Daily driving segmentation (the core).** Slice the whole route into days
   under a sane daily drive limit, place an overnight at each segment end, and
   *validate* each day: drive ≤ limit, arrive before dark, no stop hits a
   closed gate, fatigue buffer. This is the road-trip equivalent of
   connection-checking — most AI itineraries skip it.
2. **Reservation countdown.** Recreation.gov campgrounds often release ~6 months
   out; popular timed-entry a few days out; in-park lodges up to ~13 months out.
   From the departure date, work backwards into a "book by" to-do list.
3. **Fuel / charge planning.** Gas: flag long empty stretches ("next fuel in
   X mi"). EV: plan a charging corridor against the vehicle's range and note
   whether each leg makes it, charger power, and a backup.
4. **Seasonal road conditions & closures.** Mountain passes that close in winter
   (Going-to-the-Sun, Tioga Pass, Trail Ridge Rd), wildfire/hurricane/snow
   season. If the travel date hits one, down-rank or reroute and say so.
5. **Timezones & borders.** Correct arrival times across timezone lines; for
   border crossings, flag documents / vehicle papers / insurance / wait times.

## Workflow (7 steps)

> Run `scripts/helper.py "<user request>"` first — it parses slots, guesses the
> entry mode, picks the trip region (for HTML theming), and prints what's still
> missing. Use its output to drive the steps below.

### Step 1 — Collect requirements (slot filling)
Required: **start, travel date, days, party makeup, vehicle (gas/EV/RV + range)**.
Optional: destination/region, budget, preferences (scenic vs. fast, hike
intensity, loop vs. one-way, border crossing). Only ask follow-ups for missing
**required** slots; fill the rest with sensible defaults and proceed.

**Validate place names before planning.** Slot presence is not slot truth: a
made-up start like "ABC" parses fine and would otherwise flow straight into a
fabricated route. Run every user-supplied place — start, destination, named
waypoints; in heavy mode each day's from/to towns — through
`python3 tools/places_client.py "<name>"` and branch on its verdict:
`match` → adopt the returned canonical name + coordinates; `did-you-mean` →
confirm the intended place with the user (one short question, same spirit as
the required-slot follow-ups); `no-match` → **stop and ask — never plan a
route around a place you could not verify**; `unverified` (offline) → use your
own judgment and ask about any name you don't recognize. A `match` with
`outsideNA: true` is a real place outside US/Canada/Mexico — tell the user
it's beyond this skill's coverage instead of calling it fake.

### Step 2 — Route / destination planning (if not given)
Decide **loop vs. one-way** first (affects one-way drop fees and pacing).
For region-level input ("the Southwest", "Pacific Northwest"): search
candidates → seasonal & closure check → shortlist. Compute rough total miles /
driving days for the shortlist and drop any "can't be driven in N days" option.

**Present two candidate routes before committing (light mode only).** Once the
shortlist is down to viable options, draft **exactly two** genuinely distinct
routes yourself — e.g. a faster direct corridor vs. a scenic detour, or two
different geographic loops — each with a short label, a one-line summary, and
rough total miles/driving days. Show both to the user and ask them to pick
(or say "surprise me") before moving to Step 3. This is a single short
question, same spirit as the required-slot follow-up in Step 1 — don't
draft a full itinerary for either option first. If the conversation is
one-shot and no reply is possible, pick the better-rated option yourself,
proceed, and note the alternative you didn't take. Skip this entirely in
heavy mode (the user already supplied a route) or once the user has already
chosen. Carry both options into `scripts/helper.compare_routes()` to populate
`routeOptions[]` (Phase-3 module below) so the rendered page shows the
comparison table with the chosen route flagged.

### Step 3 — Daily driving segmentation (core; see five-things #1)
1. Split by a **daily drive limit** (default: relaxed adults ≤ 4–5h;
   with kids/seniors ≤ 3–4h; user-adjustable).
2. Put an **overnight** at each segment end (has lodging, supplies, good for the
   next morning).
3. Validate: arrive **before dark**, no stop hits a **closed gate**, long legs
   have a fuel/charge point mid-way.
4. If infeasible: cut miles / add a night / pick a closer overnight town.
5. Surface risks explicitly in the day, e.g. "no fast charger for 180 mi on this
   leg — charge to full before leaving."

Rule of thumb: **plan by daylight, not by odometer** — a day that ends after
dark fails at the trailhead, not on the map.

### Step 4 — Parallel research (sub-agents)
Fan out (one concern per sub-agent, run concurrently): weather (per day),
lodging/campgrounds (price + booking difficulty), fuel/charging points,
attractions & tickets/permits, food, scenic byways & hikes, Reddit real-world
gotchas. **Delegation rule: instruct each sub-agent to hit official APIs first
(NPS / NWS / Recreation.gov / Open Charge Map) and fall back to web search only
on failure.** See `reference.md` for the tool routing table and `tools/`.

### Step 5 — Reservation countdown (see five-things #2)
From the departure date, generate a "book by" to-do list:
campgrounds (Recreation.gov, ~T-6 months), timed-entry / wilderness permits
(per park rule, T-X days), popular in-park lodges (up to ~T-13 months),
one-way car/RV rental (lock price early). Render as a ⚠️ checklist at the top of
the page + a timeline. Populate `bookingCountdown[]`.

### Step 6 — Budget (with reliability grading)
Tag every line **verified / reference(~) / estimate(≈)**. Road-trip specifics:
fuel = total miles ÷ MPG × gas price (or EV charging cost); tolls; park entry or
the **America the Beautiful** annual pass; one-way drop fee; campground; lodging;
food. Force a bottom disclaimer: prices are dynamic, confirm before departure.

### Step 7 — Generate the single-file HTML (map-first)
1. Write the data to **`tripData.json`** first (data/view separation — editable,
   re-renderable).
2. Render: `python3 assets/generate.py tripData.json -o trip.html`
   → Leaflet map (numbered stops + ordered polyline) + one-tap mobile nav
   (Google/Apple deep links) + daily timeline + reservation to-do + budget.
   Responsive (mobile single-column / desktop multi-column) + print friendly.
3. **Validate before delivering** (plan §9): the generator already does a light
   schema check and a JSON parse of the injected data. Optionally syntax-check
   the inline JS, then open/preview.
4. Full-page disclaimer: AI-assembled, may be out of date, verify with official
   sources.

## Output contract

- Always produce **both** `tripData.json` and the rendered `trip.html`.
- Units: miles, °F, MPG, USD by default; switch to km/°C/local currency on
  Canadian/Mexican legs and note the change. A trip entirely within China
  prices its budget in CNY (¥) — never converted into USD.
- Never invent a precise reservation availability, live charger occupancy, or
  minute-level traffic — point to the official app / Recreation.gov / nav.

## Honesty boundaries (Phase 1)

Do **not** promise: exact live fuel/electricity prices, live charger occupancy,
minute-level traffic, live campground availability, or replacing turn-by-turn
navigation. For these, tell the user to confirm via the official app /
Recreation.gov / their navigation app in real time. The page's job is to be
right the morning you leave, not merely impressive the night it was generated.

## Files

- `reference.md` — tripData schema, reliability grading, tool routing table.
- `AGENTS.md` ("Worked examples") — typical prompts and expected outputs.
- `assets/generate.py` — `tripData.json` → single-file HTML.
- `assets/template.html` — the HTML/JS renderer (Leaflet map + timeline).
- `assets/tripData.example.json` / `assets/preview.html` — Southwest 7-day demo.
- `assets/tripData.tahoe.json` / `assets/preview-tahoe.html` — Sunnyvale→Tahoe
  3-day demo (mountain theme, state-park reservations, Sierra snow risk).
- `assets/tripData.pnw.json` / `assets/preview-pnw.html` — Seattle→Vancouver→
  Whistler EV cross-border demo (exercises all three Phase-3 modules below).

## Phase-3 modules (implemented)

These render as extra sections when their data is present (see `reference.md`):

- **Multi-route comparison** — `scripts/helper.compare_routes(options, party)`
  → `routeOptions[]`. Feeds from the Step 2 two-route pick above; it auto-rates
  drive intensity and renders a comparison table with the chosen route flagged.
- **Cross-border** — `tools/border_client.trip_section([("US","CA",rental),...])`
  → `crossBorder`. Per-crossing documents / insurance / customs / unit-switch
  checklist for US↔CA↔MX. Note the key asymmetry it encodes: US insurance is
  usually valid in **Canada** but **never in Mexico** (buy Mexican insurance).
- **Duty-free exemption** — `tools/customs_client.personal_exemption(residence,
  hours_abroad, used_within_30_days=False)` → the per-person allowance quoted in
  `crossBorder` customs notes. Encodes the 24h/48h tiers (US: USD 800 at 48h+,
  once per 30 days, else USD 200; CA: 0 / CAD 200 / CAD 800; MX land: USD 300)
  with EN + 中文 note strings — quote the tool, never recall these amounts.
- **EV charging corridor** — `tools/charging_client.corridor(legs, usableRange,
  winter_derate=...)` → `evPlan`. Simulates state-of-charge leg by leg, sets a
  recommended charge-to at each stop, and flags legs that won't make the buffer.
  Pass `winter_derate` (e.g. 0.25) for cold-weather range loss.
- `scripts/helper.py` — input parsing, entry-mode + region detection, slot check.
- `tools/*.py` — per-source clients, each with a web-search fallback
  (incl. `border_client.py` and `charging_client.corridor()`).
