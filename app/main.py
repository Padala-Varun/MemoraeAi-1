"""
FastAPI application entrypoint — routes, LangGraph wiring, lifespan.

Two LangGraph paths:
  Write-path (async, after response): detect → route → [pipelines] → mark processed
  Read-path (sync, for response): parallel_retrieve → forgetting → context → LLM

All routes inline (flat structure, no separate api/ directory).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import TypedDict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, get_llm_provider
from app.db_clients import (
    create_mongo_indexes,
    close_mongo_client,
    ensure_qdrant_collections,
    close_qdrant_client,
    verify_neo4j_connectivity,
    setup_neo4j_constraints,
    close_neo4j_driver,
)
from app.schemas import (
    LoginRequest,
    LoginResponse,
    ChatRequest,
    ChatResponse,
    HistoryRequest,
    SessionInfo,
    SessionsRequest,
    MemoryListRequest,
    ForgetRequest,
    DeleteSessionRequest,
    ExtractedMemory,
)
from app.user_service import (
    get_or_create_user,
    store_message,
    get_recent_turns,
    get_full_session_text,
    mark_memory_processed,
    get_session_list,
    delete_session,
)
from app.memory_detector import detect_memories
from app.memory_router import route_memories
from app.context_builder import (
    retrieve_all_context,
    build_context,
    build_system_prompt,
)
from app.forgetting import explicit_forget

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# Forget Intent Detection (keyword-based, no LLM call)
# ══════════════════════════════════════════════

_FORGET_PATTERNS = [
    "remove", "forget", "delete", "erase", "clear",
    "don't remember", "stop remembering", "wipe",
]

_MEMORY_KEYWORDS = [
    "memory", "from memory", "from your memory",
    "remember", "about me", "that i", "that my",
    "i like", "i love", "i hate", "i prefer",
    "my",
]

# Words to strip from the search text
_STRIP_PHRASES = [
    "please", "can you", "could you", "i want you to",
    "remove", "forget", "delete", "erase", "clear", "wipe",
    "from memory", "from your memory", "in your memory",
    "the memory", "the fact", "the note",
    "that", "about", "stop remembering",
    "don't remember", "do not remember",
]


def _detect_forget_intent(message: str) -> str | None:
    """Detect if the user wants to forget something.

    Returns the cleaned search text to pass to explicit_forget(), or None
    if the message is not a forget request.
    """
    lower = message.lower().strip()

    # Must contain at least one forget-action word
    if not any(p in lower for p in _FORGET_PATTERNS):
        return None

    # Must also contain a memory-related keyword to avoid false positives
    # (e.g. "delete this file" should not trigger memory forget)
    if not any(k in lower for k in _MEMORY_KEYWORDS):
        return None

    # Extract the search text by stripping command/boilerplate phrases
    search = lower
    for phrase in _STRIP_PHRASES:
        search = search.replace(phrase, "")

    # Clean up extra whitespace
    search = " ".join(search.split()).strip()

    if len(search) < 2:
        # Fallback: use the original message minus obvious command words
        search = lower
        for cmd in ["please", "can you", "could you", "remove", "forget",
                    "delete", "from memory", "from your memory"]:
            search = search.replace(cmd, "")
        search = " ".join(search.split()).strip()

    return search if len(search) >= 2 else None


# ══════════════════════════════════════════════
# LangGraph State Types
# ══════════════════════════════════════════════

class MemoryExtractionState(TypedDict):
    """State flowing through the write-path memory extraction graph."""
    user_id: str
    session_id: str
    recent_turns: list[dict[str, str]]
    conversation_text: str
    extracted_memories: list[ExtractedMemory]
    store_results: list[dict[str, str]]
    error: str | None


class ResponseState(TypedDict):
    """State flowing through the read-path response generation graph."""
    user_id: str
    session_id: str
    user_message: str
    retrieved_context: dict[str, object]
    context_string: str
    system_prompt: str
    conversation_turns: list[dict[str, str]]
    response: str
    error: str | None


# ══════════════════════════════════════════════
# Write-Path LangGraph (async, after response)
# ══════════════════════════════════════════════

async def _detect_node(state: MemoryExtractionState) -> dict[str, Any]:
    """LangGraph node: Run single-call memory detector."""
    try:
        result = await detect_memories(
            conversation_text=state["conversation_text"],
            recent_turns=state["recent_turns"],
        )
        if result.nothing_to_extract:
            return {"extracted_memories": [], "error": None}
        return {"extracted_memories": result.memories, "error": None}
    except Exception as e:
        logger.error("Detect node failed: %s", e)
        return {"extracted_memories": [], "error": str(e)}


async def _route_and_store_node(state: MemoryExtractionState) -> dict[str, Any]:
    """LangGraph node: Route memories to pipelines and store."""
    if not state["extracted_memories"]:
        return {"store_results": [], "error": None}

    try:
        from app.schemas import DetectorOutput
        detector_output = DetectorOutput(
            nothing_to_extract=False,
            memories=state["extracted_memories"],
        )
        results = await route_memories(
            detector_output=detector_output,
            user_id=state["user_id"],
            session_id=state["session_id"],
        )
        return {"store_results": results, "error": None}
    except Exception as e:
        logger.error("Route/store node failed: %s", e)
        return {"store_results": [], "error": str(e)}


def _build_write_graph() -> Any:
    """Build the write-path LangGraph: detect → route+store."""
    from langgraph.graph import StateGraph, END  # pyrefly: ignore

    graph = StateGraph(MemoryExtractionState)
    graph.add_node("detect_memory", _detect_node)
    graph.add_node("route_and_store", _route_and_store_node)

    graph.set_entry_point("detect_memory")

    def should_continue(state: MemoryExtractionState) -> str:
        if state.get("extracted_memories"):
            return "route_and_store"
        return END

    graph.add_conditional_edges(
        "detect_memory",
        should_continue,
        {"route_and_store": "route_and_store", END: END},
    )
    graph.add_edge("route_and_store", END)

    return graph.compile()


# ══════════════════════════════════════════════
# Read-Path LangGraph (sync, for response)
# ══════════════════════════════════════════════

async def _retrieve_node(state: ResponseState) -> dict[str, Any]:
    """LangGraph node: Retrieve memories from all backends."""
    try:
        context = await retrieve_all_context(
            user_id=state["user_id"],
            query=state["user_message"],
        )
        turns = await get_recent_turns(
            user_id=state["user_id"],
            session_id=state["session_id"],
            limit=6,
        )
        return {
            "retrieved_context": context,
            "conversation_turns": turns,
            "error": None,
        }
    except Exception as e:
        logger.error("Retrieve node failed: %s", e)
        return {"retrieved_context": {}, "conversation_turns": [], "error": str(e)}


async def _build_context_node(state: ResponseState) -> dict[str, Any]:
    """LangGraph node: Build priority-scored context."""
    try:
        ctx = state.get("retrieved_context", {})
        context_str = build_context(
            profile=ctx.get("profile"),  # pyrefly: ignore
            goals=ctx.get("goals", []),  # pyrefly: ignore
            semantic_facts=ctx.get("semantic", []),  # pyrefly: ignore
            episodic_memories=ctx.get("episodic", []),  # pyrefly: ignore
            conversation_turns=state.get("conversation_turns", []),
        )
        system_prompt = build_system_prompt(context_str)
        return {"context_string": context_str, "system_prompt": system_prompt, "error": None}
    except Exception as e:
        logger.error("Build context node failed: %s", e)
        return {"context_string": "", "system_prompt": build_system_prompt(""), "error": str(e)}


async def _call_llm_node(state: ResponseState) -> dict[str, Any]:
    """LangGraph node: Generate response via configurable LLM provider."""
    try:
        llm = get_llm_provider()
        response_text = await llm.generate_text(
            prompt=state["user_message"],
            system_prompt=state["system_prompt"],
            temperature=0.7,
        )
        return {"response": response_text, "error": None}
    except Exception as e:
        logger.error("Call LLM node failed: %s", e)
        return {
            "response": "I'm sorry, I encountered an error generating a response. Please try again.",
            "error": str(e),
        }


def _build_read_graph() -> Any:
    """Build the read-path LangGraph: retrieve → context → LLM."""
    from langgraph.graph import StateGraph, END  # pyrefly: ignore

    graph = StateGraph(ResponseState)
    graph.add_node("retrieve_context", _retrieve_node)
    graph.add_node("build_context", _build_context_node)
    graph.add_node("call_llm", _call_llm_node)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "build_context")
    graph.add_edge("build_context", "call_llm")
    graph.add_edge("call_llm", END)

    return graph.compile()


# Compiled graph singletons
_write_graph: Any = None
_read_graph: Any = None


def get_write_graph() -> Any:
    global _write_graph
    if _write_graph is None:
        _write_graph = _build_write_graph()
    return _write_graph


def get_read_graph() -> Any:
    global _read_graph
    if _read_graph is None:
        _read_graph = _build_read_graph()
    return _read_graph


# ══════════════════════════════════════════════
# High-level pipeline functions
# ══════════════════════════════════════════════

async def run_memory_extraction(user_id: str, session_id: str) -> list[dict[str, str]]:
    """Run the full write-path memory extraction pipeline."""
    assert user_id and user_id.strip(), "user_id MUST be provided."

    recent_turns = await get_recent_turns(user_id, session_id, limit=6)
    conversation_text = await get_full_session_text(user_id, session_id)

    if not recent_turns:
        return []

    compiled = get_write_graph()
    initial_state: MemoryExtractionState = {
        "user_id": user_id,
        "session_id": session_id,
        "recent_turns": recent_turns,
        "conversation_text": conversation_text,
        "extracted_memories": [],
        "store_results": [],
        "error": None,
    }

    result = await compiled.ainvoke(initial_state)
    store_results = result.get("store_results", [])

    # Mark messages as processed
    await mark_memory_processed(user_id, session_id)

    logger.info(
        "Memory extraction complete: user=%s, session=%s, %d memories.",
        user_id, session_id, len(store_results),
    )
    return store_results


async def generate_response(user_id: str, session_id: str, user_message: str) -> str:
    """Run the full read-path response generation pipeline."""
    assert user_id and user_id.strip(), "user_id MUST be provided."

    compiled = get_read_graph()
    initial_state: ResponseState = {
        "user_id": user_id,
        "session_id": session_id,
        "user_message": user_message,
        "retrieved_context": {},
        "context_string": "",
        "system_prompt": "",
        "conversation_turns": [],
        "response": "",
        "error": None,
    }

    result = await compiled.ainvoke(initial_state)
    return result.get("response", "I'm sorry, I couldn't generate a response.")


# ══════════════════════════════════════════════
# FastAPI Application
# ══════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # pyrefly: ignore
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()
    logger.info("MemoraeAI starting up (env=%s)...", settings.APP_ENV)

    # MongoDB indexes
    try:
        await create_mongo_indexes()
        logger.info("✓ MongoDB connected and indexes ready.")
    except Exception as e:
        logger.error("✗ MongoDB startup failed: %s", e)

    # Qdrant collections
    try:
        ensure_qdrant_collections()
        logger.info("✓ Qdrant connected and collections ready.")
    except Exception as e:
        logger.error("✗ Qdrant startup failed: %s", e)

    # Neo4j connectivity and constraints
    try:
        connected = await verify_neo4j_connectivity()
        if connected:
            await setup_neo4j_constraints()
            logger.info("✓ Neo4j connected and constraints ready.")
        else:
            logger.warning("✗ Neo4j connectivity check failed — will retry on first use.")
    except Exception as e:
        logger.error("✗ Neo4j startup failed: %s", e)

    logger.info("MemoraeAI startup complete. Serving requests.")

    yield

    # Shutdown
    logger.info("MemoraeAI shutting down...")
    await close_mongo_client()
    close_qdrant_client()
    await close_neo4j_driver()
    logger.info("All connections closed. Goodbye.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="MemoraeAI",
        description="Multi-Agent Memory System with Episodic, Semantic, Profile & Goals layers",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health Check ──
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "memorae-ai"}

    # ── User Routes ──
    @app.post("/api/user/login", response_model=LoginResponse)
    async def login(request: LoginRequest) -> LoginResponse:
        """Look up or create a user by username."""
        try:
            user_id = await get_or_create_user(request.username)
            return LoginResponse(
                user_id=user_id,
                username=request.username.strip().lower(),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Chat Routes ──
    @app.post("/api/chat/send", response_model=ChatResponse)
    async def send_message(request: ChatRequest) -> ChatResponse:
        """Send a message and receive an AI response with memory context."""
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required.")

        session_id = request.session_id or str(uuid.uuid4())

        # Step 1: Store user message IMMEDIATELY
        await store_message(
            user_id=request.user_id,
            session_id=session_id,
            role="user",
            content=request.message,
        )

        # Step 1.5: Detect forget intent BEFORE generating response
        forget_search = _detect_forget_intent(request.message)
        forget_result = None
        if forget_search:
            logger.info(
                "Forget intent detected for user %s: search='%s'",
                request.user_id, forget_search[:60],
            )
            forget_result = await explicit_forget(
                user_id=request.user_id,
                search_text=forget_search,
            )
            logger.info("Forget result: %s", forget_result)

        # Step 2: Generate response via read-path LangGraph
        response_text = await generate_response(
            user_id=request.user_id,
            session_id=session_id,
            user_message=request.message,
        )

        # Step 3: Store assistant response
        await store_message(
            user_id=request.user_id,
            session_id=session_id,
            role="assistant",
            content=response_text,
        )

        # Step 4: Trigger async memory extraction ONLY if this was NOT a forget request
        # (to prevent re-extracting the very memories the user just asked to delete)
        if not forget_result:
            asyncio.create_task(
                _background_memory_extraction(request.user_id, session_id)
            )
        else:
            logger.info(
                "Skipping memory extraction for forget request (user=%s, session=%s)",
                request.user_id, session_id,
            )

        return ChatResponse(
            session_id=session_id,
            response=response_text,
            memories_extracted=not bool(forget_result),
        )

    @app.post("/api/chat/history")
    async def get_history(request: HistoryRequest) -> list[dict[str, str]]:
        """Get recent conversation history for a session."""
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required.")
        return await get_recent_turns(
            user_id=request.user_id,
            session_id=request.session_id,
            limit=request.limit,
        )

    @app.post("/api/chat/sessions", response_model=list[SessionInfo])
    async def list_sessions(request: SessionsRequest) -> list[SessionInfo]:
        """List all chat sessions for a user."""
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required.")

        sessions = await get_session_list(request.user_id)
        return [
            SessionInfo(
                session_id=str(s["session_id"]),
                title=str(s["title"]),
                created_at=str(s["created_at"]),
                last_active=str(s["last_active"]),
                message_count=int(s["message_count"]),  # pyrefly: ignore
            )
            for s in sessions
        ]

    @app.post("/api/chat/delete")
    async def delete_chat_session(request: DeleteSessionRequest) -> dict[str, object]:
        """Delete a chat session and all its messages."""
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required.")
        if not request.session_id.strip():
            raise HTTPException(status_code=400, detail="session_id is required.")

        deleted_count = await delete_session(
            user_id=request.user_id,
            session_id=request.session_id,
        )
        return {
            "status": "deleted",
            "session_id": request.session_id,
            "messages_deleted": deleted_count,
        }


    # ── Memory Routes ──
    @app.post("/api/memories/list")
    async def list_memories(request: MemoryListRequest) -> dict[str, object]:
        """List all stored memories for a user across all backends."""
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required.")

        context = await retrieve_all_context(
            user_id=request.user_id,
            query="",
        )

        # Fetch ALL goals (active + completed) for the memories page,
        # not just active ones like the chat context uses.
        from app.db_clients import goals_collection
        goals_col = goals_collection()
        all_goals_cursor = goals_col.find(
            {"user_id": request.user_id},
            {"_id": 0},
        ).sort("priority", -1).limit(50)
        all_goals = await all_goals_cursor.to_list(length=50)

        return {
            "user_id": request.user_id,
            "episodic": context.get("episodic", []),
            "semantic": context.get("semantic", []),
            "profile": context.get("profile"),
            "goals": all_goals,
        }

    @app.post("/api/memories/forget")
    async def forget_memory(request: ForgetRequest) -> dict[str, object]:
        """Explicitly forget memories matching the search text."""
        if not request.user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required.")

        results = await explicit_forget(
            user_id=request.user_id,
            search_text=request.search_text,
        )
        total = sum(results.values())
        return {
            "status": "completed",
            "deleted": results,
            "total_deleted": total,
            "message": f"Removed {total} memory(ies) matching '{request.search_text}'.",
        }

    # ── Composio / Gmail Integration Routes ──
    @app.post("/api/webhooks/composio")
    async def composio_webhook(request: Request) -> dict[str, object]:
        """Receive trigger events from Composio (e.g., GMAIL_NEW_GMAIL_MESSAGE).

        Composio POSTs here when a new email arrives. We parse the email,
        look up the MemoraeAI user from the connected_account_id, and
        run the email through the memory extraction pipeline.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.")

        logger.info("Composio webhook received: %s", str(body)[:500])
        data_block = body.get("data", {})
        logger.info("Data block keys: %s", list(data_block.keys()) if isinstance(data_block, dict) else type(data_block))
        logger.info("Data block (1000 chars): %s", str(data_block)[:1000])

        # V3 webhook format: {type, metadata: {trigger_slug, ...}, data: {payload: ...}}
        metadata = body.get("metadata", {})
        trigger_name = (
            metadata.get("trigger_slug", "")
            or body.get("trigger_name", body.get("triggerName", ""))
        )
        connected_account_id = (
            metadata.get("connected_account_id", "")
            or body.get("connected_account_id", body.get("connectedAccountId", ""))
        )

        logger.info(
            "Trigger: %s, connected_account_id: %s",
            trigger_name, connected_account_id,
        )

        # Only process Gmail triggers
        if trigger_name and "gmail" not in trigger_name.lower():
            logger.info("Ignoring non-Gmail trigger: %s", trigger_name)
            return {"status": "ignored", "reason": "not a Gmail trigger"}

        # Look up which MemoraeAI user this connected account belongs to
        from app.db_clients import get_database
        db = get_database()
        mapping = await db["composio_connections"].find_one(
            {"connected_account_id": connected_account_id}
        )

        if not mapping:
            # If no mapping found, try to use a default user or log a warning
            logger.warning(
                "No user mapping for connected_account_id=%s. "
                "Checking for default user...",
                connected_account_id,
            )
            # Fall back to finding any user with a Gmail connection
            mapping = await db["composio_connections"].find_one(
                {"provider": "gmail"}
            )

        if not mapping:
            logger.error("No user found for Composio connected_account_id=%s", connected_account_id)
            return {"status": "error", "reason": "no user mapping found"}

        user_id = mapping["user_id"]

        # Parse the email from the trigger payload
        from app.composio_integration import parse_email_from_trigger
        email_data = parse_email_from_trigger(body)

        logger.info("Parsed email: subject='%s', body_len=%d, sender='%s'",
                    email_data.get('subject', '')[:80],
                    len(email_data.get('body', '')),
                    email_data.get('sender', ''))

        if not email_data.get("subject") and not email_data.get("body"):
            logger.warning("Empty email payload received, skipping.")
            return {"status": "skipped", "reason": "empty email content"}

        # Process in background (non-blocking)
        asyncio.create_task(
            _background_email_processing(user_id, email_data)
        )

        return {
            "status": "accepted",
            "user_id": user_id,
            "subject": email_data.get("subject", "")[:100],
        }

    @app.post("/api/integrations/gmail/connect")
    async def connect_gmail(request: Request) -> dict[str, object]:
        """Initiate Gmail OAuth connection for a user via Composio.

        The user calls this endpoint, and we return the Composio OAuth URL
        they need to visit to authorize their Gmail account.
        """
        body = await request.json()
        user_id = body.get("user_id", "").strip()
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required.")

        try:
            from app.composio_integration import get_composio_client
            composio = get_composio_client()

            # Use the v3 `link` method for Composio-managed OAuth
            connection_request = composio.connected_accounts.link(
                user_id=user_id,
                auth_config_id="ac_dfjaCGyc7M_f",  # Gmail auth config
                callback_url="https://memorae-ai-1.vercel.app/chat.html",
            )

            connected_account_id = getattr(connection_request, "id", "")
            redirect_url = getattr(connection_request, "redirect_url", "")

            # Store the mapping in MongoDB
            from app.db_clients import get_database
            db = get_database()
            await db["composio_connections"].update_one(
                {"user_id": user_id, "provider": "gmail"},
                {
                    "$set": {
                        "user_id": user_id,
                        "provider": "gmail",
                        "connected_account_id": connected_account_id,
                        "status": "pending",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )

            return {
                "status": "pending",
                "redirect_url": redirect_url,
                "connected_account_id": connected_account_id,
                "message": "Visit the redirect_url to authorize Gmail access.",
            }
        except Exception as e:
            logger.error("Gmail connect failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to initiate Gmail connection: {e}")

    @app.post("/api/integrations/gmail/status")
    async def gmail_status(request: Request) -> dict[str, object]:
        """Check if a user has connected their Gmail account."""
        body = await request.json()
        user_id = body.get("user_id", "").strip()
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required.")

        from app.db_clients import get_database
        db = get_database()
        connection = await db["composio_connections"].find_one(
            {"user_id": user_id, "provider": "gmail"}
        )

        if connection:
            return {
                "connected": True,
                "provider": "gmail",
                "status": connection.get("status", "unknown"),
                "connected_account_id": connection.get("connected_account_id", ""),
            }
        return {"connected": False, "provider": "gmail"}

    # Mount static files for web frontend
    import os
    web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
    if os.path.isdir(web_dir):
        app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")

    return app


async def _background_memory_extraction(user_id: str, session_id: str) -> None:
    """Run memory extraction in the background (non-blocking)."""
    try:
        results = await run_memory_extraction(user_id, session_id)
        if results:
            logger.info(
                "Background extraction complete: %d memories for user=%s session=%s",
                len(results), user_id, session_id,
            )
    except Exception as e:
        logger.error("Background memory extraction failed: %s", e)


async def _background_email_processing(user_id: str, email_data: dict[str, str]) -> None:
    """Process an email through the memory pipeline in the background."""
    try:
        from app.composio_integration import process_email_memory
        results = await process_email_memory(user_id, email_data)
        if results:
            logger.info(
                "Email memory extraction complete: %d memories for user=%s, subject='%s'",
                len(results), user_id, email_data.get("subject", "")[:50],
            )
    except Exception as e:
        logger.error("Background email memory processing failed: %s", e)


# Application instance for uvicorn
app = create_app()
