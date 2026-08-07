# Testing

Memora was validated through **manual end-to-end testing** and **automated unit tests**.

## Functional Testing

### Gmail Integration

Verified automatic memory creation from incoming Gmail via Composio webhooks.

---

### Google Chat Integration

Verified memory ingestion from Google Chat conversations.

---

### Chat UI

Verified interactive chat: message send, session history, and grounded responses.

---

### Memory Creation

Verified detection and storage of episodic, semantic, profile, and goal memories.

---

### Memory Update

Verified profile and semantic updates when new information supersedes prior facts.

---

### Retrieval

Verified relevant memories are returned and injected into the AI context.

---

### Semantic / Knowledge Graph

Verified semantic triples are stored and retrieved via Neo4j + Qdrant.

---

### Profile Memory

Verified user identity, preferences, and traits persist across sessions.

---

### End-to-End Pipeline

Verified:

```
Ingest (Gmail / Chat / UI)
        ↓
Memory Detection
        ↓
Classification / Routing
        ↓
Storage (Qdrant / Neo4j / MongoDB)
        ↓
Retriever + Context Builder
        ↓
Grounded AI Response
```

## Automated Unit Tests

Pure-logic tests live under `tests/`. They cover core helpers **without** requiring live MongoDB, Qdrant, Neo4j, or LLM API keys.

| File | Coverage |
|------|----------|
| `tests/test_memory_detector.py` | Content hashing, source-quote validation, semantic field checks |
| `tests/test_forgetting.py` | Soft decay / importance scoring |
| `tests/test_context_builder.py` | Context assembly and system prompt |
| `tests/test_schemas.py` | Memory schemas, config defaults |
| `tests/test_email_ingest.py` | Gmail webhook parse + email → conversation formatting |

### Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```
