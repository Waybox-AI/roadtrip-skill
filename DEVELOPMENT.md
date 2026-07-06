# Development Notes

Practical notes for developers working on this repo. For contribution workflow see
[CONTRIBUTING.md](CONTRIBUTING.md); for hard rules see [AGENTS.md](AGENTS.md); for domain
background see [CONTEXT.md](CONTEXT.md).

## This repo has two consumers

The same code is used by two very different callers. Keeping them straight avoids a whole
class of mistakes.

| | **Agent skill** | **External webapp** |
|---|---|---|
| Who runs it | an LLM agent (e.g. Claude Code) | a normal web server |
| Entry point | `SKILL.md` (read as instructions) | imports `scripts/routes.py` |
| Where the "intelligence" comes from | the LLM itself, reasoning through `SKILL.md` | a Claude API call |
| Uses `scripts/routes.py`? | no — uses `scripts/helper.py` | yes — calls `plan_routes()` |
| Needs `ANTHROPIC_API_KEY`? | **no** | **yes** (else falls back to samples) |

Key point: the agent skill is run *by* an LLM, so it never needs to "call" a model — and
therefore never reads `ANTHROPIC_API_KEY`. That key belongs entirely to the webapp path.
This is consistent with the **zero-required-keys** constraint in
[AGENTS.md](AGENTS.md#hard-constraints).

## `scripts/routes.py` — live / offline dual-mode (webapp-only)

`plan_routes()` proposes two candidate routes and runs in one of two modes, selected by
`_live_mode()` (`scripts/routes.py:41`):

- **Live** — `ANTHROPIC_API_KEY` is set **and** the `anthropic` package is importable.
  Makes one fast model call (`ROADTRIP_MODEL`, default `claude-sonnet-4-6`) and returns
  two normalized routes.
- **Offline** — missing key *or* missing package → `demo_routes()` (`scripts/routes.py:253`).
  It picks a curated sample trip by keyword-matching `start + destination`, then derives
  two variants (`Scenic` = every stop, `Highlights` = every other stop) from it.

This is the webapp's **Phase-1** step. It is **not** part of the agent's `SKILL.md`
workflow — do not wire this key or this file into the skill.

Curated samples the offline path selects from (`assets/`):

| Keyword match (in `start + destination`) | Sample file |
|---|---|
| `tahoe`, `sacramento`, `sierra` | `tripData.tahoe.json` |
| `vancouver`, `canada`, `whistler`, `seattle`, `bc` | `tripData.pnw.json` |
| `chicago`, `illinois`, `indiana`, `oak park` | `tripData.chicago.json` ⚠️ **missing — see below** |
| (anything else — default) | `tripData.example.json` |

## Known issues

### Offline `demo_routes()` crashes on Chicago-area input

`demo_routes()` maps `chicago` / `illinois` / `indiana` / `oak park` to
`tripData.chicago.json` (`scripts/routes.py:261-262`), **but that sample file does not
exist** in `assets/` (only `tripData.example.json`, `tripData.pnw.json`, and
`tripData.tahoe.json` are present).

- **Effect:** in offline mode, any Chicago-area `start`/`destination` hits
  `open(... "tripData.chicago.json")` and raises `FileNotFoundError`, which violates the
  project's "offline branch must never crash" contract.
- **Repro:**
  ```python
  from scripts.routes import demo_routes
  demo_routes({"start": "Chicago, IL", "destination": "Indiana Dunes"})
  # -> FileNotFoundError: ... tripData.chicago.json
  ```
- **Fix options (pick one):**
  1. Add a real `assets/tripData.chicago.json` sample (plus its `preview*.html`, per the
     "adding a sample trip" convention).
  2. Remove the `chicago` branch so Chicago-area input falls through to the default
     `tripData.example.json`.
  3. Make the file load defensive — fall back to `tripData.example.json` if the chosen
     sample is missing.

Until this is resolved, the sample table above marks the chicago entry as missing.
