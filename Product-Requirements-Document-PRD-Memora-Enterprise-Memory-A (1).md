# Product Requirements Document (PRD): Memora Enterprise Memory Agent

## 1. Executive Summary
Memora is an Enterprise Memory Agent designed to solve the "Knowledge Retention" problem within organizations. By continuously capturing, classifying, and connecting information from daily employee interactions (Gmail, Google Chat, and direct UI interactions), Memora builds a persistent, searchable, and relational organizational "brain." This allows the system to provide grounded, context-aware responses based on historical organizational knowledge rather than just general training data.

## 2. Problem Statement
Organizational knowledge is often fragmented across transient communication channels like email and chat. When employees leave or projects shift, critical context—decisions, preferences, and informal SOPs—is lost. Existing tools lack the ability to automatically detect "worth-remembering" information and link it across different data types (e.g., linking a person to a decision made in an email that resulted in a task).

## 3. Goals & Objectives
*   **Persistent Memory:** Build a self-updating organizational memory from unstructured data.
*   **Contextual Retrieval:** Enable high-precision retrieval using a combination of vector similarity and graph traversal.
*   **Automated Ingestion:** Seamlessly integrate with Google Workspace via Composio.
*   **Grounded Responses:** Ensure the AI assistant answers queries using specific organizational history.
*   **Noise Reduction:** Filter out trivial interactions (e.g., "Hi," "How are you?") from the memory pipeline.

## 4. Target Users / Stakeholders
*   **Employees:** To recall project decisions, personal preferences, or historical context.
*   **Project Managers:** To track goals, deadlines, and meeting outcomes across multiple channels.
*   **Knowledge Officers:** To maintain a structured Knowledge Graph of organizational intelligence.
*   **New Hires:** To quickly ramp up using the "organizational memory."

## 5. Functional Requirements

### 5.1 Data Ingestion
*   **Multi-Source Support:** The system must ingest data from User Chat (React UI), Gmail, and Google Chat.
*   **Real-time Triggers:** Use Composio to trigger the pipeline immediately upon receipt of a new email or chat message.

### 5.2 Memory Processing Pipeline
*   **Memory Detection:** An LLM-based filter must evaluate if content contains "long-term facts" (decisions, tasks, SOPs). Trivial queries must bypass storage and receive a standard LLM response.
*   **Importance Scoring:** Assign a score based on long-term usefulness, frequency, and relevance to prioritize retention.
*   **Memory Classification:** Categorize data into:
    *   **Profile Memory:** Personal/role-based info.
    *   **Semantic Memory:** General company knowledge/SOPs.
    *   **Episodic Memory:** Specific events/conversations/threads.
    *   **Goal Memory:** Tasks, deadlines, and objectives.

### 5.3 Knowledge Graph Construction
*   **Entity Linking:** Automatically create relationships in Neo4j (e.g., Employee → Project → Decision → Task).
*   **Relational Mapping:** Enable traversal of connections that vector search alone cannot identify.

### 5.4 Retrieval & Response
*   **Hybrid Retrieval:** Query MongoDB (Profile/Goal), Qdrant (Semantic/Episodic), and Neo4j (Relationships) simultaneously.
*   **Context Building:** Aggregate retrieved data into a structured prompt for the LLM.
*   **Grounded Generation:** Generate responses using Mistral LLM based strictly on the provided context.

### 5.5 Continuous Learning
*   **Memory Update Loop:** After every user interaction, the system must evaluate if the new conversation generated new knowledge and update the memory stores accordingly.

## 6. Non-Functional Requirements
*   **Performance:** Retrieval and context building should occur within < 2 seconds to maintain chat fluidity.
*   **Scalability:** The system must handle thousands of daily events across an enterprise.
*   **Reliability:** Use a "Triple-Store" strategy (Document, Vector, Graph) to ensure data integrity and specialized access.
*   **Extensibility:** The pipeline should allow for additional data sources (e.g., Slack, Notion) in the future via Composio.

## 7. System Architecture Overview
The system follows a modular architecture divided into four layers:
1.  **Ingestion Layer:** Composio Gateway managing Gmail, Google Chat, and UI inputs.
2.  **Processing Pipeline:** A LangGraph-orchestrated series of LLM services (Detector, Scorer, Classifier).
3.  **Storage Layer (Multi-Modal):** 
    *   **MongoDB:** Document store for profiles and goals.
    *   **Qdrant:** Vector store for embeddings.
    *   **Neo4j:** Graph store for relationships.
4.  **Retrieval & Generation Layer:** LlamaIndex-powered retrieval engine and Mistral-based response generator.

## 8. Tech Stack
*   **Frontend:** React, Tailwind CSS.
*   **Orchestration & Backend:** Python, LangGraph, FastAPI.
*   **AI/LLM Frameworks:** LangChain, LlamaIndex.
*   **LLM & Embeddings:** Mistral, Mistral Embeddings.
*   **Databases:** MongoDB, Qdrant, Neo4j.
*   **Integrations:** Composio (Gmail API, Google Chat API).

## 9. Data Requirements
### 9.1 Memory Schemas
*   **Profile/Goal (MongoDB):** JSON documents containing user IDs, role metadata, task status, and deadlines.
*   **Vectors (Qdrant):** 1024-dimension embeddings (Mistral) representing semantic meaning of SOPs and conversation snippets.
*   **Graph (Neo4j):** Nodes (Employee, Project, Email, Task) and Edges (WORKS_ON, DECIDED_IN, ASSIGNED_TO).

## 10. API Specifications
*   **POST `/ingest/event`:** Webhook for Composio to send Gmail/GChat events.
*   **POST `/chat/query`:** Endpoint for the User UI to send queries.
*   **GET `/memory/status`:** Internal endpoint to track importance scores and classification logs.

## 11. Security Requirements
*   **Authentication:** Secure access to the User Chat UI.
*   **Data Isolation:** Ensure organizational memory is partitioned by enterprise/tenant.
*   **API Security:** Secure communication between Composio and the Memory Orchestrator.

## 12. Deployment & Infrastructure
*   **Containerization:** All services (FastAPI, DBs) should be containerized using Docker.
*   **Orchestration:** Deployment via Kubernetes or similar for scaling the processing pipeline.
*   **CI/CD:** Automated testing for the Memory Detector to prevent "memory bloat" from noise.

## 13. Success Metrics
*   **Retrieval Accuracy:** Percentage of responses rated as "highly relevant" by users.
*   **Knowledge Capture Rate:** Number of "Important" memories captured per user per week.
*   **Reduction in Redundancy:** Decrease in users asking questions that were previously answered in emails/chats.

## 14. Timeline & Milestones
*   **Phase 1 (MVP):** Ingestion via Composio, basic Memory Detection, and MongoDB/Qdrant storage.
*   **Phase 2:** Integration of Neo4j Knowledge Graph and hybrid retrieval logic.
*   **Phase 3:** Implementation of the "Memory Update" loop and Importance Scorer refinement.
*   **Phase 4:** UI/UX optimization and enterprise-wide deployment.

## 15. Open Questions & Risks
*   **Risk:** LLM Hallucination—The system might misinterpret a casual comment as a "decision."
*   **Risk:** Graph Complexity—Maintaining a clean Neo4j schema as data scales.
*   **Open Question:** How should the system handle conflicting information (e.g., an email says a deadline is Friday, but a chat says it's Monday)?
*   **Open Question:** Specific data retention policies for "Episodic" vs "Semantic" memory.