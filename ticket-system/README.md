# Ticket system: UI in, shipped pull requests out

Submit a ticket from the UI and a multi-agent software-engineering pipeline delivers it. Every
ticket makes the next one converge faster, because the pipeline writes down what its reviewer kept
complaining about and feeds that back into later prompts.

```
UI ticket ─► Planner agent ─► Implementer agents ─► Reviewer agent ─┬─ pass ─► PR ready
                 │                    ▲                            │
                 │                    └──── revision comments ◄─────┘ changes_requested
                 └──────────────► Retrospective agent ─► learnings ─► injected into next ticket
```

## Agents

| Agent | Job | Never does |
| --- | --- | --- |
| Planner | splits the ticket into 1-4 independently reviewable subtasks with acceptance criteria | write code |
| Implementer (one per subtask) | implements its subtask, runs tests, opens a PR | touch another subtask |
| Reviewer | checks the PR against the acceptance criteria, returns `pass` or `changes_requested` | fix the code itself |
| Retrospective | distils recurring review comments into durable learnings | write code |

Design decisions that make the loop work:

- **Structured output everywhere.** Each agent's final message must match a JSON Schema
  (`app/models.py`), so the orchestrator branches on data, never on prose.
- **Sessions are resumed, not recreated.** Review comments go back into the implementer's existing
  session, so it keeps its context across rounds.
- **The reviewer is a different session than the implementer.** Self-review is weak.
- **Bounded iterations.** After `max_iterations` failed reviews the subtask is escalated to a human,
  who can send feedback from the UI straight back into the implementer session.
- **Self-improvement is persisted, not implicit.** Retrospective learnings are stored and rendered
  into every later planner/implementer prompt, deduplicated with a hit counter, and shown in the UI.

## Executors

The pipeline is executor-agnostic (`app/executors/`):

- `devin` — each agent is a real Devin session via the public API (`POST /v1/sessions` with
  `structured_output_schema`, resumed with `POST /v1/sessions/{id}/message`). Requires `DEVIN_API_KEY`.
- `mock` — deterministic stand-in that runs the whole loop (including one revision round per
  subtask) in seconds, with no API key. This is the default when no key is set.

## Run it

Backend:

```bash
cd ticket-system/backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (proxies `/api` to port 8000):

```bash
cd ticket-system/frontend
npm install
npm run dev
```

Open http://localhost:5173, submit a ticket, and watch the timeline.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DEVIN_API_KEY` | — | enables the `devin` executor |
| `TICKETS_EXECUTOR` | `devin` if a key is set, else `mock` | which executor to use |
| `TICKETS_MAX_ITERATIONS` | `3` | review rounds before escalating to a human |
| `TICKETS_MAX_PARALLEL` | `2` | implementer agents running at once |
| `TICKETS_DB_PATH` | `backend/data/tickets.db` | SQLite location |
| `TICKETS_POLL_INTERVAL` | `10` | seconds between Devin session polls |
| `TICKETS_SESSION_TIMEOUT` | `5400` | seconds before a stuck session fails |
| `TICKETS_MOCK_SPEED` | `1` | mock executor speed multiplier |
| `DEVIN_API_BASE` | `https://api.devin.ai` | API base URL |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/tickets` | create a ticket and dispatch the pipeline |
| `GET` | `/api/tickets` / `/api/tickets/{id}` | ticket state, subtasks, PR URLs, metrics |
| `GET` | `/api/tickets/{id}/events` | full agent timeline |
| `GET` | `/api/tickets/{id}/stream` | same timeline as server-sent events |
| `POST` | `/api/tickets/{id}/subtasks/{sid}/feedback` | send human feedback into an implementer session |
| `GET` | `/api/learnings` | what the pipeline has learned so far |
| `GET` | `/api/health` | executor and configuration |

## Tests

```bash
cd ticket-system/backend
.venv/bin/python -m pytest      # pipeline, review loop, retro feedback, API
.venv/bin/ruff check . && .venv/bin/mypy app
```
