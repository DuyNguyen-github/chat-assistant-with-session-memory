"""
Chat Assistant - Gradio interface with session memory and query understanding.
"""

import uuid
from typing import List, Optional

import gradio as gr

from config.settings import MAX_TOKENS
from core.llm_client import LLMClient
from core.query_understander import QueryUnderstander
from core.session_manager import SessionManager
from models.schemas import ConversationState, Message


# Global state for the current session
_state: Optional[ConversationState] = None
_llm: LLMClient | None = None
_session_mgr: SessionManager | None = None
_query_understander: QueryUnderstander | None = None


def _ensure_state() -> ConversationState:
    """Ensure we have a valid conversation state."""
    global _state, _llm, _session_mgr, _query_understander
    if _llm is None:
        _llm = LLMClient()
    if _session_mgr is None:
        _session_mgr = SessionManager(llm_client=_llm)
    if _query_understander is None:
        _query_understander = QueryUnderstander(llm_client=_llm)
    if _state is None:
        _state = ConversationState(session_id=str(uuid.uuid4()))
    return _state


def _format_history(state: ConversationState) -> List[dict]:
    """Convert ConversationState messages to Gradio Chatbot format.
    Gradio expects: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    """
    result = []
    for m in state.messages:
        if m.role in ("user", "assistant"):
            result.append({"role": m.role, "content": m.content})
    return result

def _build_clarifying_response(clarifying_questions: list, user_msg: str) -> str:
    """Build assistant message asking user to clarify (like ChatGPT)."""
    is_vi = any(c in "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ" for c in user_msg[:100])
    if is_vi:
        intro = "Để tôi trả lời chính xác hơn, bạn có thể làm rõ giúp tôi:\n\n"
        outro = "\n\nVui lòng cung cấp thêm thông tin để tôi có thể hỗ trợ bạn tốt hơn."
    else:
        intro = "To help me answer more accurately, could you please clarify:\n\n"
        outro = "\n\nPlease provide more details so I can better assist you."
    lines = [f"{i+1}. {q}" for i, q in enumerate(clarifying_questions)]
    return intro + "\n".join(lines) + outro

def _get_chat_prompt(state: ConversationState, user_msg: str, query_result) -> str:
    """Build prompt for chat response including context."""
    ctx = query_result.final_augmented_context if query_result else ""
    history = "\n".join(
        f"{m.role}: {m.content}"
        for m in state.messages[-8:]
        if m.role in ("user", "assistant")
    )
    prompt = f"""You are a helpful chat assistant. Respond in the same language as the user, never mix languages. Use the context below to respond.

{ctx}

Recent conversation:
{history}

User: {user_msg}
Assistant:"""
    return prompt


def chat(message: str, history: list) -> tuple[list, str]:
    """Handle user message and generate assistant response."""
    if not message.strip():
        return history, "Please enter a message."

    state = _ensure_state()

    # Check if we're waiting for clarification from user
    if state.awaiting_clarification:
        print(f"[App] User provided clarification input: {message[:100]}...")
        # Reset clarification state and add the clarification as a regular user message
        state.awaiting_clarification = False
        pending_queries = state.pending_clarifying_questions
        state.pending_clarifying_questions = []
        original_query = state.pending_original_query
        state.pending_original_query = None
        
        # Add clarification message
        _session_mgr.add_message(state, "user", message)
        
        # Create a combined query: original + user's clarification
        combined_query = f"Original question: {original_query}\n\nClarification/feedback: {message}"
        
        # Now understand this combined query (should be less ambiguous)
        recent = [m for m in state.messages if m.role in ("user", "assistant")][-10:]
        query_result = _query_understander.understand_query(
            query=combined_query,
            recent_messages=recent,
            session_summary=state.current_summary,
        )
    else:
        # Normal flow: add user message and analyze it
        _session_mgr.add_message(state, "user", message)

        # Query understanding pipeline
        recent = [m for m in state.messages if m.role in ("user", "assistant")][-10:]
        query_result = _query_understander.understand_query(
            query=message,
            recent_messages=recent,
            session_summary=state.current_summary,
        )

        # If query is ambiguous, ask for clarification instead of responding
        if query_result.is_ambiguous and query_result.clarifying_questions:
            print(f"[App] Query is ambiguous. Asking for clarification...")
            state.awaiting_clarification = True
            state.pending_clarifying_questions = query_result.clarifying_questions
            state.pending_original_query = message
            
            # Build clarifying response
            clarifying_msg = _build_clarifying_response(
                query_result.clarifying_questions,
                message
            )
            _session_mgr.add_message(state, "assistant", clarifying_msg)
            
            # Build status
            status_parts = [
                f"Session: {state.session_id[:8]}...",
                f"Messages: {len(state.messages)}",
                f"Tokens: ~{state.total_tokens}",
                "Status: Awaiting clarification",
            ]
            if state.current_summary:
                status_parts.append("Summary: active")
            
            new_history = _format_history(state)
            status = " | ".join(status_parts)
            return new_history, status

    # Build response prompt
    prompt = _get_chat_prompt(state, message, query_result)

    # Generate response
    print("[App] Generating response...")
    try:
        response = _llm.generate(prompt)
    except Exception as e:
        response = f"Error generating response: {e}"
        print(f"[App] LLM error: {e}")

    # Add assistant message
    _session_mgr.add_message(state, "assistant", response)

    # Build status with query understanding info
    status_parts = [
        f"Session: {state.session_id[:8]}...",
        f"Messages: {len(state.messages)}",
        f"Tokens: ~{state.total_tokens}",
    ]
    if query_result.is_ambiguous and not state.awaiting_clarification:
        status_parts.append("Query was ambiguous (clarified & responded)")
    if state.current_summary:
        status_parts.append("Summary: active")

    new_history = _format_history(state)
    status = " | ".join(status_parts)
    return new_history, status


