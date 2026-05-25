# unit-bot Agent Guide

This repo is agent-friendly by design and can be used from Codex, Claude Code, OpenClaw, or any similar coding agent.

## Read first

1. `README.md`
2. `SKILL.md`
3. `agents/README.md`
4. `docs/agents_architecture.md`

## Canonical workflow

- Use `agent.py` for interactive orchestration.
- Use `scripts/` for batch or reproducible runs.
- Use the 12 PLANS commands as the public workflow surface:
  `/research`, `/teardown`, `/issues`, `/dfa`, `/dfm`, `/function`, `/trim`, `/fos`, `/patent`, `/trend`, `/platform`, `/costsystem`.
- Keep sub-agents read-only against business data; only the orchestrator writes stage outputs.

## Compatibility notes

- Do not assume a specific LLM backend.
- Prefer repo-native tools and scripts over inventing new flows.
- If a task depends on live web data, use the available web/search/fetch path of the current agent runtime.
- FCC OCR remains a separate manual step via `python scripts/fetch_fcc.py find/ocr "<brand> <model>"`.

## Data boundaries

- `data/lib/` and `data/teardowns/` contain local working data and may be absent in a fresh clone.
- Avoid rewriting unrelated datasets unless the task explicitly requires it.

