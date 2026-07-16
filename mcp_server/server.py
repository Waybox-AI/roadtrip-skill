#!/usr/bin/env python3
"""
server.py — MCP server for the RoadTrip Navigator skill.

Exposes the skill's deterministic capabilities to ANY MCP host (Claude Code,
Codex CLI, Gemini CLI, Cursor, ...) over stdio:

  * the 10 data clients in tools/ as 12 typed tools (routing, weather, parks,
    reservation countdown, EV charging, border/customs rules, fuel, lodging,
    place-name validation),
  * the deterministic renderer (assets/generate.py) as `render_trip`,
  * the skill's planning knowledge as `get_planning_guide` — tool-shaped so it
    reaches hosts that support neither MCP prompts nor Bash skills.

This module is a thin adapter: every tool delegates to the existing client
functions, which keep their CLI entry points and tests. No planning logic
lives here.

Failure contract (inherited from tools/web_search.fallback): when a live
source is unavailable a tool returns {"source": "fallback", "searchQueries":
[...], "suggestedSources": [...]} instead of raising — the calling agent
should run those queries with its own web-search tool.

Run directly:            python3 -m mcp_server.server
Installed console script: roadtrip-mcp
"""

import datetime
import sys
from importlib import util as _importlib_util
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Layout resolution: repo checkout vs installed wheel
# --------------------------------------------------------------------------- #
# In a checkout, tools/ and assets/ are siblings of mcp_server/. In an
# installed wheel they are vendored under mcp_server/_vendor/ with the same
# relative layout (see pyproject.toml), so one _ROOT serves both cases.
# Prefer _vendor whenever it exists (an install always has it) and anchor the
# check on one of our own files — a bare `tools/` sibling is NOT evidence of a
# checkout, since an unrelated site-packages `tools` package satisfies it.
_HERE = Path(__file__).resolve().parent
_ANCHOR = ("tools", "border_client.py")
_VENDOR = _HERE / "_vendor"
_ROOT = _VENDOR if _VENDOR.joinpath(*_ANCHOR).is_file() else _HERE.parent
if not _ROOT.joinpath(*_ANCHOR).is_file():
    raise ImportError("roadtrip-mcp cannot locate the skill's tools/ from %s "
                      "(broken install or moved checkout)" % _HERE)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools import (  # noqa: E402
    border_client,
    charging_client,
    customs_client,
    fuel_client,
    lodging_client,
    parks_client,
    places_client,
    routing_client,
    weather_client,
    web_search,
)


def _load_renderer():
    """Import assets/generate.py by path (assets/ is not a package)."""
    spec = _importlib_util.spec_from_file_location(
        "_roadtrip_generate", _ROOT / "assets" / "generate.py")
    mod = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_generate = _load_renderer()


def _read_doc(name):
    return (_ROOT / name).read_text(encoding="utf-8")


def _strip_frontmatter(md):
    """Drop the YAML frontmatter block (--- ... ---) from a skill doc."""
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4:].lstrip("\n")
    return md


_FALLBACK_NOTE = ("If the result has source:'fallback', the live source was "
                  "unavailable — run its searchQueries with your own web-search "
                  "tool instead of treating the call as failed.")

# NOTE(v2 hook): when a connected client advertises the `sampling` capability
# (or a server-side model key is configured), a high-level `plan_trip` tool can
# be registered alongside the data tools below — data gathering + validation
# stay code-owned, generation is delegated back to the host model. Deliberately
# out of v1 scope: Codex/Gemini do not support sampling today.
mcp = FastMCP(
    "roadtrip-navigator",
    instructions=(
        "Deterministic data tools and the itinerary renderer of the RoadTrip "
        "Navigator skill (North American road trips). Before planning a full "
        "multi-day trip, call get_planning_guide(topic='workflow') for the "
        "planning rules and get_planning_guide(topic='schema') for the tripData "
        "contract that render_trip expects. Validate every user-supplied place "
        "name with validate_place before routing around it. " + _FALLBACK_NOTE),
)


# --------------------------------------------------------------------------- #
# Step 1 — place validation
# --------------------------------------------------------------------------- #
@mcp.tool()
def validate_place(name: str, na_bias: bool = True, limit: int = 8) -> dict:
    """Check that a user-supplied place name is a real place (OpenStreetMap via
    the free Photon geocoder) BEFORE planning around it.

    Verdicts: 'match' (canonical name + lat/lng; outsideNA=True when outside
    US/CA/MX), 'did-you-mean' (confirm suggestions with the user), 'no-match'
    (looks nonexistent — ask, never plan around it), 'unverified' (geocoder
    unreachable — web-search fallback shape; do NOT read as fake).
    na_bias prefers a US/CA/MX match over an equally-scored one elsewhere
    ("Paris" -> Paris, Texas).
    """
    return places_client.validate_place(name, na_bias=na_bias, limit=limit)


