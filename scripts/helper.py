#!/usr/bin/env python3
"""
helper.py — parse a road-trip request into slots, guess the entry mode and the
visual region, and report which required slots are still missing.

This is a *heuristic* aid for Step 1 of the workflow, not a parser of record.
The agent should treat the output as hints and still read the user's intent.

Usage:
    python3 helper.py "drive from Las Vegas, southwest national parks, 7 days, 2 adults, EV"
    echo "<request>" | python3 helper.py
"""

import json
import re
import sys

REQUIRED_SLOTS = ["start", "days", "date", "party", "vehicle"]

# region keyword -> theme used by template.html (data-region)
REGION_HINTS = {
    "desert": ["southwest", "arizona", "utah", "nevada", "zion", "bryce", "moab",
               "grand canyon", "death valley", "sedona", "mojave", "vegas", "西南", "沙漠"],
    "coast": ["pacific coast", "highway 1", "pch", "big sur", "oregon coast",
              "california coast", "monterey", "san diego", "海岸", "太平洋"],
    "forest": ["pacific northwest", "washington", "olympic", "rainier", "redwood",
               "cascades", "smoky", "森林", "雨林"],
    "autumn": ["new england", "vermont", "maine", "new hampshire", "fall foliage",
               "leaf peeping", "秋色", "枫叶"],
    "mountain": ["rockies", "rocky mountain", "colorado", "glacier", "tetons",
                 "yellowstone", "montana", "banff", "jasper", "tahoe", "lake tahoe",
                 "sierra", "sierra nevada", "mammoth", "aspen", "telluride",
                 "yosemite", "山", "落基", "太浩", "内华达山"],
}

VEHICLE_HINTS = {
    "EV": ["ev", "electric", "tesla", "rivian", "电车", "电动"],
    "RV": ["rv", "motorhome", "camper", "campervan", "房车"],
    "gas": ["gas", "gasoline", "suv", "sedan", "燃油", "汽油"],
}

# Phrases that indicate the user pasted an existing route to verify (heavy mode)
HEAVY_HINTS = ["here is my", "here's my", "my route", "my itinerary", "my plan",
               "this itinerary", "check this", "verify", "day 1", "day1", "d1:",
               "我的路线", "这是我的", "帮我核实", "已有路线", "现成路线", "行程如下"]

US_STATES = ["alabama", "alaska", "arizona", "arkansas", "california", "colorado",
             "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
             "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
             "maine", "maryland", "massachusetts", "michigan", "minnesota",
             "mississippi", "missouri", "montana", "nebraska", "nevada",
             "new hampshire", "new jersey", "new mexico", "new york",
             "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
             "pennsylvania", "rhode island", "south carolina", "south dakota",
             "tennessee", "texas", "utah", "vermont", "virginia", "washington",
             "west virginia", "wisconsin", "wyoming"]


def detect_mode(text):
    low = text.lower()
    score = sum(1 for h in HEAVY_HINTS if h in low)
    # multiple "day N" mentions strongly imply a pasted itinerary
    day_markers = len(re.findall(r"\bday\s*\d+\b", low))
    if day_markers >= 2:
        score += 2
    return "heavy" if score >= 2 else "light"


def detect_region(text):
    low = text.lower()
    best, best_hits = "desert", 0
    for region, kws in REGION_HINTS.items():
        hits = sum(1 for k in kws if k in low)
        if hits > best_hits:
            best, best_hits = region, hits
    return best if best_hits else None


def detect_vehicle(text):
    low = text.lower()
    for vtype, kws in VEHICLE_HINTS.items():
        if any(re.search(r"\b" + re.escape(k) + r"\b", low) for k in kws):
            return vtype
    return None


def detect_days(text):
    low = text.lower()
    m = re.search(r"(\d+)\s*(?:days?|天|日)\b", low)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)[-\s]?day\b", low)
    return int(m.group(1)) if m else None


def detect_party(text):
    low = text.lower()
    parts = []
    m = re.search(r"(\d+)\s*adults?", low)
    if m:
        parts.append(m.group(1) + " adults")
    m = re.search(r"(\d+)\s*(?:kids?|children|child)", low)
    if m:
        parts.append(m.group(1) + " kids")
    if "family" in low or "家庭" in text:
        parts.append("family")
    if "couple" in low or "情侣" in text:
        parts.append("couple")
    if re.search(r"\d+\s*(?:people|pax|人)", low):
        parts.append(re.search(r"\d+\s*(?:people|pax|人)", low).group(0))
    return ", ".join(dict.fromkeys(parts)) if parts else None


