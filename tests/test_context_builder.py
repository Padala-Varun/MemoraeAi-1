"""Unit tests for context builder helpers (no DB, no LLM)."""

from __future__ import annotations

from app.context_builder import build_context, build_system_prompt


def test_context_builder_priority_scoring():
    """Context should include profile, goals, and semantic facts."""
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
    context = build_context(
        profile=None,
        goals=[],
        semantic_facts=[],
        episodic_memories=[],
        conversation_turns=[],
    )
    assert isinstance(context, str)


def test_system_prompt_includes_context():
    """System prompt should include the context block."""
    prompt = build_system_prompt("User likes Python programming")
    assert "MemoraeAI" in prompt
    assert "Python programming" in prompt
    assert "Memory Context" in prompt
