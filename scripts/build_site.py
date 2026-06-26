#!/usr/bin/env python3
"""
build_site.py — build the static marketing / SEO site into ./docs.

Why: the skill's strongest asset is the *output* — real, drivable itineraries.
Travellers search Google for "7 day southwest national parks road trip
itinerary" every day. Publishing the sample trips as standalone, SEO-tagged
pages turns that search traffic into a funnel: a visitor finds a great
itinerary, then learns they can generate their own with the skill.

What it produces (served via GitHub Pages from /docs):
    docs/index.html                       landing hub (hand-written, crawlable)
    docs/trips/<slug>.html                each sample trip + injected SEO <head>
    docs/sitemap.xml, docs/robots.txt

Each trip page is the normal single-file itinerary (from assets/generate.py)
with an SEO <head> (title/description/canonical/OpenGraph/Twitter/JSON-LD) and
a slim brand ribbon linking back to the repo. The itinerary itself still
renders client-side from the embedded data, exactly like the downloadable file.

Usage:
    python3 scripts/build_site.py
    SITE_BASE_URL=https://roadtripskill.dev python3 scripts/build_site.py

Set SITE_BASE_URL to wherever the site is actually served so canonical/OG URLs
are correct (default: https://roadtripskill.dev).
"""

import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
DOCS = os.path.join(ROOT, "docs")

sys.path.insert(0, ASSETS)
import generate  # noqa: E402  (assets/generate.py)

BASE_URL = os.environ.get("SITE_BASE_URL", "https://roadtripskill.dev").rstrip("/")
REPO_URL = "https://github.com/Waybox-AI/roadtrip-skill"

# Per-trip SEO metadata. `data` is the source tripData; `img` the OG screenshot
# produced by scripts/capture_demo.js.
TRIPS = [
    {
        "slug": "southwest-national-parks-road-trip-7-days",
        "data": "tripData.example.json",
        "img": "southwest-og.png",
        "title": "7-Day Southwest National Parks Road Trip Itinerary (Las Vegas Loop)",
        "desc": (
            "A drivable 7-day Southwest road trip from Las Vegas — Zion, Bryce, "
            "Antelope Canyon/Page and the Grand Canyon. Day-by-day driving "
            "segments, overnight towns, fuel stops and a national-park "
            "reservation countdown."
        ),
        "keywords": "southwest road trip, las vegas national parks loop, zion bryce grand canyon itinerary, 7 day road trip",
        "blurb": (
            "A relaxed week-long loop out of Las Vegas hitting four of the "
            "Southwest's headline parks. Paced so no day is a slog, with the "
            "must-book-early reservations (Antelope Canyon tour, Grand Canyon "
            "South Rim lodging) called out as a dated countdown."
        ),
    },
    {
        "slug": "sunnyvale-lake-tahoe-road-trip-3-days",
        "data": "tripData.tahoe.json",
        "img": "tahoe-og.png",
        "title": "3-Day Lake Tahoe Road Trip from the Bay Area (Sunnyvale Loop)",
        "desc": (
            "A 3-day Sunnyvale to Lake Tahoe road trip: US-50 out, around the "
            "lake, I-80 back via Truckee. Day-by-day driving, ReserveCalifornia "
            "state-park bookings and Sierra snow/chain-control risk."
        ),
        "keywords": "lake tahoe road trip, bay area to tahoe, 3 day tahoe itinerary, reservecalifornia, sierra snow chains",
        "blurb": (
            "A long-weekend escape from the Bay Area to South Lake Tahoe and "
            "back. Short driving days, ReserveCalifornia booking windows, and an "
            "honest read on Sierra snow and chain-control season."
        ),
    },
    {
        "slug": "seattle-vancouver-whistler-ev-road-trip-4-days",
        "data": "tripData.pnw.json",
        "img": "pnw-og.png",
        "title": "4-Day Seattle to Vancouver & Whistler EV Road Trip (Cross-Border)",
        "desc": (
            "An electric 4-day Seattle to Vancouver and Whistler road trip with "
            "a leg-by-leg EV charging corridor (state-of-charge per stop) and a "
            "US-to-Canada border-crossing document & insurance checklist."
        ),
        "keywords": "seattle to vancouver road trip, whistler ev road trip, cross border ev charging, sea to sky electric",
        "blurb": (
            "A four-day electric loop from Seattle up to Vancouver and the Sea-"
            "to-Sky highway to Whistler. Includes a per-leg charging corridor "
            "with state-of-charge planning and a two-crossing border checklist "
            "(US insurance is valid in Canada — but not Mexico)."
        ),
    },
]

