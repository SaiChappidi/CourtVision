# CourtVision: Autonomous NBA GM Agent

AI-driven predictive analytics platform that evaluates NBA rosters and models team win distributions using an LLM-guided agent loop.

**Stack:** Python · FastAPI · LangChain · Redis · Docker

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GM Agent   │────▶│  FastAPI Gateway │────▶│  NBA Stats API  │
│ (LangChain) │     │  + Redis Cache   │     │  (stats.nba.com)│
└──────┬──────┘     └──────────────────┘     └─────────────────┘
       │
       ▼
┌──────────────────┐
│ Monte Carlo Sim  │
│ (1000 iterations)│
└──────────────────┘
```

## Features

- **FastAPI Gateway** — Proxy routing to official NBA endpoints with dynamic header rotation and Redis caching to mitigate API throttling
- **LangChain Tool-Calling** — Maps unstructured user inputs into structured JSON payloads, automatically updating team minute allocations and roster charts
- **Monte Carlo Simulator** — 1,000 asynchronous seasonal iterations projecting team standings, win-loss percentages, and playoff viability
- **Roster Management** — Dynamic minute allocation with team rating computation

## Quick Start

### Prerequisites

- Python 3.12+
- Redis (or use Docker Compose)
- Gemini API key (optional — fallback mode available)

### Local Development

```bash
# Clone and setup
cd CourtVision-1
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your GEMINI_API_KEY

# Start Redis (if not using Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run the server
uvicorn app.main:app --reload --port 8000
```

### Docker

```bash
docker compose up --build
```

**Web UI** available at [http://localhost:8000](http://localhost:8000)
API docs available at [http://localhost:8000/docs](http://localhost:8000/docs)

## Web Frontend

CourtVision ships with a built-in single-page web app (served by FastAPI, no build step). Open [http://localhost:8000](http://localhost:8000) after starting the server. It has four sections:

- **Simulate Season** — pick a team, run the Monte Carlo engine, and view projected record, playoff odds, team rating, and an interactive win-distribution chart
- **Roster & Minutes** — edit minute allocations inline (live 240-minute total check) and re-simulate with one click
- **GM Agent** — chat with the LLM agent in plain English (falls back to the simulation engine if the LLM is rate-limited)
- **NBA Data** — browse live rosters and search players through the gateway

## API Endpoints

### NBA Gateway (`/api/v1/nba`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/teams` | List all 30 NBA teams |
| GET | `/roster/{team_abbr}` | Full roster with stats |
| GET | `/standings` | League standings |
| GET | `/player-stats` | League-wide player stats |
| GET | `/search/{name}` | Search players by name |

### Roster Management (`/api/v1/roster`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{team_abbr}` | Get roster chart with minute allocations |
| PUT | `/{team_abbr}` | Update minute allocations |
| GET | `/{team_abbr}/rating` | Get computed team rating |

### Simulation (`/api/v1/simulate`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/season` | Run Monte Carlo simulation |
| GET | `/season/{team_abbr}` | Quick simulation (1000 iterations) |

### GM Agent (`/api/v1/agent`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Natural language roster analysis |
| GET | `/status` | Agent availability status |

## Example Usage

### Simulate the Lakers season

```bash
curl http://localhost:8000/api/v1/simulate/season/LAL
```

### Chat with the GM Agent

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze the Lakers roster and project their season", "team_context": "LAL"}'
```

### Update minute allocations

```bash
curl -X PUT http://localhost:8000/api/v1/roster/LAL \
  -H "Content-Type: application/json" \
  -d '{
    "team_abbreviation": "LAL",
    "minute_allocations": [
      {"player_id": 2544, "player_name": "LeBron James", "minutes": 34.0},
      {"player_id": 203076, "player_name": "Anthony Davis", "minutes": 34.0}
    ]
  }'
```

## Project Structure

```
app/
├── main.py              # FastAPI entry point
├── config.py            # Settings (pydantic-settings)
├── api/routes/          # API route handlers
├── agent/               # LangChain GM agent + tools
├── gateway/             # NBA proxy, cache, header rotation
├── models/              # Pydantic data models
├── services/            # Roster state management
└── simulator/           # Monte Carlo engine
```

## License

MIT
