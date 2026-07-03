# GEMINI.md — Gemini-specific guidance

Behavioral tweaks for Gemini agents working in this repo. The authoritative rules live
in [AGENTS.md](AGENTS.md) (technical) and [CONTEXT.md](CONTEXT.md) (domain) — read those
first. This file only adds Gemini-specific prompting preferences.

## Read these first, every time
1. [CONTEXT.md](CONTEXT.md) — what this skill is and the domain vocabulary.
2. [AGENTS.md](AGENTS.md) — the hard constraints (stdlib-only, zero keys, commands).
3. `SKILL.md` + `reference.md` — the load-bearing agent instructions and schema.

## Ground rules that Gemini most often gets wrong here
- **Do not add dependencies.** If a task feels like it needs `requests`, `pandas`, or
  `jinja2`, stop — use `urllib`, plain dicts, and the existing `__TRIP_DATA__` token
  injection instead. Runtime code is Python 3.8+ **stdlib only**.
- **Do not emit HTML from planning code.** Produce `tripData.json`; let
  `assets/generate.py` render it. See data/view separation in AGENTS.md.
- **Keep `generate.py` warnings non-fatal.** Do not "fix" `[warn]` lines by raising.
- **Never fabricate live data** (fuel prices, charger occupancy, traffic, campground
  availability). Point to the official app and tag figures with the reliability grade.

## Response format preferences
- When proposing code, show a **minimal diff or the changed function only** — do not
  reprint whole files.
- Prefer fenced code blocks with an explicit language tag (```python, ```bash,
  ```json). Keep bash examples runnable and copy-pasteable.
- Lead with a one-line summary of what changed and why, then the code, then the exact
  command to verify (usually `python3 -m pytest tests/ -v`).
- Do not add sycophantic preambles ("Great question!"). Be terse and technical.
- When touching the schema, state explicitly which of the three places you updated:
  the producing Python, `template.html`'s reader, and `reference.md`.

## Verification expectation
After any code change, run and report:
```bash
python3 -m pytest tests/ -v
```
If you added a client or feature, add a matching test in `tests/` in the same change.
