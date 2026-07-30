"""
Context Builder — parallel retrieval + priority-scored assembly.

Retrieval:
  Given user_id + query, runs concurrently (asyncio.gather):
    - Qdrant episodic: top-k similarity search filtered by user_id
    - Qdrant semantic_facts: top-k similarity, filtered by user_id + status:active
    - Neo4j: active relationships for entities in the query
    - MongoDB: profile + active goals

  Applies Forgetting Filter (decay-based re-ranking) to Qdrant/Neo4j results.

Context Assembly:
  Priority-scored, NOT fixed order. Every item gets:
    priority_score = base_type_weight * final_score
  where base_type_weight is tunable (profile=0.9, goal=0.85, semantic=0.7, episodic=0.6).
  A highly relevant episodic memory CAN outrank a generic profile field.

  Always includes: profile core fields + last 4-6 raw conversation turns (baseline context).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import get_settings, get_embedding_provider
from app.db_clients import (
    get_qdrant_client,
    get_neo4j_driver,
    profiles_collection,
    goals_collection,
)
from app.forgetting import compute_final_score

logger = logging.getLogger(__name__)

# Base type weights for priority scoring
BASE_WEIGHTS = {
    "profile": 0.9,
    "goal": 0.85,
    "semantic": 0.7,
    "episodic": 0.6,
}

# Rough token estimation: ~4 chars per token
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Rough token count estimation."""
    return len(text) // CHARS_PER_TOKEN


# ──────────────────────────────────────────────
# Parallel Retrieval
# ──────────────────────────────────────────────

async def _retrieve_episodic(
    user_id: str,
    query_vector: list[float],
    top_k: int,
) -> list[dict[str, object]]:
    """Retrieve episodic memories from Qdrant with decay-based re-ranking."""
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore

    settings = get_settings()
    client = get_qdrant_client()

    try:
        results = client.query_points(
            collection_name=settings.QDRANT_EPISODIC_COLLECTION,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id))
                ]
            ),
            limit=top_k * 2,  # Fetch extra for post-decay filtering
            with_payload=True,
        )
    except Exception as e:
        logger.error("Qdrant episodic retrieval failed: %s", e)
        return []

    scored_results: list[dict[str, object]] = []
    for point in results.points:
        payload = point.payload or {}
        final = compute_final_score(
            similarity_score=point.score,
            importance_score=int(payload.get("importance_score", 5)),  # pyrefly: ignore
            last_accessed_at=payload.get("last_accessed_at"),  # pyrefly: ignore
        )

        if final >= settings.FORGETTING_THRESHOLD:
            scored_results.append({
                "id": str(point.id),
                "content": payload.get("content", ""),
                "importance_score": payload.get("importance_score", 5),
                "similarity_score": point.score,
                "final_score": final,
                "source_quote": payload.get("source_quote", ""),
                "created_at": payload.get("created_at", ""),
                "memory_type": "episodic",
            })

    scored_results.sort(key=lambda x: float(str(x["final_score"])), reverse=True)
    scored_results = scored_results[:top_k]

    # Update last_accessed_at on retrieved points
    if scored_results:
        now_iso = datetime.now(timezone.utc).isoformat()
        for r in scored_results:
            try:
                client.set_payload(
                    collection_name=settings.QDRANT_EPISODIC_COLLECTION,
                    payload={"last_accessed_at": now_iso},
                    points=[r["id"]],  # pyrefly: ignore
                )
            except Exception:
                pass

    return scored_results


async def _browse_episodic(user_id: str, limit: int = 50) -> list[dict[str, object]]:
    """Browse ALL episodic memories for a user via Qdrant scroll (no query vector needed).

    Used by the memories list endpoint where there is no search query.
    """
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore

    settings = get_settings()
    client = get_qdrant_client()

    try:
        records, _next_offset = client.scroll(
            collection_name=settings.QDRANT_EPISODIC_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id))
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.error("Qdrant episodic browse failed: %s", e)
        return []

    results: list[dict[str, object]] = []
    for point in records:
        payload = point.payload or {}
        results.append({
            "id": str(point.id),
            "content": payload.get("content", ""),
            "importance_score": payload.get("importance_score", 5),
            "source_quote": payload.get("source_quote", ""),
            "created_at": payload.get("created_at", ""),
            "memory_type": "episodic",
        })

    return results


