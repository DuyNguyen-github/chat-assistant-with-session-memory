"""Session management with automatic summarization."""

from datetime import datetime
from typing import List, Optional

from config.settings import MAX_TOKENS
from core.llm_client import LLMClient
from models.schemas import ConversationState, Message, SessionSummary, UserProfile
from storage.json_storage import save_session, save_summary
from utils.prompt_templates import SUMMARIZATION_PROMPT
from utils.token_counter import count_messages_tokens, estimate_tokens


def _effective_tokens_for_trigger(state: ConversationState, token_threshold: int) -> int:
    """Compute effective tokens: when we have a summary, count summary + messages since summary."""
    if not state.current_summary:
        return count_messages_tokens(state.messages)
    s = state.current_summary
    to_idx = s.message_range_summarized.get("to", -1)
    summary_str = (
        str(s.key_facts) + str(s.decisions) + str(s.user_profile.preferences) + str(s.user_profile.interests)
    )
    summary_tokens = estimate_tokens(summary_str)
    messages_after = state.messages[to_idx + 1:]
    return summary_tokens + count_messages_tokens(messages_after)


class SessionManager:
    """Manages conversation state and triggers summarization when needed."""

    def __init__(self, llm_client: Optional[LLMClient] = None, token_threshold: int = MAX_TOKENS):
        self.llm = llm_client or LLMClient()
        self.token_threshold = token_threshold

    def add_message(
        self,
        state: ConversationState,
        role: str,
        content: str
    ) -> ConversationState:
        """Add message and optionally trigger summarization. Keeps full chat history."""
        msg = Message(role=role, content=content, timestamp=datetime.now().isoformat())
        state.messages.append(msg)

        effective = _effective_tokens_for_trigger(state, self.token_threshold)
        state.total_tokens = effective

        if effective > self.token_threshold:
            print(f"[SessionManager] Token threshold exceeded ({effective} > {self.token_threshold})")
            self.trigger_summarization(state)
            state.total_tokens = _effective_tokens_for_trigger(state, self.token_threshold)

        return state

    def _format_conversation(self, messages: List[Message]) -> str:
        """Format messages for summarization prompt."""
        lines = []
        for i, m in enumerate(messages):
            lines.append(f"[{i}] {m.role}: {m.content}")
        return "\n".join(lines)

    def _parse_summary_response(self, data: dict, from_idx: int, to_idx: int) -> SessionSummary:
        """Parse LLM JSON response into SessionSummary."""
        def _ensure_list(val):
            if val is None:
                return []
            return list(val) if isinstance(val, (list, tuple)) else [val] if isinstance(val, str) else []

        user_profile_data = data.get("user_profile", {})
        if isinstance(user_profile_data, dict):
            user_profile = UserProfile(
                preferences=_ensure_list(user_profile_data.get("preferences")),
                constraints=_ensure_list(user_profile_data.get("constraints")),
                interests=_ensure_list(user_profile_data.get("interests")),
            )
        else:
            user_profile = UserProfile()

        key_facts = _ensure_list(data.get("key_facts"))
        decisions = _ensure_list(data.get("decisions"))
        open_questions = _ensure_list(data.get("open_questions"))
        todos = _ensure_list(data.get("todos"))

        return SessionSummary(
            user_profile=user_profile,
            key_facts=key_facts,
            decisions=decisions,
            open_questions=open_questions,
            todos=todos,
            message_range_summarized={"from": from_idx, "to": to_idx},
        )

    def trigger_summarization(self, state: ConversationState) -> Optional[SessionSummary]:
        """Summarize conversation. Keeps full message history; summary used for context augmentation."""
        messages = state.messages
        if not messages:
            return None

        from_idx = 0
        to_idx = len(messages) - 1

        # Merge with previous summary if exists
        prev_summary = ""
        if state.current_summary:
            s = state.current_summary
            prev_summary = (
                f"Previous summary - Key facts: {s.key_facts}; "
                f"Decisions: {s.decisions}; Open questions: {s.open_questions}"
            )

        conversation = self._format_conversation(messages)
        if prev_summary:
            conversation = f"{prev_summary}\n\n---\n\nCurrent conversation:\n{conversation}"

        prompt = SUMMARIZATION_PROMPT.format(conversation=conversation)
        print("[SessionManager] Triggering summarization...")

        try:
            data = self.llm.generate_json(prompt)
            summary = self._parse_summary_response(data, from_idx, to_idx)
            state.current_summary = summary

            # Save summary to JSON
            save_summary(state.session_id, summary)
            save_session(state)

            print("[SessionManager] Summary extracted:")
            print(f"  - Key facts: {summary.key_facts[:3]}...")
            print(f"  - Decisions: {summary.decisions[:3]}...")
            print(f"  - Range: {from_idx} to {to_idx}")
            print(f"[SessionManager] Full chat history preserved ({len(state.messages)} messages). "
                  "New responses will use summary + recent messages as context.")

            return summary
        except (ValueError, KeyError) as e:
            print(f"[SessionManager] Summarization failed: {e}")
            return None
