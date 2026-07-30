"""
User service + conversation service — user identification and raw message storage.

Handles:
  - get_or_create_user: simple username lookup in MongoDB (no password auth)
  - store_message: immediate raw storage before any LLM processing
  - get_recent_turns / get_full_session_text: conversation retrieval
  - mark_memory_processed: flip the memory_processed flag
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.db_clients import users_collection, conversations_collection
from app.schemas import ConversationMessage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# User Identification
# ──────────────────────────────────────────────

async def get_or_create_user(username: str) -> str:
    """Look up a user by username, or create a new one.

    Args:
        username: Display username (case-insensitive lookup).

    Returns:
        user_id (str): UUID string for this user.

    Raises:
        ValueError: If username is empty or invalid.
    """
    if not username or not username.strip():
        raise ValueError("Username must be a non-empty string.")

    username_clean = username.strip().lower()
    collection = users_collection()

    # Try to find existing user
    existing = await collection.find_one({"username": username_clean})
    if existing is not None:
        # Update last_active timestamp
        await collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {"last_active": datetime.now(timezone.utc)}},
        )
        user_id: str = existing["user_id"]
        logger.info("User found: %s (user_id=%s)", username_clean, user_id)
        return user_id

    # Create new user
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    user_doc = {
        "user_id": user_id,
        "username": username_clean,
        "created_at": now,
        "last_active": now,
    }
    await collection.insert_one(user_doc)
    logger.info("User created: %s (user_id=%s)", username_clean, user_id)
    return user_id


# ──────────────────────────────────────────────
# Raw Conversation Storage
# ──────────────────────────────────────────────

async def store_message(
    user_id: str,
    session_id: str,
    role: str,
    content: str,
) -> str:
    """Store a conversation message in MongoDB immediately.

    Stored BEFORE any LLM processing — this is the source of truth.

    Args:
        user_id: Owner user ID. MUST be provided.
        session_id: Session identifier.
        role: "user" or "assistant".
        content: Message text.

    Returns:
        str: The inserted document's ObjectId as a string.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided for every message."
    assert role in ("user", "assistant"), f"Invalid role: {role}"

    message = ConversationMessage(
        user_id=user_id,
        session_id=session_id,
        role=role,  # pyrefly: ignore
        content=content,
        timestamp=datetime.now(timezone.utc),
        memory_processed=False,
    )

    collection = conversations_collection()
    result = await collection.insert_one(message.model_dump())
    doc_id = str(result.inserted_id)
    logger.debug(
        "Stored %s message for user=%s session=%s (id=%s)",
        role, user_id, session_id, doc_id,
    )
    return doc_id


async def get_recent_turns(
    user_id: str,
    session_id: str,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Fetch the most recent conversation messages for context.

    Args:
        user_id: Owner user ID.
        session_id: Session to retrieve from.
        limit: Max number of messages to return.

    Returns:
        List of dicts with 'role' and 'content' keys, oldest first.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = conversations_collection()
    cursor = collection.find(
        {"user_id": user_id, "session_id": session_id},
        {"role": 1, "content": 1, "timestamp": 1, "_id": 0},
    ).sort("timestamp", -1).limit(limit)

    messages = await cursor.to_list(length=limit)
    # Return in chronological order (oldest first)
    messages.reverse()
    return [{"role": m["role"], "content": m["content"]} for m in messages]


async def get_full_session_text(
    user_id: str,
    session_id: str,
) -> str:
    """Get the full conversation text for a session as a single string.

    Used by the Memory Detector to validate source_quote against
    the actual conversation content.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = conversations_collection()
    cursor = collection.find(
        {"user_id": user_id, "session_id": session_id},
        {"role": 1, "content": 1, "_id": 0},
    ).sort("timestamp", 1)

    messages = await cursor.to_list(length=1000)
    lines: list[str] = []
    for m in messages:
        prefix = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {m['content']}")
    return "\n".join(lines)


async def mark_memory_processed(
    user_id: str,
    session_id: str,
) -> None:
    """Flip memory_processed to true for all messages in a session.

    Called after the Memory Router finishes dispatching extractions.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = conversations_collection()
    result = await collection.update_many(
        {
            "user_id": user_id,
            "session_id": session_id,
            "memory_processed": False,
        },
        {"$set": {"memory_processed": True}},
    )
    if result.modified_count > 0:
        logger.info(
            "Marked %d messages as memory_processed for user=%s session=%s",
            result.modified_count, user_id, session_id,
        )


async def get_session_list(user_id: str) -> list[dict[str, object]]:
    """List all chat sessions for a user, with title from first message.

    Returns sessions ordered by most recent first.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = conversations_collection()

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"timestamp": 1}},
        {"$group": {
            "_id": "$session_id",
            "first_message": {"$first": "$content"},
            "first_role": {"$first": "$role"},
            "created_at": {"$first": "$timestamp"},
            "message_count": {"$sum": 1},
        }},
        {"$sort": {"created_at": -1}},
        {"$limit": 50},
    ]

    sessions: list[dict[str, object]] = []
    async for doc in collection.aggregate(pipeline):
        title = doc["first_message"]
        if len(title) > 60:
            title = title[:57] + "..."
        sessions.append({
            "session_id": doc["_id"],
            "title": title,
            "created_at": (
                doc["created_at"].isoformat()
                if hasattr(doc["created_at"], "isoformat")
                else str(doc["created_at"])
            ),
            "message_count": doc["message_count"],
        })

    return sessions
