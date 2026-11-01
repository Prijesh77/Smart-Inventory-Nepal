"""Import every model so Base.metadata knows all tables (needed by Alembic)."""

from app.models.catalog import Category, Product, Supplier
from app.models.forecasting import Forecast, ForecastRun, ModelEvaluation
from app.models.inventory import InventoryBalance, InventoryTransaction
from app.models.operations import AppSetting, ImportJob, SimulationRun
from app.models.purchasing import PurchaseOrder, PurchaseOrderItem
from app.models.recommendations import RecommendationRun, ReorderRecommendation
from app.models.sales import CalendarDay, DailySales
from app.models.users import User

__all__ = [
    "AppSetting", "CalendarDay", "Category", "DailySales", "Forecast", "ForecastRun", "ImportJob",
    "InventoryBalance", "InventoryTransaction", "ModelEvaluation", "Product", "PurchaseOrder",
    "PurchaseOrderItem", "RecommendationRun", "ReorderRecommendation", "SimulationRun", "Supplier", "User",
]
