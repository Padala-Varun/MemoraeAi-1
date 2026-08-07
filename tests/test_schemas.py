"""Unit tests for schemas and config defaults (no DB)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import DetectorOutput, ExtractedMemory


def test_detector_output_nothing_to_extract():
    """DetectorOutput with nothing_to_extract should have empty memories."""
    output = DetectorOutput(nothing_to_extract=True, memories=[])
    assert output.nothing_to_extract is True
    assert len(output.memories) == 0


def test_extracted_memory_validation():
    """ExtractedMemory should enforce field constraints."""
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


def test_memory_type_literals():
    """Supported memory types include profile, goal, semantic, and episodic."""
    for mem_type in ("episodic", "semantic_fact", "profile_update", "goal", "goal_completed"):
        mem = ExtractedMemory(
            type=mem_type,
            content=f"Sample {mem_type}",
            source_quote="sample quote text",
            confidence=0.9,
            importance_score=6,
            subject="user" if mem_type == "semantic_fact" else None,
            predicate="likes" if mem_type == "semantic_fact" else None,
            object="python" if mem_type == "semantic_fact" else None,
        )
        assert mem.type == mem_type


def test_invalid_memory_type_rejected():
    """Unknown memory types must fail validation."""
    with pytest.raises(ValidationError):
        ExtractedMemory(
            type="unknown_type",  # type: ignore[arg-type]
            content="Invalid",
            source_quote="invalid quote",
            confidence=0.9,
            importance_score=5,
        )


def test_config_settings_defaults():
    """Settings should have sensible defaults."""
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
