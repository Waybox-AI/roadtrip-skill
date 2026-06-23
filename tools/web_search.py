#!/usr/bin/env python3
"""
web_search.py — the universal fallback.

This skill runs inside an agent that already has a real web-search capability.
These clients are *not* meant to replace it; they reach official/free APIs when
possible and otherwise hand back a structured "search this" instruction that the
agent should execute with its own search tool.

So the contract here is: build good queries and a clear fallback payload.
"""

from urllib.parse import quote_plus


def fallback(reason, queries, sources=None):
    """Standard fallback payload returned by every client when a live source
    is unavailable. The agent should run `queries` with its web-search tool."""
    return {
        "source": "fallback",
        "reason": reason,
        "searchQueries": queries if isinstance(queries, list) else [queries],
        "suggestedSources": sources or [],
    }


def reddit_query(topic):
    return ('site:reddit.com (r/roadtrip OR r/nationalparks OR r/RVliving) '
            + topic)


def search_links(query):
    """Convenience: ready-made search URLs for a few engines (the agent may also
    just use its native search)."""
    q = quote_plus(query)
    return {
        "google": "https://www.google.com/search?q=" + q,
        "ddg": "https://duckduckgo.com/?q=" + q,
    }


if __name__ == "__main__":
    import json
    import sys
    topic = " ".join(sys.argv[1:]) or "Southwest national parks road trip tips"
    print(json.dumps({
        "fallback": fallback("demo", [topic, reddit_query(topic)]),
        "links": search_links(topic),
    }, indent=2))
