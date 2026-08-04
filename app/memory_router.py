"""
Memory Router — routes detected memories to the correct pipeline by type.

Takes the DetectorOutput and dispatches each ExtractedMemory to:
  - episodic_pipeline.handle()
  - semantic_pipeline.handle()
  - profile_goal_pipeline.handle()

Each pipeline exposes a single handle(memory, user_id) entrypoint.
The Router doesn't know or care about dedup/conflict/storage internals.
"""

from __future__ import annotations

import logging

from app.schemas import DetectorOutput, ExtractedMemory

logger = logging.getLogger(__name__)


async def route_memories(
    detector_output: DetectorOutput,
    user_id: str,
    session_id: str | None = None,
) -> list[dict[str, str]]:
    """Route each extracted memory to its pipeline based on .type.

    Args:
        detector_output: Output from memory_detector.detect_memories().
        user_id: Owner user ID. MUST be provided.
        session_id: Optional session ID for episodic context.

    Returns:
        List of result dicts with 'type' and 'action' keys.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided for routing."

    if detector_output.nothing_to_extract or not detector_output.memories:
        logger.info("Memory Router: nothing to route.")
        return []

    results: list[dict[str, str]] = []

    for memory in detector_output.memories:
        try:
            result = await _dispatch_single(memory, user_id, session_id)
            results.append(result)
            logger.info(
                "Memory Router: %s → %s", result["type"], result["action"]
            )
        except Exception as e:
            logger.error(
                "Memory Router: failed to route '%s' (%s): %s",
                memory.content[:40], memory.type, e,
            )
            results.append({
                "type": memory.type,
                "action": "error",
                "error": str(e),
            })

    logger.info(
        "Memory Router: dispatched %d/%d memories.",
        len([r for r in results if r["action"] != "error"]),
        len(detector_output.memories),
    )
    return results


async def _dispatch_single(
    memory: ExtractedMemory,
    user_id: str,
    session_id: str | None,
) -> dict[str, str]:
    """Dispatch a single memory to the appropriate pipeline."""

    if memory.type == "episodic":
        from app.episodic_pipeline import handle as episodic_handle
        return await episodic_handle(memory, user_id, session_id)

    elif memory.type == "semantic_fact":
        from app.semantic_pipeline import handle as semantic_handle
        return await semantic_handle(memory, user_id)

    elif memory.type == "profile_update":
        from app.profile_goal_pipeline import handle_profile as profile_handle
        result = await profile_handle(memory, user_id)

        # If the profile update also carries a full semantic triple,
        # forward it to the semantic pipeline so any contradicting
        # semantic facts (in Neo4j + Qdrant) get marked outdated.
        if memory.subject and memory.predicate and memory.object:
            try:
                from app.semantic_pipeline import handle as semantic_handle
                await semantic_handle(memory, user_id)
                logger.info(
                    "Memory Router: profile_update also routed to semantic pipeline "
                    "for conflict resolution: (%s, %s, %s)",
                    memory.subject, memory.predicate, memory.object,
                )
            except Exception as e:
                logger.warning(
                    "Memory Router: semantic side-dispatch failed for profile_update: %s", e
                )

        return result

    elif memory.type == "goal":
        from app.profile_goal_pipeline import handle_goal as goal_handle
        return await goal_handle(memory, user_id)

    elif memory.type == "goal_completed":
        from app.profile_goal_pipeline import handle_goal_completed
        return await handle_goal_completed(memory, user_id)

    else:
        logger.warning("Unknown memory type: %s", memory.type)
        return {"type": memory.type, "action": "skipped"}
