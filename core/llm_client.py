"""Ollama LLM client wrapper using LangChain."""

import json
import re
from langchain_community.llms import Ollama

from config.settings import MODEL, OLLAMA_BASE_URL


class LLMClient:
    """Wrapper for Ollama LLM via LangChain."""

    def __init__(self, model: str = MODEL, base_url: str = OLLAMA_BASE_URL):
        self.llm = Ollama(model=model, base_url=base_url)
        self.model = model

    def generate(self, prompt: str) -> str:
        """Generate text response from prompt."""
        return self.llm.invoke(prompt)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown and extra text."""
        # Remove markdown code blocks if present
        text = text.strip()
        
        # Try to find JSON in the response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError as e:
                # Try to fix common issues
                json_str = json_match.group()
                # Remove trailing commas before ]
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    raise ValueError(f"Failed to parse JSON: {e}") from e
        raise ValueError("No JSON object found in response")

    def generate_json(self, prompt: str) -> dict:
        """Generate and parse JSON response. Raises ValueError on parse failure."""
        response = self.generate(prompt)
        return self._extract_json(response)