async def _browse_semantic_qdrant(user_id: str, limit: int = 50) -> list[dict[str, object]]:
    """Browse ALL semantic facts for a user via Qdrant scroll (no query vector needed).

    Used by the memories list endpoint where there is no search query.
    """
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore

    settings = get_settings()
    client = get_qdrant_client()

    try:
        records, _next_offset = client.scroll(
            collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="status", match=MatchValue(value="active")),
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.error("Qdrant semantic browse failed: %s", e)
        return []

    results: list[dict[str, object]] = []
    for point in records:
        payload = point.payload or {}
        results.append({
            "subject": payload.get("subject", "?"),
            "predicate": payload.get("predicate", "?"),
            "object": payload.get("object", "?"),
            "content": payload.get("content", ""),
            "confidence": payload.get("confidence", 0.5),
            "importance_score": payload.get("importance_score", 5),
            "memory_type": "semantic",
        })

    return results


async def _retrieve_semantic_qdrant(
    user_id: str,
    query_vector: list[float],
    top_k: int,
) -> list[dict[str, object]]:
    """Retrieve semantic facts from Qdrant semantic_facts collection."""
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore

    settings = get_settings()
    client = get_qdrant_client()

    try:
        results = client.query_points(
            collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="status", match=MatchValue(value="active")),
                ]
            ),
            limit=top_k * 2,
            with_payload=True,
        )
    except Exception as e:
        logger.error("Qdrant semantic retrieval failed: %s", e)
        return []

    scored_results: list[dict[str, object]] = []
    for point in results.points:
        payload = point.payload or {}
        final = compute_final_score(
            similarity_score=point.score,
            importance_score=int(payload.get("importance_score", 5)),  # pyrefly: ignore
            last_accessed_at=payload.get("last_accessed_at"),  # pyrefly: ignore
        )

        if final >= settings.FORGETTING_THRESHOLD:
            scored_results.append({
                "subject": payload.get("subject", "?"),
                "predicate": payload.get("predicate", "?"),
                "object": payload.get("object", "?"),
                "content": payload.get("content", ""),
                "confidence": payload.get("confidence", 0.5),
                "importance_score": payload.get("importance_score", 5),
                "final_score": final,
                "memory_type": "semantic",
            })

    scored_results.sort(key=lambda x: float(str(x["final_score"])), reverse=True)
    return scored_results[:top_k]


async def _retrieve_semantic_neo4j(user_id: str) -> list[dict[str, object]]:
    """Retrieve active semantic facts from Neo4j."""
    settings = get_settings()
    driver = get_neo4j_driver()

    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                """
                MATCH (s:Entity {user_id: $user_id})
                      -[r:RELATES_TO {status: 'active'}]->
                      (o:Entity {user_id: $user_id})
                RETURN s.name AS subject,
                       r.predicate AS predicate,
                       o.name AS object,
                       r.confidence AS confidence,
                       r.importance_score AS importance_score,
                       r.last_accessed_at AS last_accessed_at
                ORDER BY r.importance_score DESC, r.confidence DESC
                LIMIT 20
                """,
                user_id=user_id,
            )

            facts: list[dict[str, object]] = []
            records = await result.data()
            for record in records:
                facts.append({
                    "subject": record["subject"],
                    "predicate": record["predicate"],
                    "object": record["object"],
                    "confidence": record.get("confidence", 0.5),
                    "importance_score": record.get("importance_score", 5),
                    "memory_type": "semantic",
                })

            # Update access timestamps
            if facts:
                await session.run(
                    """
                    MATCH (s:Entity {user_id: $user_id})
                          -[r:RELATES_TO {status: 'active'}]->
                          (o:Entity {user_id: $user_id})
                    SET r.last_accessed_at = datetime(),
                        r.access_count = COALESCE(r.access_count, 0) + 1
                    """,
                    user_id=user_id,
                )

            return facts

    except Exception as e:
        logger.error("Neo4j retrieval failed: %s", e)
        return []


