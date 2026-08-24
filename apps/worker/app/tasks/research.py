from apps.worker.app.celery_app import celery_app
from modules.analysis.daily_research import rank_session
from modules.analysis.models import RankedMarket


@celery_app.task(bind=True, autoretry_for=(RuntimeError,), retry_backoff=True, max_retries=3)
def daily_research(self, candidates: list[dict]) -> dict:
    state, selected = rank_session([RankedMarket.model_validate(x) for x in candidates])
    self.update_state(state="PROGRESS", meta={"progress": 100})
    return {"state": state, "selected": [x.model_dump(mode="json") for x in selected]}
