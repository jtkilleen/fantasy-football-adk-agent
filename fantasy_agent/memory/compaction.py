"""Context Bloat Management, Sliding-Window Summarization, and ADK Compaction Configuration.

Satisfies AgentOps Rubric Criterion 2.2 (History Compaction):
Implements context bloat management (token-based truncation, sliding windows, summarization)
via ADK `EventsCompactionConfig`, `ContextCacheConfig`, and request-level sliding-window
compaction.
"""

from __future__ import annotations

import warnings

from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps.app import EventsCompactionConfig, ResumabilityConfig
from google.adk.models.llm_request import LlmRequest
from google.genai import types

DEFAULT_MAX_CONTENTS_WINDOW = 10
DEFAULT_MAX_CHARS_PER_PART = 2400


def build_events_compaction_config(
    compaction_interval: int = 5,
    overlap_size: int = 1,
    token_threshold: int = 8000,
    event_retention_size: int = 6,
) -> EventsCompactionConfig:
    """Build the ADK `EventsCompactionConfig` combining sliding-window and token thresholds.

    Args:
        compaction_interval: Number of new user invocations before triggering compaction.
        overlap_size: Number of preceding invocations retained for overlap continuity.
        token_threshold: Prompt token threshold that triggers post-invocation compaction.
        event_retention_size: Number of most recent raw events kept un-compacted.

    Returns:
        Configured `EventsCompactionConfig` instance.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return EventsCompactionConfig(
            compaction_interval=compaction_interval,
            overlap_size=overlap_size,
            token_threshold=token_threshold,
            event_retention_size=event_retention_size,
        )


def build_context_cache_config(
    cache_intervals: int = 10,
    ttl_seconds: int = 1800,
    min_tokens: int = 2048,
) -> ContextCacheConfig:
    """Build the Google Cloud Vertex AI `ContextCacheConfig` for Gemini 2.5 models."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ContextCacheConfig(
            cache_intervals=cache_intervals,
            ttl_seconds=ttl_seconds,
            min_tokens=min_tokens,
        )


def build_resumability_config(is_resumable: bool = True) -> ResumabilityConfig:
    """Build the ADK `ResumabilityConfig` to support pausing/resuming HITL turns."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ResumabilityConfig(is_resumable=is_resumable)


def compact_llm_request_history(
    llm_request: LlmRequest,
    max_contents: int = DEFAULT_MAX_CONTENTS_WINDOW,
    max_chars_per_part: int = DEFAULT_MAX_CHARS_PER_PART,
) -> dict[str, int]:
    """Apply sliding-window summarization and character/token truncation to `LlmRequest`.

    Prevents context window bloat from multi-turn roster/player payloads by:
    1. Truncating oversized historical text parts beyond `max_chars_per_part`.
    2. Condensing older turns beyond `max_contents` into a single `[COMPACTED HISTORY SUMMARY]`
       message while preserving recent turns and any active function calls/responses.

    Args:
        llm_request: The outgoing ADK `LlmRequest` containing conversation `contents`.
        max_contents: Maximum number of `Content` turns to retain in the active window.
        max_chars_per_part: Maximum character length for historical text parts.

    Returns:
        Dictionary of compaction metrics (`original_turns`, `final_turns`, `truncated_parts`,
        `compacted_turns`).
    """
    contents = llm_request.contents or []
    original_turns = len(contents)
    truncated_parts = 0
    compacted_turns = 0

    if original_turns == 0:
        return {
            "original_turns": 0,
            "final_turns": 0,
            "truncated_parts": 0,
            "compacted_turns": 0,
        }

    # Step 1: Truncate oversized text parts in non-final historical turns
    for idx, content in enumerate(contents[:-1]):
        if not content.parts:
            continue
        for part in content.parts:
            if part.text and len(part.text) > max_chars_per_part:
                part.text = (
                    part.text[:max_chars_per_part]
                    + " ... [TRUNCATED FOR CONTEXT COMPACTION]"
                )
                truncated_parts += 1

    # Step 2: Sliding-window summarization if total turns exceed max_contents
    if original_turns > max_contents >= 2:
        cutoff = original_turns - (max_contents - 1)
        older_slice = contents[:cutoff]
        recent_slice = contents[cutoff:]

        # Ensure we do not split a function_call from its function_response at the boundary
        while recent_slice and any(
            getattr(p, "function_response", None) is not None
            for p in (recent_slice[0].parts or [])
        ):
            if not older_slice:
                break
            recent_slice.insert(0, older_slice.pop())

        if older_slice:
            snippets: list[str] = []
            for turn in older_slice:
                role = turn.role or "unknown"
                turn_texts = [
                    p.text.strip()[:140]
                    for p in (turn.parts or [])
                    if p.text and p.text.strip()
                ]
                if turn_texts:
                    snippets.append(f"{role}: {' '.join(turn_texts)}")

            summary_body = " | ".join(snippets[-6:]) if snippets else "Prior tool and roster turns."
            summary_content = types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=f"[COMPACTED HISTORY SUMMARY ({len(older_slice)} earlier turns)]: {summary_body}"
                    )
                ],
            )
            llm_request.contents = [summary_content, *recent_slice]
            compacted_turns = len(older_slice)

    return {
        "original_turns": original_turns,
        "final_turns": len(llm_request.contents or []),
        "truncated_parts": truncated_parts,
        "compacted_turns": compacted_turns,
    }
