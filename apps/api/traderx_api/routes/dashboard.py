from fastapi import APIRouter, Depends

from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(tags=["Command Center"])


@router.get("/dashboard")
def dashboard(_: AuthenticationContext = Depends(authenticated_context)) -> dict[str, object]:
    return {
        "account": None,
        "risk": {
            "state": "LOCKDOWN",
            "capacity": 0,
            "reason_codes": ["NO_VERIFIED_ACCOUNT_SNAPSHOT"],
        },
        "active_markets": [],
        "opportunities": [],
        "critical_alerts": [],
        "integration_health": [],
    }
