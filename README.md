# MemoraeAI

### Persistent Memory Infrastructure for AI

MemoraeAI is a persistent memory system that enables AI assistants to remember users, understand past interactions, retain important knowledge, and retrieve the right context when it matters.

Instead of treating every conversation as an isolated session, MemoraeAI continuously extracts meaningful information, classifies it into different memory types, stores it in purpose-built databases, and brings relevant memories back into future interactions.

---

## What MemoraeAI Does

An AI assistant becomes significantly more useful when it can remember:

* Who the user is
* What they prefer
* What they are working toward
* Important facts they have shared
* What happened in previous conversations
* Knowledge contained in their emails
* How previously stored information relates to new information

MemoraeAI provides the infrastructure required to make that possible.

The system follows a continuous memory lifecycle:

```text
Interaction
     │
     ▼
Memory Detection
     │
     ▼
Importance Scoring
     │
     ▼
Memory Classification
     │
     ▼
Deduplication / Conflict Resolution
     │
     ▼
Memory Storage
     │
     ▼
Memory Retrieval
     │
     ▼
Context Construction
     │
     ▼
LLM Response
     │
     ▼
Memory Update
```

---

# Core Capabilities

## 🧠 Persistent Memory

MemoraeAI maintains memory across conversations instead of relying only on the current context window.

It can retain:

* User profile information
* Preferences and traits
* Semantic facts
* Past events and interactions
* Goals and objectives
* Email-derived knowledge

---

## 👤 Profile Memory

Profile memory stores relatively stable information about a user.

Examples:

```text
Name
Role
Preferences
Skills
Traits
Personal attributes
```

Profile information is stored in MongoDB and can be updated when new information conflicts with previously stored data.

---

## 📚 Semantic Memory

Semantic memory represents factual knowledge extracted from interactions.

For example:

```text
User → works_at → Company
User → knows → Python
Project → uses → FastAPI
System → migrated_to → Kubernetes
```

Semantic facts are stored in two complementary forms:

```text
Qdrant
   │
   └── Vector representation for semantic retrieval

Neo4j
   │
   └── Structured relationships between entities
```

This allows the system to combine semantic similarity with structured relationships.

---

## ⚡ Episodic Memory

Episodic memory represents events and previous experiences.

Examples:

```text
User discussed a project yesterday
User mentioned a previous decision
User described an important event
A previous conversation contained relevant context
```

Episodic memories are embedded and stored in Qdrant for semantic retrieval.

---

## 🎯 Goal Memory

MemoraeAI can identify and maintain user goals.

Examples:

```text
Learn Python
Prepare for an interview
Complete a project
Build an AI application
Apply for a job
```

Goals are stored in MongoDB with their state and importance information.

The system also supports goal completion and updates.

---

# 📧 Gmail Memory

MemoraeAI can connect to Gmail through Composio.

When a new Gmail message is received:

```text
Gmail
  │
  ▼
Composio Trigger
  │
  ▼
Email Parsing
  │
  ▼
Memory Detection
  │
  ▼
Memory Classification
  │
  ▼
Memory Storage
```

Email content is processed using the same memory pipeline used for conversational interactions.

This allows important information contained in emails to become part of persistent memory.

### Gmail capabilities

* Gmail connection through OAuth
* New Gmail message trigger handling
* Email content extraction
* Memory detection from email content
* Memory classification
* Storage through the existing memory pipelines

---

# 🔍 Memory Detection

MemoraeAI uses an LLM-powered memory detector to determine whether an interaction contains information worth remembering.

The detector identifies memory types such as:

```text
episodic
semantic_fact
profile_update
goal
goal_completed
```

Each extracted memory contains information such as:

```text
Memory type
Content
Source quote
Confidence
Importance score
Semantic subject
Semantic predicate
Semantic object
```

The system also validates extracted information before storing it.

For example, semantic memories require a valid:

```text
Subject → Predicate → Object
```

relationship.

Source quotes are validated against the original conversation to reduce unsupported memory creation.

---

# ⭐ Importance Scoring

Not every piece of information deserves long-term storage.

MemoraeAI assigns an importance score to extracted memories.

```text
1 ─────────────── 10
Low importance    High importance
```

Low-value information can be discarded before entering long-term memory.

This keeps the memory system focused on information that is actually useful later.

---

# ♻️ Deduplication

Repeated information should not create unlimited duplicate memories.

MemoraeAI uses:

* Content hashing
* Semantic similarity
* Similarity thresholds

to identify duplicate memories.

For example:

```text
"I work at Google."

"I am currently working at Google."

"I work for Google."
```

can be recognized as highly similar information rather than blindly creating independent memories.

---

# 🔄 Conflict Resolution

User information can change over time.

For example:

```text
Previous:
User → works_at → Company A

New:
User → works_at → Company B
```

Instead of keeping contradictory information indefinitely, MemoraeAI identifies conflicting semantic facts and updates their state.

This allows memory to evolve with the user.

---

# 🕰 Memory Decay & Forgetting

