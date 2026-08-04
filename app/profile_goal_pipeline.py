"""
Profile & Goals Pipeline — MongoDB structured storage.

No embedding, no graph — structured lookup only.
  - Profile: update_one({user_id}, {$set: ...}, upsert=True)
  - Goals: update_one({user_id, description}, {$set: ...}, upsert=True)
    with status (active/completed/abandoned), deadline, progress_notes
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db_clients import profiles_collection, goals_collection
from app.schemas import ExtractedMemory

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Profile handler
# ──────────────────────────────────────────────

def _extract_trait_key(memory: ExtractedMemory) -> str:
    """Build a normalised key that identifies the *topic* of a trait.

    Uses (subject, predicate) from the LLM extraction. If the LLM did not
    fill them, falls back to the first few significant words of the content
    so we can still deduplicate obvious duplicates.
    """
    if memory.subject and memory.predicate:
        return f"{memory.subject.lower().strip()}|{memory.predicate.lower().strip()}"
    # Fallback: rough category from content
    words = memory.content.lower().split()
    # Take up to the first 4 significant words as a rough topic key
    significant = [w for w in words if w not in {"is", "a", "the", "an", "my", "i", "user", "user's"}]
    return "|".join(significant[:4])


async def _replace_conflicting_trait(
    collection: object,  # pyrefly: ignore
    user_id: str,
    trait_key: str,
    new_trait: str,
) -> bool:
    """Remove any existing trait whose key matches, then add the new one.

    Returns True if an old trait was replaced, False if it's a fresh addition.
    """
    # Fetch current profile to check existing traits
    doc = await collection.find_one({"user_id": user_id}, {"traits": 1})  # pyrefly: ignore
    if not doc or not doc.get("traits"):
        return False

    existing_traits: list[str] = doc["traits"]
    # Compare each existing trait's rough key to the new one
    traits_to_remove: list[str] = []
    new_key_lower = trait_key.lower()

    for old_trait in existing_traits:
        # Quick heuristic: if the old trait and new trait share the same
        # predicate words (e.g. both contain "favorite hero"), they conflict.
        old_lower = old_trait.lower()
        # Split the trait_key into subject and predicate parts
        key_parts = new_key_lower.split("|")
        # Match if both key parts appear in the old trait
        if len(key_parts) >= 2:
            subject_match = key_parts[0] in old_lower
            predicate_match = key_parts[1] in old_lower
            if subject_match and predicate_match and old_lower != new_trait.lower():
                traits_to_remove.append(old_trait)
        elif len(key_parts) == 1 and key_parts[0] in old_lower and old_lower != new_trait.lower():
            traits_to_remove.append(old_trait)

    if traits_to_remove:
        # Pull the old conflicting traits, then push the new one
        await collection.update_one(  # pyrefly: ignore
            {"user_id": user_id},
            {"$pull": {"traits": {"$in": traits_to_remove}}},
        )
        logger.info(
            "Removed conflicting traits for user %s: %s (replaced by: %s)",
            user_id, traits_to_remove, new_trait[:60],
        )
        return True

    return False


async def handle_profile(
    memory: ExtractedMemory,
    user_id: str,
) -> dict[str, str]:
    """Upsert a profile update in MongoDB.

    Handles conflict resolution for traits: if an existing trait covers the
    same subject+predicate (e.g. "favorite hero"), the old one is REPLACED,
    not appended alongside. This prevents contradictory facts.

    Args:
        memory: The extracted profile_update memory.
        user_id: Owner user ID. MUST be provided.

    Returns:
        Dict with 'type' and 'action'.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = profiles_collection()
    now = datetime.now(timezone.utc)

    update: dict[str, object] = {
        "$set": {
            "user_id": user_id,
            "updated_at": now,
        },
        "$setOnInsert": {
            "created_at": now,
        },
        "$addToSet": {
            "source_quotes": memory.source_quote,
        },
    }

    # Try to extract structured info from content
    content_lower = memory.content.lower()
    if "name" in content_lower and memory.subject:
        update["$set"]["name"] = memory.object or memory.content  # pyrefly: ignore
    elif "prefer" in content_lower:
        # Add to preferences dict — $set naturally overwrites on same key
        pref_key = memory.predicate or "general"
        pref_val = memory.object or memory.content
        update["$set"][f"preferences.{pref_key}"] = pref_val  # pyrefly: ignore
    else:
        # Trait: first remove any conflicting old trait, THEN add new
        trait_key = _extract_trait_key(memory)
        await _replace_conflicting_trait(collection, user_id, trait_key, memory.content)
        update["$addToSet"]["traits"] = memory.content  # pyrefly: ignore

    await collection.update_one(
        {"user_id": user_id},
        update,
        upsert=True,
    )

    logger.info("Profile updated for user %s: '%s'", user_id, memory.content[:50])
    return {"type": "profile_update", "action": "upserted"}


