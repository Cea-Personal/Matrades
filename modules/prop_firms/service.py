from modules.prop_firms.models import RuleSet, RuleStatus


class RuleSetService:
    def __init__(self):
        self.items = {}

    def save(self, item: RuleSet):
        self.items[item.id] = item
        return item

    def verify(self, item: RuleSet) -> RuleSet:
        if not item.rules:
            raise ValueError("ruleset cannot be empty")
        updated = item.model_copy(update={"status": RuleStatus.VERIFIED})
        self.items[item.id] = updated
        return updated

    def activate(self, item: RuleSet) -> RuleSet:
        if item.status != RuleStatus.VERIFIED:
            raise ValueError("only verified rulesets activate")
        for key, value in list(self.items.items()):
            if value.program_id == item.program_id and value.status == RuleStatus.ACTIVE:
                self.items[key] = value.model_copy(update={"status": RuleStatus.RETIRED})
        updated = item.model_copy(update={"status": RuleStatus.ACTIVE})
        self.items[item.id] = updated
        return updated
