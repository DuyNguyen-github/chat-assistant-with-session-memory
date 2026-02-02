"""Token estimation utilities using character-based approximation."""

from typing import List

from models.schemas import Message


def estimate_tokens(text: str) -> int:
    """Estimate token count: ~4 characters per token."""
    return len(text) // 4


def count_messages_tokens(messages: List[Message]) -> int:
    """Count total tokens across messages (including role overhead ~4 tokens)."""
    total = sum(
        estimate_tokens(f"{m.role}: {m.content}") + 4
        for m in messages
    )
    return total


def should_trigger_summarization(
    messages: List[Message],
    threshold: int = 10000
) -> bool:
    """Check if conversation exceeds token threshold."""
    return count_messages_tokens(messages) > threshold