def detect_start(text):
    # "from X" / "starting in X" / "出发自X"
    m = re.search(r"(?:from|start(?:ing)?(?: in| at| from)?|depart(?:ing)? from)\s+"
                  r"([A-Z][A-Za-z .'-]+(?:,\s*[A-Z]{2})?)", text)
    if m:
        return m.group(1).strip(" .")
    low = text.lower()
    for st in US_STATES:
        if st in low:
            return st.title()
    return None


def detect_date(text):
    low = text.lower()
    m = re.search(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b", text)
    if m:
        return m.group(1)
    months = ("january february march april may june july august september "
              "october november december").split()
    for mo in months:
        if mo in low or mo[:3] in low:
            # optional day = 1-2 digits NOT part of a longer number (e.g. a year)
            mm = re.search(r"\b" + mo[:3] + r"[a-z]*\.?(?:\s+(\d{1,2})(?!\d))?", low)
            if mm:
                return mo.title() + (" " + mm.group(1) if mm.group(1) else "")
            return mo.title()
    return None


def detect_loop(text):
    low = text.lower()
    if any(w in low for w in ["loop", "round trip", "round-trip", "环线", "往返", "回到"]):
        return "loop"
    if any(w in low for w in ["one way", "one-way", "single", "单程"]):
        return "one-way"
    return None


def detect_border(text):
    low = text.lower()
    return any(w in low for w in ["canada", "canadian", "mexico", "mexican",
                                  "border", "banff", "jasper", "tijuana",
                                  "跨境", "加拿大", "墨西哥"])


def analyze(text):
    slots = {
        "start": detect_start(text),
        "date": detect_date(text),
        "days": detect_days(text),
        "party": detect_party(text),
        "vehicle": detect_vehicle(text),
        "region": detect_region(text),
        "loopType": detect_loop(text),
        "crossBorder": detect_border(text),
    }
    missing = [s for s in REQUIRED_SLOTS if not slots.get(s)]
    return {
        "mode": detect_mode(text),
        "slots": slots,
        "missingRequired": missing,
        "ready": not missing,
        "hint": _hint(slots, missing),
    }


def drive_intensity(total_miles, days, party=""):
    """Classify the daily driving load for a route option (multi-route compare)."""
    if not days:
        return "unknown"
    per_day = total_miles / float(days)
    soft = "kid" in (party or "").lower() or "senior" in (party or "").lower() \
        or "family" in (party or "").lower()
    # rough hours assuming ~55 mph incl. stops
    hours = per_day / 55.0
    cap = 4.0 if soft else 5.0
    if hours <= cap * 0.6:
        return "relaxed (~%.1fh/day)" % hours
    if hours <= cap:
        return "moderate (~%.1fh/day)" % hours
    return "intense (~%.1fh/day)" % hours


def compare_routes(options, party=""):
    """Build a routeOptions[] comparison for the schema.

    options: list of dicts, each {name, miles, days, highlights, bestSeason,
             estCost, pros, cons, chosen?}. Fills driveIntensity if absent.
    """
    out = []
    for o in options:
        row = dict(o)
        if not row.get("driveIntensity"):
            row["driveIntensity"] = drive_intensity(row.get("miles", 0),
                                                     row.get("days"), party)
        out.append(row)
    return {"routeOptions": out}


def _hint(slots, missing):
    if missing:
        return ("Ask the user for: " + ", ".join(missing) +
                ". Fill optional slots with defaults and proceed.")
    return "All required slots present — proceed to Step 2/3 (route + segmentation)."


def main(argv):
    if len(argv) > 1 and argv[1] == "--compare":
        demo = [
            {"name": "Loop via US-50 & I-80", "miles": 500, "days": 3,
             "highlights": "Apple Hill, Emerald Bay, Donner", "bestSeason": "Jun–Oct",
             "estCost": 857, "pros": "sees both shores", "cons": "two mountain passes",
             "chosen": True},
            {"name": "Out-and-back on US-50", "miles": 470, "days": 3,
             "highlights": "South shore focus", "bestSeason": "year-round (chains in winter)",
             "estCost": 800, "pros": "simpler, one pass", "cons": "misses north shore"},
        ]
        print(json.dumps(compare_routes(demo, "2 adults"), ensure_ascii=False, indent=2))
        return 0
    text = " ".join(argv[1:]).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print("usage: helper.py \"<road trip request>\"", file=sys.stderr)
        return 2
    print(json.dumps(analyze(text), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
