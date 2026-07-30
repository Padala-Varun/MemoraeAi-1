"""
Semantic Pipeline — dedup + conflict + store + retrieve (Neo4j + Qdrant hybrid).

handle() entrypoint:
  1. Neo4j: Query for existing (User)-[predicate]->(Object) with same user_id + subject + predicate
     - Same object → update confidence/last_confirmed_at (dedup)
     - Different object → CONFLICT: set old to outdated, create new as active
     - Nothing found → create new as active
  2. Qdrant: Upsert embedding of fact text into semantic_facts collection
     with payload {user_id, subject, predicate, object, status}
     Keep Qdrant status in sync with Neo4j.

Provides upsert_semantic_fact() Cypher helper encapsulating step 1.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.config import get_settings, get_embedding_provider
from app.db_clients import get_neo4j_driver, get_qdrant_client, audit_log_collection
from app.schemas import ExtractedMemory, AuditLogEntry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Main handle entrypoint
# ──────────────────────────────────────────────

async def handle(
    memory: ExtractedMemory,
    user_id: str,
) -> dict[str, str]:
    """Process a semantic fact: Neo4j dedup/conflict → Qdrant upsert.

    Args:
        memory: The extracted semantic fact memory.
        user_id: Owner user ID. MUST be provided.

    Returns:
        Dict with 'type' and 'action' keys.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."
    assert memory.subject and memory.predicate and memory.object, \
        "Semantic fact must have subject, predicate, and object."

    # Step 1: Neo4j upsert (handles dedup + conflict)
    neo4j_result = await upsert_semantic_fact(
        user_id=user_id,
        subject=memory.subject,
        predicate=memory.predicate,
        object_value=memory.object,
        confidence=memory.confidence,
        importance_score=memory.importance_score,
        source_quote=memory.source_quote,
    )

    # Step 2: Qdrant upsert (regardless of Neo4j outcome)
    await _upsert_qdrant_fact(
        user_id=user_id,
        memory=memory,
        status="active",  # New/updated facts are always active
    )

    # If conflict was resolved, also update the OLD fact's status in Qdrant
    if neo4j_result == "conflict_resolved":
        await _mark_qdrant_fact_outdated(
            user_id=user_id,
            subject=memory.subject,
            predicate=memory.predicate,
            exclude_object=memory.object,
        )

    logger.info(
        "Semantic memory %s: (%s, %s, %s) for user %s",
        neo4j_result, memory.subject, memory.predicate, memory.object, user_id,
    )
    return {"type": "semantic_fact", "action": neo4j_result}


# ──────────────────────────────────────────────
# Neo4j Cypher helper (encapsulates conflict detection)
# ──────────────────────────────────────────────