# ──────────────────────────────────────────────
# Goals handler
# ──────────────────────────────────────────────

async def handle_goal(
    memory: ExtractedMemory,
    user_id: str,
) -> dict[str, str]:
    """Upsert a goal in MongoDB.

    Args:
        memory: The extracted goal memory.
        user_id: Owner user ID. MUST be provided.

    Returns:
        Dict with 'type' and 'action'.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = goals_collection()
    now = datetime.now(timezone.utc)

    # Check if goal already exists (by user_id + description)
    existing = await collection.find_one(
        {"user_id": user_id, "description": memory.content}
    )

    if existing:
        # Update existing goal
        await collection.update_one(
            {"user_id": user_id, "description": memory.content},
            {
                "$set": {
                    "status": "active",
                    "importance_score": memory.importance_score,
                    "source_quote": memory.source_quote,
                    "last_accessed_at": now,
                },
                "$inc": {"access_count": 1},
            },
        )
        logger.info("Goal updated for user %s: '%s'", user_id, memory.content[:50])
        return {"type": "goal", "action": "updated"}
    else:
        # Insert new goal
        await collection.insert_one({
            "user_id": user_id,
            "description": memory.content,
            "status": "active",
            "importance_score": memory.importance_score,
            "source_quote": memory.source_quote,
            "priority": min(memory.importance_score, 10),
            "created_at": now,
            "last_accessed_at": now,
            "access_count": 1,
            "progress_notes": [],
            "deadline": None,
        })
        logger.info("Goal created for user %s: '%s'", user_id, memory.content[:50])
        return {"type": "goal", "action": "created"}


async def handle_goal_completed(
    memory: ExtractedMemory,
    user_id: str,
) -> dict[str, str]:
    """Mark matching active goals as completed.

    Uses word-overlap matching to find the best-matching active goal,
    since the user's phrasing when completing ("I paid the Google bill")
    will differ from the original goal description ("Resolve Google One
    payment issue").

    Args:
        memory: The extracted goal_completed memory.
        user_id: Owner user ID.

    Returns:
        Dict with 'type' and 'action'.
    """
    assert user_id and user_id.strip(), "user_id MUST be provided."

    collection = goals_collection()
    now = datetime.now(timezone.utc)

    # Fetch all active goals for this user
    cursor = collection.find({"user_id": user_id, "status": "active"})
    active_goals = await cursor.to_list(length=100)

    if not active_goals:
        logger.info("No active goals to complete for user %s", user_id)
        return {"type": "goal_completed", "action": "no_match"}

    # Fuzzy match: find the goal with the highest word overlap
    completed_words = set(memory.content.lower().split())
    # Remove common stop words for better matching
    stop_words = {"i", "have", "has", "the", "a", "an", "my", "is", "was",
                  "been", "it", "to", "and", "of", "for", "that", "this",
                  "done", "completed", "cleared", "finished", "resolved",
                  "paid", "fixed"}
    completed_words -= stop_words

    best_match = None
    best_score = 0

    for goal in active_goals:
        desc = goal.get("description", "")
        goal_words = set(desc.lower().split()) - stop_words
        if not goal_words:
            continue
        overlap = len(completed_words & goal_words)
        # Normalize by the smaller set size
        score = overlap / max(min(len(completed_words), len(goal_words)), 1)
        if score > best_score:
            best_score = score
            best_match = goal

    # Require at least some meaningful overlap
    if best_match and best_score >= 0.2:
        await collection.update_one(
            {"_id": best_match["_id"]},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": now,
                    "last_accessed_at": now,
                },
                "$push": {
                    "progress_notes": f"Completed: {memory.content}"
                },
            },
        )
        logger.info(
            "Goal completed for user %s: '%s' (matched: '%s', score=%.2f)",
            user_id, memory.content[:50],
            best_match.get("description", "")[:50], best_score,
        )
        return {"type": "goal_completed", "action": "completed"}
    else:
        logger.info(
            "Goal completion did not match any active goal for user %s: '%s' (best_score=%.2f)",
            user_id, memory.content[:50], best_score,
        )
        return {"type": "goal_completed", "action": "no_match"}
