# downtime-agents

Monorepo consolidating the DownTime event collection and email digest agents.

## Structure

```
downtime-agents/
├── email-agent/          # DownTime Weekend Email Digest Agent
│   ├── Dockerfile        # Slim Python 3.12-slim-bookworm image
│   ├── agent.py          # Entry point: fetch → curate → compose → send
│   ├── curator.py        # Event curation pipeline (imports downtime-backend)
│   ├── email_composer.py # HTML + plain-text email composition
│   ├── sender.py         # Resend API integration
│   └── ...
└── event-agent/          # DownTime Event Collection Agent
    ├── Dockerfile        # Python 3.12 + Playwright + Chromium image
    ├── agent.py          # Entry point: crawl → deduplicate → score → push
    ├── fetchers/         # AllEvents.in, Facebook Events, Eventbrite
    └── ...
```

## Source Repos

This monorepo was created by merging:

- **[downtime-email-agent](https://github.com/lkmotto/downtime-email-agent)** (archived) → `email-agent/`
- **[downtime-event-agent](https://github.com/lkmotto/downtime-event-agent)** (archived) → `event-agent/`

All git history is preserved.

## Docker Setups

Each agent has its own Dockerfile in its subdirectory:

| Agent | Base Image | Key Dependencies |
|-------|-----------|-----------------|
| `email-agent/` | `python:3.12-slim-bookworm` | httpx, pydantic, sentry-sdk, downtime-backend |
| `event-agent/` | `python:3.12-slim-bookworm` + Chromium | Playwright, httpx, pydantic, sentry-sdk |

Build independently:
```bash
docker build -t downtime-email-agent email-agent/
docker build -t downtime-event-agent event-agent/
```

## License

MIT
