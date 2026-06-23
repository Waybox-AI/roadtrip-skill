#!/usr/bin/env python3
"""
border_client.py — cross-border checklist for US <-> Canada <-> Mexico drives.

Generates a documents/insurance/units checklist per crossing, plus pointers to
the official live wait-time sources (this is rules + links, not live data).

These requirements change — always confirm against CBP / CBSA / Mexican customs
before travel. Treat this as a prompt, not legal advice.

CLI:
    python3 border_client.py US CA            # driving into Canada
    python3 border_client.py US MX --rental   # into Mexico in a rental
"""

import json
import sys

UNITS = {
    "US": {"distance": "mi", "temp": "F", "currency": "USD", "fuel": "gallon"},
    "CA": {"distance": "km", "temp": "C", "currency": "CAD", "fuel": "litre"},
    "MX": {"distance": "km", "temp": "C", "currency": "MXN", "fuel": "litre"},
}

WAIT_SOURCES = {
    "US": "CBP Border Wait Times (bwt.cbp.gov) / CBP One app",
    "CA": "CBSA Border Wait Times (cbsa-asfc.gc.ca)",
    "MX": "Local port reports; northbound US re-entry via CBP bwt.cbp.gov",
}


def _checklist(to_country, rental):
    """Return (docs, vehicleDocs, insuranceNote, customsNotes) for the destination."""
    if to_country == "CA":
        docs = ["Valid passport (or NEXUS / enhanced driver's license at land crossings)",
                "Birth certificate + photo ID for minors; consent letter if a child travels without both parents"]
        vehicle = ["Vehicle registration",
                   "Driver's license"]
        if rental:
            vehicle.append("Rental agreement that EXPLICITLY permits crossing into Canada "
                           "(many US rentals require a cross-border authorization letter)")
        insurance = ("US auto insurance is generally valid in Canada — carry a Canadian "
                     "Non-Resident Inter-Province Motor Vehicle Liability Insurance Card "
                     "(ask your insurer) as proof. Confirm coverage before you go.")
        customs = ["Declare all food, alcohol, tobacco, and cash > CAD $10,000",
                   "Cannabis is illegal to carry across the border in EITHER direction",
                   "Firearms must be declared and most handguns are prohibited",
                   "Radar detectors are illegal in several provinces"]
    elif to_country == "MX":
        docs = ["Valid passport",
                "FMM tourist permit (Multiple Migratory Form) if going beyond the "
                "border zone or staying > 7 days",
                "Notarized consent letter for minors traveling without both parents"]
        vehicle = ["Vehicle registration",
                   "Driver's license",
                   "Temporary Vehicle Import Permit (TIP) if driving beyond the free "
                   "zone / outside Baja & most of Sonora (obtain at Banjercito)"]
        if rental:
            vehicle.append("MOST US rental contracts PROHIBIT driving into Mexico — confirm "
                           "in writing; you typically need a special permission and Mexican policy")
        insurance = ("CRITICAL: US/Canadian auto insurance is NOT valid in Mexico. You must "
                     "buy Mexican liability auto insurance (from a licensed Mexican insurer) "
                     "for the entire trip — driving uninsured is a serious offense.")
        customs = ["Declare cash > USD $10,000 equivalent",
                   "Firearms and ammunition are strictly illegal — severe penalties",
                   "Keep tourist permit + TIP receipt; you must cancel the TIP and get the "
                   "deposit back when you exit"]
    elif to_country == "US":
        docs = ["Valid passport / passport card / NEXUS / enhanced ID (WHTI-compliant)",
                "Visa or ESTA if applicable to your nationality"]
        vehicle = ["Vehicle registration", "Driver's license", "Proof of insurance"]
        if rental:
            vehicle.append("Rental agreement permitting US entry")
        insurance = ("Carry proof of US-valid auto insurance. If entering from Mexico, your "
                     "Mexican policy will not cover you in the US.")
        customs = ["Declare all agricultural products, food, and cash > USD $10,000",
                   "Cannabis remains federally illegal to bring into the US",
                   "Have your CBP declaration ready; consider Global Entry to speed re-entry"]
    else:
        return None
    return docs, vehicle, insurance, customs


def crossing(from_country, to_country, rental=False):
    from_country, to_country = from_country.upper(), to_country.upper()
    res = _checklist(to_country, rental)
    if res is None:
        return {"source": "error", "reason": "unsupported country: %s" % to_country}
    docs, vehicle, insurance, customs = res
    return {
        "source": "rules",
        "from": from_country,
        "to": to_country,
        "docs": docs,
        "vehicleDocs": vehicle,
        "insuranceNote": insurance,
        "customsNotes": customs,
        "unitsAfter": UNITS.get(to_country),
        "waitTimes": WAIT_SOURCES.get(to_country),
        "estWaitNote": "Border waits swing from minutes to 2+ hours by port/time of day — "
                       "check live before you go and avoid weekend/holiday peaks.",
        "disclaimer": "Entry rules change frequently — confirm with CBP / CBSA / Mexican "
                      "customs (Banjercito) before travel.",
    }


def trip_section(crossings):
    """Build the tripData crossBorder section from a list of (from,to,rental) tuples."""
    out = [crossing(*c) for c in crossings]
    return {"crossings": out,
            "summary": " · ".join("%s→%s" % (c["from"], c["to"]) for c in out
                                  if c.get("source") == "rules")}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rental = "--rental" in sys.argv
    if len(args) >= 2:
        print(json.dumps(crossing(args[0], args[1], rental), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(crossing("US", "CA", rental), indent=2, ensure_ascii=False))
