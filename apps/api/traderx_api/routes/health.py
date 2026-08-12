from fastapi import APIRouter

router = APIRouter(tags=["Audit and Health"])


@router.get("/health", include_in_schema=True)
def health() -> dict[str, str]:
    return {"status": "ok"}
