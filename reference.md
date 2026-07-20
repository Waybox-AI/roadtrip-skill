# Reference — schema, reliability, tool routing

## 1. tripData schema

The renderer (`assets/template.html`) reads a single `TRIP_DATA` object. Write it
to `tripData.json`, then render with `assets/generate.py`. All fields are
optional except where noted; the renderer degrades gracefully when fields are
missing.

```jsonc
{
  "title": "Southwest Loop · 7 Days",        // required
  "subtitle": "Las Vegas → Zion → ... → Las Vegas",
  "dateRange": "2026-09-12 ~ 2026-09-18",
  "travelers": "2 adults",
  "vehicle": {
    "type": "gas",                 // "gas" | "EV" | "RV"
    "model": "Midsize SUV (rental)",
    "mpg": 26,                     // gas only
    "rangeMiles": null             // EV only — usable range
  },
  "loopType": "loop",              // "loop" | "one-way"
  "totalMiles": 1180,
  "drivingDays": 7,
  "region": "desert",              // theming: desert|coast|forest|autumn|mountain
  "units": { "distance": "mi", "temp": "F", "currency": "USD" },  // currency = the trip country's code: USD|CAD|MXN|CNY

  "days": [                        // required, ordered
    {
      "date": "09/12",             // required
      "title": "Las Vegas → Zion", // required
      "from": "Las Vegas, NV",
      "to": "Springdale, UT",
      "driveMiles": 165,
      "driveTime": "2h45m",
      "driveSource": "osrm",       // set when miles/time came from routing_client (else model estimate)
      "overnight": "Springdale, UT",   // null on the final return day
      "timezoneNote": "PT → MT (+1h)", // shown highlighted when crossing zones
      "weather": { "icon": "sunny", "high": 88, "low": 60 },
      "stops": [
        {
          "name": "Zion National Park",
          "type": "park",          // park|hike|scenic|city|tour|food|lodging
          "lat": 37.2982, "lng": -113.0263,   // needed for the map + nav links
          "timedEntry": false,     // true → red "timed entry" badge
          "ticket": "park pass",   // free text badge (e.g. "guided tour required")
          "permitNote": "...",
          "note": "Park at Springdale, ride the free shuttle."
        }
      ],
      "fuelCharging": [
        { "name": "Fuel @ St. George", "type": "gas",   // "gas" | "charge"
          "lat": 37.09, "lng": -113.56, "powerKW": 250, "note": "charge to 90%" }
      ],
      "meal": { "name": "Oscar's Cafe", "perPerson": 28 },
      "risks": ["Town fills up by mid-morning in peak season — arrive early."]
    }
  ],

  "lodging": [
    { "name": "...", "area": "...", "nights": 2,
      "pricePerNight": 245, "rating": "4.6", "booked": false,
      "links": { "booking": "https://…", "airbnb": "https://…" } }
      // optional platform deep links (lodging_client.search_links) — rendered
      // as a small links row under the name
  ],

  "bookingCountdown": [            // drives the top ⚠️ countdown banner
    { "item": "Watchman Campground", "bookBy": "2026-03-12",
      "where": "Recreation.gov", "priority": "high", "note": "T-6 months.",
      "source": "parks_client" }   // set when bookBy came from the release-rule table
  ],

  "budget": {
    "currency": "USD",             // the country the trip drives in (CNY for China-domestic); never converted
    "items": [
      { "label": "Fuel (~1,180 mi ÷ 26 MPG × $4.10)", "amount": 186,
        "reliability": "estimate" }   // verified | reference | estimate
    ],
    "total": 3191,
    "perPerson": 1596
  },

  "tips": ["..."],
  "disclaimer": "AI-assembled, may be out of date — verify with official sources.",
  "generationDate": "2026-06-16"
}
```

### Optional sections (Phase 3 modules)

These render only when present. Build them with the matching tool, then drop the
result straight into `tripData.json`.

```jsonc
// Multi-route comparison — renders a table near the top (>= 2 options).
// Build with scripts/helper.compare_routes(options, party).
"routeOptions": [
  { "name": "Sea-to-Sky loop", "miles": 450, "days": 4,
    "driveIntensity": "relaxed (~2.0h/day)",   // auto-filled if omitted
    "highlights": "Vancouver, Whistler", "bestSeason": "year-round",
    "estCost": 1680, "pros": "open all year", "cons": "two crossings",
    "chosen": true }
],

// Cross-border — renders a documents/insurance/units checklist per crossing.
// Build with tools/border_client.trip_section([("US","CA",rental), ...]).
// The single-shot webapp path instead has the model emit a top-level
// "crossings":[{"from":"US","to":"CA","day":2}, ...] (structure only) and
// planner.refresh_trip_border builds this section from it — including
// "dutyFree" (customs_client.personal_exemption) when the trip re-enters
// the home country and both crossing days are known.
"crossBorder": {
  "summary": "US→CA · CA→US",
  "crossings": [
    { "from": "US", "to": "CA", "docs": [...], "vehicleDocs": [...],
      "insuranceNote": "...", "customsNotes": [...],
      "unitsAfter": { "distance": "km", "temp": "C", "currency": "CAD", "fuel": "litre" },
      "waitTimes": "CBSA Border Wait Times ...", "estWaitNote": "..." }
  ],
  "dutyFree": { "amount": 800, "currency": "USD", "tier": "standard",
                "note": "...", "noteZh": "...", "conditions": [...],
                "conditionsZh": [...], "verify": "..." }   // optional
},

// EV charging corridor — renders a per-leg state-of-charge table.
// Build with tools/charging_client.corridor(legs, usableRange, winter_derate=...).
"evPlan": {
  "usableRange": 280, "effectiveRange": 280, "winterDerate": 0,
  "assumptions": { "startSoC": 90, "minSoC": 10, "bufferSoC": 10, "maxChargeSoC": 90 },
  "legs": [
    { "to": "Bellingham, WA", "miles": 90, "departSoC": 90, "arriveSoC": 58,
      "ok": true, "charger": true, "chargerKW": 350,
      "chargeTo": 49, "chargeNote": "charge to ~49% before the next leg",
      "note": "WON'T MAKE IT ..." }     // only when a leg fails the buffer
  ],
  "warnings": ["..."]
}
```

