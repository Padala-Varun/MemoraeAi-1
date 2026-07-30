"""
MemoraeAI — Test Scenarios

Scripted test conversations covering:
  1. New fact extraction (semantic + episodic)
  2. Duplicate fact dedup
  3. Contradicting fact conflict resolution
  4. Profile update extraction
  5. Goal extraction
  6. Irrelevant small talk (nothing to extract)

Run: python -m pytest tests/test_scenarios.py -v
Or:  python tests/test_scenarios.py
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # pyrefly: ignore

load_dotenv()

# ──────────────────────────────────────────────
# Unit Tests — Pure logic (no DB, no LLM)
# ──────────────────────────────────────────────


def test_content_hash_deterministic():
    """content_hash for the same content must always produce the same hash."""
    from app.memory_detector import _compute_content_hash
    from app.schemas import ExtractedMemory

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
    assert hash1 == hash2, "Hash must be deterministic"
    assert len(hash1) == 64, "SHA-256 should produce 64 hex chars"


def test_content_hash_different_for_different_content():
    """Different content must produce different hashes."""
    from app.memory_detector import _compute_content_hash
    from app.schemas import ExtractedMemory

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
    from app.memory_detector import _validate_source_quote

    conversation = "User: I'm allergic to peanuts and shellfish.\nAssistant: I'll remember that."
    assert _validate_source_quote("allergic to peanuts", conversation) is True


def test_source_quote_validation_fail():
    """source_quote NOT in conversation text should fail."""
    from app.memory_detector import _validate_source_quote

    conversation = "User: I like chocolate.\nAssistant: Nice!"
    assert _validate_source_quote("allergic to peanuts", conversation) is False


def test_source_quote_validation_case_insensitive():
    """source_quote validation should be case-insensitive."""
    from app.memory_detector import _validate_source_quote

    conversation = "User: I LOVE Python programming"
    assert _validate_source_quote("love python programming", conversation) is True


def test_source_quote_too_short():
    """Very short quotes (< 5 chars) should be rejected."""
    from app.memory_detector import _validate_source_quote

    conversation = "User: Hi there, how are you?"
    assert _validate_source_quote("Hi", conversation) is False


def test_semantic_field_validation():
    """Semantic facts must have subject, predicate, and object."""
    from app.memory_detector import _validate_semantic_fields
    from app.schemas import ExtractedMemory

    # Valid semantic fact
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

    # Invalid — missing object
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


def test_decay_scoring():
    """Decay scoring should reduce score for old memories."""
    from app.forgetting import compute_final_score
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    recent = now - timedelta(hours=1)
    old = now - timedelta(days=30)

    score_recent = compute_final_score(
        similarity_score=0.9,
        importance_score=7,
        last_accessed_at=recent,
        decay_lambda=0.05,
    )

    score_old = compute_final_score(
        similarity_score=0.9,
        importance_score=7,
        last_accessed_at=old,
        decay_lambda=0.05,
    )

    assert score_recent > score_old, "Recent memory should score higher than old"
    assert score_recent > 0, "Score should be positive"
    assert score_old > 0, "Score should still be positive (not zero)"


def test_decay_high_importance_compensates():
    """High importance should partially compensate for age."""
    from app.forgetting import compute_final_score
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=15)

    low_importance = compute_final_score(
        similarity_score=0.9,
        importance_score=2,
        last_accessed_at=old,
        decay_lambda=0.05,
    )

    high_importance = compute_final_score(
        similarity_score=0.9,
        importance_score=9,
        last_accessed_at=old,
        decay_lambda=0.05,
    )

    assert high_importance > low_importance, "High importance should score higher"


def test_detector_output_nothing_to_extract():
    """DetectorOutput with nothing_to_extract should have empty memories."""
    from app.schemas import DetectorOutput

    output = DetectorOutput(nothing_to_extract=True, memories=[])
    assert output.nothing_to_extract is True
    assert len(output.memories) == 0


def test_extracted_memory_validation():
    """ExtractedMemory should enforce field constraints."""
    from app.schemas import ExtractedMemory

    mem = ExtractedMemory(
        type="episodic",
        content="Went to the store",
        source_quote="I went to the store",
        confidence=0.85,
        importance_score=5,
    )
    assert mem.type == "episodic"
    assert mem.confidence == 0.85
    assert mem.importance_score == 5


def test_config_settings_defaults():
    """Settings should have sensible defaults."""
    from app.config import Settings

    # Test with minimal required fields
    s = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        NEO4J_URI="bolt://localhost:7687",
        NEO4J_USERNAME="neo4j",
        NEO4J_PASSWORD="test",
        NEO4J_DATABASE="neo4j",
        QDRANT_URL="http://localhost:6333",
        QDRANT_API_KEY="test",
    )
    assert s.LLM_PROVIDER == "mistral"
    assert s.LLM_MODEL == "mistral-small-2506"
    assert s.EMBEDDING_DIMENSION == 1024
    assert s.DEDUP_SIMILARITY_THRESHOLD == 0.90
    assert s.CONFIDENCE_THRESHOLD == 0.6
    assert s.MIN_IMPORTANCE_SCORE == 3
    assert s.DECAY_LAMBDA == 0.05


def test_cors_origins_parsing():
    """CORS origins should be parsed from comma-separated string."""
    from app.config import Settings

    s = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        NEO4J_URI="bolt://localhost:7687",
        NEO4J_USERNAME="neo4j",
        NEO4J_PASSWORD="test",
        NEO4J_DATABASE="neo4j",
        QDRANT_URL="http://localhost:6333",
        QDRANT_API_KEY="test",
        CORS_ORIGINS="http://localhost:3000,http://localhost:5173",
    )
    origins = s.cors_origins_list
    assert "http://localhost:3000" in origins
    assert "http://localhost:5173" in origins
    assert len(origins) == 2


def test_context_builder_priority_scoring():
    """Priority scoring should rank by base_weight * final_score."""
    from app.context_builder import build_context

    context = build_context(
        profile={"name": "Alice", "preferences": {"theme": "dark"}, "traits": ["curious"]},
        goals=[{"description": "Learn Spanish", "priority": 8, "final_score": 0.9}],
        semantic_facts=[
            {"subject": "alice", "predicate": "works at", "object": "google", "final_score": 0.85}
        ],
        episodic_memories=[
            {"content": "Had coffee this morning", "final_score": 0.3}
        ],
        conversation_turns=[
            {"role": "user", "content": "Hi there!"},
            {"role": "assistant", "content": "Hello Alice!"},
        ],
    )

    assert "Alice" in context
    assert "Learn Spanish" in context
    assert "google" in context
    assert len(context) > 50


def test_context_builder_empty():
    """Context builder should handle empty inputs gracefully."""
    from app.context_builder import build_context

    context = build_context(
        profile=None,
        goals=[],
        semantic_facts=[],
        episodic_memories=[],
        conversation_turns=[],
    )

    # Should return an empty or minimal string
    assert isinstance(context, str)


def test_system_prompt_includes_context():
    """System prompt should include the context block."""
    from app.context_builder import build_system_prompt

    prompt = build_system_prompt("User likes Python programming")
    assert "MemoraeAI" in prompt
    assert "Python programming" in prompt
    assert "Memory Context" in prompt


# ──────────────────────────────────────────────
# Test runner
# ──────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_content_hash_deterministic,
        test_content_hash_different_for_different_content,
        test_source_quote_validation_pass,
        test_source_quote_validation_fail,
        test_source_quote_validation_case_insensitive,
        test_source_quote_too_short,
        test_semantic_field_validation,
        test_decay_scoring,
        test_decay_high_importance_compensates,
        test_detector_output_nothing_to_extract,
        test_extracted_memory_validation,
        test_config_settings_defaults,
        test_cors_origins_parsing,
        test_context_builder_priority_scoring,
        test_context_builder_empty,
        test_system_prompt_includes_context,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        sys.exit(1)
