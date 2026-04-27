from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    auth,
    categories,
    expenses,
    receipts,
    stats,
    subscriptions,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(receipts.router, prefix="/receipts", tags=["receipts"])
api_router.include_router(
    subscriptions.router, prefix="/subscriptions", tags=["subscriptions"]
)
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