### Renderer guarantees
- Map: one numbered marker per stop with lat/lng (in day order) + dashed
  polyline + popup with Google/Apple Maps deep links. Empty/absent coords → map
  hides and a fallback note appears (offline-safe).
- `region` picks the color theme. `vehicle.type` picks 🚗/🔌/🚐.
- Budget rows show a colored reliability badge; the footer total is the source
  of truth (generator warns if `total` ≠ sum of items).
- `budget.currency` / `units.currency` map to symbols: USD `$`, CAD `C$`,
  MXN `MX$`, CNY/RMB `¥`; unknown codes fall back to `$`.

## 2. Reliability grading

Tag every researched figure so the user knows how much to trust it:

| Grade | Badge | Meaning | Use for |
|-------|-------|---------|---------|
| `verified` | green | from an official/authoritative source this run | NPS fees, park-pass price, confirmed hours |
| `reference` | accent `~` | a real but indicative price/figure (not booked) | hotel nightly rates, tour prices, rental quotes |
| `estimate` | grey `≈` | computed or rough | fuel cost, food totals, "misc" |

Default to the **lowest** grade you can honestly claim. Never label something
`verified` unless this run actually confirmed it. An honest ≈ outranks a
borrowed ✓.

## 3. Tool routing table

Every tool has a web-search fallback so the skill runs even when nothing is
installed. **Delegation rule:** when fanning out to sub-agents, instruct them to
hit official/free APIs first and fall back to web search only on failure.

| Concern | Preferred source | Client | Fallback |
|---------|------------------|--------|----------|
| Place-name validation (Step 1) | **Photon geocoder (OSM, no key)** | `tools/places_client.py` | ask the user — never plan around an unverified name |
| Route / miles / drive time | Google/Apple Directions, OSRM (OSM) | `tools/routing_client.py` | web search estimate |
| Map tiles | **Leaflet + OSM (no key)** | built into template | — |
| National park info | **NPS API (free)** | `tools/parks_client.py` | nps.gov scrape / search |
| Campgrounds / permits | **Recreation.gov** | `tools/parks_client.py` | official link + countdown |
| Weather (per day) | **NWS api.weather.gov (US, free)**, Env. Canada | `tools/weather_client.py` | OpenWeather / search |
| EV charging | Open Charge Map (free), PlugShare, ABRP idea | `tools/charging_client.py` | search chargers |
| EV corridor (SoC精算) | linear range model | `tools/charging_client.corridor()` | `leg_ok()` quick check |
| Cross-border checklist | CBP / CBSA / Banjercito rules | `tools/border_client.py` | search current rules |
| Duty-free exemption (免税额) | CBP / CBSA / SAT rules table | `tools/customs_client.py` | search current allowances |
| Multi-route compare | computed | `scripts/helper.compare_routes()` | — |
| Fuel price | GasBuddy | `tools/fuel_client.py` | regional average estimate |
| Lodging / campgrounds | Booking/Expedia/Airbnb, KOA/Hipcamp | `tools/lodging_client.py` | search reference price |
| Hikes | AllTrails | (via `web_search`) | search |
| Scenic byways | FHWA National Scenic Byways | (via `web_search`) | search |
| Live road conditions / closures | State DOT 511, Caltrans, park alerts | `tools/weather_client.py` notes | search |
| Real-world reviews | Reddit r/roadtrip, r/nationalparks, blogs | `tools/web_search.py` | — |

### Client contract
Each `tools/*.py` exposes simple functions returning plain dicts/lists and a
`FALLBACK` note when it could not reach a live source. None require API keys to
*run* — without a key they return a structured "use web search" fallback rather
than crashing. Read keys from environment variables (e.g. `NPS_API_KEY`,
`OCM_API_KEY`, `OPENWEATHER_API_KEY`); `NWS`, `OSRM`, `Photon`, and
`Open Charge Map` (demo) need no key.

## 4. Daily-drive defaults (Step 3 validation)

| Party | Relaxed daily drive | Hard cap |
|-------|--------------------|----------|
| Adults only | 4–5 h | ~6.5 h |
| With kids / seniors | 3–4 h | ~5 h |
| RV / towing | 3–4 h | ~5 h |

Also check: arrival before dark (sunset varies by season/latitude), no stop
arrival after a gate/closing time, and a fuel/charge point on any leg longer
than ~60–70% of the vehicle's tank/usable range.

## 5. Seasonal closure cheat-sheet (verify each trip)

| Road / pass | Typical closure |
|-------------|-----------------|
| Going-to-the-Sun Rd (Glacier) | ~mid-Oct → late Jun/Jul |
| Tioga Pass (Yosemite, CA-120) | ~Nov → late May/Jun |
| Trail Ridge Rd (RMNP) | ~mid-Oct → late May |
| Beartooth Hwy (US-212) | ~mid-Oct → late May |
| Many Glacier / high passes | snow-dependent |

Other seasonal hazards: wildfire (late summer/fall, West), hurricane (Jun–Nov,
Gulf/Atlantic/SE), winter storms (mountains, Midwest, Northeast). Always confirm
against live park alerts and DOT 511 — this table is a starting prompt, not truth.