# --------------------------------------------------------------------------- #
# Step 2/3 — routing
# --------------------------------------------------------------------------- #
@mcp.tool()
def route(waypoints: list[list[float]]) -> dict:
    """Real driving distance and time through 2+ waypoints (OSRM, no key).

    waypoints: ordered [[lat, lng], ...]. Returns {miles, driveTime "XhYYm",
    hours}. On OSRM failure falls back to great-circle x 1.25 road factor and
    includes web-search queries — grade that result as an estimate, not
    verified. Use this instead of guessing distances: it is the basis for
    daily-drive segmentation.
    """
    pts = []
    for w in waypoints:
        if not isinstance(w, (list, tuple)) or len(w) < 2:
            return {"source": "error",
                    "reason": "each waypoint must be [lat, lng], got: %r" % (w,)}
        pts.append((float(w[0]), float(w[1])))
    return routing_client.route(pts)


# --------------------------------------------------------------------------- #
# Weather
# --------------------------------------------------------------------------- #
@mcp.tool()
def weather_forecast(lat: float, lng: float) -> dict:
    """Real per-day weather forecast for a point: NWS (US, ~7 days) first,
    Open-Meteo (global, ~16 days — covers Canada/Mexico legs) second.

    Returns {source, units:'F', days:[{date, high, low, icon, summary,
    precipProb?, windMph?}]}. Use for trips departing within the forecast
    window; for far-future dates use weather_climatology instead.
    """
    return weather_client.forecast(lat, lng)


@mcp.tool()
def weather_climatology(lat: float, lng: float, month: int, day: int,
                        span_days: int = 7) -> dict:
    """'Typical for the season' weather for a calendar date beyond any forecast
    window (Open-Meteo archive, same week last year). NOT a forecast — a
    climatological hint for seasonal risk (snow closures, monsoon, heat).

    Returns {high, low, icon, summary, wetShare (fraction of sampled days with
    precip), year} or {source:'unavailable'} when the archive can't be reached.
    """
    res = weather_client.climatology(lat, lng, month, day, span_days=span_days)
    if res is None:
        return web_search.fallback(
            "climatology archive unreachable or returned no data",
            ["typical weather %02d-%02d near %.3f,%.3f" % (int(month), int(day), lat, lng)],
            ["https://open-meteo.com", "https://www.usclimatedata.com"])
    return res


# --------------------------------------------------------------------------- #
# Parks & reservations
# --------------------------------------------------------------------------- #
@mcp.tool()
def park_info(query: str) -> dict:
    """Official national-park info via the NPS API: name, states, entrance fee,
    coordinates, description, nps.gov URL (top 3 matches).

    Needs the free NPS_API_KEY env var on the server; without it (or on API
    failure) returns the web-search fallback shape pointing at nps.gov.
    """
    return parks_client.park_info(query)


@mcp.tool()
def reservation_countdown(arrival_date: str,
                          items: list[dict] = []) -> dict:
    """Work BACKWARDS from an arrival date (YYYY-MM-DD) to 'book by' deadlines —
    the reservation-countdown discipline that separates an executable trip from
    a wish list.

    items: [{item, rule, where}] where rule is one of: campground
    (Recreation.gov ~T-180d), timed-entry (~T-7d), wilderness-permit (~T-90d),
    in-park-lodge (~T-395d), one-way-rental (~T-60d). An empty list (the
    default) uses a generic park set. Deadlines already past clamp to today
    ('book ASAP'). Windows are starting points — confirm the exact rule per
    park/system.
    """
    try:
        datetime.date.fromisoformat(arrival_date)
    except (TypeError, ValueError):
        return {"source": "error",
                "reason": "arrival_date must be YYYY-MM-DD, got %r" % (arrival_date,)}
    valid = sorted(parks_client.RELEASE_RULES)
    tuples = None
    if items:
        tuples = []
        for it in items:
            rule = (it or {}).get("rule")
            if rule not in parks_client.RELEASE_RULES:
                return {"source": "error",
                        "reason": "unknown rule %r — valid rules: %s"
                                  % (rule, ", ".join(valid))}
            tuples.append((it.get("item") or it.get("label") or rule,
                           rule, it.get("where") or ""))
    return parks_client.countdown(arrival_date, tuples)


# --------------------------------------------------------------------------- #
# EV charging
# --------------------------------------------------------------------------- #
@mcp.tool()
def chargers_near(lat: float, lng: float, distance_mi: float = 25,
                  min_kw: int = 50, limit: int = 8) -> dict:
    """DC fast chargers near a point via Open Charge Map (free; OCM_API_KEY env
    var recommended). Returns {chargers:[{name, town, lat, lng, powerKW}]}
    filtered to >= min_kw. Falls back to PlugShare/ABRP search queries.
    """
    return charging_client.chargers_near(lat, lng, distance_mi=distance_mi,
                                         min_kw=min_kw, limit=limit)


