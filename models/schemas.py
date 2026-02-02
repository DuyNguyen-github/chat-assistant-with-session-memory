"""Pydantic schemas for Chat Assistant."""

from pydantic import BaseModel
from typing import List, Optional


class Message(BaseModel):
    """Single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None


class UserProfile(BaseModel):
    """Extracted user profile from conversation."""
    preferences: List[str] = []
    constraints: List[str] = []
    interests: List[str] = []


class SessionSummary(BaseModel):
    """Summary of a conversation segment for memory compression."""
    user_profile: UserProfile
    key_facts: List[str] = []
    decisions: List[str] = []
    open_questions: List[str] = []
    todos: List[str] = []
    message_range_summarized: dict  # {"from": 0, "to": N}


class QueryUnderstanding(BaseModel):
    """Result of query analysis pipeline."""
    original_query: str
    is_ambiguous: bool
    rewritten_query: Optional[str] = None
    needed_context_from_memory: List[str] = []
    clarifying_questions: List[str] = []
    final_augmented_context: str = ""
    confidence_score: float = 0.5


class ConversationState(BaseModel):
    """Full conversation state with session memory."""
    session_id: str
    messages: List[Message] = []
    current_summary: Optional[SessionSummary] = None
    total_tokens: int = 0
    # Clarification state management
    awaiting_clarification: bool = False  # True when waiting for user to clarify ambiguous query
    pending_clarifying_questions: List[str] = []  # Questions to show user
    pending_original_query: Optional[str] = None  # Original query that was ambiguous