HEAD_TEMPLATE = """\
<title>{title} | RoadTrip Navigator</title>
<meta name="description" content="{desc}" />
<meta name="keywords" content="{keywords}" />
<meta name="robots" content="index,follow" />
<link rel="canonical" href="{url}" />
<meta property="og:type" content="article" />
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{desc}" />
<meta property="og:url" content="{url}" />
<meta property="og:image" content="{img_url}" />
<meta property="og:site_name" content="RoadTrip Navigator" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{title}" />
<meta name="twitter:description" content="{desc}" />
<meta name="twitter:image" content="{img_url}" />
<script type="application/ld+json">
{jsonld}
</script>"""

RIBBON = """\
<div style="background:#1f2a30;color:#fff;font:14px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:9px 14px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:center;text-align:center;">
  <span>🚗 This itinerary was generated by <strong>RoadTrip Navigator</strong>, a free open-source Claude Code skill.</span>
  <a href="{repo}" style="color:#fff;background:#c2641a;border-radius:6px;padding:4px 12px;text-decoration:none;font-weight:600;">Plan your own →</a>
</div>"""


def jsonld_for(trip, url, img_url, src):
    parts = (src.get("subtitle") or "").replace("→", "to").split(" to ")
    waypoints = [
        {"@type": "TouristAttraction", "name": p.strip()}
        for p in parts if p.strip()
    ][:8]
    obj = {
        "@context": "https://schema.org",
        "@type": "TouristTrip",
        "name": trip["title"],
        "description": trip["desc"],
        "url": url,
        "image": img_url,
        "touristType": "Road trip / self-drive",
    }
    if waypoints:
        obj["itinerary"] = {"@type": "ItemList", "itemListElement": waypoints}
    return json.dumps(obj, ensure_ascii=False, indent=2)


def build_trip(trip):
    src_path = os.path.join(ASSETS, trip["data"])
    with open(src_path, encoding="utf-8") as f:
        src = json.load(f)
    with open(os.path.join(ASSETS, "template.html"), encoding="utf-8") as f:
        template = f.read()

    page = generate.build_html(src, template)

    url = "%s/trips/%s.html" % (BASE_URL, trip["slug"])
    img_url = "%s/img/%s" % (BASE_URL, trip["img"])
    head = HEAD_TEMPLATE.format(
        title=html.escape(trip["title"]),
        desc=html.escape(trip["desc"]),
        keywords=html.escape(trip["keywords"]),
        url=url,
        img_url=img_url,
        jsonld=jsonld_for(trip, url, img_url, src),
    )

    # Replace the placeholder <title> with the full SEO head block.
    page = page.replace("<title>RoadTrip Navigator</title>", head, 1)
    # Brand CTA ribbon right after <body>.
    page = page.replace("<body>", "<body>\n" + RIBBON.format(repo=REPO_URL), 1)

    out_dir = os.path.join(DOCS, "trips")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, trip["slug"] + ".html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return url


def trip_card(trip, src):
    return """\
    <a class="card" href="trips/{slug}.html">
      <img loading="lazy" src="img/{img}" alt="{alt}" />
      <div class="card-body">
        <h3>{title}</h3>
        <p class="meta">{miles} mi · {days} days · {dates}</p>
        <p>{blurb}</p>
        <span class="more">View the itinerary →</span>
      </div>
    </a>""".format(
        slug=trip["slug"],
        img=trip["img"],
        alt=html.escape(trip["title"]),
        title=html.escape(trip["title"]),
        miles=src.get("totalMiles", "—"),
        days=src.get("drivingDays", "—"),
        dates=html.escape(src.get("dateRange", "")),
        blurb=html.escape(trip["blurb"]),
    )


