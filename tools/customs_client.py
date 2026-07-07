#!/usr/bin/env python3
"""
customs_client.py — personal duty-free exemption ("免税额") for US <-> Canada <-> Mexico trips.

Deterministic rules table for the personal exemption a resident can bring home
duty-free, keyed by residence country and hours spent abroad (the 24h / 48h
thresholds the model must never recall from memory). This is rules, not live
data — amounts change; always confirm against CBP / CBSA / SAT before travel.

User-facing strings come in English (`note`) and Simplified Chinese (`noteZh`)
so rendered itineraries stay language-independent.

CLI:
    python3 customs_client.py US 72             # US resident, 72h abroad
    python3 customs_client.py US 72 --used-30d  # USD 800 already claimed this month
    python3 customs_client.py CA 30             # Canadian resident, 30h abroad
"""

import json
import sys

_VERIFY = {
    "US": "CBP — Customs Duty Information (cbp.gov)",
    "CA": "CBSA — Personal exemptions (cbsa-asfc.gc.ca)",
    "MX": "SAT / Aduanas — franquicia de pasajeros (sat.gob.mx)",
}

_DISCLAIMER    = ("Exemption rules change and carry per-person fine print — "
                  "confirm with the official source before you cross.")
_DISCLAIMER_ZH = "免税额规则会调整且有细则限制——过境前请以官方口径为准。"


def _result(residence, hours, amount, currency, tier,
            note, note_zh, conditions, conditions_zh):
    return {
        "source":       "rules",
        "residence":    residence,
        "hoursAbroad":  round(float(hours), 1),
        "amount":       amount,
        "currency":     currency,
        "tier":         tier,  # "standard" | "reduced" | "none"
        "note":         note,
        "noteZh":       note_zh,
        "conditions":   conditions,
        "conditionsZh": conditions_zh,
        "verify":       _VERIFY.get(residence),
        "disclaimer":   _DISCLAIMER,
        "disclaimerZh": _DISCLAIMER_ZH,
    }


def personal_exemption(residence, hours_abroad, used_within_30_days=False):
    """Duty-free personal exemption for a resident RE-ENTERING their home
    country after `hours_abroad` hours away.

    residence:  "US" | "CA" | "MX" — the traveler's home country. One-way
                trips that never re-enter it have no exemption to show.
    hours_abroad: total hours outside the home country. Deriving it from the
                itinerary ((return-crossing day − outbound-crossing day) × 24)
                is accurate enough for the 24h/48h thresholds.
    used_within_30_days: US only — True if the USD 800 exemption was already
                claimed in the past 30 days (drops this crossing to USD 200).
    """
    residence = (residence or "").upper()
    h = float(hours_abroad)

    if residence == "US":
        if h >= 48 and not used_within_30_days:
            return _result(
                "US", h, 800, "USD", "standard",
                "US residents abroad 48+ hours: USD 800 duty-free per person "
                "(claimable once every 30 days).",
                "美国居民在境外满 48 小时:每人 800 美元免税额(每 30 天限用一次)。",
                ["May include up to 1L of alcohol, 200 cigarettes and 100 cigars",
                 "Family members on a joint declaration may pool their exemptions",
                 "The next USD 1,000 above the exemption is dutied at a flat 3%"],
                ["额度内可含至多 1 升酒、200 支香烟和 100 支雪茄",
                 "同行家庭成员联合申报时可合并额度",
                 "超出额度的头 1,000 美元按 3% 统一税率计税"])
        reason    = ("under 48 hours abroad" if h < 48
                     else "USD 800 already claimed within the past 30 days")
        reason_zh = ("境外停留不满 48 小时" if h < 48
                     else "30 天内已用过 800 美元额度")
        return _result(
            "US", h, 200, "USD", "reduced",
            "US residents (%s): USD 200 duty-free per person." % reason,
            "美国居民(%s):每人 200 美元免税额。" % reason_zh,
            ["Includes at most 150 ml of alcohol and 50 cigarettes"],
            ["至多含 150 毫升酒和 50 支香烟"])

    if residence == "CA":
        if h < 24:
            return _result(
                "CA", h, 0, "CAD", "none",
                "Canadian residents away under 24 hours get no personal "
                "exemption — regular duties/taxes apply to everything.",
                "加拿大居民离境不满 24 小时没有个人免税额——所有物品按常规征税。",
                [], [])
        if h < 48:
            return _result(
                "CA", h, 200, "CAD", "reduced",
                "Canadian residents away 24-48 hours: CAD 200 duty-free per person.",
                "加拿大居民离境 24-48 小时:每人 200 加元免税额。",
                ["Alcohol and tobacco are NOT covered by this tier",
                 "Exceed CAD 200 and duties apply to the FULL value, "
                 "not just the excess"],
                ["该档不含酒类和烟草",
                 "超过 200 加元则按全额计税,而不是只对超出部分"])
        return _result(
            "CA", h, 800, "CAD", "standard",
            "Canadian residents away 48+ hours: CAD 800 duty-free per person.",
            "加拿大居民离境满 48 小时:每人 800 加元免税额。",
            ["May include one of 1.5L wine / 1.14L spirits / 24 cans of beer, "
             "plus 200 cigarettes",
             "Only the value above CAD 800 is dutied",
             "Exemptions cannot be pooled between family members"],
            ["额度内可含 1.5 升葡萄酒 / 1.14 升烈酒 / 24 罐啤酒三者其一,"
             "外加 200 支香烟",
             "只对超出 800 加元的部分计税",
             "家庭成员之间不可合并额度"])

    if residence == "MX":
        return _result(
            "MX", h, 300, "USD", "standard",
            "Mexican residents returning by land: USD 300 franquicia per person "
            "(USD 500 by air; seasonal 'paisano' windows can raise the land amount).",
            "墨西哥居民陆路回国:每人 300 美元免税额(空路 500 美元;"
            "'paisano' 季节性政策可能上调陆路额度)。",
            ["Personal luggage is exempt separately from the franquicia"],
            ["个人行李另行免税,不占用该额度"])

    return {"source": "error", "reason": "unsupported residence: %s" % residence}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    used = "--used-30d" in sys.argv
    res  = args[0] if args else "US"
    hrs  = float(args[1]) if len(args) > 1 else 72
    print(json.dumps(personal_exemption(res, hrs, used),
                     indent=2, ensure_ascii=False))
