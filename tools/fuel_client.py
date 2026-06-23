#!/usr/bin/env python3
"""
fuel_client.py — fuel cost estimate + GasBuddy link.

There is no free, stable, key-less live gas-price API, so this is intentionally
an *estimator* (clearly graded "estimate") plus a link to GasBuddy for the user
to confirm. Regional averages below are rough priors — the agent should override
with a fresh web-search figure when accuracy matters.

CLI:
    python3 fuel_client.py 1180 26            # miles, mpg  (default region price)
    python3 fuel_client.py 1180 26 west 4.50  # miles, mpg, region, price/gal
"""

import json
import sys
from urllib.parse import quote_plus

# Rough US regional priors ($/gal). Treat as last-resort defaults only.
REGION_PRICE = {
    "west": 4.50, "california": 4.90, "southwest": 4.10, "mountain": 3.80,
    "midwest": 3.40, "south": 3.20, "northeast": 3.60, "pacificnw": 4.30,
    "us": 3.70,
}
# EV: rough public DC fast-charge cost per kWh and a typical efficiency.
EV_PRICE_PER_KWH = 0.40
EV_MI_PER_KWH = 3.3


def gas_cost(miles, mpg, price_per_gal=None, region="us"):
    price = price_per_gal if price_per_gal is not None else REGION_PRICE.get(region, REGION_PRICE["us"])
    gallons = miles / float(mpg)
    return {
        "source": "estimate",
        "reliability": "estimate",
        "type": "gas",
        "miles": miles, "mpg": mpg, "pricePerGal": round(price, 2),
        "gallons": round(gallons, 1),
        "cost": round(gallons * price, 2),
        "label": "Fuel (~%d mi / %g MPG / $%.2f-gal)" % (miles, mpg, price),
        "gasbuddy": "https://www.gasbuddy.com/gasprices",
        "note": "estimate only — confirm live prices on GasBuddy / at the pump.",
    }


def ev_cost(miles, mi_per_kwh=EV_MI_PER_KWH, price_per_kwh=EV_PRICE_PER_KWH):
    kwh = miles / float(mi_per_kwh)
    return {
        "source": "estimate",
        "reliability": "estimate",
        "type": "charge",
        "miles": miles, "miPerKWh": mi_per_kwh, "pricePerKWh": price_per_kwh,
        "kWh": round(kwh, 1),
        "cost": round(kwh * price_per_kwh, 2),
        "label": "Charging (~%d mi / %g mi-per-kWh / $%.2f-kWh)" % (miles, mi_per_kwh, price_per_kwh),
        "note": "public DC fast-charge estimate; home/Level-2 is much cheaper.",
    }


def gasbuddy_link(place):
    return "https://www.gasbuddy.com/home?search=" + quote_plus(place)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2:
        miles, mpg = float(a[0]), float(a[1])
        region = a[2] if len(a) > 2 else "us"
        price = float(a[3]) if len(a) > 3 else None
        print(json.dumps(gas_cost(miles, mpg, price, region), indent=2))
    else:
        print(json.dumps(gas_cost(1180, 26, region="southwest"), indent=2))