def build_index(cards):
    url = BASE_URL + "/"
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "RoadTrip Navigator",
        "applicationCategory": "TravelApplication",
        "operatingSystem": "Claude Code (macOS, Windows, Linux, Web)",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "url": url,
        "description": (
            "An open-source Claude Code skill that turns a start point and a "
            "number of days into a drivable North American road-trip itinerary."
        ),
    }, ensure_ascii=False, indent=2)

    return INDEX_TEMPLATE.format(
        base=BASE_URL,
        repo=REPO_URL,
        cards="\n".join(cards),
        jsonld=jsonld,
    )


INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>RoadTrip Navigator — AI road-trip itineraries you can actually drive</title>
<meta name="description" content="A free, open-source Claude Code skill that turns 'start + days' into a drivable North American road trip: daily driving segments, overnight stops, fuel/EV charging, national-park reservations, seasonal closures and border crossings — as a map-first single-file HTML page." />
<meta name="keywords" content="ai road trip planner, road trip itinerary generator, national park road trip, ev road trip planner, claude code skill" />
<link rel="canonical" href="{base}/" />
<meta property="og:type" content="website" />
<meta property="og:title" content="RoadTrip Navigator — AI road-trip itineraries you can actually drive" />
<meta property="og:description" content="Turn 'start + days' into a drivable North American road trip. Free, open-source Claude Code skill." />
<meta property="og:url" content="{base}/" />
<meta property="og:image" content="{base}/img/southwest-og.png" />
<meta property="og:site_name" content="RoadTrip Navigator" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="RoadTrip Navigator" />
<meta name="twitter:description" content="AI road-trip itineraries you can actually drive. Free, open-source Claude Code skill." />
<meta name="twitter:image" content="{base}/img/southwest-og.png" />
<script type="application/ld+json">
{jsonld}
</script>
<style>
  :root {{ --bg:#f7f5f0; --card:#fff; --ink:#2a2724; --muted:#6b6258; --line:#e7e1d6; --accent:#c2641a; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); line-height:1.6;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif; }}
  a {{ color:var(--accent); }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:0 18px; }}
  header.hero {{ background:linear-gradient(135deg,#c2641a,#8f3f12); color:#fff; padding:64px 18px 56px; text-align:center; }}
  header.hero h1 {{ font-size:2.5rem; margin:.2em 0; }}
  header.hero p {{ font-size:1.2rem; max-width:680px; margin:.4em auto 1.4em; opacity:.95; }}
  .cta {{ display:inline-flex; gap:10px; flex-wrap:wrap; justify-content:center; }}
  .btn {{ background:#fff; color:#8f3f12; border-radius:8px; padding:11px 20px; font-weight:700; text-decoration:none; }}
  .btn.ghost {{ background:transparent; color:#fff; border:1.5px solid #ffffff88; }}
  section {{ padding:48px 0; }}
  h2 {{ font-size:1.7rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:22px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden;
    text-decoration:none; color:inherit; display:flex; flex-direction:column; transition:transform .12s, box-shadow .12s; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 10px 28px rgba(0,0,0,.10); }}
  .card img {{ width:100%; aspect-ratio:1200/630; object-fit:cover; border-bottom:1px solid var(--line); background:#eee; }}
  .card-body {{ padding:16px 18px 20px; }}
  .card-body h3 {{ margin:.1em 0 .3em; font-size:1.12rem; }}
  .meta {{ color:var(--muted); font-size:.9rem; margin:.1em 0 .7em; }}
  .more {{ color:var(--accent); font-weight:600; }}
  .features {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:20px; }}
  .feature {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }}
  .feature h3 {{ margin:.1em 0 .4em; font-size:1.05rem; }}
  pre {{ background:#1f2a30; color:#e8edf0; padding:16px 18px; border-radius:10px; overflow:auto; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em; }}
  footer {{ border-top:1px solid var(--line); padding:32px 18px; text-align:center; color:var(--muted); font-size:.92rem; }}
</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <h1>🚗 Road trips you can actually drive</h1>
    <p>RoadTrip Navigator turns <strong>“start + days”</strong> into a North American road trip — paced into daily drives, with overnight stops, fuel/EV charging, national-park reservations, seasonal closures and border crossings — as a map-first, offline-friendly single-file page.</p>
    <div class="cta">
      <a class="btn" href="{repo}#-install">Install the skill</a>
      <a class="btn ghost" href="#samples">See sample trips</a>
    </div>
  </div>
</header>

<main class="wrap">
  <section id="samples">
    <h2>Sample itineraries</h2>
    <p>Real, generated trips — open one on your phone, every stop has one-tap Google/Apple Maps links.</p>
    <div class="grid">
{cards}
    </div>
  </section>

  <section>
    <h2>Why it’s different from a generic AI itinerary</h2>
    <div class="features">
      <div class="feature"><h3>🛣️ Daily driving segmentation</h3><p>The route is sliced into days under a sane drive limit, with overnight towns and “arrive before dark / no closed gate” checks — not just a wishlist of stops.</p></div>
      <div class="feature"><h3>⏳ Reservation countdown</h3><p>Exact “book by” dates on the right system (Recreation.gov, ReserveCalifornia, Parks Canada): campgrounds ~6 months out, in-park lodges up to ~13 months.</p></div>
      <div class="feature"><h3>⚡ Fuel &amp; EV charging</h3><p>Long empty-stretch warnings for gas; a per-leg charging corridor with state-of-charge and a winter-range derate for EVs.</p></div>
      <div class="feature"><h3>❄️ Season &amp; closures</h3><p>Closure-aware: winter passes (Going-to-the-Sun, Tioga, Trail Ridge), wildfire and snow — it down-ranks or reroutes and says so.</p></div>
      <div class="feature"><h3>🛂 Borders &amp; timezones</h3><p>Timezone-corrected arrivals and a US↔Canada↔Mexico documents / insurance / wait checklist.</p></div>
      <div class="feature"><h3>📊 Reliability-graded budget</h3><p>Every figure tagged verified / reference / estimate, so you know what to double-check before you leave.</p></div>
    </div>
  </section>

  <section>
    <h2>Get started in two commands</h2>
    <p>Install it into <a href="{repo}">Claude Code</a> as a plugin — no API key required:</p>
    <pre><code>/plugin marketplace add Waybox-AI/roadtrip-skill
/plugin install roadtrip-navigator@roadtrip-skill</code></pre>
    <p>Then just ask in plain language: <em>“Plan a 7-day Southwest national parks road trip from Las Vegas for 2 adults in September, gas SUV, loop.”</em></p>
    <p><a class="more" href="{repo}">Read the docs &amp; source on GitHub →</a></p>
  </section>
</main>

<footer>
  <p>RoadTrip Navigator is free and open-source (MIT). Itineraries are AI-assembled and may be out of date — always verify with official sources before you drive.</p>
  <p><a href="{repo}">GitHub</a> · <a href="{base}/">{base}</a></p>
</footer>
</body>
</html>
"""


def main():
    os.makedirs(DOCS, exist_ok=True)
    cards = []
    urls = [BASE_URL + "/"]
    for trip in TRIPS:
        url = build_trip(trip)
        urls.append(url)
        with open(os.path.join(ASSETS, trip["data"]), encoding="utf-8") as f:
            src = json.load(f)
        cards.append(trip_card(trip, src))
        print("built", os.path.relpath(url.replace(BASE_URL, DOCS)))

    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(cards))
    print("built docs/index.html")

    # sitemap + robots
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append("  <url><loc>%s</loc></url>" % u)
    sm.append("</urlset>")
    with open(os.path.join(DOCS, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")
    with open(os.path.join(DOCS, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % BASE_URL)
    # Jekyll on GitHub Pages would otherwise ignore files; disable it.
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("built sitemap.xml, robots.txt, .nojekyll")


if __name__ == "__main__":
    main()
