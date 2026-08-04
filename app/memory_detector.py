"""
Memory Detector — THE MOST CRITICAL COMPONENT.

Single LLM call that returns extraction + verification + importance scoring
combined. Avoids redundant second LLM round-trip per the spec.

Hard requirements enforced:
  - Structured output via LangChain's with_structured_output (Pydantic binding)
  - Only extracts explicitly stated or directly implied information
  - Returns nothing_to_extract=true if nothing worth remembering
  - Every extraction includes a verbatim source_quote
  - source_quote validated PROGRAMMATICALLY in Python (exact substring check)
  - content_hash (SHA-256) computed in Python, not by the LLM
  - Discard confidence < 0.6 OR importance_score < 3 before routing
  - Self-verification pass included in the same structured call
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.config import get_settings, get_llm_provider
from app.schemas import DetectorOutput, ExtractedMemory

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Combined extraction + scoring + verification prompt
# ──────────────────────────────────────────────

DETECTOR_SYSTEM_PROMPT = """You are a precise memory extraction and scoring system for a personal AI assistant. Your job is to analyze conversation turns and:
1. EXTRACT memories that are explicitly stated or directly implied
2. SCORE each memory's importance (1-10)
3. SELF-VERIFY each extraction against the source text

## EXTRACTION RULES — FOLLOW EXACTLY:
1. ONLY extract facts, preferences, goals, or events the user EXPLICITLY states.
2. NEVER infer, assume, or fabricate information not directly in the text.
3. If nothing worth remembering is found, set nothing_to_extract=true and return empty memories list.
4. For every extraction, provide a VERBATIM quote (exact substring) from the conversation as source_quote.
5. Classify each extraction into EXACTLY ONE type:
   - "episodic": A specific event, experience, or interaction (e.g., "I went to Paris last summer")
   - "semantic_fact": A factual statement — MUST include subject, predicate, and object fields (e.g., "I'm allergic to peanuts")
   - "profile_update": Identity info, preferences, characteristics (e.g., "I prefer dark mode")
   - "goal": Something the user wants to achieve (e.g., "I'm trying to learn Spanish")
   - "goal_completed": The user indicates they have FINISHED, CLEARED, DONE, RESOLVED, or COMPLETED a previously mentioned task or goal (e.g., "I paid the Google bill", "I have cleared the payment", "done with the interview"). The content should describe what was completed.
6. For semantic_fact type, you MUST provide subject, predicate, and object to form a knowledge triple.
7. Do NOT extract: greetings, pleasantries, small talk, questions (unless revealing info), assistant responses, vague/ambiguous info.

## IMPORTANCE SCORING RUBRIC (1-10):
Score each memory based on how valuable it is to remember for future conversations.

**1-2 (Trivial):** Weather, temporary moods, generic reactions.
  Example score 2: "User mentioned it's raining today"

**3-4 (Low context):** Routine actions, mildly interesting one-off mentions.
  Example score 3: "User had coffee this morning"

**5-6 (Moderate):** Useful preferences, current activities, specific interests.
  Example score 5: "User prefers email over phone calls"
  Example score 6: "User is learning Python programming"

**7-8 (Important):** Career info, relationships, meaningful life events.
  Example score 7: "User works as a data scientist at Google"
  Example score 8: "User's mother was recently diagnosed with diabetes"

**9-10 (Critical):** Safety-critical info, core identity, major life events.
  Example score 9: "User is allergic to penicillin"
  Example score 10: "User is getting married next month"

## SELF-VERIFICATION:
For each extraction, double-check:
- Is the content DIRECTLY supported by the conversation text?
- Is the source_quote an actual substring from the conversation?
- Is the classification correct?
Set self_verification_passed=false for any extraction you're not confident about.

