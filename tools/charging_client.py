#!/usr/bin/env python3
"""
charging_client.py — EV charging stations near a point + a corridor sanity check.

Preferred: Open Charge Map API (free; OCM_API_KEY recommended, demo works
sometimes without). Fallback: web-search / PlugShare note.

Also provides leg_ok(): a quick range check for the daily-segmentation step —
flags legs that exceed a safe fraction of usable range.

CLI:
    python3 charging_client.py 37.0965 -113.5684
    python3 charging_client.py --leg 165 280
"""

import json
import os
import sys
from urllib.parse import urlencode
from urllib.request import urlopen, Request

try:
    from web_search import fallback
except ImportError:
    from tools.web_search import fallback

OCM = "https://api.openchargemap.io/v3/poi/"
UA = {"User-Agent": "roadtrip-navigator/1.0"}
SAFE_FRACTION = 0.7  # don't plan a leg longer than 70% of usable range


def chargers_near(lat, lng, distance_mi=25, min_kw=50, limit=8, timeout=8):
    params = {
        "output": "json", "latitude": lat, "longitude": lng,
        "distance": distance_mi, "distanceunit": "Miles",
        "maxresults": limit, "compact": "true", "verbose": "false",
    }
    key = os.environ.get("OCM_API_KEY")
    if key:
        params["key"] = key
    try:
        url = OCM + "?" + urlencode(params)
        with urlopen(Request(url, headers=UA), timeout=timeout) as r:
            data = json.loads(r.read().decode())
        out = []
        for poi in data:
            ai = poi.get("AddressInfo") or {}
            conns = poi.get("Connections") or []
            kw = max([c.get("PowerKW") or 0 for c in conns] or [0])
            if kw and kw < min_kw:
                continue
            out.append({
                "name": ai.get("Title"),
                "town": ai.get("Town"),
                "lat": ai.get("Latitude"),
                "lng": ai.get("Longitude"),
                "powerKW": kw or None,
                "type": "charge",
            })
        if out:
            return {"source": "openchargemap", "chargers": out}
        return fallback("OCM returned no >=%dkW chargers nearby" % min_kw,
                        ["fast EV chargers near %.3f,%.3f" % (lat, lng)],
                        ["https://www.plugshare.com", "https://abetterrouteplanner.com"])
    except Exception as e:
        return fallback("Open Charge Map error: %s" % e,
                        ["fast EV chargers near %.3f,%.3f" % (lat, lng)],
                        ["https://www.plugshare.com", "https://abetterrouteplanner.com"])


def leg_ok(leg_miles, usable_range_miles, safe_fraction=SAFE_FRACTION):
    """Range sanity check for one driving leg (Step 3)."""
    limit = usable_range_miles * safe_fraction
    ok = leg_miles <= limit
    return {
        "legMiles": leg_miles,
        "usableRange": usable_range_miles,
        "safeLegLimit": round(limit, 1),
        "ok": ok,
        "advice": ("fine on a full charge" if ok else
                   "exceeds %.0f%% of range — plan a charging stop mid-leg"
                   % (safe_fraction * 100)),
    }


