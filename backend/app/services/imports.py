"""Onboarding imports from Excel (.xlsx) or CSV: suppliers, products, opening stock and sales history.

Rules for every import type
  - The first sheet (Excel) or the file (CSV) has one header row; columns are
    matched by name, ignoring upper/lower case and spaces around names.
  - Every row is checked. If ANY row is invalid, NOTHING is imported; the job
    is recorded as failed with row-by-row errors. Rows are never silently skipped.
  - Two steps: preview (check only, nothing saved), then import.
  - Rows refer to this shop's data only (the shop filter in app/db/tenancy.py).

Suggested order for a new shop: suppliers -> products -> opening stock -> sales.
  suppliers      add new codes, update existing ones
  products       add new SKUs (stock 0), update existing ones; new categories are created by name
  opening_stock  starting stock for products that have no stock movements yet ('initial' audit rows)
  sales          daily sales history (feeds forecasts; does NOT change stock). Columns can be renamed
                 with a mapping; new (product, day) rows are added, existing ones replaced.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import insert, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.db.tenancy import current_shop_id
from app.models import (
    CalendarDay, Category, DailySales, ImportJob, InventoryBalance, InventoryTransaction, Product, Supplier, User,
)
from app.models.enums import RunStatus, TransactionType
from app.services.inventory import apply_movement

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 200_000
MAX_REPORTED_ERRORS = 200
PREVIEW_ROWS = 20
MAX_MONEY = Decimal("10000000")          # Rs 1 crore per unit is far above any shop item
SKU_PATTERN = re.compile(r"^[A-Z0-9_\-]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- what each import type expects

@dataclass(frozen=True)
class Column:
    name: str
    required: bool
    meaning: str
    examples: tuple[str, str]


IMPORT_TYPES: dict[str, dict] = {
    "suppliers": {
        "label": "Suppliers",
        "description": "Who you buy from and how many days delivery takes. Existing supplier codes are updated.",
        "columns": [
            Column("code", True, "Short unique code, e.g. KTM-GRAIN (letters, digits, - or _)", ("KTM-GRAIN", "HIM-FMCG")),
            Column("name", True, "Supplier name", ("Kathmandu Grain Traders", "Himalayan FMCG Distributors")),
            Column("lead_time_days", True, "Days from ordering to delivery (1-365)", ("3", "2")),
            Column("lead_time_sd_days", False, "How many days delivery usually varies by (0 if always on time)", ("1", "0.5")),
            Column("contact_email", False, "Email for orders", ("orders@example.com", "")),
        ],
    },
    "products": {
        "label": "Products",
        "description": "Your items with prices in rupees. Import suppliers first. Existing SKUs are updated; "
                       "new products start with 0 stock.",
        "columns": [
            Column("sku", True, "Your unique product code (letters, digits, - or _)", ("RICE-JEERA-5KG", "NOODLES-70G")),
            Column("name", True, "Product name", ("Jeera masino rice 5 kg", "Instant noodles 70 g")),
            Column("category", True, "Category name; a new name creates the category", ("Rice, dal & flour", "Snacks")),
            Column("supplier_code", False, "Code from the suppliers sheet (empty = no supplier)", ("KTM-GRAIN", "HIM-FMCG")),
            Column("unit_price", True, "Selling price in Rs", ("780", "25")),
            Column("unit_cost", False, "Buying price in Rs (needed for stock value and order cost)", ("705", "21.50")),
            Column("pack_size", False, "Units per pack or carton (default 1)", ("4", "30")),
            Column("min_order_qty", False, "Smallest quantity the supplier accepts (default 1)", ("4", "30")),
            Column("lead_time_days", False, "Only if different from the supplier's lead time", ("", "")),
        ],
    },
    "opening_stock": {
        "label": "Opening stock",
        "description": "How many units you have now, for products with no stock movements yet. "
                       "Later changes go through stock adjustments or received orders.",
        "columns": [
            Column("sku", True, "Product SKU (import products first)", ("RICE-JEERA-5KG", "NOODLES-70G")),
            Column("quantity", True, "Units on hand now (whole number, 0 or more)", ("12", "150")),
        ],
    },
    "sales": {
        "label": "Sales history",
        "description": "Units sold per product per day. Used for forecasts; does not change stock levels. "
                       "Existing days are replaced.",
        "columns": [
            Column("sku", True, "Product SKU", ("NOODLES-70G", "RICE-JEERA-5KG")),
            Column("date", True, "Day of the sale, YYYY-MM-DD (or an Excel date cell)", ("2026-10-31", "2026-10-31")),
            Column("units", True, "Units sold that day (whole number, 0 or more)", ("24", "2")),
            Column("unit_price", False, "Selling price that day in Rs", ("25", "")),
        ],
    },
}


@dataclass
class Mapping:
    """Sales only: which file column holds each field (defaults: the template's names)."""

    sku: str = "sku"
    date: str = "date"
    units: str = "units"
    unit_price: str | None = "unit_price"


# ---------------------------------------------------------------- reading the file

@dataclass
class Table:
    headers: list[str]
    rows: list[tuple[int, dict[str, str]]]   # (row number as shown in Excel / the CSV, values by lower-case header)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))                    # Excel stores 12 as 12.0
    return str(value).strip()


def _read_xlsx(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise AppError("The Excel file could not be opened; save it as .xlsx and try again") from None
    try:
        sheet = workbook.worksheets[0]
        lines = []
        for values in sheet.iter_rows(values_only=True):
            if len(lines) > MAX_ROWS + 1:
                raise AppError(f"Too many rows (limit {MAX_ROWS:,}); split the file")
            lines.append([_cell_text(v) for v in values])
        return lines
    finally:
        workbook.close()


def _read_csv(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError("File is not UTF-8 text; save it as 'CSV UTF-8' (or as Excel .xlsx) and try again") from None
    return [[v.strip() for v in line] for line in csv.reader(io.StringIO(text))]


def read_table(content: bytes, filename: str) -> Table:
    if len(content) > MAX_BYTES:
        raise AppError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not content.strip():
        raise AppError("File is empty")
    is_excel = filename.lower().endswith(".xlsx") or content[:4] == b"PK\x03\x04"
    lines = _read_xlsx(content) if is_excel else _read_csv(content)
    if not lines:
        raise AppError("File is empty")
    headers = [h.strip() for h in lines[0]]
    while headers and not headers[-1]:
        headers.pop()
    keys = [h.lower() for h in headers]
    rows = []
    for number, values in enumerate(lines[1:], start=2):     # row 1 is the header
        if not any(values):
            continue                                          # blank lines at the end of a sheet
        rows.append((number, {k: (values[i] if i < len(values) else "") for i, k in enumerate(keys) if k}))
        if len(rows) > MAX_ROWS:
            raise AppError(f"Too many rows (limit {MAX_ROWS:,}); split the file")
    if not rows:
        raise AppError("The file has a header but no data rows")
    return Table(headers=headers, rows=rows)


def _require_columns(table: Table, wanted: dict[str, str]) -> None:
    """wanted: field -> column name. Error lists the missing ones and the file's own columns."""
    present = {h.lower() for h in table.headers}
    missing = [f"{f} -> '{c}'" if f != c else f"'{c}'" for f, c in wanted.items() if c.lower() not in present]
    if missing:
        raise AppError(f"Missing column(s): {', '.join(missing)}. File columns: {', '.join(table.headers) or 'none'}")


# ---------------------------------------------------------------- checking values

@dataclass
class Parsed:
    rows: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total: int = 0
    error_count: int = 0
    invalid_lines: set[int] = field(default_factory=set)   # one row can have several errors
    would_replace: int = 0

    @property
    def invalid_rows(self) -> int:
        return len(self.invalid_lines)

    def error(self, line: int, column: str, message: str) -> None:
        self.error_count += 1
        self.invalid_lines.add(line)
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append({"row": line, "column": column, "message": message})


class _Row:
    """Reads one row's values, recording an error for each bad one."""

    def __init__(self, result: Parsed, line: int, values: dict[str, str]):
        self.result, self.line, self.values, self.ok = result, line, values, True

    def bad(self, column: str, message: str) -> None:
        self.result.error(self.line, column, message)
        self.ok = False

    def raw(self, column: str) -> str:
        return (self.values.get(column.lower()) or "").strip()

    def text(self, column: str, *, required: bool, max_length: int) -> str | None:
        value = self.raw(column)
        if not value:
            if required:
                self.bad(column, f"{column} is empty")
            return None
        if len(value) > max_length:
            self.bad(column, f"{column} is longer than {max_length} characters")
        return value

    def code(self, column: str, *, required: bool, max_length: int) -> str | None:
        value = self.text(column, required=required, max_length=max_length)
        if value is None:
            return None
        value = value.upper()
        if not SKU_PATTERN.match(value):
            self.bad(column, f"'{value}' may contain only letters, digits, '-' or '_'")
        return value

    def whole(self, column: str, *, required: bool, minimum: int, maximum: int | None = None,
              default: int | None = None) -> int | None:
        value = self.raw(column)
        if not value:
            if required:
                self.bad(column, f"{column} is empty")
            return default
        number = int(value[:-2]) if value.endswith(".0") and value[:-2].isdigit() else (
            int(value) if value.isdigit() else None)
        if number is None or number < minimum or (maximum is not None and number > maximum):
            limits = f">= {minimum}" if maximum is None else f"from {minimum} to {maximum}"
            self.bad(column, f"{column} '{value}' must be a whole number {limits}")
            return None
        return number

    def decimal(self, column: str, *, required: bool, maximum: Decimal = MAX_MONEY, places: int = 2,
                default: Decimal | None = None) -> Decimal | None:
        value = self.raw(column).replace(",", "")         # allow 1,250.50
        if not value:
            if required:
                self.bad(column, f"{column} is empty")
            return default
        try:
            number = Decimal(value)
            if not number.is_finite() or number < 0 or number > maximum or number.as_tuple().exponent < -places:
                raise InvalidOperation
        except InvalidOperation:
            self.bad(column, f"{column} '{value}' must be a number >= 0 with at most {places} decimals")
            return None
        return number

    def day(self, column: str) -> date | None:
        value = self.raw(column)
        try:
            return date.fromisoformat(value[:10] if len(value) > 10 and value[10] in " T" else value)
        except ValueError:
            self.bad(column, f"Date '{value}' is not YYYY-MM-DD")
            return None


def _duplicate(result: Parsed, seen: set, key, line: int, column: str, message: str) -> bool:
    if key in seen:
        result.error(line, column, message)
        return True
    seen.add(key)
    return False


# ---------------------------------------------------------------- suppliers

def _parse_suppliers(db: Session, table: Table, _mapping: Mapping) -> Parsed:
    _require_columns(table, {"code": "code", "name": "name", "lead_time_days": "lead_time_days"})
    existing = set(db.scalars(select(Supplier.code)))
    result, seen = Parsed(), set()
    for line, values in table.rows:
        result.total += 1
        row = _Row(result, line, values)
        code = row.code("code", required=True, max_length=30)
        name = row.text("name", required=True, max_length=120)
        lead = row.whole("lead_time_days", required=True, minimum=1, maximum=365)
        sd = row.decimal("lead_time_sd_days", required=False, maximum=Decimal("365"), default=Decimal("0"))
        email = row.text("contact_email", required=False, max_length=254)
        if email and not EMAIL_PATTERN.match(email):
            row.bad("contact_email", f"'{email}' is not an email address")
        if row.ok and not _duplicate(result, seen, code, line, "code", f"Supplier {code} appears twice"):
            result.rows.append({"code": code, "name": name, "lead_time_days": lead, "lead_time_sd_days": sd,
                                "contact_email": email or None, "exists": code in existing})
    result.would_replace = sum(r["exists"] for r in result.rows)
    return result


def _write_suppliers(db: Session, parsed: Parsed, _user: User, _filename: str) -> dict:
    by_code = {s.code: s for s in db.scalars(select(Supplier))}
    for r in parsed.rows:
        fields = {k: r[k] for k in ("name", "lead_time_days", "lead_time_sd_days", "contact_email")}
        if r["code"] in by_code:
            for key, value in fields.items():
                setattr(by_code[r["code"]], key, value)
        else:
            db.add(Supplier(code=r["code"], **fields))
    return {"added": len(parsed.rows) - parsed.would_replace, "replaced": parsed.would_replace}


# ---------------------------------------------------------------- products

def category_code(name: str) -> str:
    """'Rice, dal & flour' -> 'RICE_DAL_FLOUR' (max 30 characters)."""
    return (re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "CATEGORY")[:30].rstrip("_")


def _parse_products(db: Session, table: Table, _mapping: Mapping) -> Parsed:
    _require_columns(table, {"sku": "sku", "name": "name", "category": "category", "unit_price": "unit_price"})
    existing = set(db.scalars(select(Product.sku)))
    suppliers = dict(db.execute(select(Supplier.code, Supplier.id)).all())
    result, seen = Parsed(), set()
    for line, values in table.rows:
        result.total += 1
        row = _Row(result, line, values)
        sku = row.code("sku", required=True, max_length=50)
        name = row.text("name", required=True, max_length=200)
        category = row.text("category", required=True, max_length=100)
        supplier_code = row.code("supplier_code", required=False, max_length=30)
        if supplier_code and supplier_code not in suppliers:
            row.bad("supplier_code", f"Unknown supplier '{supplier_code}' (import suppliers first)")
        price = row.decimal("unit_price", required=True)
        cost = row.decimal("unit_cost", required=False)
        pack = row.whole("pack_size", required=False, minimum=1, maximum=100_000, default=1)
        moq = row.whole("min_order_qty", required=False, minimum=1, maximum=100_000, default=1)
        lead = row.whole("lead_time_days", required=False, minimum=1, maximum=365)
        if row.ok and not _duplicate(result, seen, sku, line, "sku", f"SKU {sku} appears twice"):
            result.rows.append({"sku": sku, "name": name, "category": category,
                                "supplier_id": suppliers.get(supplier_code) if supplier_code else None,
                                "supplier_code": supplier_code, "unit_price": price, "unit_cost": cost,
                                "pack_size": pack, "min_order_qty": moq, "lead_time_days": lead,
                                "exists": sku in existing})
    result.would_replace = sum(r["exists"] for r in result.rows)
    return result


def _category_ids(db: Session, names: set[str]) -> tuple[dict[str, int], int]:
    """Category id for each name (matched by name or code, ignoring case); missing ones are created."""
    by_key: dict[str, int] = {}
    for c in db.scalars(select(Category)):
        by_key[c.name.lower()] = c.id
        by_key[c.code.lower()] = c.id
    created = 0
    ids = {}
    for name in sorted(names):
        key = name.lower()
        if key not in by_key and category_code(name).lower() not in by_key:
            category = Category(code=category_code(name), name=name)
            db.add(category)
            db.flush()
            by_key[key] = by_key[category.code.lower()] = category.id
            created += 1
        ids[name] = by_key.get(key) or by_key[category_code(name).lower()]
    return ids, created


def _write_products(db: Session, parsed: Parsed, _user: User, _filename: str) -> dict:
    categories, created = _category_ids(db, {r["category"] for r in parsed.rows})
    by_sku = {p.sku: p for p in db.scalars(select(Product))}
    for r in parsed.rows:
        fields = {"name": r["name"], "category_id": categories[r["category"]], "supplier_id": r["supplier_id"],
                  "unit_price": r["unit_price"], "unit_cost": r["unit_cost"], "pack_size": r["pack_size"],
                  "min_order_qty": r["min_order_qty"], "lead_time_days": r["lead_time_days"]}
        if r["sku"] in by_sku:
            for key, value in fields.items():
                setattr(by_sku[r["sku"]], key, value)
        else:
            product = Product(sku=r["sku"], **fields)
            db.add(product)
            db.flush()
            db.add(InventoryBalance(product_id=product.id, on_hand=0, backorders=0))
    return {"added": len(parsed.rows) - parsed.would_replace, "replaced": parsed.would_replace,
            "categories_added": created}


# ---------------------------------------------------------------- opening stock

def _parse_opening_stock(db: Session, table: Table, _mapping: Mapping) -> Parsed:
    _require_columns(table, {"sku": "sku", "quantity": "quantity"})
    product_of = dict(db.execute(select(Product.sku, Product.id)).all())
    with_history = set(db.scalars(select(InventoryTransaction.product_id).distinct()))
    result, seen = Parsed(), set()
    for line, values in table.rows:
        result.total += 1
        row = _Row(result, line, values)
        sku = row.code("sku", required=True, max_length=50)
        product_id = product_of.get(sku) if sku else None
        if sku and product_id is None:
            row.bad("sku", f"Unknown SKU '{sku}' (import products first)")
        elif product_id in with_history:
            row.bad("sku", f"{sku} already has stock movements; change its stock with an adjustment instead")
        quantity = row.whole("quantity", required=True, minimum=0, maximum=10_000_000)
        if row.ok and not _duplicate(result, seen, sku, line, "sku", f"SKU {sku} appears twice"):
            result.rows.append({"sku": sku, "product_id": product_id, "quantity": quantity})
    return result


def _write_opening_stock(db: Session, parsed: Parsed, user: User, filename: str) -> dict:
    reason = f"Opening stock (imported from {filename[:120]})"
    for r in parsed.rows:
        if r["quantity"] > 0:
            apply_movement(db, product_id=r["product_id"], quantity=r["quantity"], txn_type=TransactionType.INITIAL,
                           reason=reason, user=user)
    return {"added": len(parsed.rows), "replaced": 0, "units": sum(r["quantity"] for r in parsed.rows)}


# ---------------------------------------------------------------- sales

def _parse_sales(db: Session, table: Table, mapping: Mapping) -> Parsed:
    wanted = {"sku": mapping.sku, "date": mapping.date, "units": mapping.units}
    if mapping.unit_price and mapping.unit_price != "unit_price":
        wanted["unit_price"] = mapping.unit_price               # a renamed price column must exist
    _require_columns(table, wanted)
    present = {h.lower() for h in table.headers}
    price_col = mapping.unit_price if mapping.unit_price and mapping.unit_price.lower() in present else None

    product_of = dict(db.execute(select(Product.sku, Product.id)).all())
    result, seen = Parsed(), set()
    for line, values in table.rows:
        result.total += 1
        row = _Row(result, line, values)
        sku = row.raw(mapping.sku).upper()
        product_id = product_of.get(sku)
        if not sku:
            row.bad(mapping.sku, "SKU is empty")
        elif product_id is None:
            row.bad(mapping.sku, f"Unknown SKU '{sku}' (create the product first)")
        day = row.day(mapping.date)
        units = row.whole(mapping.units, required=False, minimum=0)
        if units is None and row.ok:
            row.bad(mapping.units, f"Units '{row.raw(mapping.units)}' must be a whole number >= 0")
        price = row.decimal(price_col, required=False) if price_col else None
        if row.ok and not _duplicate(result, seen, (product_id, day), line, mapping.date,
                                     f"Duplicate row for {sku} on {day}"):
            result.rows.append({"product_id": product_id, "sku": sku, "sales_date": day, "units": units,
                                "unit_price": price})
    if result.rows:
        result.would_replace = len(_existing_sales(db, result.rows))
    return result


def _existing_sales(db: Session, rows: list[dict]) -> set[tuple[int, date]]:
    key_list = list({(r["product_id"], r["sales_date"]) for r in rows})
    found: set[tuple[int, date]] = set()
    for start in range(0, len(key_list), 1000):
        chunk = key_list[start:start + 1000]
        found.update(db.execute(select(DailySales.product_id, DailySales.sales_date)
                                .where(tuple_(DailySales.product_id, DailySales.sales_date).in_(chunk))).all())
    return found


def _write_sales(db: Session, parsed: Parsed, _user: User, _filename: str) -> dict:
    existing = _existing_sales(db, parsed.rows)
    days_needed = {r["sales_date"] for r in parsed.rows}
    calendar = dict(db.execute(select(CalendarDay.day, CalendarDay.is_store_open)
                               .where(CalendarDay.day.in_(days_needed))).all())
    new_days = [{"day": d, "is_store_open": True} for d in sorted(days_needed - set(calendar))]
    if new_days:
        db.execute(insert(CalendarDay), new_days)
        calendar.update({d["day"]: True for d in new_days})
    shop_id = current_shop_id(db)
    to_add = [r for r in parsed.rows if (r["product_id"], r["sales_date"]) not in existing]
    for start in range(0, len(to_add), 20_000):
        db.execute(insert(DailySales), [
            {"shop_id": shop_id, "product_id": r["product_id"], "sales_date": r["sales_date"], "units": r["units"],
             "unit_price": r["unit_price"], "is_available": calendar[r["sales_date"]]}
            for r in to_add[start:start + 20_000]])
    for r in parsed.rows:
        if (r["product_id"], r["sales_date"]) in existing:
            row = db.get(DailySales, (r["product_id"], r["sales_date"]))
            row.units = r["units"]
            if r["unit_price"] is not None:
                row.unit_price = r["unit_price"]
    return {"added": len(to_add), "replaced": len(parsed.rows) - len(to_add), "calendar_days_added": len(new_days)}


# ---------------------------------------------------------------- the two steps

Parser = Callable[[Session, Table, Mapping], Parsed]
Writer = Callable[[Session, Parsed, User, str], dict]
HANDLERS: dict[str, tuple[Parser, Writer]] = {
    "suppliers": (_parse_suppliers, _write_suppliers),
    "products": (_parse_products, _write_products),
    "opening_stock": (_parse_opening_stock, _write_opening_stock),
    "sales": (_parse_sales, _write_sales),
}
PREVIEW_HIDDEN = {"product_id", "supplier_id", "exists"}


def _handlers(import_type: str) -> tuple[Parser, Writer]:
    if import_type not in HANDLERS:
        raise NotFoundError(f"Unknown import type '{import_type}'. Choose from: {', '.join(HANDLERS)}")
    return HANDLERS[import_type]


def parse(db: Session, import_type: str, content: bytes, filename: str, mapping: Mapping | None = None) -> Parsed:
    parser, _ = _handlers(import_type)
    return parser(db, read_table(content, filename), mapping or Mapping())


def preview(db: Session, import_type: str, content: bytes, filename: str, mapping: Mapping | None = None) -> dict:
    parsed = parse(db, import_type, content, filename, mapping)
    return {
        "import_type": import_type,
        "rows_total": parsed.total, "rows_valid": len(parsed.rows), "rows_invalid": parsed.invalid_rows,
        "would_add": len(parsed.rows) - parsed.would_replace, "would_replace": parsed.would_replace,
        "errors": parsed.errors, "errors_truncated": parsed.error_count > len(parsed.errors),
        "preview": [{k: v for k, v in r.items() if k not in PREVIEW_HIDDEN} for r in parsed.rows[:PREVIEW_ROWS]],
        "can_import": parsed.error_count == 0,
    }


def commit(db: Session, import_type: str, content: bytes, filename: str, user: User,
           mapping: Mapping | None = None) -> ImportJob:
    _, writer = _handlers(import_type)
    parsed = parse(db, import_type, content, filename, mapping)
    job = ImportJob(filename=filename[:255], import_type=import_type, rows_total=parsed.total,
                    rows_valid=len(parsed.rows), rows_invalid=parsed.invalid_rows, created_by=user.id,
                    errors={"errors": parsed.errors, "truncated": parsed.error_count > len(parsed.errors)})
    if parsed.error_count:
        job.status = RunStatus.FAILED            # recorded, but nothing is written
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    try:
        counts = writer(db, parsed, user, filename)
        job.status = RunStatus.COMPLETED
        job.errors = {"errors": [], **counts}
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(job)
    return job


def list_jobs(db: Session, limit: int = 50) -> list[ImportJob]:
    return list(db.scalars(select(ImportJob).order_by(ImportJob.id.desc()).limit(limit)))


# ---------------------------------------------------------------- templates

def template_xlsx(import_type: str) -> bytes:
    """An Excel file with the right column names, two example rows, and an Instructions sheet."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    if import_type not in IMPORT_TYPES:
        raise NotFoundError(f"Unknown import type '{import_type}'")
    spec = IMPORT_TYPES[import_type]
    workbook = Workbook()
    data = workbook.active
    data.title = spec["label"][:31]
    data.append([c.name for c in spec["columns"]])
    for i in range(2):
        data.append([c.examples[i] for c in spec["columns"]])
    for cell in data[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E0F2FE")
    for column, spec_col in zip(data.columns, spec["columns"]):
        data.column_dimensions[column[0].column_letter].width = max(14, len(spec_col.name) + 4,
                                                                    *(len(e) + 2 for e in spec_col.examples))
    data.freeze_panes = "A2"

    notes = workbook.create_sheet("Instructions")
    notes.append([f"{spec['label']} import"])
    notes["A1"].font = Font(bold=True, size=13)
    notes.append([spec["description"]])
    notes.append(["Replace the two example rows with your own. Keep the header row. Amounts are in Nepalese rupees."])
    notes.append(["The app checks every row first; if any row has a problem, nothing is imported and each problem "
                  "is listed with its row number."])
    notes.append([])
    notes.append(["Column", "Required?", "What to enter"])
    for cell in notes[6]:
        cell.font = Font(bold=True)
    for c in spec["columns"]:
        notes.append([c.name, "Required" if c.required else "Optional", c.meaning])
    notes.column_dimensions["A"].width = 22
    notes.column_dimensions["B"].width = 12
    notes.column_dimensions["C"].width = 90
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def types_out() -> list[dict]:
    return [{"type": key, "label": spec["label"], "description": spec["description"],
             "columns": [{"name": c.name, "required": c.required, "meaning": c.meaning} for c in spec["columns"]]}
            for key, spec in IMPORT_TYPES.items()]
