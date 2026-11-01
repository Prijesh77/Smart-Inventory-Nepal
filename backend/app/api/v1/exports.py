from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbSession
from app.services import exports as service
from app.services.purchasing import app_today

router = APIRouter(prefix="/exports", tags=["exports"])
Dataset = Literal["products", "inventory", "transactions", "recommendations", "purchase-orders", "forecast"]


@router.get("/{dataset}.csv", summary="Download a dataset as CSV (spreadsheet-safe)",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_csv(dataset: Dataset, db: DbSession, run_id: int | None = None) -> Response:
    content = service.export(db, dataset, run_id)
    filename = f"{dataset}_{app_today(db).isoformat()}.csv"
    # utf-8-sig adds a byte-order mark so Excel reads accents correctly.
    return Response(content=content.encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
