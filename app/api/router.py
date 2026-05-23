from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.manager.router import router as manager_router
from app.work_orders.router import router as work_orders_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(manager_router)
api_router.include_router(work_orders_router)