Memory should not remain equally relevant forever.

MemoraeAI applies time-aware scoring during retrieval:

```text
Final Score =
Similarity × Recency Weight × Importance
```

Recent and important memories receive higher retrieval priority.

The system also supports hard cleanup of stale, low-importance memories.

---

# 🗑️ Explicit Forgetting

Users can explicitly ask the system to forget information.

For example:

```text
Forget that I work at Company A.
```

MemoraeAI searches across the relevant memory stores and removes or invalidates matching memories.

The system also maintains audit records for memory operations.

---

# 🧩 Memory Architecture

```text
                         ┌───────────────┐
                         │   User Chat   │
                         └───────┬───────┘
                                 │
                                 │
                         ┌───────▼───────┐
                         │     Gmail     │
                         │   via Composio│
                         └───────┬───────┘
                                 │
                                 ▼
                      ┌────────────────────┐
                      │  Memory Detection  │
                      │      LangGraph     │
                      └─────────┬──────────┘
                                │
                                ▼
                      ┌────────────────────┐
                      │ Importance Scoring │
                      │ & Validation       │
                      └─────────┬──────────┘
                                │
                                ▼
                      ┌────────────────────┐
                      │   Memory Router    │
                      └─────────┬──────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
       ┌────────────┐    ┌────────────┐    ┌────────────┐
       │  Episodic  │    │  Semantic  │    │  Profile / │
       │   Memory   │    │   Memory   │    │    Goals   │
       └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
             │                 │                 │
             ▼                 ▼                 ▼
          Qdrant          Qdrant + Neo4j      MongoDB
             │                 │                 │
             └─────────────────┼─────────────────┘
                               │
                               ▼
                     ┌────────────────────┐
                     │  Retrieval Engine  │
                     └─────────┬──────────┘
                               │
                               ▼
                     ┌────────────────────┐
                     │  Context Builder   │
                     │ Priority Scoring   │
                     └─────────┬──────────┘
                               │
                               ▼
                     ┌────────────────────┐
                     │   Mistral LLM      │
                     └─────────┬──────────┘
                               │
                               ▼
                         AI Response
```

---

# 🔀 Two Memory Paths

MemoraeAI separates memory processing from response generation.

## Write Path

The write path is responsible for learning from new information.

```text
New Interaction
      │
      ▼
Memory Detector
      │
      ▼
Validation
      │
      ▼
Memory Router
      │
      ├── Episodic Pipeline
      │
      ├── Semantic Pipeline
      │
      ├── Profile Pipeline
      │
      └── Goal Pipeline
```

The write path runs through LangGraph and performs memory extraction asynchronously after the response is generated.

---

## Read Path

The read path is responsible for using memory.

```text
User Query
    │
    ▼
Retrieve Relevant Memory
    │
    ├── Episodic
    ├── Semantic
    ├── Knowledge Graph
    ├── Profile
    └── Goals
    │
    ▼
Merge & Deduplicate
    │
    ▼
Priority Scoring
    │
    ▼
Context Builder
    │
    ▼
Mistral
    │
    ▼
Response
```

This separation allows memory ingestion and response generation to remain independent parts of the system.

---

# 🗄️ Storage Architecture

MemoraeAI uses different storage systems according to the characteristics of each memory type.

| Memory / Data          | Storage | Purpose                                  |
| ---------------------- | ------- | ---------------------------------------- |
| Episodic memories      | Qdrant  | Semantic similarity search               |
| Semantic memories      | Qdrant  | Vector retrieval                         |
| Semantic relationships | Neo4j   | Entity relationships and knowledge graph |
| User profiles          | MongoDB | Structured user information              |
| Goals                  | MongoDB | Goal state and metadata                  |
| Conversations          | MongoDB | Chat history and sessions                |
| Audit logs             | MongoDB | Memory lifecycle tracking                |

---

# 🧠 Retrieval Strategy

When a user sends a message, MemoraeAI retrieves relevant information from multiple memory sources.

```text
                         User Query
                              │
                              ▼
                         Embedding
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          Qdrant          Neo4j           MongoDB
         Episodic        Semantic       Profile/Goals
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                     Context Construction
                              │
                              ▼
                       Priority Scoring
                              │
                              ▼
                         Mistral LLM
```

The context builder considers:

* Relevance
* Importance
* Recency
* Memory type
* User profile
* Goals
* Recent conversation turns

Only the most useful information is placed into the final model context.

---

# 🛡️ Memory Reliability

MemoraeAI includes several safeguards around memory creation:

### Source Validation

Extracted memories retain a source quote and validate that the quote actually exists in the original conversation.

### Confidence Threshold

Low-confidence extractions can be rejected before storage.

### Importance Threshold

Unimportant information can be discarded.

### Deduplication

Repeated information is detected using hashing and semantic similarity.

### Conflict Handling

Contradictory semantic facts can be marked outdated and replaced with newer information.

### Audit Logging

Memory lifecycle operations are recorded for traceability.

---

# 🖥️ Application