@mcp.tool()
def ev_corridor(legs: list[dict], usable_range_miles: float,
                start_soc: float = 90, min_soc: float = 10,
                buffer_soc: float = 10, max_charge_soc: float = 90,
                winter_derate: float = 0.0) -> dict:
    """Simulate EV state-of-charge along an ordered route and flag legs that
    won't make it on the planned charge (linear model — planning aid, not a
    substitute for ABRP/the car).

    legs: [{to, miles, charger (bool: charger at that stop), chargerKW}].
    winter_derate: fraction of range lost to cold (e.g. 0.25). Returns per-leg
    depart/arrive SoC, charge-to targets at stops, and warnings for gaps —
    run it whenever the vehicle is an EV.
    """
    return charging_client.corridor(legs, usable_range_miles,
                                    start_soc=start_soc, min_soc=min_soc,
                                    buffer_soc=buffer_soc,
                                    max_charge_soc=max_charge_soc,
                                    winter_derate=winter_derate)


# --------------------------------------------------------------------------- #
# Cross-border
# --------------------------------------------------------------------------- #
@mcp.tool()
def border_crossing(crossings: list[dict]) -> dict:
    """Checklist for US/Canada/Mexico land crossings: documents, vehicle papers,
    insurance validity (Mexican liability insurance is mandatory in MX), customs
    notes, unit/currency switches, and live wait-time sources.

    crossings: ordered [{from, to, rental}] with ISO country codes US|CA|MX and
    rental=True when driving a rental across (rental contracts often forbid or
    restrict it). Rules-based, not live data — confirm with CBP/CBSA/Banjercito.
    """
    tuples = []
    for c in crossings:
        c = c or {}
        tuples.append((str(c.get("from", "")), str(c.get("to", "")),
                       bool(c.get("rental", False))))
    return border_client.trip_section(tuples)


@mcp.tool()
def customs_exemption(residence: str, hours_abroad: float,
                      used_within_30_days: bool = False) -> dict:
    """Duty-free personal exemption for a US/CA/MX resident RE-ENTERING their
    home country, keyed by the 24h/48h thresholds a model should never recall
    from memory (US: $800 at 48h+; CA: none <24h / CAD 200 / CAD 800; MX: $300
    by land).

    hours_abroad ~= (return-crossing day - outbound day) x 24.
    used_within_30_days (US only): True drops the exemption to USD 200.
    English + Chinese strings; rules change — verify against CBP/CBSA/SAT.
    """
    return customs_client.personal_exemption(residence, hours_abroad,
                                             used_within_30_days)


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
@mcp.tool()
def fuel_cost(miles: float, vehicle: Literal["gas", "ev"] = "gas",
              mpg: float = 26.0, region: str = "us",
              price_per_gal: float = -1, mi_per_kwh: float = -1,
              price_per_kwh: float = -1, place: str = "") -> dict:
    """Trip fuel or charging cost estimate for the budget (graded 'estimate' —
    no free live price API exists; override the price when you have a fresher
    figure).

    vehicle='gas': uses mpg + price_per_gal (or a regional prior: west,
    california, southwest, mountain, midwest, south, northeast, pacificnw, us).
    vehicle='ev': uses mi_per_kwh (default 3.3) + price_per_kwh (default $0.40
    DC fast-charge). Leave a price/efficiency at its -1 default to use the
    prior; any value <= 0 means "auto". place (non-empty) adds a GasBuddy
    live-price link for that town.
    """
    if vehicle == "ev":
        out = fuel_client.ev_cost(
            miles,
            mi_per_kwh if mi_per_kwh > 0 else fuel_client.EV_MI_PER_KWH,
            price_per_kwh if price_per_kwh > 0 else fuel_client.EV_PRICE_PER_KWH)
    else:
        out = fuel_client.gas_cost(
            miles, mpg, price_per_gal if price_per_gal > 0 else None, region)
    if place:
        out["gasbuddySearch"] = fuel_client.gasbuddy_link(place)
    return out


