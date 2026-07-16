# RoadTrip Navigator — MCP server

The [RoadTrip Navigator skill](../SKILL.md)'s deterministic capabilities,
served over the [Model Context Protocol](https://modelcontextprotocol.io) so
**any** MCP host — Claude Code, OpenAI Codex CLI, Google Gemini CLI, Cursor,
VS Code, … — can call them as typed tools. No shell access, Python setup, or
repo checkout required on the agent's side.

14 tools in three groups:

| Group | Tools |
|---|---|
| Live data & rules | `validate_place` · `route` · `weather_forecast` · `weather_climatology` · `park_info` · `reservation_countdown` · `chargers_near` · `ev_corridor` · `border_crossing` · `customs_exemption` · `fuel_cost` · `lodging_quote` |
| Renderer | `render_trip` — tripData JSON → the skill's single-file HTML itinerary page |
| Knowledge | `get_planning_guide` — the skill's workflow / tripData schema / tool-usage guide, tool-shaped so it reaches hosts without skill support (also registered as the `plan_road_trip` MCP prompt and the `roadtrip://skill.md` / `roadtrip://reference.md` resources for hosts that support those primitives) |

Every data tool follows the skill's **fallback contract**: when a live source
is unreachable it returns `{"source": "fallback", "searchQueries": [...]}`
instead of failing — run those queries with your agent's own web search.

## Install

One command per host (needs [uv](https://docs.astral.sh/uv/) — or substitute
`pipx run`):

```bash
# Claude Code
claude mcp add roadtrip -- uvx --from git+https://github.com/Waybox-AI/roadtrip-skill roadtrip-mcp

# OpenAI Codex CLI
codex mcp add roadtrip -- uvx --from git+https://github.com/Waybox-AI/roadtrip-skill roadtrip-mcp

# Google Gemini CLI
gemini mcp add roadtrip uvx --from git+https://github.com/Waybox-AI/roadtrip-skill roadtrip-mcp
```

> **Codex note:** interactive `codex` sessions ask you to approve each MCP tool
> call. Non-interactive `codex exec` runs cannot ask and auto-reject MCP calls
> (reported as "user cancelled") — pass
> `--dangerously-bypass-approvals-and-sandbox` for unattended runs.

From a local checkout (contributors), point the same hosts at:

```bash
python3 -m mcp_server.server   # run from the repo root
```

### Optional API keys (server-side env)

Everything works without keys; two tools get better with them:

| Env var | Tool | Without it |
|---|---|---|
| `NPS_API_KEY` ([free](https://www.nps.gov/subjects/developer/)) | `park_info` | web-search fallback |
| `OCM_API_KEY` ([free](https://openchargemap.org/site/developerinfo)) | `chargers_near` | demo quota, may throttle |

## Pairs with the skill

The MCP server carries the **execution layer** (typed tools, renderer). The
skill markdown carries the **planning discipline**. Best experience installs
both:

```bash
npx skills add Waybox-AI/roadtrip-skill   # workflow knowledge → your agent
<host> mcp add roadtrip ...               # tools → your agent (see above)
```

Hosts without skill support still get the discipline on demand via
`get_planning_guide(topic="workflow")`.

## Development

```bash
pip install -e ".[dev]"       # installs the mcp SDK + pytest
python3 -m pytest tests/test_mcp_server.py
```

`mcp_server/server.py` is a thin adapter over [`tools/`](../tools) and
[`assets/generate.py`](../assets/generate.py) — planning logic and HTTP calls
live in the clients (each with its own tests and CLI), never here. When you
add a client, wrap it here, mirror its schema in a test, and mention it in
`_TOOLS_GUIDE`.
