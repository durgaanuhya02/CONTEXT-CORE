# ContextCore™ — Hackathon Implementation

Institutional Memory Intelligence Platform built on top of Microsoft GraphRAG.

## Project Structure

```
contextcore/
  backend/          FastAPI — query, risk, graph, audit endpoints
  frontend/         Next.js — chat, risk dashboard, D3 graph, audit log
  scripts/          DB schema, metadata linker, setup guide
  docker-compose.yml
```

## Quick Start

### Option A — Full pipeline (recommended)
```bash
# 1. Start PostgreSQL
docker-compose up postgres -d

# 2. Set API key (Claude preferred, OpenAI also works)
cp backend/.env.example backend/.env
# Edit backend/.env: set ANTHROPIC_API_KEY or OPENAI_API_KEY

# 3. Run the full data pipeline (NER → graph → embeddings)
cd scripts
pip install -r ../backend/requirements.txt
python run_pipeline.py

# 4. Start backend
cd ../backend
uvicorn main:app --reload --port 8000

# 5. Start frontend
cd ../frontend
npm install && npm run dev
```

### Option B — Docker Compose
```bash
# Set your API key first
export ANTHROPIC_API_KEY=your_key_here   # or OPENAI_API_KEY

docker-compose up --build
# UI at http://localhost:3000
# API at http://localhost:8000/docs
```

> The system works without any API key — it uses template answers and pseudo-embeddings for demo mode.

## Demo Queries

| Query | Expected Result |
|---|---|
| "Why did we choose pgBouncer over RDS Proxy?" | Reconstructs from ADR-004 + Slack + PR #142 + postmortem |
| "Why is the circuit breaker threshold 50%?" | Traces back to April 2023 load test empirical validation |
| "Who owns the most critical knowledge?" | Alice Chen — 70% billing-service knowledge |
| "What should a new engineer know about billing-service?" | Surfaces GOTCHAS.md content |
| "Is the Istio decision still valid?" | Flags HIGH RISK — sole owner, contractor leaving |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | /query | Ask a question, get answer + source chain |
| GET | /risk/health | Overall knowledge health score |
| GET | /risk/owners | Per-person risk scores |
| GET | /risk/domains | Per-domain risk scores |
| GET | /risk/transfer/{owner_id} | Knowledge transfer checklist |
| GET | /risk/departure/{owner_id} | Departure risk simulation — what knowledge is lost if this person leaves |
| GET | /graph | Nodes + edges for D3 visualization |
| GET | /audit-log | Full query history with provenance |
| POST | /compliance/tag/auto | Auto-tag all nodes with regulatory frameworks |
| GET | /compliance/tags | All regulatory tags (filter by framework) |
| GET | /compliance/tags/summary | Node count per framework |
| GET | /compliance/gaps | Coverage gap analysis — underdocumented topics |
| GET | /compliance/audit-chain | Full audit chain with hash verification |
| GET | /compliance/audit-chain/status | Quick chain integrity check |
