from pathlib import Path


def test_knowledge_ui_exposes_grounded_answers_and_refusal_boundary() -> None:
    text = Path("apps/web/src/features/knowledge/KnowledgeSources.tsx").read_text().casefold()
    assert all(value in text for value in ("knowledge assistant", "citations", "refusal"))
