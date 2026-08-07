"""Unit tests for memory detector helpers (no DB, no LLM)."""

from __future__ import annotations

from app.memory_detector import (
    _compute_content_hash,
    _validate_semantic_fields,
    _validate_source_quote,
)
from app.schemas import ExtractedMemory


def test_content_hash_deterministic():
    """content_hash for the same content must always produce the same hash."""
    mem = ExtractedMemory(
        type="semantic_fact",
        content="User is allergic to peanuts",
        source_quote="I'm allergic to peanuts",
        confidence=0.95,
        importance_score=9,
        subject="user",
        predicate="allergic to",
        object="peanuts",
    )

    hash1 = _compute_content_hash(mem)
    hash2 = _compute_content_hash(mem)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_content_hash_different_for_different_content():
    """Different content must produce different hashes."""
    mem1 = ExtractedMemory(
        type="episodic",
        content="Went to Paris last summer",
        source_quote="I went to Paris last summer",
        confidence=0.9,
        importance_score=7,
    )
    mem2 = ExtractedMemory(
        type="episodic",
        content="Went to London last winter",
        source_quote="I went to London last winter",
        confidence=0.9,
        importance_score=7,
    )

    assert _compute_content_hash(mem1) != _compute_content_hash(mem2)


def test_source_quote_validation_pass():
    """source_quote that exists in conversation text should pass."""
    conversation = "User: I'm allergic to peanuts and shellfish.\nAssistant: I'll remember that."
    assert _validate_source_quote("allergic to peanuts", conversation) is True


def test_source_quote_validation_fail():
    """source_quote NOT in conversation text should fail."""
    conversation = "User: I like chocolate.\nAssistant: Nice!"
    assert _validate_source_quote("allergic to peanuts", conversation) is False


def test_source_quote_validation_case_insensitive():
    """source_quote validation should be case-insensitive."""
    conversation = "User: I LOVE Python programming"
    assert _validate_source_quote("love python programming", conversation) is True


def test_source_quote_too_short():
    """Very short quotes (< 5 chars) should be rejected."""
    conversation = "User: Hi there, how are you?"
    assert _validate_source_quote("Hi", conversation) is False


def test_semantic_field_validation():
    """Semantic facts must have subject, predicate, and object."""
    valid = ExtractedMemory(
        type="semantic_fact",
        content="User works at Google",
        source_quote="I work at Google",
        confidence=0.95,
        importance_score=7,
        subject="user",
        predicate="works at",
        object="Google",
    )
    assert _validate_semantic_fields(valid) is True

    invalid = ExtractedMemory(
        type="semantic_fact",
        content="User works somewhere",
        source_quote="I work somewhere",
        confidence=0.9,
        importance_score=5,
        subject="user",
        predicate="works at",
        object=None,
    )
    assert _validate_semantic_fields(invalid) is False
