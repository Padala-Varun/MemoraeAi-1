Description = 
              We're not building another chatbot , we're    
              building the memory layer for enterprise AI.

              Every organization has a memory problem.

              Critical knowledge is scattered across Gmail, Google Chat, meetings, and employee conversations. When people leave or projects evolve, valuable context is lost, forcing teams to repeat the same discussions and decisions.

              Meet Memora, an Enterprise Memory Agent that transforms everyday communication into a persistent organizational memory. Using AI, Memora automatically detects important information, classifies it into long-term memory, connects related knowledge through a knowledge graph, and retrieves the right context whenever it's needed.

Demo Link   = https://www.youtube.com/watch?v=bbaifPpQyIw&t=4s

Github Repo = https://github.com/Padala-Varun/MemoraeAi-1


<div align="center">

# 🧠 Memora

### Enterprise Memory Agent

**Organizations Forget. Memora Doesn't.**

Transform emails, conversations, and organizational knowledge into persistent AI memory.

---

![Next.js](https://img.shields.io/badge/Next.js-16-black?style=for-the-badge&logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?style=for-the-badge&logo=fastapi)
![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?style=for-the-badge&logo=mongodb)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC244C?style=for-the-badge)
![Neo4j](https://img.shields.io/badge/Neo4j-Knowledge_Graph-4581C3?style=for-the-badge&logo=neo4j)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent_Framework-black?style=for-the-badge)

</div>

---

# 🚀 Overview

Memora is an **Enterprise Memory Agent** that continuously captures, understands, and remembers organizational knowledge from emails, conversations, and user interactions.

Unlike traditional chatbots or Retrieval-Augmented Generation (RAG) systems that only search documents, Memora builds **persistent organizational memory**.

Every important conversation becomes institutional knowledge.

---

# 💡 The Problem

Organizations lose valuable knowledge every day.

Knowledge is scattered across:

- 📧 Gmail
- 💬 Google Chat
- 👥 Employee conversations
- 📄 Documents
- 🗂 Project discussions

When employees leave...

Knowledge leaves with them.

Traditional AI assistants only remember the current conversation.

Memora remembers your organization.

---

# ✨ Features

- 🧠 Long-Term Memory
- 📧 Gmail Integration
- 💬 Google Chat Integration
- 🤖 AI Memory Detection
- ⭐ Importance Scoring
- 📂 Multi-Type Memory Storage
- 🔍 Semantic Retrieval
- 🕸 Knowledge Graph
- 👤 User Profile Memory
- 🎯 Goal Memory
- ⚡ Context-Aware AI Responses
- 🔄 Continuous Learning

---

# 🏗 Architecture

```
                Gmail
                  │
                  │
          Google Chat
                  │
                  │
        User Conversations
                  │
                  ▼
            Composio Events
                  │
                  ▼
        Memory Detection Agent
                  │
                  ▼
         Importance Scoring
                  │
                  ▼
         Memory Classification
      ┌─────────┼──────────┐
      ▼         ▼          ▼
 Profile    Semantic    Episodic
 MongoDB     Qdrant      Qdrant
      │         │          │
      └─────────┴──────────┘
                  │
             Neo4j Graph
                  │
                  ▼
         Retrieval Engine
                  │
                  ▼
          Context Builder
                  │
                  ▼
             LLM Response
                  │
                  ▼
          Memory Update Loop
```

---

# 🧠 Memory Types

## 👤 Profile Memory

Stores

- User preferences
- Employee role
- Skills
- Team
- Personal information

Database

MongoDB

---

## 📚 Semantic Memory

Stores

- Company knowledge
- SOPs
- Technical discussions
- Architecture decisions

Database

Qdrant

---

## 🕒 Episodic Memory

Stores

- Conversations
- Gmail threads
- Project history
- Meetings

Database

Qdrant

---

## 🎯 Goal Memory

Stores

- Tasks
- Objectives
- Follow-ups
- Deadlines

Database

MongoDB

---

# 🔄 Memory Pipeline

```
Incoming Event

↓

Memory Detection

↓

Importance Scoring

↓

Memory Classification

↓

Embedding Generation

↓

Memory Storage

↓

Knowledge Graph Update

↓

Retriever

↓

Context Builder

↓

Grounded AI Response
```

---

# 🏛 Tech Stack

| Layer | Technology |
|--------|------------|
| Frontend | Next.js |
| Backend | FastAPI |
| Agent Framework | LangGraph |
| LLM | Mistral |
| Embeddings | Mistral Embeddings |
| Vector Database | Qdrant |
| Graph Database | Neo4j |
| Database | MongoDB |
| Integrations | Composio |
| Sources | Gmail, Google Chat |

---

# 🔌 Integrations

✅ Gmail

✅ Google Chat

🚧 Google Drive

🚧 Slack

🚧 Notion

🚧 Jira

🚧 GitHub

---

# 🚀 Why Memora?

Traditional RAG

❌ Searches documents

❌ Forgets after every session

❌ No organizational memory

❌ No user understanding

❌ No relationship modeling

---

Memora

✅ Continuously learns

✅ Remembers conversations

✅ Understands organizational context

✅ Builds knowledge graphs

✅ Retrieves personalized memories

✅ Improves over time

---

# 🎯 Example

Employee asks

> Why did we migrate our backend to Kubernetes?

Memora retrieves

- Gmail discussion
- Google Chat conversation
- Meeting summary
- Architecture decision
- Previous implementation notes

The AI answers using historical organizational knowledge instead of only the current conversation.

---

# 🌎 Use Cases

- Enterprise Knowledge Retention
- Employee Onboarding
- AI Copilot Memory
- Project Knowledge Management
- Decision Tracking
- Customer Success Memory
- Internal Support Assistant

---

# 📈 Future Roadmap

### Phase 1

- Gmail
- Google Chat
- Persistent Memory

### Phase 2

- Slack
- Google Drive
- Notion

### Phase 3

- Jira
- GitHub
- Confluence

### Phase 4

- Enterprise Memory Cloud
- Knowledge Analytics
- Multi-Agent Memory

---

# 📷 Screenshots

Add screenshots here

```
/docs/images/dashboard.png

/docs/images/chat.png

/docs/images/memory.png
```

---

# 🛠 Installation

```bash
git clone https://github.com/yourusername/memora.git

cd memora

pip install -r requirements.txt

npm install
```

Run backend

```bash
uvicorn app.main:app --reload
```

Run frontend

```bash
npm run dev
```

---

# 🏆 Built For

**AI House National Finale 2026**

Challenge Track

**Knowledge Retention**

---

# 📜 License

MIT License

---

<div align="center">

## ⭐ Organizations Forget. Memora Doesn't.

### Building the Memory Layer for Enterprise AI.

</div>