"""Query understanding pipeline with ambiguity detection and context augmentation."""

from typing import List, Optional

from core.llm_client import LLMClient
from models.schemas import Message, QueryUnderstanding, SessionSummary
from utils.prompt_templates import QUERY_ANALYSIS_PROMPT


class QueryUnderstander:
    """Analyzes user queries for ambiguity and augments context."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def _format_recent_context(self, messages: List[Message], max_messages: int = 6) -> str:
        """Format recent messages as context string."""
        recent = messages[-max_messages:] if len(messages) > max_messages else messages
        return "\n".join(f"{m.role}: {m.content}" for m in recent)

    def _format_memory(self, summary: Optional[SessionSummary]) -> str:
        """Format session summary as memory context."""
        if not summary:
            return "No session memory yet."
        parts = []
        if summary.user_profile.preferences:
            parts.append(f"Preferences: {', '.join(summary.user_profile.preferences)}")
        if summary.user_profile.constraints:
            parts.append(f"Constraints: {', '.join(summary.user_profile.constraints)}")
        if summary.user_profile.interests:
            parts.append(f"Interests: {', '.join(summary.user_profile.interests)}")
        if summary.key_facts:
            parts.append(f"Key facts: {', '.join(summary.key_facts)}")
        if summary.decisions:
            parts.append(f"Decisions: {', '.join(summary.decisions)}")
        if summary.open_questions:
            parts.append(f"Open questions: {', '.join(summary.open_questions)}")
        if summary.todos:
            parts.append(f"Todos: {', '.join(summary.todos)}")
        return "\n".join(parts) if parts else "No session memory yet."

    def _detect_language_hint(self, query: str) -> str:
        """Detect query language for explicit instruction to avoid wrong-language output."""
        sample = query[:200]
        # Vietnamese: có dấu tiếng Việt (àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ)
        vi_chars = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        if any(c in sample for c in vi_chars) or any("\u1e00" <= c <= "\u1eff" for c in sample):
            return "CRITICAL: The user wrote in VIETNAMESE. You MUST output rewritten_query and clarifying_questions ONLY in Vietnamese. Do NOT use Chinese (中文) or English for these fields."
        # Chinese: CJK characters
        if any("\u4e00" <= c <= "\u9fff" for c in sample):
            return "CRITICAL: The user wrote in CHINESE. You MUST output rewritten_query and clarifying_questions ONLY in Chinese."
        # Default: English
        return "CRITICAL: The user wrote in ENGLISH. You MUST output rewritten_query and clarifying_questions ONLY in English."

    def understand_query(
        self,
        query: str,
        recent_messages: List[Message],
        session_summary: Optional[SessionSummary] = None,
    ) -> QueryUnderstanding:
        """
        Full pipeline: detect ambiguity, rewrite, augment context, generate clarifying questions.
        """
        context = self._format_recent_context(recent_messages)
        memory = self._format_memory(session_summary)
        language_hint = self._detect_language_hint(query)

        prompt = QUERY_ANALYSIS_PROMPT.format(
            query=query,
            context=context or "(no recent messages)",
            memory=memory,
            language_hint=language_hint,
        )

        print("[QueryUnderstander] Analyzing query...")

        try:
            data = self.llm.generate_json(prompt)
        except ValueError as e:
            print(f"[QueryUnderstander] Parse error, using fallback: {e}")
            return QueryUnderstanding(
                original_query=query,
                is_ambiguous=False,
                final_augmented_context=context,
                confidence_score=0.5,
            )

        # Build augmented context from memory + recent
        needed = data.get("needed_context_from_memory", [])
        if isinstance(needed, str):
            needed = [needed] if needed else []
        memory_context = "\n".join(needed) if needed else memory
        final_context = f"Session memory:\n{memory_context}\n\nRecent conversation:\n{context}"

        clarifying = data.get("clarifying_questions", [])
        if isinstance(clarifying, str):
            clarifying = [clarifying] if clarifying else []

        result = QueryUnderstanding(
            original_query=query,
            is_ambiguous=data.get("is_ambiguous", False),
            rewritten_query=data.get("rewritten_query"),
            needed_context_from_memory=needed,
            clarifying_questions=clarifying,
            final_augmented_context=final_context,
            confidence_score=float(data.get("confidence_score", 0.5)),
        )

        print(f"[QueryUnderstander] is_ambiguous={result.is_ambiguous}, confidence={result.confidence_score}")
        if result.rewritten_query:
            print(f"[QueryUnderstander] Rewritten: {result.rewritten_query[:80]}...")
        if result.clarifying_questions:
            print(f"[QueryUnderstander] Clarifying questions: {result.clarifying_questions}")

        return result
