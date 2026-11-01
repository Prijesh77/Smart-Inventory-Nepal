"""Keeps each shop's data private, in one place instead of in every query.

How it works (SQLAlchemy session events, so no service can forget it):
  1. Reading and changing: every ORM select, update, delete and Session.get on a
     ShopOwned table gets "AND shop_id = <current shop>" added, including in
     joins and sub-queries. Another shop's rows are simply not found (404).
  2. Adding: new ShopOwned rows get the current shop's id; a row for a
     different shop is refused.
  3. Fail closed: with no shop set, a query on shop data is refused (or, inside a
     join, finds nothing) instead of returning every shop's rows.

The current shop is kept in session.info. The API sets it from the logged-in
user (app/api/deps.py); background jobs and scripts set it with use_shop() or
shop_session(). Code that must look across shops (login, creating a shop) uses
the all_shops() block.

Bulk inserts with insert(Model) and a list of dicts are not ORM objects, so they
must include shop_id themselves; the NOT NULL column refuses any that forget.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.db.base import ShopOwned

SHOP_KEY = "shop_id"
ALL_SHOPS_KEY = "all_shops"


class ShopNotSet(RuntimeError):
    """Shop data was used without choosing a shop first (a programming error, never a user error)."""


def use_shop(session: Session, shop_id: int) -> Session:
    session.info[SHOP_KEY] = shop_id
    return session


def current_shop_id(session: Session) -> int:
    shop_id = session.info.get(SHOP_KEY)
    if shop_id is None:
        raise ShopNotSet("No shop selected for this database session")
    return shop_id


def shop_session(factory: sessionmaker[Session], shop_id: int) -> Session:
    """A new session limited to one shop (for background jobs)."""
    return factory(info={SHOP_KEY: shop_id})


@contextmanager
def all_shops(session: Session) -> Iterator[Session]:
    """Temporarily see every shop's rows. Use only where that is the point (login, shop set-up)."""
    previous = session.info.get(ALL_SHOPS_KEY)
    session.info[ALL_SHOPS_KEY] = True
    try:
        yield session
    finally:
        session.info[ALL_SHOPS_KEY] = previous


def _touches_shop_data(state: ORMExecuteState) -> bool:
    return any(issubclass(mapper.class_, ShopOwned) for mapper in state.all_mappers)


@event.listens_for(Session, "do_orm_execute")
def _limit_to_current_shop(state: ORMExecuteState) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    # Lazy loads and refreshes follow rows that were already loaded for this shop.
    if state.is_column_load or state.is_relationship_load or state.session.info.get(ALL_SHOPS_KEY):
        return
    shop_id = state.session.info.get(SHOP_KEY)
    if shop_id is None:
        if _touches_shop_data(state):
            raise ShopNotSet("Shop data was queried without choosing a shop")
        criteria = lambda cls: cls.shop_id.is_(None)            # noqa: E731  (matches nothing: shop_id is NOT NULL)
    else:
        criteria = lambda cls: cls.shop_id == shop_id          # noqa: E731
    state.statement = state.statement.options(with_loader_criteria(ShopOwned, criteria, include_aliases=True))


@event.listens_for(Session, "before_flush")
def _stamp_new_rows(session: Session, _context, _instances) -> None:
    shop_id = session.info.get(SHOP_KEY)
    for obj in session.new:
        if not isinstance(obj, ShopOwned):
            continue
        if obj.shop_id is None:
            if shop_id is None:
                raise ShopNotSet(f"Cannot add a {type(obj).__name__} without choosing a shop")
            obj.shop_id = shop_id
        elif shop_id is not None and obj.shop_id != shop_id and not session.info.get(ALL_SHOPS_KEY):
            raise ShopNotSet(f"Refusing to add a {type(obj).__name__} for shop {obj.shop_id} while working in shop {shop_id}")
