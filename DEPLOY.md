# Deploy

## Stack

- `backend`: FastAPI in Docker
- `frontend`: static Vite build served by nginx
- persistence: host `./data` mounted into backend container

## Required env

Create `.env` on the server:

```env
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-sonnet-4-6
MAX_PDF_SIZE_MB=32
DATA_DIR=/app/data/projects
CORS_ORIGINS=
```

`CORS_ORIGINS` can stay empty when frontend and API are served from the same host through nginx.

## First deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## Update

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Check status

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs backend --tail=100
docker compose -f docker-compose.prod.yml logs frontend --tail=100
```
