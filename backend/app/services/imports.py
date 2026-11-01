"""Sales CSV import: validate every row, preview, then import all-or-nothing.

Rules
  - Columns are mapped by name (defaults: sku, date, units, unit_price).
  - Every row is checked: known SKU, date as YYYY-MM-DD, whole units >= 0,
    optional price >= 0, no duplicate (SKU, date) within the file.
  - If ANY row is invalid, NOTHING is imported; the job is recorded as failed
    with row-by-row errors. Invalid records are never silently skipped.
  - Valid files: new (product, date) rows are added; existing ones are
    replaced, and the counts say how many of each.
  - Imported sales are demand history only; they do not change stock levels.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import insert, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import CalendarDay, DailySales, ImportJob, Product, User
from app.models.enums import RunStatus

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 200_000
MAX_REPORTED_ERRORS = 200
PREVIEW_ROWS = 20


@dataclass
class Mapping:
    sku: str = "sku"
    date: str = "date"
    units: str = "units"
    unit_price: str | None = "unit_price"


@dataclass
class Parsed:
    rows: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total: int = 0
    error_count: int = 0
    invalid_lines: set[int] = field(default_factory=set)   # one row can have several errors

    @property
    def invalid_rows(self) -> int:
        return len(self.invalid_lines)

    def error(self, line: int, column: str, message: str) -> None:
        self.error_count += 1
        self.invalid_lines.add(line)
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append({"row": line, "column": column, "message": message})


def decode(content: bytes) -> str:
    if len(content) > MAX_BYTES:
        raise AppError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not content.strip():
        raise AppError("File is empty")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError("File is not UTF-8 text; save it as 'CSV UTF-8' and try again") from None


def parse(db: Session, content: bytes, mapping: Mapping) -> Parsed:
    reader = csv.DictReader(io.StringIO(decode(content)))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    wanted = {"sku": mapping.sku, "date": mapping.date, "units": mapping.units}
    missing = [f"{role} -> '{col}'" for role, col in wanted.items() if col not in headers]
    price_col = mapping.unit_price if mapping.unit_price in headers else None
    if mapping.unit_price and mapping.unit_price != "unit_price" and price_col is None:
        missing.append(f"unit_price -> '{mapping.unit_price}'")
    if missing:
        raise AppError(f"Missing column(s): {', '.join(missing)}. File columns: {', '.join(headers) or 'none'}")

    product_of = dict(db.execute(select(Product.sku, Product.id)).all())
    result, seen = Parsed(), set()
    for line, raw in enumerate(reader, start=2):          # line 1 is the header
        result.total += 1
        if result.total > MAX_ROWS:
            raise AppError(f"Too many rows (limit {MAX_ROWS:,}); split the file")
        ok = True
        sku = (raw.get(mapping.sku) or "").strip().upper()
        product_id = product_of.get(sku)
        if not sku:
            result.error(line, mapping.sku, "SKU is empty"); ok = False
        elif product_id is None:
            result.error(line, mapping.sku, f"Unknown SKU '{sku}' (create the product first)"); ok = False
        try:
            day = date.fromisoformat((raw.get(mapping.date) or "").strip())
        except ValueError:
            result.error(line, mapping.date, f"Date '{raw.get(mapping.date)}' is not YYYY-MM-DD"); ok = False
            day = None
        units_text = (raw.get(mapping.units) or "").strip()
        units = int(units_text) if units_text.isdigit() else None
        if units is None:
            result.error(line, mapping.units, f"Units '{units_text}' must be a whole number >= 0"); ok = False
        price = None
        if price_col and (raw.get(price_col) or "").strip():
            try:
                price = Decimal(raw[price_col].strip())
                if price < 0 or price > Decimal("1000000") or price.as_tuple().exponent < -2:
                    raise InvalidOperation
            except InvalidOperation:
                result.error(line, price_col, f"Price '{raw[price_col]}' must be >= 0 with at most 2 decimals")
                ok = False
        if ok:
            key = (product_id, day)
            if key in seen:
                result.error(line, mapping.date, f"Duplicate row for {sku} on {day}"); continue
            seen.add(key)
            result.rows.append({"product_id": product_id, "sku": sku, "sales_date": day, "units": units,
                                "unit_price": price})
    if result.total == 0:
        raise AppError("The file has a header but no data rows")
    return result


def _existing_keys(db: Session, rows: list[dict]) -> set[tuple[int, date]]:
    keys = {(r["product_id"], r["sales_date"]) for r in rows}
    found: set[tuple[int, date]] = set()
    key_list = list(keys)
    for start in range(0, len(key_list), 1000):
        chunk = key_list[start:start + 1000]
        found.update(db.execute(select(DailySales.product_id, DailySales.sales_date)
                                .where(tuple_(DailySales.product_id, DailySales.sales_date).in_(chunk))).all())
    return found


def preview(db: Session, content: bytes, mapping: Mapping) -> dict:
    parsed = parse(db, content, mapping)
    existing = _existing_keys(db, parsed.rows) if parsed.rows else set()
    return {
        "rows_total": parsed.total, "rows_valid": len(parsed.rows), "rows_invalid": parsed.invalid_rows,
        "would_add": len(parsed.rows) - len(existing), "would_replace": len(existing),
        "errors": parsed.errors, "errors_truncated": parsed.error_count > len(parsed.errors),
        "preview": [{k: v for k, v in r.items() if k != "product_id"} for r in parsed.rows[:PREVIEW_ROWS]],
        "can_import": parsed.error_count == 0,
    }


def commit(db: Session, content: bytes, mapping: Mapping, filename: str, user: User) -> ImportJob:
    parsed = parse(db, content, mapping)
    job = ImportJob(filename=filename[:255], import_type="sales", rows_total=parsed.total,
                    rows_valid=len(parsed.rows), rows_invalid=parsed.invalid_rows, created_by=user.id,
                    errors={"errors": parsed.errors, "truncated": parsed.error_count > len(parsed.errors)})
    if parsed.error_count:
        job.status = RunStatus.FAILED            # recorded, but no sales rows are written
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    existing = _existing_keys(db, parsed.rows)
    days_needed = {r["sales_date"] for r in parsed.rows}
    known_days = set(db.scalars(select(CalendarDay.day).where(CalendarDay.day.in_(days_needed))))
    calendar = {d: c for d, c in db.execute(select(CalendarDay.day, CalendarDay.is_store_open)
                                            .where(CalendarDay.day.in_(days_needed)))}
    new_days = [{"day": d, "is_store_open": not (d.month == 12 and d.day == 25)} for d in days_needed - known_days]
    try:
        if new_days:
            db.execute(insert(CalendarDay), new_days)
            calendar.update({d["day"]: d["is_store_open"] for d in new_days})
        to_add = [r for r in parsed.rows if (r["product_id"], r["sales_date"]) not in existing]
        if to_add:
            db.execute(insert(DailySales), [
                {"product_id": r["product_id"], "sales_date": r["sales_date"], "units": r["units"],
                 "unit_price": r["unit_price"], "is_available": calendar[r["sales_date"]]} for r in to_add])
        for r in parsed.rows:
            if (r["product_id"], r["sales_date"]) in existing:
                row = db.get(DailySales, (r["product_id"], r["sales_date"]))
                row.units = r["units"]
                if r["unit_price"] is not None:
                    row.unit_price = r["unit_price"]
        job.status = RunStatus.COMPLETED
        job.errors = {"errors": [], "added": len(to_add), "replaced": len(parsed.rows) - len(to_add),
                      "calendar_days_added": len(new_days)}
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(job)
    return job


def list_jobs(db: Session, limit: int = 50) -> list[ImportJob]:
    return list(db.scalars(select(ImportJob).order_by(ImportJob.id.desc()).limit(limit)))