## CONFIDENCE:
Assign 0.0-1.0 based on how clearly the information is stated.
Only return items with confidence >= 0.6.
"""


# ──────────────────────────────────────────────
# Validation helpers (Python code, not LLM)
# ──────────────────────────────────────────────

def _validate_source_quote(quote: str, conversation_text: str) -> bool:
    """Programmatically verify that source_quote appears in the conversation.

    Does a case-insensitive, whitespace-normalized substring check.
    This is a CODE check — we never trust the LLM's claim alone.
    """
    # Normalize whitespace for comparison
    norm_conv = " ".join(conversation_text.lower().split())
    norm_quote = " ".join(quote.lower().split())

    if len(norm_quote) < 5:
        return False  # Quote too short to be meaningful

    return norm_quote in norm_conv


def _validate_semantic_fields(memory: ExtractedMemory) -> bool:
    """Ensure semantic_fact type has required triple fields."""
    if memory.type == "semantic_fact":
        return bool(memory.subject and memory.predicate and memory.object)
    return True


def _compute_content_hash(memory: ExtractedMemory) -> str:
    """Compute SHA-256 hash for fast exact-dedup.

    For semantic_fact: hash of type + subject + predicate + object
    For others: hash of type + content (normalized)
    """
    if memory.type == "semantic_fact" and memory.subject and memory.predicate and memory.object:
        raw = f"{memory.type}|{memory.subject.lower().strip()}|{memory.predicate.lower().strip()}|{memory.object.lower().strip()}"
    else:
        raw = f"{memory.type}|{memory.content.lower().strip()}"

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────
# Main detect function
# ──────────────────────────────────────────────

async def detect_memories(
    conversation_text: str,
    recent_turns: list[dict[str, str]],
) -> DetectorOutput:
    """Run the single-call memory extraction + scoring + verification pipeline.

    Args:
        conversation_text: Full session text for source_quote validation.
        recent_turns: Last N conversation turns as [{"role": ..., "content": ...}].

    Returns:
        DetectorOutput with validated, verified, scored memories.
    """
    if not recent_turns:
        return DetectorOutput(nothing_to_extract=True, memories=[])

    # Format conversation for the LLM
    formatted_turns = "\n".join(
        f"{'User' if t['role'] == 'user' else 'Assistant'}: {t['content']}"
        for t in recent_turns
    )

    # ── Single LLM call: extract + score + self-verify ──
    logger.info("Memory Detector: Running single-call extraction + scoring + verification...")
    llm = get_llm_provider()

    try:
        extraction_result: Any = await llm.generate_structured(
            prompt=f"Analyze this conversation and extract memories. Score each for importance (1-10). Self-verify each extraction.\n\n{formatted_turns}",
            schema=DetectorOutput,
            system_prompt=DETECTOR_SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.error("Memory Detector LLM call failed: %s", e)
        return DetectorOutput(nothing_to_extract=True, memories=[])

    if extraction_result.nothing_to_extract or not extraction_result.memories:
        logger.info("Memory Detector: Nothing to extract.")
        return DetectorOutput(nothing_to_extract=True, memories=[])

    logger.info(
        "Memory Detector: %d candidate(s) from LLM.",
        len(extraction_result.memories),
    )

    # ── Post-LLM validation in Python ──
    settings = get_settings()
    validated_memories: list[ExtractedMemory] = []

    for mem in extraction_result.memories:
        # 1. Self-verification check (from LLM's own assessment)
        if not mem.self_verification_passed:
            logger.info(
                "Discarded (self-verification failed): %s", mem.content[:60]
            )
            continue

        # 2. Confidence threshold
        if mem.confidence < settings.CONFIDENCE_THRESHOLD:
            logger.debug(
                "Discarded (low confidence %.2f): %s", mem.confidence, mem.content[:60]
            )
            continue

        # 3. Importance threshold
        if mem.importance_score < settings.MIN_IMPORTANCE_SCORE:
            logger.debug(
                "Discarded (low importance %d): %s", mem.importance_score, mem.content[:60]
            )
            continue

        # 4. Programmatic source_quote validation — NEVER trust LLM alone
        if not _validate_source_quote(mem.source_quote, conversation_text):
            logger.warning(
                "Discarded (source_quote not found in text): quote='%s' content='%s'",
                mem.source_quote[:60],
                mem.content[:60],
            )
            continue

        # 5. Semantic triple validation
        if not _validate_semantic_fields(mem):
            logger.warning(
                "Discarded (missing semantic fields): content='%s'",
                mem.content[:60],
            )
            continue

        # 6. Compute content_hash in Python (never by LLM)
        mem.content_hash = _compute_content_hash(mem)

        validated_memories.append(mem)

    if not validated_memories:
        logger.info("Memory Detector: All candidates filtered out after validation.")
        return DetectorOutput(nothing_to_extract=True, memories=[])

    logger.info(
        "Memory Detector: %d memory(ies) validated and accepted.",
        len(validated_memories),
    )

    return DetectorOutput(nothing_to_extract=False, memories=validated_memories)
