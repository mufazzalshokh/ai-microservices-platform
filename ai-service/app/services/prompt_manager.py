from __future__ import annotations

from shared.exceptions import NotFoundError
from shared.logging import get_logger

logger = get_logger(__name__)

# ── Built-in prompt templates ─────────────────────────────────────────────────
# In production these would live in a DB or config file.
# Keeping them here shows interviewers you think about prompt management.

_TEMPLATES: dict[str, dict[str, str]] = {
    "summarize": {
        "name": "summarize",
        "description": "Summarize a piece of text concisely",
        "template": (
            "You are a professional summarizer. "
            "Summarize the following text in a clear and concise way:\n\n{text}"
        ),
    },
    "qa": {
        "name": "qa",
        "description": "Answer a question based on provided context",
        "template": (
            "You are a helpful assistant. "
            "Use only the provided context to answer the question. "
            "If the answer is not in the context, say so.\n\n"
            "Context:\n{context}\n\n"
            "Question: {question}"
        ),
    },
    "code_review": {
        "name": "code_review",
        "description": "Review code and suggest improvements",
        "template": (
            "You are a senior software engineer doing a code review. "
            "Review the following code and provide specific, actionable feedback "
            "on correctness, performance, security, and readability.\n\n"
            "Language: {language}\n\n"
            "Code:\n```{language}\n{code}\n```"
        ),
    },
    "explain": {
        "name": "explain",
        "description": "Explain a concept in simple terms",
        "template": (
            "You are an expert teacher. Explain the following concept "
            "in simple terms that a {audience} could understand:\n\n{concept}"
        ),
    },
}


class PromptManager:
    """
    Manages prompt templates with variable substitution.
    Demonstrates that you think about LLM prompt engineering as a
    first-class concern, not an afterthought.
    """

    def list_templates(self) -> list[dict[str, str]]:
        """Return all available templates (without the template string)."""
        return [
            {"name": t["name"], "description": t["description"]}
            for t in _TEMPLATES.values()
        ]

    def get_template(self, name: str) -> dict[str, str]:
        """Get a specific template by name."""
        if name not in _TEMPLATES:
            raise NotFoundError(f"Template '{name}'")
        return _TEMPLATES[name]

    def render(self, template_name: str, variables: dict[str, str]) -> str:
        """
        Render a template with variable substitution.
        Uses Python str.format_map so {variable} placeholders get replaced.
        Raises ValueError if required variables are missing.
        """
        template = self.get_template(template_name)
        try:
            rendered = template["template"].format_map(variables)
        except KeyError as exc:
            raise ValueError(
                f"Template '{template_name}' requires variable {exc} "
                f"but it was not provided"
            ) from exc

        logger.debug(
            "template_rendered",
            template=template_name,
            variables=list(variables.keys()),
        )
        return rendered
