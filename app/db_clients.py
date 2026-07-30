"""
Database clients — Qdrant, Neo4j, MongoDB connection setup in one file.

Singleton pattern for all three clients. Collection accessors for MongoDB.
Qdrant collection creation for both episodic_memories and semantic_facts.
Neo4j constraints for the Entity graph model.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# MongoDB (Motor async driver)
# ══════════════════════════════════════════════

_mongo_client: Any = None


def get_mongo_client() -> Any:
    """Get or create the singleton MongoDB async client."""
    global _mongo_client
    if _mongo_client is None:
        from motor.motor_asyncio import AsyncIOMotorClient  # pyrefly: ignore

        settings = get_settings()
        _mongo_client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
        )
        logger.info("MongoDB client created for %s", settings.MONGODB_URI[:40] + "...")
    return _mongo_client


def get_database() -> Any:
    """Get the configured database reference."""
    settings = get_settings()
    client = get_mongo_client()
    return client[settings.MONGODB_DATABASE]


def users_collection() -> Any:
    """Collection: users — stores user documents."""
    return get_database()["users"]


def conversations_collection() -> Any:
    """Collection: conversations — raw message storage (source of truth)."""
    return get_database()["conversations"]


def audit_log_collection() -> Any:
    """Collection: memory_audit_log — every dedup/conflict/forget action."""
    return get_database()["memory_audit_log"]


def profiles_collection() -> Any:
    """Collection: profiles — user profile documents."""
    return get_database()["profiles"]


def goals_collection() -> Any:
    """Collection: goals — user goal documents."""
    return get_database()["goals"]


async def close_mongo_client() -> None:
    """Close the MongoDB client connection. Call on app shutdown."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
        logger.info("MongoDB client closed.")


async def create_mongo_indexes() -> None:
    """Create necessary indexes on MongoDB collections.
    Called once on application startup."""
    # Users: unique username index
    await users_collection().create_index("username", unique=True)

    # Conversations: compound index for efficient per-user session queries
    await conversations_collection().create_index(
        [("user_id", 1), ("session_id", 1), ("timestamp", 1)]
    )

    # Conversations: index on memory_processed for background retry
    await conversations_collection().create_index(
        [("memory_processed", 1), ("timestamp", 1)]
    )

    # Profiles: unique per user
    await profiles_collection().create_index("user_id", unique=True)

    # Goals: compound for per-user queries
    await goals_collection().create_index([("user_id", 1), ("status", 1)])

    # Audit log: per-user time-ordered
    await audit_log_collection().create_index(
        [("user_id", 1), ("timestamp", -1)]
    )

    logger.info("MongoDB indexes created/verified.")


# ══════════════════════════════════════════════
# Qdrant (vector database)
# ══════════════════════════════════════════════

_qdrant_client: Any = None


def get_qdrant_client() -> Any:
    """Get or create the singleton Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient  # pyrefly: ignore

        settings = get_settings()
        _qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=10,
        )
        logger.info("Qdrant client created for %s", settings.QDRANT_URL[:50] + "...")
    return _qdrant_client


def ensure_qdrant_collections() -> None:
    """Create episodic_memories and semantic_facts collections if they don't exist.

    Vector config: mistral-embed outputs 1024-dim vectors, cosine distance.
    Payload indexes on user_id for filtered search.
    """
    from qdrant_client.http.models import (  # pyrefly: ignore
        Distance,
        VectorParams,
        PayloadSchemaType,
    )

    settings = get_settings()
    client = get_qdrant_client()

    # Get existing collection names
    collections = client.get_collections().collections
    existing_names = {c.name for c in collections}

    # Create both collections
    for collection_name in [
        settings.QDRANT_EPISODIC_COLLECTION,
        settings.QDRANT_SEMANTIC_COLLECTION,
    ]:
        if collection_name in existing_names:
            logger.info("Qdrant collection '%s' already exists.", collection_name)
            continue

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )

        # Payload index on user_id for efficient filtered queries
        client.create_payload_index(
            collection_name=collection_name,
            field_name="user_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

        logger.info(
            "Qdrant collection '%s' created (dim=%d, cosine).",
            collection_name,
            settings.EMBEDDING_DIMENSION,
        )

    # Additional index on status for semantic_facts
    if settings.QDRANT_SEMANTIC_COLLECTION not in existing_names:
        try:
            client.create_payload_index(
                collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
                field_name="status",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # Index may already exist


def close_qdrant_client() -> None:
    """Close the Qdrant client. Call on app shutdown."""
    global _qdrant_client
    if _qdrant_client is not None:
        _qdrant_client.close()
        _qdrant_client = None
        logger.info("Qdrant client closed.")


# ══════════════════════════════════════════════
# Neo4j (graph database)
# ══════════════════════════════════════════════

_neo4j_driver: Any = None


def get_neo4j_driver() -> Any:
    """Get or create the singleton Neo4j async driver."""
    global _neo4j_driver
    if _neo4j_driver is None:
        from neo4j import AsyncGraphDatabase  # pyrefly: ignore

        settings = get_settings()
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )
        logger.info("Neo4j driver created for %s", settings.NEO4J_URI)
    return _neo4j_driver


async def verify_neo4j_connectivity() -> bool:
    """Test the Neo4j connection. Returns True if successful."""
    driver = get_neo4j_driver()
    settings = get_settings()
    try:
        await driver.verify_connectivity()
        logger.info("Neo4j connectivity verified (database: %s).", settings.NEO4J_DATABASE)
        return True
    except Exception as e:
        logger.error("Neo4j connectivity check failed: %s", e)
        return False


async def setup_neo4j_constraints() -> None:
    """Create Neo4j constraints and indexes for the semantic memory schema.

    Graph model:
        (:Entity {name, user_id})-[r:RELATES_TO {predicate, status, ...}]->(:Entity)
    """
    driver = get_neo4j_driver()
    settings = get_settings()

    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        # Constraint: unique entity per user
        await session.run(
            "CREATE CONSTRAINT entity_user_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.user_id, e.name) IS UNIQUE"
        )

        # Index on Entity.user_id for fast filtered lookups
        await session.run(
            "CREATE INDEX entity_user_idx IF NOT EXISTS "
            "FOR (e:Entity) ON (e.user_id)"
        )

        logger.info("Neo4j constraints and indexes created/verified.")


async def close_neo4j_driver() -> None:
    """Close the Neo4j driver. Call on app shutdown."""
    global _neo4j_driver
    if _neo4j_driver is not None:
        await _neo4j_driver.close()
        _neo4j_driver = None
        logger.info("Neo4j driver closed.")
