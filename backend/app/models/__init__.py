"""Import every model so Base.metadata knows all tables (needed by Alembic)."""

import app.db.tenancy  # noqa: F401  (registers the per-shop query filter)

from app.models.catalog import Category, Product, Supplier
from app.models.forecasting import Forecast, ForecastRun, ModelEvaluation
from app.models.inventory import InventoryBalance, InventoryTransaction
from app.models.operations import AppSetting, ImportJob
from app.models.purchasing import PurchaseOrder, PurchaseOrderItem
from app.models.recommendations import RecommendationRun, ReorderRecommendation
from app.models.sales import CalendarDay, DailySales
from app.models.shops import Shop
from app.models.users import User

__all__ = [
    "AppSetting", "CalendarDay", "Category", "DailySales", "Forecast", "ForecastRun", "ImportJob",
    "InventoryBalance", "InventoryTransaction", "ModelEvaluation", "Product", "PurchaseOrder",
    "PurchaseOrderItem", "RecommendationRun", "ReorderRecommendation", "Shop", "Supplier", "User",
]