The project includes a lightweight web interface for interacting with the memory system.

### Chat

Users can:

* Start conversations
* Continue previous sessions
* View conversation history
* Ask questions using persistent memory

### Memory Dashboard

Users can inspect:

* Episodic memories
* Semantic memories
* Profile information
* Goals

The dashboard also provides an explicit **Forget** operation.

---

# 🏗️ Project Structure

```text
MemoraeAi/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── db_clients.py
│   │
│   ├── memory_detector.py
│   ├── memory_router.py
│   │
│   ├── episodic_pipeline.py
│   ├── semantic_pipeline.py
│   ├── profile_goal_pipeline.py
│   │
│   ├── context_builder.py
│   ├── forgetting.py
│   ├── user_service.py
│   └── composio_integration.py
│
├── web/
│   ├── index.html
│   ├── chat.html
│   ├── memories.html
│   │
│   ├── css/
│   └── js/
│
├── scripts/
│   ├── cleanup_job.py
│   ├── debug_trigger.py
│   ├── setup_composio.py
│   └── ...
│
├── tests/
│   └── test_scenarios.py
│
├── e2e_test.py
├── modal_app.py
├── requirements.txt
├── .env.example
└── README.md
```

---

# ⚙️ Technology Stack

| Component              | Technology            |
| ---------------------- | --------------------- |
| Backend                | FastAPI               |
| Workflow Orchestration | LangGraph             |
| LLM                    | Mistral               |
| Embeddings             | Mistral Embeddings    |
| Vector Database        | Qdrant                |
| Knowledge Graph        | Neo4j                 |
| Document Database      | MongoDB               |
| Gmail Integration      | Composio              |
| Frontend               | HTML, CSS, JavaScript |
| Deployment             | Modal                 |

---

# 🔌 API

The backend exposes endpoints for:

```text
POST /api/user/login
POST /api/chat/send
POST /api/chat/history
POST /api/chat/sessions

POST /api/memories/list
POST /api/memories/forget

POST /api/integrations/gmail/connect
POST /api/integrations/gmail/status
POST /api/integrations/composio/webhook

GET  /health
```

---

# 🧪 Testing

The project includes unit tests covering core memory behavior:

* Content hash generation
* Duplicate detection
* Source quote validation
* Semantic field validation
* Memory schema validation
* Memory decay scoring
* Importance-based ranking
* Context construction
* Configuration validation

An end-to-end test is also included covering:

```text
Health Check
     ↓
Login
     ↓
Send Message
     ↓
Memory Extraction
     ↓
Memory Recall
     ↓
Memory Listing
     ↓
Conflict Resolution
```

Run the test suite with:

```bash
pytest tests/ -v
```

Run the end-to-end test with:

```bash
python e2e_test.py
```

---

# 🚀 Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/Padala-Varun/MemoraeAi-1.git
cd MemoraeAi-1
```

## 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

### Windows

```bash
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure environment variables

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Configure the required credentials for:

```text
Mistral
MongoDB
Qdrant
Neo4j
Composio
```

## 5. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at:

```text
http://localhost:8000
```

## 6. Open the web application

Serve the `web/` directory using a local static server or configure it against the running FastAPI backend.

---

# ☁️ Deployment

The project includes a Modal deployment configuration in:

```text
modal_app.py
```

Development:

```bash
modal serve modal_app.py
```

Deployment:

```bash
modal deploy modal_app.py
```

The deployment configuration packages the backend and web application and loads production credentials through a Modal secret.

---

# 🔐 Environment Configuration

The main configuration categories are:

```text
Mistral API
MongoDB
Qdrant
Neo4j
Composio
CORS
Memory thresholds
Forgetting parameters
```

See:

```text
.env.example
```

for the complete configuration template.

---

# 🧭 Design Principles

MemoraeAI is built around a few core principles:

### Memory should be selective

The system should not remember everything.

### Memory should be structured

Different kinds of knowledge require different storage and retrieval strategies.

### Memory should evolve

New information can update or invalidate old information.

### Memory should be retrievable

Stored information is useful only when the right context can be brought back at the right time.

### Memory should be controllable

Users should be able to inspect and explicitly forget stored information.

### Memory should be traceable

Important memory operations should be auditable.

---

# 📌 Current Scope

The current implementation focuses on:

* Persistent conversational memory
* Episodic memory
* Semantic memory
* Profile memory
* Goal memory
* Gmail ingestion
* Vector retrieval
* Knowledge graph relationships
* Memory deduplication
* Conflict resolution
* Importance scoring
* Memory decay
* Explicit forgetting
* Conversation history
* Memory inspection

The architecture is intentionally modular so additional data sources and memory capabilities can be added without redesigning the core memory pipeline.

---

# 🔗 Project

**Repository:** GitHub — `Padala-Varun/MemoraeAi-1`


---

# ⭐ MemoraeAI

> **AI should not just answer. It should remember.**

MemoraeAI provides the memory layer that allows an AI system to retain knowledge, learn from interactions, and use relevant context across time.