@mcp.tool()
def lodging_quote(place: str, checkin: str = "", checkout: str = "",
                  tier: Literal["budget", "midrange", "upscale", "campground",
                                "rv-site", "in-park-lodge"] = "midrange") -> dict:
    """Nightly reference price by lodging tier plus deep links to quote live
    (Booking, Airbnb, Google Hotels, KOA, Hipcamp, Recreation.gov).

    checkin/checkout (YYYY-MM-DD, both or neither) pre-fill the Booking link.
    The price is graded 'reference' — replace with a live quote when accuracy
    matters.
    """
    return lodging_client.quote(place, checkin, checkout, tier)


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #
@mcp.tool()
def render_trip(trip_data: dict, output_path: str = "trip.html") -> dict:
    """Render a tripData JSON object into the skill's map-first, single-file,
    offline-friendly HTML itinerary page.

    Writes the page to output_path (relative paths resolve against the server's
    working directory) and returns {path, sizeKB, days, warnings} — the HTML
    itself is deliberately NOT returned (tens to hundreds of KB would flood the
    conversation context). Get the
    tripData contract from get_planning_guide(topic='schema') first; warnings
    list schema gaps (missing coords, budget mismatch, ...) without failing.
    """
    out = Path(output_path).expanduser().resolve()
    if out.suffix.lower() not in (".html", ".htm"):
        return {"source": "error",
                "reason": "output_path must end in .html or .htm, got %r" % output_path}
    if not out.parent.is_dir():
        return {"source": "error",
                "reason": "parent directory does not exist: %s" % out.parent}
    template = (_ROOT / "assets" / "template.html").read_text(encoding="utf-8")
    warnings = _generate.validate(trip_data)
    html = _generate.build_html(trip_data, template)
    _generate.syntax_check(html)
    out.write_text(html, encoding="utf-8")
    return {
        "path": str(out),
        "sizeKB": len(html) // 1024,
        "days": len(trip_data.get("days", []) or []),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# Planning knowledge
# --------------------------------------------------------------------------- #
_TOOLS_GUIDE = """\
How to use the roadtrip-navigator MCP tools when planning a trip:

1. validate_place — every user-supplied place name, BEFORE routing around it.
2. route — real miles/drive-time between consecutive stops; slice the trip into
   days under a sane daily drive limit (see the workflow guide).
3. weather_forecast (departing within ~2 weeks) or weather_climatology
   (further out) — per overnight stop.
4. park_info + reservation_countdown — for every national park on the route;
   turn release windows into 'book by' deadlines.
5. ev_corridor (+ chargers_near for gaps) — whenever the vehicle is an EV.
6. border_crossing + customs_exemption — whenever the route crosses
   US/CA/MX borders.
7. fuel_cost + lodging_quote — budget lines, graded estimate/reference.
8. render_trip — final step: turn the assembled tripData JSON (contract:
   get_planning_guide(topic='schema')) into the single-file HTML page.

Failure contract: any tool may return {"source": "fallback", "searchQueries":
[...], "suggestedSources": [...]} when its live source is unreachable. Run the
queries with your own web-search tool and grade the answer accordingly
(verified / reference / estimate).

Optional server-side env keys: NPS_API_KEY (park_info), OCM_API_KEY
(chargers_near reliability). Everything else needs no key.
"""


@mcp.tool()
def get_planning_guide(topic: Literal["workflow", "schema", "tools"] = "workflow") -> str:
    """The skill's planning knowledge, tool-shaped so it works in every host.

    topic='workflow': the full RoadTrip Navigator planning method (daily-drive
    segmentation, overnight logic, reservation lead times, seasonal closures,
    honesty grading) — read this before planning a multi-day trip.
    topic='schema': the tripData JSON contract render_trip expects, plus
    reliability grading and the tool routing table.
    topic='tools': recommended call order for THESE MCP tools + the fallback
    contract.
    """
    if topic == "workflow":
        return _strip_frontmatter(_read_doc("SKILL.md"))
    if topic == "schema":
        return _read_doc("reference.md")
    return _TOOLS_GUIDE


# The same knowledge, also exposed via the standard MCP primitives for hosts
# that support them (e.g. Gemini CLI surfaces prompts as slash commands). The
# get_planning_guide TOOL above stays the lowest-common-denominator path.
@mcp.resource("roadtrip://skill.md")
def skill_doc() -> str:
    """The RoadTrip Navigator planning workflow (SKILL.md, frontmatter stripped)."""
    return _strip_frontmatter(_read_doc("SKILL.md"))


@mcp.resource("roadtrip://reference.md")
def reference_doc() -> str:
    """tripData schema, reliability grading, and tool-routing reference."""
    return _read_doc("reference.md")


@mcp.prompt()
def plan_road_trip(request: str = "") -> str:
    """Plan a North American road trip with the RoadTrip Navigator method."""
    return (_strip_frontmatter(_read_doc("SKILL.md"))
            + "\n\n---\n\nPlan the following trip with the workflow above, using "
              "the roadtrip-navigator MCP tools for every live figure "
              "(get_planning_guide(topic='tools') lists the call order):\n\n"
            + (request or "(ask the user for start, destination/region, days, "
                          "party, and vehicle)"))


def main():
    """Console-script entry point: serve over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
