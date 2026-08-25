from fastapi import APIRouter

from apps.api.app.routes.agents import router as agents_router
from apps.api.app.routes.auth import router as auth_router
from apps.api.app.routes.configuration import router as configuration_router
from apps.api.app.routes.events import router as events_router
from apps.api.app.routes.extras import router as extras_router
from apps.api.app.routes.knowledge import router as knowledge_router
from apps.api.app.routes.operations import router as operations_router
from apps.api.app.routes.research import router as research_router
from apps.api.app.routes.research_matrix import router as research_matrix_router
from apps.api.app.routes.risk import router as risk_router
from apps.api.app.routes.strategies import router as strategies_router
from apps.api.app.routes.trade_management import router as trade_management_router
from apps.api.app.routes.trade_proposals import router as trade_proposals_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(events_router)
api_router.include_router(extras_router)
api_router.include_router(risk_router)
api_router.include_router(trade_proposals_router)
api_router.include_router(research_router)
api_router.include_router(research_matrix_router)
api_router.include_router(trade_management_router)
api_router.include_router(strategies_router)
api_router.include_router(configuration_router)
api_router.include_router(agents_router)
api_router.include_router(knowledge_router)
api_router.include_router(operations_router)
