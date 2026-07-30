# MemoraeAI — Multi-Agent Memory System

A production-quality AI memory layer with episodic, semantic, profile, and goal memory types. Built with Python, FastAPI, LangGraph, Qdrant, Neo4j, and MongoDB.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI + LangGraph                      │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ Read Path   │    │  Write Path  │    │  Forgetting   │  │
│  │ retrieve →  │    │  detect →    │    │  soft decay + │  │
│  │ context →   │    │  route →     │    │  hard delete  │  │
│  │ LLM        │    │  pipelines   │    │  + user forget│  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
│         │                  │                    │           │
│  ┌──────┴──────────────────┴────────────────────┴────────┐ │
│  │              Memory Detector (single LLM call)        │ │
│  │         extract + score + self-verify in one pass     │ │
│  └───────────────────────────────────────────────────────┘ │
│         │                  │                    │           │
│  ┌──────┴───────┐  ┌──────┴───────┐    ┌───────┴────────┐ │
│  │   Qdrant     │  │    Neo4j     │    │    MongoDB     │ │
│  │  episodic +  │  │  semantic    │    │  users, conv,  │ │
│  │  semantic    │  │  triples     │    │  profile, goal │ │
│  │  (vectors)   │  │  (graph)     │    │  (documents)   │ │
│  └──────────────┘  └──────────────┘    └────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your API keys and database URIs
```

### 3. Start the Backend
```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 4. Open the Frontend
```bash
# Option A: Separate static server
cd web && python -m http.server 3000
# Open http://localhost:3000

# Option B: Served by FastAPI
# Open http://localhost:8000/web/index.html
```

## Project Structure

```
├── app/
│   ├── config.py                 # Settings + LLM/Embedding provider protocols
│   ├── schemas.py                # ALL Pydantic models
│   ├── db_clients.py             # MongoDB + Qdrant + Neo4j clients
│   ├── user_service.py           # User ID + conversation storage
│   ├── memory_detector.py        # Single-call extraction + scoring
│   ├── memory_router.py          # Routes by memory type
│   ├── episodic_pipeline.py      # Qdrant dedup + store
│   ├── semantic_pipeline.py      # Neo4j + Qdrant hybrid
│   ├── profile_goal_pipeline.py  # MongoDB upsert
│   ├── forgetting.py             # Decay + hard forget + explicit
│   ├── context_builder.py        # Parallel retrieval + priority scoring
│   └── main.py                   # FastAPI + LangGraph + routes
├── web/                          # HTML/CSS/JS frontend
├── scripts/cleanup_job.py        # Background hard-forgetting job
├── tests/test_scenarios.py       # Unit tests (16 tests, no DB needed)
└── e2e_test.py                   # Full integration test
```

## Memory Types

| Type | Storage | Description |
|------|---------|-------------|
| **Episodic** | Qdrant | Specific events and experiences |
| **Semantic** | Neo4j + Qdrant | Knowledge triples (subject → predicate → object) |
| **Profile** | MongoDB | User identity, preferences, traits |
| **Goals** | MongoDB | User objectives with status tracking |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/user/login` | Login/register by username |
| `POST` | `/api/chat/send` | Send message, get response |
| `POST` | `/api/chat/history` | Get conversation history |
| `POST` | `/api/chat/sessions` | List all sessions |
| `POST` | `/api/memories/list` | List all stored memories |
| `POST` | `/api/memories/forget` | Explicitly forget memories |

## Running Tests

```bash
# Unit tests (no DB required)
python tests/test_scenarios.py
# or
python -m pytest tests/test_scenarios.py -v

# E2E test (requires running server + databases)
python e2e_test.py

# Background cleanup (dry run)
python scripts/cleanup_job.py --dry-run
```

## Tech Stack

- **Python** + **FastAPI** — async API server
- **LangGraph** — orchestration (write-path + read-path graphs)
- **Qdrant** — vector search for episodic + semantic memories
- **Neo4j** — knowledge graph for semantic triples
- **MongoDB** — document store for users, conversations, profiles, goals
- **Mistral AI** — LLM (configurable via `.env`)