def corridor(legs, usable_range_miles, start_soc=90, min_soc=10,
             buffer_soc=10, max_charge_soc=90, winter_derate=0.0):
    """Simulate state-of-charge (SoC) along an EV route ("充电走廊精算").

    legs: ordered list of dicts: {"to": str, "miles": float,
          "charger": bool (charger available at this stop), "chargerKW": int|None}
          (the first leg starts from the trip origin; "to" is each leg's destination)
    usable_range_miles: vehicle usable range at 100%.
    start_soc / min_soc / buffer_soc / max_charge_soc: percentages.
    winter_derate: fraction (e.g. 0.25) to shave off effective range for cold.

    Returns per-leg arrival SoC, recommended charge-to at each stop, ok flags,
    and a list of warnings. Energy is modeled simply as miles vs. effective range
    (linear) — good enough for planning, not a substitute for ABRP/the car.
    """
    eff_range = usable_range_miles * (1.0 - winter_derate)
    if eff_range <= 0:
        return {"source": "error", "reason": "non-positive effective range"}

    def pct_for_miles(mi):
        return (mi / eff_range) * 100.0

    soc = float(start_soc)
    out_legs = []
    warnings = []

    for i, leg in enumerate(legs):
        miles = float(leg.get("miles") or 0)
        depart_soc = soc
        need_pct = pct_for_miles(miles)
        arrive_soc = depart_soc - need_pct

        leg_rec = {
            "to": leg.get("to"),
            "miles": round(miles, 1),
            "departSoC": round(depart_soc),
            "arriveSoC": round(arrive_soc),
            "ok": arrive_soc >= min_soc,
            "charger": bool(leg.get("charger")),
            "chargerKW": leg.get("chargerKW"),
        }
        if arrive_soc < min_soc:
            short_by = (min_soc - arrive_soc) / 100.0 * eff_range
            leg_rec["note"] = ("WON'T MAKE IT on this charge — short by ~%d %s; "
                               "add a charging stop mid-leg." % (round(short_by), "mi"))
            warnings.append("Leg to %s arrives at %d%% (below %d%% buffer)%s"
                            % (leg.get("to"), round(arrive_soc), min_soc,
                               " — winter derate applied" if winter_derate else ""))
        soc = max(arrive_soc, 0.0)

        # Decide a charge at this stop, based on the NEXT leg's need.
        nxt = legs[i + 1] if i + 1 < len(legs) else None
        if nxt is not None:
            next_need = pct_for_miles(float(nxt.get("miles") or 0))
            target = min(max_charge_soc, next_need + min_soc + buffer_soc)
            if target > soc:
                if leg.get("charger"):
                    leg_rec["chargeTo"] = round(target)
                    kw = leg.get("chargerKW")
                    leg_rec["chargeNote"] = ("charge to ~%d%%%s before the next leg"
                                             % (round(target),
                                                " (%dkW)" % kw if kw else ""))
                    soc = target
                else:
                    leg_rec["chargeTo"] = None
                    leg_rec["chargeNote"] = ("NO charger here but you need ~%d%% for "
                                             "the next leg — find one nearby." % round(target))
                    warnings.append("No charger at %s but next leg needs a top-up."
                                    % leg.get("to"))
        out_legs.append(leg_rec)

    return {
        "source": "model",
        "usableRange": usable_range_miles,
        "effectiveRange": round(eff_range, 1),
        "winterDerate": winter_derate,
        "assumptions": {"startSoC": start_soc, "minSoC": min_soc,
                        "bufferSoC": buffer_soc, "maxChargeSoC": max_charge_soc},
        "legs": out_legs,
        "warnings": warnings,
        "note": "Linear range model for planning only — verify with ABRP / the car's planner.",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--leg":
        print(json.dumps(leg_ok(float(sys.argv[2]), float(sys.argv[3])), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--corridor":
        # demo: 280-mi EV, a few legs, one stop without a charger
        demo = [
            {"to": "Tacoma, WA", "miles": 35, "charger": True, "chargerKW": 150},
            {"to": "Bellingham, WA", "miles": 130, "charger": True, "chargerKW": 250},
            {"to": "Vancouver, BC", "miles": 55, "charger": True, "chargerKW": 100},
            {"to": "Whistler, BC", "miles": 80, "charger": False, "chargerKW": None},
        ]
        print(json.dumps(corridor(demo, 280, winter_derate=0.0), indent=2))
    else:
        lat = float(sys.argv[1]) if len(sys.argv) > 1 else 37.0965
        lng = float(sys.argv[2]) if len(sys.argv) > 2 else -113.5684
        print(json.dumps(chargers_near(lat, lng), indent=2))
