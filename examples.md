# Examples — prompts and how the skill responds

These show the two entry modes and the shape of a good interaction. The agent
should adapt, not follow verbatim.

---

## Example 1 — Light mode (plan it for me)

**User:**
> Plan a 7-day road trip from Las Vegas through the Southwest national parks for
> 2 adults in mid-September. Renting a gas SUV, want a loop back to Vegas.

**Agent flow:**
1. `python3 scripts/helper.py "..."` → mode=light, region=desert, all required
   slots present (start=Las Vegas, days=7, party=2 adults, vehicle=gas, date=Sep).
2. **Route (Step 2):** loop confirmed → Vegas → Zion → Bryce → Page → Grand
   Canyon → Vegas. Rough total ≈ 1,180 mi — drivable in 7 days. ✓
3. **Segmentation (Step 3):** split into days, each drive ≤ ~4.5h (longest is the
   final 280-mi / 4.5h return — flagged). Overnights: Springdale ×2, Bryce, Page,
   Grand Canyon ×2.
4. **Parallel research (Step 4):** weather per day, lodging quotes, fuel stops,
   park passes, Antelope Canyon tour requirement, Reddit gotchas.
5. **Countdown (Step 5):** Antelope Canyon tour (book ~T-30d), South Rim lodge
   (~T-13mo), Springdale hotel.
6. **Budget (Step 6):** fuel ≈$186 (estimate), lodging ~$1,365 (reference),
   America the Beautiful pass $80 (verified), etc.
7. **Generate (Step 7):** write `tripData.json`, then
   `python3 assets/generate.py tripData.json -o trip.html`.

**Output:** `trip.html` (map-first, see `assets/preview.html` for exactly this
trip) + the editable `tripData.json`, plus a short chat summary highlighting the
reservation countdown and the long final-day drive.

---

## Example 2 — Heavy mode (verify my route)

**User:**
> Here's my plan, can you check it and make a page?
> Day 1: Seattle → Port Angeles. Day 2: Olympic NP. Day 3: → Forks → coast.
> Day 4: → Seattle. 4 days, 2 adults + 1 kid, gas, late October.

**Agent flow:**
1. helper → mode=heavy (multiple "Day N"), region=forest.
2. **Parse** their days into the schema (don't re-invent the route).
3. **Verify (Step 3):** check each leg's drive time against the "with kids ≤
   3–4h" limit; confirm ferry vs. drive around the peninsula; check daylight in
   late October (early sunset → don't plan coast arrival after dark).
4. **Fill gaps:** add fuel stops (sparse on US-101 west side), weather (rain
   likely — Olympic is a rainforest), Hoh Rainforest hours, lodging in Forks/Port
   Angeles, ferry reservation note.
5. **Closures/season:** Hurricane Ridge Rd can close on snow days in late Oct —
   flag and give the alternative.
6. Generate `tripData.json` + `trip.html`, calling out anything that didn't check
   out (e.g. "Day 3 as written is ~5.5h driving with a kid — suggest splitting").

---

## Example 3 — EV-specific

**User:**
> EV road trip, Tesla-ish ~280 mi range, San Francisco to LA via Highway 1, 3
> days, couple.

**Agent flow:**
- region=coast, vehicle=EV (range 280).
- Run the full corridor: `tools/charging_client.corridor(legs, 280)` → a per-leg
  state-of-charge table with recommended charge-to levels, written to `evPlan`.
  Big Sur's sparse charging shows up as a low arrival SoC / "no charger here"
  warning. Pass `winter_derate=0.25` for a cold-weather plan.
- `fuel_client.ev_cost(...)` for the budget (graded estimate).
- Each day's `fuelCharging[]` lists chargers with `powerKW` and a backup.
- See `assets/preview-pnw.html` for a rendered EV corridor.

---

## Example 4 — Cross-border

**User:**
> Seattle to Banff and Jasper, 6 days, 2 adults, gas.

**Agent flow:**
- `crossBorder=true` → `tools/border_client.trip_section([("US","CA",rental),
  ("CA","US",rental)])` → a per-crossing documents / insurance / customs /
  unit-switch checklist written to `crossBorder` (renders as its own section).
- Switch units to **km / °C / CAD** on the Canadian legs (the page flags it).
- Parks Canada reservations (not Recreation.gov) for popular sites.
- See `assets/preview-pnw.html` (Seattle→Vancouver→Whistler) for a rendered
  cross-border + EV + route-comparison page. Note the asymmetry the tool encodes:
  US insurance usually works in Canada, but you **must** buy Mexican insurance
  for Mexico.

---

## Quick commands

```bash
# Parse a request into slots / mode / region
python3 scripts/helper.py "from Boston, 5 days, family, gas, New England fall"

# Render an itinerary
python3 assets/generate.py tripData.json -o trip.html

# Try the bundled demos
python3 assets/generate.py assets/tripData.example.json -o assets/preview.html      # Southwest 7-day
python3 assets/generate.py assets/tripData.tahoe.json   -o assets/preview-tahoe.html # Sunnyvale→Tahoe 3-day
python3 assets/generate.py assets/tripData.pnw.json     -o assets/preview-pnw.html   # Seattle→Vancouver EV cross-border

# Phase-3 module quick tests
python3 tools/charging_client.py --corridor          # EV state-of-charge simulation
python3 tools/border_client.py US MX --rental        # cross-border checklist
python3 scripts/helper.py --compare                  # multi-route comparison

# Probe a data source directly
python3 tools/routing_client.py 36.17,-115.14 37.30,-113.03
python3 tools/parks_client.py --countdown 2026-09-12
python3 tools/charging_client.py --leg 165 280
```
