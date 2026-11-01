"""Version 1 of the REST API, mounted under /api/v1.

Access rules:
  /health, /auth/login                        public
  every GET (read, export)                    any logged-in user (viewer, manager, admin)
  changes: products, stock, forecasts,
    recommendations, orders, imports,
    simulations                               manager or admin
  /users, PUT /settings/policy                admin only
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import (
    auth, dashboard, exports, forecasts, health, imports, inventory, products, purchase_orders, recommendations,
    reference, settings, simulations, users,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
# Everything below needs a valid login; individual write endpoints add role checks.
protected = [Depends(get_current_user)]
for module in (dashboard, products, reference, inventory, forecasts, recommendations, purchase_orders,
               imports, exports, simulations, settings):
    router.include_router(module.router, dependencies=protected)
