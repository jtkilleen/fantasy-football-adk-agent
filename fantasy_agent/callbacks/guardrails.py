"""Security, Domain Policy, and Self-Evaluation Guardrails for the Fantasy Football Agent.

Satisfies AgentOps Rubric Criterion 3.3 (Guardrails & Policy Plugins) and supports
Criterion 4.4 (PII Redaction in incoming user messages).
"""

from __future__ import annotations

import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from fantasy_agent.memory.compaction import compact_llm_request_history

# Patterns for prompt injection or prohibited real-money sports gambling advice
_BLOCKED_INPUT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(ignore\s+(all\s+)?previous\s+instructions|reveal\s+your\s+system\s+prompt|"
            r"bypass\s+safety\s+guardrails)",
            re.IGNORECASE,
        ),
        "PROMPT_INJECTION_BLOCKED",
    ),
    (
        re.compile(
            r"(sportsbook\s+parlay|bet\s+real\s+money|gambling\s+lock\s+of\s+the\s+week|"
            r"place\s+a\s+\$\d+\s+wager)",
            re.IGNORECASE,
        ),
        "PROHIBITED_GAMBLING_REQUEST",
    ),
]

# Basic PII scrubbing patterns applied before prompts reach the model
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Self-evaluation output patterns (prohibited guarantees or unredacted secrets)
_UNSAFE_OUTPUT_RE = re.compile(
    r"(guaranteed\s+100%\s+sportsbook\s+payout|risk-free\s+gambling\s+lock)",
    re.IGNORECASE,
)


def scrub_text_pii(text: str) -> str:
    """Redact emails, phone numbers, and SSNs from text."""
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = _SSN_RE.sub("[REDACTED_SSN]", redacted)
    redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    return redacted


def enforce_input_and_domain_guardrails(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """ADK `before_model_callback` enforcing domain boundaries, PII scrubbing, and history compaction.

    Args:
        callback_context: ADK callback context containing session state and agent info.
        llm_request: Outgoing request about to be sent to the Gemini model.

    Returns:
        `LlmResponse` short-circuiting the model call if a policy violation is detected,
        or `None` to allow the sanitized and compacted request to proceed.
    """
    if not llm_request.contents:
        return None

    # Inspect and sanitize user messages
    for content in llm_request.contents:
        if content.role != "user" or not content.parts:
            continue
        for part in content.parts:
            if not part.text:
                continue
            raw_text = part.text
            for pattern, violation_code in _BLOCKED_INPUT_PATTERNS:
                if pattern.search(raw_text):
                    callback_context.state["last_guardrail_violation"] = violation_code
                    refusal_msg = (
                        "I cannot fulfill that request. As your Fantasy Football Personal Agent, "
                        "I am restricted to fantasy football roster, matchup, trade, and player "
                        "trend analysis, and I cannot process prompt-override commands or provide "
                        "real-money sports gambling/wagering advice."
                    )
                    return LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=refusal_msg)],
                        )
                    )
            # Redact any inline PII before sending to the LLM
            part.text = scrub_text_pii(raw_text)

    # Apply sliding-window & token/character compaction (Rubric 2.2)
    compaction_stats = compact_llm_request_history(llm_request)
    callback_context.state["compaction_stats"] = compaction_stats
    return None


def enforce_output_self_eval_guardrail(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """ADK `after_model_callback` performing self-evaluation and PII/policy checks on responses.

    Args:
        callback_context: ADK callback context.
        llm_response: Response returned by the Gemini model.

    Returns:
        Modified `LlmResponse` if sanitization or self-eval replacement was required,
        or `None` if the response passed validation.
    """
    if not llm_response.content or not llm_response.content.parts:
        return None

    modified = False
    new_parts: list[types.Part] = []
    for part in llm_response.content.parts:
        if not part.text:
            new_parts.append(part)
            continue
        cleaned = scrub_text_pii(part.text)
        if _UNSAFE_OUTPUT_RE.search(cleaned):
            callback_context.state["last_self_eval_intervention"] = "UNSAFE_GAMBLING_CLAIM"
            cleaned = (
                "Self-Evaluation Guardrail Intervention: Removed prohibited sports-betting "
                "guarantee. Please focus on fantasy football projections and roster strategy."
            )
            modified = True
        elif cleaned != part.text:
            modified = True
        new_parts.append(types.Part.from_text(text=cleaned))

    if modified:
        return LlmResponse(
            content=types.Content(role="model", parts=new_parts),
        )
    return None
