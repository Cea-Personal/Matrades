from decimal import Decimal
from uuid import uuid4

from modules.prop_firms.models import PropRule, RuleSet
from modules.prop_firms.service import RuleSetService


def test_only_verified_rules_activate_and_history_remains():
    service = RuleSetService()
    item = service.save(
        RuleSet(
            program_id=uuid4(),
            version=1,
            rules=[PropRule(kind="drawdown", value=Decimal("8"), unit="percent")],
        )
    )
    active = service.activate(service.verify(item))
    assert active.status == "ACTIVE"
    assert item.id in service.items
