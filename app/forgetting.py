"""
Forgetting — decay scoring (soft) + cleanup job logic (hard) + explicit user forget.

Soft forgetting (applied at every retrieval):
    recency_weight = exp(-0.05 * days_since_last_accessed)
    final_score = similarity_score * recency_weight * (importance_score / 10)
    Drop below 0.15 threshold. Update last_accessed_at + increment access_count.

Hard forgetting (background job, scripts/cleanup_job.py):
    - Delete Qdrant points: importance < 3 AND last_accessed > 30 days
    - Delete Neo4j relationships: status=outdated AND outdated_at > 60 days
    - Also delete corresponding Qdrant semantic_facts entry
    - Log every deletion to MongoDB memory_audit_log BEFORE deleting

Explicit user-triggered forgetting:
    - Find by content match across all DBs, delete, log.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta

from app.config import get_settings, get_embedding_provider
from app.db_clients import audit_log_collection
from app.schemas import AuditLogEntry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Soft Forgetting (decay scoring)
# ──────────────────────────────────────────────

def compute_final_score(
    similarity_score: float,
    importance_score: int,
    last_accessed_at: datetime | str | None,
    decay_lambda: float | None = None,
) -> float:
    """Compute the decay-weighted final score for a memory.

    Formula:
        recency_weight = exp(-λ * days_since_last_accessed)
        final_score = similarity_score * recency_weight * (importance_score / 10)
    """
    settings = get_settings()
    lam = decay_lambda if decay_lambda is not None else settings.DECAY_LAMBDA
    now = datetime.now(timezone.utc)

    if last_accessed_at is None:
        days_since = 0.0
    elif isinstance(last_accessed_at, str):
        try:
            last_dt = datetime.fromisoformat(last_accessed_at.replace("Z", "+00:00"))
            days_since = (now - last_dt).total_seconds() / 86400.0
        except (ValueError, TypeError):
            days_since = 0.0
    else:
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)
        days_since = (now - last_accessed_at).total_seconds() / 86400.0

    days_since = max(days_since, 0.0)
    recency_weight = math.exp(-lam * days_since)
    final_score = similarity_score * recency_weight * (importance_score / 10.0)
    return final_score


# ──────────────────────────────────────────────
# Hard Forgetting (background job functions)
# ──────────────────────────────────────────────

async def hard_forget_episodic(dry_run: bool = False) -> int:
    """Delete low-importance, stale episodic memories from Qdrant.

    Criteria: importance_score < threshold AND last_accessed_at > N days ago.
    """
    from qdrant_client.http.models import (  # pyrefly: ignore
        Filter,
        FieldCondition,
        Range,
    )
    from app.db_clients import get_qdrant_client

    settings = get_settings()
    client = get_qdrant_client()
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=settings.HARD_FORGET_EPISODIC_DAYS)
    ).isoformat()

    deleted_count = 0

    try:
        scroll_result = client.scroll(
            collection_name=settings.QDRANT_EPISODIC_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="importance_score",
                        range=Range(lt=settings.HARD_FORGET_IMPORTANCE_THRESHOLD),  # pyrefly: ignore
                    ),
                ]
            ),
            limit=100,
            with_payload=True,
        )

        points_to_delete: list[str] = []
        for point in scroll_result[0]:
            payload = point.payload or {}
            last_accessed = payload.get("last_accessed_at", "")

            if isinstance(last_accessed, str) and last_accessed < cutoff:
                user_id = str(payload.get("user_id", "unknown"))

                if not dry_run:
                    audit = AuditLogEntry(
                        user_id=user_id,
                        action="hard_forget_deleted",
                        memory_type="episodic",
                        memory_id=str(point.id),
                        details=(
                            f"Hard forget: importance={payload.get('importance_score')}, "
                            f"last_accessed={last_accessed}"
                        ),
                    )
                    await audit_log_collection().insert_one(audit.model_dump())

                points_to_delete.append(str(point.id))
                deleted_count += 1

        if points_to_delete and not dry_run:
            client.delete(
                collection_name=settings.QDRANT_EPISODIC_COLLECTION,
                points_selector=points_to_delete,  # pyrefly: ignore
            )

        action = "Would delete" if dry_run else "Deleted"
        logger.info("Hard forget (episodic): %s %d points.", action, deleted_count)

    except Exception as e:
        logger.error("Hard forget episodic failed: %s", e)

    return deleted_count


async def hard_forget_semantic(dry_run: bool = False) -> int:
    """Delete outdated semantic facts from Neo4j AND corresponding Qdrant entries.

    Criteria: status=outdated AND outdated_at > N days ago.
    """
    from app.db_clients import get_neo4j_driver, get_qdrant_client
    from qdrant_client.http.models import (  # pyrefly: ignore
        Filter,
        FieldCondition,
        MatchValue,
    )

    settings = get_settings()
    driver = get_neo4j_driver()
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=settings.HARD_FORGET_SEMANTIC_DAYS)
    )

    deleted_count = 0

    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            if dry_run:
                result = await session.run(
                    """
                    MATCH (s:Entity)-[r:RELATES_TO {status: 'outdated'}]->(o:Entity)
                    WHERE r.outdated_at < datetime($cutoff)
                    RETURN count(r) AS count
                    """,
                    cutoff=cutoff.isoformat(),
                )
                record = await result.single()
                count = record["count"] if record else 0
                logger.info("Hard forget (semantic): Would delete %d relationships.", count)
                return count  # pyrefly: ignore

            # Fetch before deleting to log
            result = await session.run(
                """
                MATCH (s:Entity)-[r:RELATES_TO {status: 'outdated'}]->(o:Entity)
                WHERE r.outdated_at < datetime($cutoff)
                RETURN s.name AS subject, r.predicate AS predicate,
                       o.name AS object, s.user_id AS user_id
                """,
                cutoff=cutoff.isoformat(),
            )

            records = await result.data()

            for rec in records:
                audit = AuditLogEntry(
                    user_id=rec.get("user_id", "unknown"),
                    action="hard_forget_deleted",
                    memory_type="semantic_fact",
                    details=(
                        f"Hard forget outdated: ({rec['subject']}, "
                        f"{rec['predicate']}, {rec['object']})"
                    ),
                )
                await audit_log_collection().insert_one(audit.model_dump())

            # Delete from Neo4j
            delete_result = await session.run(
                """
                MATCH (s:Entity)-[r:RELATES_TO {status: 'outdated'}]->(o:Entity)
                WHERE r.outdated_at < datetime($cutoff)
                DELETE r
                RETURN count(*) AS deleted
                """,
                cutoff=cutoff.isoformat(),
            )
            del_record = await delete_result.single()
            deleted_count = del_record["deleted"] if del_record else 0  # pyrefly: ignore

            # Also delete corresponding Qdrant semantic_facts entries
            qdrant_client = get_qdrant_client()
            for rec in records:
                try:
                    scroll = qdrant_client.scroll(
                        collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
                        scroll_filter=Filter(
                            must=[
                                FieldCondition(key="user_id", match=MatchValue(value=rec.get("user_id", ""))),
                                FieldCondition(key="subject", match=MatchValue(value=rec["subject"])),
                                FieldCondition(key="predicate", match=MatchValue(value=rec["predicate"])),
                                FieldCondition(key="object", match=MatchValue(value=rec["object"])),
                                FieldCondition(key="status", match=MatchValue(value="outdated")),
                            ]
                        ),
                        limit=5,
                    )
                    point_ids = [str(p.id) for p in scroll[0]]
                    if point_ids:
                        qdrant_client.delete(
                            collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
                            points_selector=point_ids,  # pyrefly: ignore
                        )
                except Exception as qe:
                    logger.warning("Failed to delete Qdrant semantic fact: %s", qe)

            logger.info(
                "Hard forget (semantic): Deleted %d outdated relationships.", deleted_count
            )

    except Exception as e:
        logger.error("Hard forget semantic failed: %s", e)

    return deleted_count


# ──────────────────────────────────────────────
# Explicit User-Triggered Forgetting
# ──────────────────────────────────────────────

async def explicit_forget(
    user_id: str,
    search_text: str,
) -> dict[str, int]:
    """Handle explicit user forget request — search and delete across all DBs.

    Args:
        user_id: Owner user ID.
        search_text: Text describing what the user wants forgotten.

    Returns:
        Dict with counts of deleted items per type.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore
    from app.db_clients import get_qdrant_client, get_neo4j_driver, goals_collection

    settings = get_settings()
    deleted = {"episodic": 0, "semantic": 0, "goals": 0}

    # 1. Search and delete from Qdrant episodic
    try:
        embedding_provider = get_embedding_provider()
        query_vector = await embedding_provider.embed(search_text)
        client = get_qdrant_client()

        results = client.query_points(
            collection_name=settings.QDRANT_EPISODIC_COLLECTION,
            query=query_vector,
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
            if point.score > 0.75:
                audit = AuditLogEntry(
                    user_id=user_id,
                    action="user_forget_request",
                    memory_type="episodic",
                    memory_id=str(point.id),
                    details=f"User requested forget: '{search_text[:60]}'",
                )
                await audit_log_collection().insert_one(audit.model_dump())
                client.delete(
                    collection_name=settings.QDRANT_EPISODIC_COLLECTION,
                    points_selector=[str(point.id)],  # pyrefly: ignore
                )
                deleted["episodic"] += 1

    except Exception as e:
        logger.error("Explicit forget (Qdrant episodic) failed: %s", e)

    # 2. Search and delete from Neo4j + Qdrant semantic_facts
    try:
        driver = get_neo4j_driver()
        search_lower = search_text.lower()
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                """
                MATCH (s:Entity {user_id: $user_id})
                      -[r:RELATES_TO {status: 'active'}]->
                      (o:Entity {user_id: $user_id})
                WHERE toLower(s.name) CONTAINS $search
                   OR toLower(o.name) CONTAINS $search
                   OR toLower(r.predicate) CONTAINS $search
                SET r.status = 'outdated', r.outdated_at = datetime()
                RETURN count(r) AS updated
                """,
                user_id=user_id,
                search=search_lower,
            )
            record = await result.single()
            if record and record["updated"] > 0:
                audit = AuditLogEntry(
                    user_id=user_id,
                    action="user_forget_request",
                    memory_type="semantic_fact",
                    details=f"User forget: marked {record['updated']} facts as outdated for '{search_text[:60]}'",
                )
                await audit_log_collection().insert_one(audit.model_dump())
                deleted["semantic"] = record["updated"]

    except Exception as e:
        logger.error("Explicit forget (Neo4j) failed: %s", e)

    # 3. Search and delete goals from MongoDB
    try:
        result = await goals_collection().update_many(
            {
                "user_id": user_id,
                "status": "active",
                "description": {"$regex": search_text, "$options": "i"},
            },
            {"$set": {"status": "abandoned"}},
        )
        if result.modified_count > 0:
            audit = AuditLogEntry(
                user_id=user_id,
                action="user_forget_request",
                memory_type="goal",
                details=f"User forget: abandoned {result.modified_count} goal(s) matching '{search_text[:60]}'",
            )
            await audit_log_collection().insert_one(audit.model_dump())
            deleted["goals"] = result.modified_count

    except Exception as e:
        logger.error("Explicit forget (MongoDB goals) failed: %s", e)

    logger.info(
        "Explicit forget for user %s ('%s'): %s",
        user_id, search_text[:40], deleted,
    )
    return deleted
