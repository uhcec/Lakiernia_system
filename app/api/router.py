from fastapi import APIRouter, Depends

from app.api.routes.health import router as health_router
from app.audit.router import router as audit_router
from app.auth.dependencies import get_current_user
from app.auth.router import router as auth_router
from app.clients.router import router as clients_router
from app.employees.router import router as employees_router
from app.manager.router import router as manager_router
from app.paints.router import router as paints_router
from app.process.router import router as process_router
from app.work_orders.router import router as work_orders_router

_auth_dep = [Depends(get_current_user)]

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(audit_router, dependencies=_auth_dep)
api_router.include_router(clients_router, dependencies=_auth_dep)
api_router.include_router(employees_router, dependencies=_auth_dep)
api_router.include_router(manager_router, dependencies=_auth_dep)
api_router.include_router(paints_router, dependencies=_auth_dep)
api_router.include_router(process_router, dependencies=_auth_dep)
api_router.include_router(work_orders_router, dependencies=_auth_dep)