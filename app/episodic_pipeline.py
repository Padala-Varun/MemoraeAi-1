"""
Episodic Pipeline — dedup + store + retrieve for episodic memories (Qdrant only).

handle() entrypoint:
  1. Fast-path: check content_hash against recent-hash cache → if exact match, skip
  2. Embed memory content, query Qdrant top-3 filtered by user_id
     If cosine similarity > 0.90 → update existing point's last_seen/access_count
  3. Otherwise insert new point with full payload
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.config import get_settings, get_embedding_provider
from app.db_clients import get_qdrant_client, audit_log_collection
from app.schemas import ExtractedMemory, StoredEpisodicMemory, AuditLogEntry

logger = logging.getLogger(__name__)

# In-memory recent-hash cache for fast exact-dedup (per-process)
_recent_hashes: dict[str, str] = {}  # content_hash -> point_id
_MAX_CACHE_SIZE = 500


# ──────────────────────────────────────────────
# Main handle entrypoint
# ──────────────────────────────────────────────

async def handle(
    memory: ExtractedMemory,
    user_id: str,
    session_id: str | None = None,
) -> dict[str, str]:
    """Process an episodic memory: dedup → store.

    Args:
        memory: The extracted episodic memory.
        user_id: Owner user ID. MUST be provided.
        session_id: Optional session ID for context.

    Returns:
        Dict with 'type' and 'action' keys.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    settings = get_settings()

    # ── Step 1: Fast-path content_hash check ──
    if memory.content_hash and memory.content_hash in _recent_hashes:
        existing_id = _recent_hashes[memory.content_hash]
        logger.info(
            "Episodic fast-dedup (hash match): content='%s' existing_id=%s",
            memory.content[:50], existing_id,
        )
        await _update_last_seen(existing_id, user_id)

        audit = AuditLogEntry(
            user_id=user_id,
            action="dedup_update",
            memory_type="episodic",
            memory_id=existing_id,
            details=f"Hash-based fast dedup. Updated last_seen.",
        )
        await audit_log_collection().insert_one(audit.model_dump())

        return {"type": "episodic", "action": "deduplicated"}

    # ── Step 2: Embed and similarity check ──
    embedding_provider = get_embedding_provider()
    vector = await embedding_provider.embed(memory.content)

    dup = await _check_similarity_dedup(user_id, memory.content, vector)
    if dup is not None:
        await _update_last_seen(dup["point_id"], user_id)

        # Cache the hash for fast future dedup
        if memory.content_hash:
            _cache_hash(memory.content_hash, str(dup["point_id"]))

        return {"type": "episodic", "action": "deduplicated"}

    # ── Step 3: Insert new point ──
    point_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    payload = StoredEpisodicMemory(
        id=point_id,
        user_id=user_id,
        content=memory.content,
        source_quote=memory.source_quote,
        importance_score=memory.importance_score,
        content_hash=memory.content_hash,
        created_at=now,
        last_accessed_at=now,
        access_count=0,
        session_id=session_id,
    )

    from qdrant_client.http.models import PointStruct  # pyrefly: ignore

    client = get_qdrant_client()
    client.upsert(
        collection_name=settings.QDRANT_EPISODIC_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload.model_dump(mode="json"),
            )
        ],
    )

    # Cache the hash
    if memory.content_hash:
        _cache_hash(memory.content_hash, point_id)

    logger.info("Stored episodic memory: id=%s content='%s'", point_id, memory.content[:50])
    return {"type": "episodic", "action": "stored", "id": point_id}


# ──────────────────────────────────────────────
# Dedup helpers
# ──────────────────────────────────────────────

async def _check_similarity_dedup(
    user_id: str,
    content: str,
    embedding: list[float],
) -> dict[str, object] | None:
    """Check if an episodic memory is a duplicate via Qdrant similarity search.

    Returns None if no duplicate, or dict with 'point_id' and 'score'.
    """
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore

    settings = get_settings()
    client = get_qdrant_client()

    try:
        results = client.query_points(
            collection_name=settings.QDRANT_EPISODIC_COLLECTION,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                ]
            ),
            limit=3,
            with_payload=True,
        )

        for point in results.points:
            if point.score >= settings.DEDUP_SIMILARITY_THRESHOLD:
                logger.info(
                    "Episodic duplicate found (score=%.3f): existing='%s' new='%s'",
                    point.score,
                    str(point.payload.get("content", ""))[:50],  # pyrefly: ignore
                    content[:50],
                )

                audit = AuditLogEntry(
                    user_id=user_id,
                    action="dedup_update",
                    memory_type="episodic",
                    memory_id=str(point.id),
                    details=f"Similarity dedup (score={point.score:.3f}). Updated last_seen.",
                )
                await audit_log_collection().insert_one(audit.model_dump())

                return {"point_id": point.id, "score": point.score}

    except Exception as e:
        logger.error("Episodic dedup check failed: %s", e)

    return None


async def _update_last_seen(point_id: str | int, user_id: str) -> None:
    """Update last_accessed_at and increment access_count on a Qdrant point."""
    assert user_id and user_id.strip(), "user_id MUST be provided."

    settings = get_settings()
    client = get_qdrant_client()

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        client.set_payload(
            collection_name=settings.QDRANT_EPISODIC_COLLECTION,
            payload={"last_accessed_at": now_iso},
            points=[point_id],  # pyrefly: ignore
        )
        logger.debug("Updated last_seen for episodic point %s", point_id)
    except Exception as e:
        logger.error("Failed to update last_seen for point %s: %s", point_id, e)


def _cache_hash(content_hash: str, point_id: str) -> None:
    """Add a hash to the in-memory cache, evicting oldest if full."""
    global _recent_hashes
    if len(_recent_hashes) >= _MAX_CACHE_SIZE:
        # Evict oldest entries (first 100)
        keys = list(_recent_hashes.keys())[:100]
        for k in keys:
            del _recent_hashes[k]
    _recent_hashes[content_hash] = point_id
