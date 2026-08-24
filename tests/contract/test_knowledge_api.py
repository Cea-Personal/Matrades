from uuid import uuid4

from modules.knowledge.models import KnowledgeSource, SourceState


def test_source_lifecycle_is_versionable():
    item = KnowledgeSource(owner_id=uuid4(), name="playbook")
    disabled = item.model_copy(update={"state": SourceState.DISABLED, "version": 2})
    assert item.state == SourceState.ACTIVE
    assert disabled.version == 2