def new_session() -> tuple[list, str]:
    """Start a new conversation session."""
    global _state
    _state = ConversationState(session_id=str(uuid.uuid4()))
    print(f"[App] New session: {_state.session_id}")
    return [], f"New session started. ID: {_state.session_id[:8]}..."


def load_test_data(filename: str) -> tuple[list, str]:
    """Load test conversation from JSONL file."""
    import json
    from pathlib import Path

    path = Path("test_data") / filename
    if not path.exists():
        return [], f"File not found: {path}"

    state = _ensure_state()
    state.messages.clear()
    state.current_summary = None
    state.total_tokens = 0

    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                role = obj.get("role", "user")
                content = obj.get("content", "")
                _session_mgr.add_message(state, role, content)
                count += 1
            except json.JSONDecodeError as e:
                print(f"[App] Parse error: {e}")

    history = _format_history(state)
    status = f"Loaded {count} messages. Tokens: ~{state.total_tokens}. "
    if state.current_summary:
        status += "Summarization was triggered."
    return history, status


def build_ui():
    """Build Gradio interface."""
    with gr.Blocks(title="Chat Assistant", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# Chat Assistant with Session Memory")
        gr.Markdown(
            "Uses Qwen2.5 via Ollama. Features: automatic summarization (~3k tokens), "
            "query understanding, clarifying questions."
        )

        with gr.Row():
            chatbot = gr.Chatbot(label="Conversation", height=400)
            with gr.Column(scale=1):
                msg = gr.Textbox(
                    label="Your Message",
                    placeholder="Type your message...",
                    lines=2,
                )
                with gr.Row():
                    submit_btn = gr.Button("Send", variant="primary")
                    new_session_btn = gr.Button("New Session")

        with gr.Row():
            load_test_btn = gr.Button("Load Test Data")
            test_file = gr.Dropdown(
                choices=[
                    "demo-flow1.jsonl",
                    "demo-flow2.jsonl"
                ],
                value="demo-flow1.jsonl",
                label="Test file",
            )
        status = gr.Textbox(label="Status", interactive=False)
        pending_msg = gr.State(value="")

        def show_user_immediately(msg_text, hist, _pending):
            """Show user's message immediately."""
            if not msg_text.strip():
                return hist, "Please enter a message.", _pending, ""
            new_hist = hist + [
                {"role": "user", "content": msg_text},
                {"role": "assistant", "content": "Loading..."},
            ]
            return new_hist, "Processing...", msg_text, ""

        def generate_response(hist, _status, msg_text, _):
            """Generate response and update chatbot."""
            if not msg_text:
                return hist, _status
            new_hist, new_status = chat(msg_text, hist)
            return new_hist, new_status

        submit_fn = lambda msg_text, hist, pend: show_user_immediately(msg_text, hist, pend)
        msg.submit(
            submit_fn,
            [msg, chatbot, pending_msg],
            [chatbot, status, pending_msg, msg],
        ).then(
            generate_response,
            [chatbot, status, pending_msg, msg],
            [chatbot, status],
        )
        submit_btn.click(
            submit_fn,
            [msg, chatbot, pending_msg],
            [chatbot, status, pending_msg, msg],
        ).then(
            generate_response,
            [chatbot, status, pending_msg, msg],
            [chatbot, status],
        )

        new_session_btn.click(new_session, outputs=[chatbot, status])

        load_test_btn.click(
            lambda f: load_test_data(f),
            inputs=[test_file],
            outputs=[chatbot, status],
        )

    return demo


if __name__ == "__main__":
    demo = build_ui()
    print("Starting Chat Assistant. Ensure Ollama is running with qwen2.5:latest.")
    demo.launch()
