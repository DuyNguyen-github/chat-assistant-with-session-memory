"""JSON file-based session storage."""

import json
import os
from pathlib import Path
from typing import Optional

from config.settings import STORAGE_DIR
from models.schemas import ConversationState, SessionSummary


def _ensure_storage_dir() -> Path:
    """Ensure storage directory exists."""
    path = Path(STORAGE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path(session_id: str) -> Path:
    """Get file path for session."""
    return _ensure_storage_dir() / f"{session_id}.json"


def save_session(state: ConversationState) -> str:
    """Save conversation state to JSON file. Returns path."""
    path = _session_path(state.session_id)
    # Convert to dict, handling Pydantic models
    data = state.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(path)


def load_session(session_id: str) -> Optional[ConversationState]:
    """Load conversation state from JSON file."""
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ConversationState.model_validate(data)


def save_summary(session_id: str, summary: SessionSummary) -> str:
    """Save session summary to separate JSON file."""
    path = _ensure_storage_dir() / f"{session_id}_summary.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    return str(path)
