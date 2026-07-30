"""
Composio Gmail Integration — parse email triggers and feed into memory pipeline.

Receives webhook payloads from Composio's GMAIL_NEW_GMAIL_MESSAGE trigger,
extracts email content (subject, body/snippet, sender), and runs it through
the existing memory detection → routing pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.memory_detector import detect_memories
from app.memory_router import route_memories
from app.schemas import DetectorOutput

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# Composio Client (lazy singleton)
# ══════════════════════════════════════════════

_composio_client: Any = None


def get_composio_client() -> Any:
    """Get or create the singleton Composio client."""
    global _composio_client
    if _composio_client is None:
        from composio import Composio  # pyrefly: ignore

        settings = get_settings()
        if not settings.COMPOSIO_API_KEY:
            raise ValueError("COMPOSIO_API_KEY is not set in .env")
        _composio_client = Composio(api_key=settings.COMPOSIO_API_KEY)
        logger.info("Composio client initialized.")
    return _composio_client


# ══════════════════════════════════════════════
# Email Parsing
# ══════════════════════════════════════════════

def parse_email_from_trigger(payload: dict[str, Any]) -> dict[str, str]:
    """Extract email fields from a Composio GMAIL_NEW_GMAIL_MESSAGE trigger payload.

    Handles both v1 (flat) and v3 (nested) webhook formats:
      v1: {payload: {subject, body, ...}}
      v3: {data: {payload: {messageText, subject, from, ...}}}

    Returns a dict with: subject, body, sender, timestamp, thread_id, message_id
    """
    # V3 format: email fields may be directly in 'data' or in 'data.payload'
    data_block = payload.get("data", {})
    if isinstance(data_block, dict):
        # Check if data itself has email fields (subject, messageText, from, etc.)
        if any(k in data_block for k in ("subject", "messageText", "snippet", "from", "threadId")):
            email_data = data_block
        else:
            email_data = data_block.get("payload", {})
    else:
        email_data = {}

    # V1 fallback: payload at top level
    if not email_data:
        email_data = payload.get("payload", payload)

    logger.info("Email data keys: %s", list(email_data.keys()) if isinstance(email_data, dict) else "not-dict")

    if not isinstance(email_data, dict):
        email_data = {}

    subject = email_data.get("subject", email_data.get("Subject", ""))
    body = email_data.get("message_text", email_data.get("messageText", email_data.get("body", "")))
    snippet = email_data.get("preview", email_data.get("snippet", email_data.get("Snippet", "")))
    sender = email_data.get("sender", email_data.get("from", email_data.get("From", "unknown")))
    thread_id = email_data.get("thread_id", email_data.get("threadId", ""))
    message_id = email_data.get("message_id", email_data.get("messageId", email_data.get("id", "")))
    timestamp = email_data.get("message_timestamp", email_data.get("date", email_data.get("timestamp", "")))

    # Fall back to snippet if body is empty
    if not body and snippet:
        body = snippet

    return {
        "subject": str(subject).strip(),
        "body": str(body).strip(),
        "sender": str(sender).strip(),
        "thread_id": str(thread_id),
        "message_id": str(message_id),
        "timestamp": str(timestamp) if timestamp else datetime.now(timezone.utc).isoformat(),
    }


def format_email_as_conversation(email_data: dict[str, str]) -> str:
    """Convert parsed email data into a conversation-like text format
    that the memory detector can process.

    The memory detector expects conversation text, so we format the email
    as if a user reported receiving it.
    """
    parts = []

    if email_data.get("sender"):
        parts.append(f"Email from: {email_data['sender']}")

    if email_data.get("subject"):
        parts.append(f"Subject: {email_data['subject']}")

    if email_data.get("body"):
        parts.append(f"Content: {email_data['body']}")

    if email_data.get("timestamp"):
        parts.append(f"Received at: {email_data['timestamp']}")

    return "\n".join(parts)


# ══════════════════════════════════════════════
# Memory Processing Pipeline
# ══════════════════════════════════════════════

async def process_email_memory(
    user_id: str,
    email_data: dict[str, str],
    session_id: str = "email-ingest",
) -> list[dict[str, str]]:
    """Run an email through the memory detection and routing pipeline.

    This reuses the exact same detect_memories() → route_memories() flow
    used for chat messages, but with email content formatted as conversation text.

    Args:
        user_id: The MemoraeAI user ID who owns this email connection.
        email_data: Parsed email data from parse_email_from_trigger().
        session_id: Session identifier for this ingestion (defaults to "email-ingest").

    Returns:
        List of store results from the memory pipeline.
    """
    conversation_text = format_email_as_conversation(email_data)

    if not conversation_text.strip():
        logger.warning("Empty email content, skipping memory extraction.")
        return []

    # Build recent_turns in the format the detector expects
    recent_turns = [
        {"role": "user", "content": conversation_text},
    ]

    logger.info(
        "Processing email memory: user=%s, subject='%s', sender='%s'",
        user_id,
        email_data.get("subject", "")[:50],
        email_data.get("sender", ""),
    )

    # Step 1: Detect memories from the email content
    try:
        result = await detect_memories(
            conversation_text=conversation_text,
            recent_turns=recent_turns,
        )
    except Exception as e:
        logger.error("Email memory detection failed: %s", e)
        return []

    if result.nothing_to_extract:
        logger.info("No memories extracted from email (subject='%s').", email_data.get("subject", ""))
        return []

    # Step 2: Route memories through existing pipelines
    try:
        detector_output = DetectorOutput(
            nothing_to_extract=False,
            memories=result.memories,
        )
        store_results = await route_memories(
            detector_output=detector_output,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as e:
        logger.error("Email memory routing failed: %s", e)
        return []

    logger.info(
        "Email memory extraction complete: user=%s, %d memories from '%s'.",
        user_id,
        len(store_results),
        email_data.get("subject", "")[:50],
    )
    return store_results
