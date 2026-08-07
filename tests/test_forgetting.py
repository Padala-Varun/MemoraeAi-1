"""Unit tests for soft-forgetting / decay scoring (no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.forgetting import compute_final_score


def test_decay_scoring():
    """Decay scoring should reduce score for old memories."""
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

    assert score_recent > score_old
    assert score_recent > 0
    assert score_old > 0


def test_decay_high_importance_compensates():
    """High importance should partially compensate for age."""
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

    assert high_importance > low_importance