async def _retrieve_profile(user_id: str) -> dict[str, object] | None:
    """Retrieve user profile from MongoDB."""
    collection = profiles_collection()
    profile = await collection.find_one(
        {"user_id": user_id},
        {"_id": 0},
    )
    return profile  # pyrefly: ignore


async def _retrieve_goals(user_id: str) -> list[dict[str, object]]:
    """Retrieve active goals from MongoDB."""
    collection = goals_collection()
    cursor = collection.find(
        {"user_id": user_id, "status": "active"},
        {"_id": 0},
    ).sort("priority", -1).limit(10)

    goals = await cursor.to_list(length=10)
    return goals  # pyrefly: ignore


async def retrieve_all_context(
    user_id: str,
    query: str,
) -> dict[str, object]:
    """Retrieve memories from ALL backends in parallel.

    Returns a structured dict with all memory types.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    settings = get_settings()
    top_k = settings.RETRIEVAL_TOP_K

    # Embed the query once, reuse for both Qdrant collections
    embedding_provider = get_embedding_provider()
    query_vector: list[float] = []
    if query.strip():
        query_vector = await embedding_provider.embed(query)

    # Helper for empty async results
    async def _empty_list() -> list[dict[str, object]]:
        return []

    # Run all retrievals in parallel
    # When query_vector is empty (e.g. memories list page), use scroll-based
    # browse to fetch all memories without needing a similarity search.
    tasks = [
        _retrieve_episodic(user_id, query_vector, top_k) if query_vector else _browse_episodic(user_id),
        _retrieve_semantic_qdrant(user_id, query_vector, top_k) if query_vector else _browse_semantic_qdrant(user_id),
        _retrieve_semantic_neo4j(user_id),
        _retrieve_profile(user_id),
        _retrieve_goals(user_id),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    episodic = results[0] if not isinstance(results[0], Exception) else []
    semantic_qdrant = results[1] if not isinstance(results[1], Exception) else []
    semantic_neo4j = results[2] if not isinstance(results[2], Exception) else []
    profile = results[3] if not isinstance(results[3], Exception) else None
    goals = results[4] if not isinstance(results[4], Exception) else []

    # Merge semantic results (Qdrant fuzzy + Neo4j structured, dedup by triple)
    seen_triples: set[str] = set()
    merged_semantic: list[dict[str, object]] = []

    for fact in list(semantic_qdrant) + list(semantic_neo4j):  # pyrefly: ignore
        triple_key = f"{fact.get('subject')}|{fact.get('predicate')}|{fact.get('object')}"
        if triple_key not in seen_triples:
            seen_triples.add(triple_key)
            merged_semantic.append(fact)

    # Log errors
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("Retrieval task %d failed: %s", i, r)

    logger.info(
        "Retrieved: episodic=%d, semantic=%d, profile=%s, goals=%d",
        len(episodic), len(merged_semantic),  # pyrefly: ignore
        profile is not None, len(goals),  # pyrefly: ignore
    )

    return {
        "episodic": episodic,
        "semantic": merged_semantic,
        "profile": profile,
        "goals": goals,
    }


# ──────────────────────────────────────────────
# Priority-Scored Context Assembly
# ──────────────────────────────────────────────

def build_context(
    profile: dict[str, object] | None,
    goals: list[dict[str, object]],
    semantic_facts: list[dict[str, object]],
    episodic_memories: list[dict[str, object]],
    conversation_turns: list[dict[str, str]],
    token_budget: int | None = None,
) -> str:
    """Assemble the final context block using priority scoring.

    Instead of fixed order, assigns every item a priority_score:
        priority_score = base_type_weight * final_score
    Sort descending, fill until token budget reached.

    Always includes: profile core fields + last 4-6 conversation turns.
    """
    settings = get_settings()
    budget = token_budget or settings.CONTEXT_TOKEN_BUDGET

    # ── Baseline context (always included, not competing) ──
    baseline_parts: list[str] = []

    # Profile core fields
    if profile:
        profile_lines = ["## User Profile"]
        if profile.get("name"):
            profile_lines.append(f"- Name: {profile['name']}")
        if profile.get("preferences"):
            prefs = profile["preferences"]
            if isinstance(prefs, dict):
                for k, v in prefs.items():
                    profile_lines.append(f"- Preference ({k}): {v}")
        if profile.get("traits"):
            traits = profile["traits"]
            if isinstance(traits, list) and traits:
                profile_lines.append(f"- Traits: {', '.join(str(t) for t in traits)}")
        if len(profile_lines) > 1:
            baseline_parts.append("\n".join(profile_lines))

    # Conversation turns
    if conversation_turns:
        conv_lines = ["## Recent Conversation"]
        for t in conversation_turns[-6:]:
            role = "User" if t["role"] == "user" else "Assistant"
            conv_lines.append(f"{role}: {t['content']}")
        baseline_parts.append("\n".join(conv_lines))

    baseline_text = "\n\n".join(baseline_parts)
    baseline_tokens = _estimate_tokens(baseline_text)
    remaining_budget = max(budget - baseline_tokens, 200)

    # ── Priority-scored items ──
    scored_items: list[tuple[float, str]] = []

    # Goals
    for g in goals:
        desc = g.get("description", "")
        priority = g.get("priority", "?")
        final = float(g.get("final_score", 0.8))  # pyrefly: ignore
        priority_score = BASE_WEIGHTS["goal"] * max(final, 0.5)
        text = f"- [Goal {priority}/10] {desc}"
        scored_items.append((priority_score, text))

    # Semantic facts
    for f in semantic_facts:
        subj = f.get("subject", "?")
        pred = f.get("predicate", "?")
        obj = f.get("object", "?")
        final = float(f.get("final_score", 0.7))  # pyrefly: ignore
        priority_score = BASE_WEIGHTS["semantic"] * max(final, 0.3)
        text = f"- {subj} → {pred} → {obj}"
        scored_items.append((priority_score, text))

    # Episodic memories
    for m in episodic_memories:
        content = m.get("content", "")
        final = float(m.get("final_score", 0.5))  # pyrefly: ignore
        priority_score = BASE_WEIGHTS["episodic"] * max(final, 0.2)
        text = f"- {content}"
        scored_items.append((priority_score, text))

    # Sort by priority_score descending
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # Fill until budget
    scored_lines: list[str] = []
    used_tokens = 0
    for score, text in scored_items:
        item_tokens = _estimate_tokens(text)
        if used_tokens + item_tokens > remaining_budget:
            break
        scored_lines.append(text)
        used_tokens += item_tokens

    # Assemble final context
    parts: list[str] = []
    if baseline_text:
        parts.append(baseline_text)

    if scored_lines:
        memory_section = "## Relevant Memories & Knowledge\n" + "\n".join(scored_lines)
        parts.append(memory_section)

    context = "\n\n".join(parts)
    logger.debug(
        "Context built: ~%d tokens (budget: %d, baseline: %d, scored: %d items)",
        _estimate_tokens(context), budget, baseline_tokens, len(scored_lines),
    )
    return context


def build_system_prompt(context: str) -> str:
    """Build the full system prompt including memory context."""
    base_prompt = (
        "You are MemoraeAI, a helpful AI assistant with persistent memory. "
        "You remember facts, preferences, goals, and past interactions with the user. "
        "Use the context below to personalize your responses. "
        "Be warm, helpful, and reference relevant memories naturally — "
        "don't explicitly say 'I remember that you said...' unless asked. "
        "If something contradicts your memory, gently ask for clarification.\n\n"
    )

    if context:
        return f"{base_prompt}--- Memory Context ---\n{context}\n--- End Context ---"
    else:
        return base_prompt
