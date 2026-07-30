"""
ALL Pydantic models for the memory system — one file.

Covers:
  - Memory Detector output schemas (ExtractedMemory, DetectorOutput)
  - Stored memory schemas (episodic, semantic, profile, goals)
  - Conversation message schema
  - User document schema
  - Audit log schema
  - API request/response schemas
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Memory Detector output schemas
# ──────────────────────────────────────────────

class ExtractedMemory(BaseModel):
    """A single memory extracted by the Memory Detector.

    The content_hash is computed in Python (SHA-256) AFTER the LLM returns,
    never by the LLM itself. importance_score is part of the same
    single LLM call (merged extraction + scoring).
    """

    type: Literal["episodic", "semantic_fact", "profile_update", "goal"] = Field(
        ..., description="Classification of the memory type."
    )
    content: str = Field(
        ...,
        min_length=3,
        description="Human-readable description of the extracted memory.",
    )
    source_quote: str = Field(
        ...,
        min_length=3,
        description="Verbatim quote from the conversation that justifies this extraction.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for this extraction (0.0–1.0).",
    )
    importance_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="Importance rating (1-10), scored in the same LLM call.",
    )
    content_hash: str = Field(
        default="",
        description="SHA-256 hash computed in Python for fast exact-dedup.",
    )
    self_verification_passed: bool = Field(
        default=True,
        description="Whether the LLM's self-verification pass confirmed this extraction.",
    )

    # Semantic-fact-specific fields
    subject: str | None = Field(
        default=None,
        description="Entity the fact is about (required for semantic_fact).",
    )
    predicate: str | None = Field(
        default=None,
        description="Relationship or attribute (required for semantic_fact).",
    )
    object: str | None = Field(
        default=None,
        description="Value of the attribute (required for semantic_fact).",
    )

    @field_validator("subject", "predicate", "object")
    @classmethod
    def normalize_semantic_fields(
        cls, v: str | None, info: object  # pyrefly: ignore
    ) -> str | None:
        """Strip and lowercase semantic triple fields for consistency."""
        if v is not None:
            return v.strip()
        return v


class DetectorOutput(BaseModel):
    """Output schema for the Memory Detector — single LLM call.

    If nothing_to_extract is True, memories MUST be empty.
    """

    nothing_to_extract: bool = Field(
        ...,
        description="Set to true if no memories worth storing are found.",
    )
    memories: list[ExtractedMemory] = Field(
        default_factory=list,
        description="List of extracted memories. Empty if nothing_to_extract is true.",
    )


# ──────────────────────────────────────────────
# Stored memory schemas (persisted in DBs)
# ──────────────────────────────────────────────

class StoredEpisodicMemory(BaseModel):
    """Episodic memory point payload stored in Qdrant."""

    id: str = Field(..., description="UUID for this memory point.")
    user_id: str = Field(..., description="Owner user ID. MUST always be set.")
    content: str = Field(..., description="Text content of the memory.")
    source_quote: str = Field(..., description="Original source text from conversation.")
    importance_score: int = Field(..., ge=1, le=10, description="Importance rating (1–10).")
    content_hash: str = Field(default="", description="SHA-256 for fast exact-dedup.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0, ge=0)
    session_id: str | None = Field(default=None, description="Session during creation.")


class StoredSemanticFact(BaseModel):
    """Semantic fact stored as Neo4j relationship + Qdrant embedding."""

    user_id: str = Field(..., description="Owner user ID. MUST always be set.")
    subject: str = Field(..., description="Entity the fact is about.")
    predicate: str = Field(..., description="Relationship or attribute name.")
    object: str = Field(..., description="Value of the attribute.")
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: Literal["active", "outdated"] = Field(default="active")
    importance_score: int = Field(..., ge=1, le=10, description="Importance rating (1–10).")
    content_hash: str = Field(default="", description="SHA-256 for fast exact-dedup.")
    source_quote: str = Field(default="", description="Original source text.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0, ge=0)
    outdated_at: datetime | None = Field(
        default=None,
        description="When this fact was marked outdated (conflict replacement).",
    )
    neo4j_relationship_id: str | None = Field(
        default=None,
        description="ID of the corresponding Neo4j relationship.",
    )


class StoredGoal(BaseModel):
    """A user goal stored in MongoDB."""

    user_id: str = Field(..., description="Owner user ID. MUST always be set.")
    description: str = Field(..., description="Goal description text.")
    status: Literal["active", "completed", "abandoned"] = Field(default="active")
    priority: int = Field(default=5, ge=1, le=10, description="Priority (1–10).")
    importance_score: int = Field(default=5, ge=1, le=10, description="Importance rating.")
    source_quote: str = Field(default="", description="Original source text.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0, ge=0)


class StoredProfile(BaseModel):
    """User profile document stored in MongoDB."""

    user_id: str = Field(..., description="Owner user ID. MUST always be set.")
    name: str | None = Field(default=None, description="User's name if known.")
    preferences: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs of user preferences.",
    )
    traits: list[str] = Field(
        default_factory=list,
        description="Personality traits or characteristics.",
    )
    source_quotes: list[str] = Field(
        default_factory=list,
        description="Source quotes that led to profile updates.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────
# User document schema
# ──────────────────────────────────────────────

class UserDocument(BaseModel):
    """User document stored in MongoDB users collection."""

    user_id: str = Field(..., description="UUID string identifier.")
    username: str = Field(..., description="Display username (lowercase).")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────
# Conversation message schema
# ──────────────────────────────────────────────

class ConversationMessage(BaseModel):
    """A single conversation message stored in MongoDB."""

    user_id: str = Field(..., description="Owner user ID.")
    session_id: str = Field(..., description="Session identifier.")
    role: Literal["user", "assistant"] = Field(..., description="Message sender role.")
    content: str = Field(..., description="Message text content.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    memory_processed: bool = Field(
        default=False,
        description="Flipped to true once memory extraction completes.",
    )


# ──────────────────────────────────────────────
# Audit log schema
# ──────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    """Entry written to MongoDB memory_audit_log on every
    dedup, conflict, forget, or delete action."""

    user_id: str = Field(..., description="Owner user ID.")
    action: Literal[
        "dedup_skip",
        "dedup_update",
        "conflict_outdated",
        "conflict_created",
        "hard_forget_deleted",
        "user_forget_request",
        "importance_discard",
    ] = Field(..., description="Type of audit action.")
    memory_type: Literal["episodic", "semantic_fact", "profile_update", "goal"]
    memory_id: str | None = Field(default=None, description="ID of affected memory.")
    details: str = Field(default="", description="Human-readable details.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────
# API request/response schemas
# ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Request body for user login/registration."""
    username: str = Field(..., min_length=1, max_length=64)


class LoginResponse(BaseModel):
    """Response body for user login/registration."""
    user_id: str
    username: str


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""
    user_id: str = Field(..., min_length=1)
    session_id: str | None = Field(
        default=None,
        description="Session ID. Auto-generated if not provided.",
    )
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """Response body for a chat message."""
    session_id: str
    response: str
    memories_extracted: bool = False


class HistoryRequest(BaseModel):
    """Request body for fetching conversation history."""
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class SessionInfo(BaseModel):
    """Info about a single chat session."""
    session_id: str
    title: str
    created_at: str
    message_count: int


class SessionsRequest(BaseModel):
    """Request body for listing sessions."""
    user_id: str = Field(..., min_length=1)


class MemoryListRequest(BaseModel):
    """Request body for listing stored memories."""
    user_id: str = Field(..., min_length=1)


class ForgetRequest(BaseModel):
    """Request body for explicitly forgetting memories."""
    user_id: str = Field(..., min_length=1)
    search_text: str = Field(
        ...,
        min_length=1,
        description="Text describing what to forget.",
    )
