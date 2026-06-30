# AGENTS.md for downtime-agents

## Overview
Monorepo consolidating the DownTime event collection and email digest agents. Contains two agents: email-agent (weekend email digest) and event-agent (event collection/crawling).

## Development

### Setup
```bash
uv sync
```

### Run
```bash
uv run python email-agent/agent.py
uv run python event-agent/agent.py
```

### Test
```bash
uv run pytest
```

### Lint
```bash
uv run ruff check .
```

### Type Check
```bash
uv run mypy .
```

## Deployment
Each agent is deployed as its own Docker container via Maritime.sh. Build independently with `docker build -t downtime-email-agent email-agent/` and `docker build -t downtime-event-agent event-agent/`.