async def upsert_semantic_fact(
    user_id: str,
    subject: str,
    predicate: str,
    object_value: str,
    confidence: float,
    importance_score: int,
    source_quote: str = "",
) -> str:
    """Insert or update a semantic fact with full conflict handling.

    Args:
        user_id: Owner user ID. MUST be provided.
        subject: Entity the fact is about.
        predicate: Relationship or attribute.
        object_value: Value of the attribute.
        confidence: Confidence score (0-1).
        importance_score: Importance rating (1-10).
        source_quote: Original source text from conversation.

    Returns:
        'created' | 'updated' | 'conflict_resolved'
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    driver = get_neo4j_driver()
    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()

    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        # Step 1: Check for existing active relationship
        check_result = await session.run(
            """
            MATCH (s:Entity {name: $subject, user_id: $user_id})
                  -[r:RELATES_TO {predicate: $predicate, status: 'active'}]->
                  (o:Entity {user_id: $user_id})
            RETURN o.name AS existing_object, id(r) AS rel_id
            LIMIT 1
            """,
            subject=subject.lower(),
            predicate=predicate.lower(),
            user_id=user_id,
        )

        record = await check_result.single()

        if record is not None:
            existing_object = record["existing_object"]

            if existing_object.lower() == object_value.lower():
                # Same fact — just update confidence and timestamp (dedup)
                await session.run(
                    """
                    MATCH (s:Entity {name: $subject, user_id: $user_id})
                          -[r:RELATES_TO {predicate: $predicate, status: 'active'}]->
                          (o:Entity {user_id: $user_id})
                    SET r.confidence = CASE WHEN $confidence > r.confidence
                            THEN $confidence ELSE r.confidence END,
                        r.last_confirmed_at = datetime($now),
                        r.access_count = COALESCE(r.access_count, 0) + 1
                    """,
                    subject=subject.lower(),
                    predicate=predicate.lower(),
                    user_id=user_id,
                    confidence=confidence,
                    now=now,
                )

                audit = AuditLogEntry(
                    user_id=user_id,
                    action="dedup_skip",
                    memory_type="semantic_fact",
                    details=f"Duplicate triple ({subject}, {predicate}, {object_value}). Confidence boosted.",
                )
                await audit_log_collection().insert_one(audit.model_dump())

                logger.info(
                    "Semantic fact updated (dedup): (%s, %s, %s) for user %s",
                    subject, predicate, object_value, user_id,
                )
                return "updated"

            else:
                # CONFLICT — different object value
                # Mark existing as outdated
                await session.run(
                    """
                    MATCH (s:Entity {name: $subject, user_id: $user_id})
                          -[r:RELATES_TO {predicate: $predicate, status: 'active'}]->
                          (o:Entity {user_id: $user_id})
                    SET r.status = 'outdated',
                        r.outdated_at = datetime($now)
                    """,
                    subject=subject.lower(),
                    predicate=predicate.lower(),
                    user_id=user_id,
                    now=now,
                )

                # Log the conflict
                audit_outdated = AuditLogEntry(
                    user_id=user_id,
                    action="conflict_outdated",
                    memory_type="semantic_fact",
                    details=(
                        f"Marked outdated: ({subject}, {predicate}, {existing_object}). "
                        f"Replaced by: ({subject}, {predicate}, {object_value})"
                    ),
                )
                await audit_log_collection().insert_one(audit_outdated.model_dump())

                logger.info(
                    "Semantic conflict resolved: (%s, %s) '%s' → '%s' for user %s",
                    subject, predicate, existing_object, object_value, user_id,
                )

        # Step 2: Create the new relationship (for both new and conflict cases)
        await session.run(
            """
            MERGE (s:Entity {name: $subject, user_id: $user_id})
            MERGE (o:Entity {name: $object_value, user_id: $user_id})
            CREATE (s)-[r:RELATES_TO {
                predicate: $predicate,
                status: 'active',
                confidence: $confidence,
                importance_score: $importance_score,
                source_quote: $source_quote,
                created_at: datetime($now),
                last_accessed_at: datetime($now),
                access_count: 0
            }]->(o)
            """,
            subject=subject.lower(),
            object_value=object_value.lower(),
            predicate=predicate.lower(),
            user_id=user_id,
            confidence=confidence,
            importance_score=importance_score,
            source_quote=source_quote,
            now=now,
        )

        result_action = (
            "conflict_resolved"
            if record is not None and record["existing_object"].lower() != object_value.lower()
            else "created"
        )

        if result_action == "created":
            audit_created = AuditLogEntry(
                user_id=user_id,
                action="conflict_created",
                memory_type="semantic_fact",
                details=f"Created: ({subject}, {predicate}, {object_value})",
            )
            await audit_log_collection().insert_one(audit_created.model_dump())

        return result_action


# ──────────────────────────────────────────────
# Qdrant semantic_facts helpers
# ──────────────────────────────────────────────

async def _upsert_qdrant_fact(
    user_id: str,
    memory: ExtractedMemory,
    status: str = "active",
) -> None:
    """Upsert a semantic fact embedding into the Qdrant semantic_facts collection."""
    from qdrant_client.http.models import PointStruct  # pyrefly: ignore

    settings = get_settings()
    embedding_provider = get_embedding_provider()

    # Embed the fact as a natural sentence
    fact_text = f"{memory.subject} {memory.predicate} {memory.object}"
    vector = await embedding_provider.embed(fact_text)

    point_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "user_id": user_id,
        "subject": memory.subject.lower() if memory.subject else "",
        "predicate": memory.predicate.lower() if memory.predicate else "",
        "object": memory.object.lower() if memory.object else "",
        "content": memory.content,
        "source_quote": memory.source_quote,
        "status": status,
        "confidence": memory.confidence,
        "importance_score": memory.importance_score,
        "content_hash": memory.content_hash,
        "created_at": now,
        "last_accessed_at": now,
        "access_count": 0,
    }

    client = get_qdrant_client()
    client.upsert(
        collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
        points=[
            PointStruct(id=point_id, vector=vector, payload=payload)
        ],
    )
    logger.debug("Qdrant semantic_facts upserted: %s", fact_text[:60])


async def _mark_qdrant_fact_outdated(
    user_id: str,
    subject: str,
    predicate: str,
    exclude_object: str,
) -> None:
    """Mark old Qdrant semantic_facts entries as outdated when a conflict is resolved.

    Searches for facts matching user_id + subject + predicate but NOT the new object,
    and updates their status to 'outdated'.
    """
    from qdrant_client.http.models import (  # pyrefly: ignore
        Filter,
        FieldCondition,
        MatchValue,
    )

    settings = get_settings()
    client = get_qdrant_client()

    try:
        results = client.scroll(
            collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="subject", match=MatchValue(value=subject.lower())),
                    FieldCondition(key="predicate", match=MatchValue(value=predicate.lower())),
                    FieldCondition(key="status", match=MatchValue(value="active")),
                ]
            ),
            limit=10,
            with_payload=True,
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        for point in results[0]:
            payload = point.payload or {}
            if payload.get("object", "").lower() != exclude_object.lower():
                client.set_payload(
                    collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
                    payload={"status": "outdated", "outdated_at": now_iso},
                    points=[point.id],  # pyrefly: ignore
                )
                logger.debug(
                    "Marked Qdrant semantic fact outdated: %s %s %s",
                    payload.get("subject"), payload.get("predicate"), payload.get("object"),
                )

    except Exception as e:
        logger.error("Failed to mark Qdrant semantic facts outdated: %s", e)
