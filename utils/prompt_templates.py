"""LLM prompt templates for summarization and query analysis."""

SUMMARIZATION_PROMPT = """Analyze the following conversation and extract structured information.

Conversation:
{conversation}

Extract the following as valid JSON (no markdown, no extra text):
{{
  "user_profile": {{
    "preferences": ["list of user preferences mentioned"],
    "constraints": ["limitations or constraints"],
    "interests": ["user interests expressed"]
  }},
  "key_facts": ["important facts from the conversation"],
  "decisions": ["decisions made or agreed upon"],
  "open_questions": ["questions that remain unanswered"],
  "todos": ["action items or tasks to do"]
}}

Return ONLY valid JSON. No explanations before or after."""


QUERY_ANALYSIS_PROMPT = """Analyze the following user query in context.

IMPORTANT: All output (rewritten_query, clarifying_questions, needed_context_from_memory) MUST be in the SAME language as the user's query. If user writes in Vietnamese → respond in Vietnamese. If in English → respond in English. Never use a different language.
{language_hint}

User query: "{query}"

Recent conversation context:
{context}

Session memory (if any):
{memory}

Determine:
1. Is the query ambiguous? (multiple interpretations, vague references, missing context)
2. If ambiguous, provide a rewritten/clearer version
3. What context from session memory would help answer this?
4. If still unclear, suggest 1-3 clarifying questions
5. Confidence score (0.0-1.0) in understanding the query

Return ONLY valid JSON:
{{
  "is_ambiguous": true or false,
  "rewritten_query": "clearer version or null if not ambiguous",
  "needed_context_from_memory": ["relevant memory items"],
  "clarifying_questions": ["question 1", "question 2"] or [],
  "confidence_score": 0.0 to 1.0
}}

No markdown, no explanations. JSON only."""


CLARIFYING_QUESTIONS_PROMPT = """Based on the ambiguous query and context, generate 1-3 helpful clarifying questions.

IMPORTANT: All output MUST be in the SAME language as the user's query. Never use a different language.
Query: "{query}"
Context: {context}

Return a JSON array of strings: ["question1", "question2"]
Keep questions concise and relevant. Return [] if no questions needed."""
