---
description: Plan or verify a North American road trip with the roadtrip-navigator skill
argument-hint: e.g. "from Las Vegas, 7 days, 2 adults, gas SUV, Southwest loop" — or paste an existing route to verify
---

Invoke the **roadtrip-navigator** skill and follow its full `SKILL.md` workflow to
handle this road-trip request: detect the entry mode (plan-from-scratch vs.
verify-an-existing-route), segment the drive into sane daily legs, research
stops / fuel / EV-charging / national-park reservations, build the reservation
countdown and reliability-graded budget, and render the map-first single-file
HTML itinerary.

User request:
$ARGUMENTS

If the request above is empty or missing required slots — start location,
destination or region, number of days, party size, vehicle / fuel type, travel
month — run the skill's `scripts/helper.py` slot check and ask the user for the
missing pieces first, then proceed with planning.
