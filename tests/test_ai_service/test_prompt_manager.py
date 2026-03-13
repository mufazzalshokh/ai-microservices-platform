from __future__ import annotations

import pytest


def test_list_templates(prompt_manager):
    templates = prompt_manager.list_templates()
    assert len(templates) >= 4
    names = [t["name"] for t in templates]
    assert "summarize" in names
    assert "qa" in names
    assert "code_review" in names
    assert "explain" in names


def test_get_template(prompt_manager):
    t = prompt_manager.get_template("summarize")
    assert t["name"] == "summarize"
    assert "{text}" in t["template"]


def test_get_nonexistent_template(prompt_manager):
    from shared.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        prompt_manager.get_template("nonexistent")


def test_render_summarize(prompt_manager):
    result = prompt_manager.render("summarize", {"text": "Python is great."})
    assert "Python is great." in result


def test_render_qa(prompt_manager):
    result = prompt_manager.render(
        "qa",
        {"context": "The sky is blue.", "question": "What color is the sky?"},
    )
    assert "blue" in result
    assert "What color" in result


def test_render_missing_variable(prompt_manager):
    """Missing required variable must raise ValueError."""
    with pytest.raises(ValueError, match="requires variable"):
        prompt_manager.render("summarize", {})


def test_render_code_review(prompt_manager):
    result = prompt_manager.render(
        "code_review",
        {"language": "python", "code": "def foo(): pass"},
    )
    assert "python" in result
    assert "def foo" in result
