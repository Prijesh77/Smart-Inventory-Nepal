"""Allowed values for status and type columns."""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"          # everything, including users and settings
    MANAGER = "manager"      # products, stock, forecasts, approvals, draft orders
    VIEWER = "viewer"        # read-only


class TransactionType(str, enum.Enum):
    INITIAL = "initial"          # opening balance
    RECEIPT = "receipt"          # purchase order received
    SALE = "sale"                # customer sale
    ADJUSTMENT = "adjustment"    # count correction, damage, loss (reason required)
    RETURN = "return"            # customer return


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskCategory(str, enum.Enum):
    """Mirrors ml/inventory/recommend.py."""
    CRITICAL = "critical_stockout_risk"
    REORDER_SOON = "reorder_soon"
    HEALTHY = "healthy"
    EXCESS = "excess_inventory"
    INSUFFICIENT = "insufficient_data"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ORDERED = "ordered"      # added to a draft purchase order


class EvaluationPeriod(str, enum.Enum):
    VALIDATION = "validation"
    TEST = "test"
