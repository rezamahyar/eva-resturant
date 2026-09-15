"""Critical business-rule tests for EVA Restaurant."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eva_restaurant.core import (
    LOCKED_STATUSES,
    OPEN_STATUSES,
    Base,
    Order,
    find_open_order,
    is_locked,
    now_iso,
)

# ─── pure invariant tests (no DB) ─────────────────────────────────────────

def test_locked_statuses_membership():
    assert "paid" in LOCKED_STATUSES
    assert "cancelled" in LOCKED_STATUSES


def test_is_locked_true_for_final_states():
    assert is_locked("paid") is True
    assert is_locked("cancelled") is True
    assert is_locked(None) is False
    assert is_locked("") is False


def test_is_locked_false_for_active_states():
    for status in ("pending", "preparing", "ready", "delivered"):
        assert is_locked(status) is False


def test_open_and_locked_are_disjoint_and_cover_known():
    known = {"pending", "preparing", "ready", "delivered", "paid", "cancelled"}
    assert OPEN_STATUSES.isdisjoint(LOCKED_STATUSES)
    assert known == (OPEN_STATUSES | LOCKED_STATUSES)


# ─── DB integration (in-memory) ───────────────────────────────────────────

def _memory_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_find_open_order_returns_existing():
    s = _memory_session()
    try:
        o = Order(
            table_no=7,
            status="pending",
            items_json="[]",
            total=0,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        s.add(o)
        s.commit()
        found = find_open_order(7, session=s)
        assert found is not None
        assert found.id == o.id
    finally:
        s.close()


def test_find_open_order_ignores_locked():
    s = _memory_session()
    try:
        o = Order(
            table_no=3,
            status="paid",
            items_json="[]",
            total=100,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        s.add(o)
        s.commit()
        assert find_open_order(3, session=s) is None
    finally:
        s.close()


def test_find_open_order_none_when_empty():
    s = _memory_session()
    try:
        assert find_open_order(99, session=s) is None
    finally:
        s.close()


def test_find_open_order_returns_oldest_when_multiple():
    s = _memory_session()
    try:
        o1 = Order(
            table_no=5,
            status="pending",
            items_json="[]",
            total=10,
            created_at="2024-01-01T10:00:00",
            updated_at="2024-01-01T10:00:00",
        )
        o2 = Order(
            table_no=5,
            status="preparing",
            items_json="[]",
            total=20,
            created_at="2024-01-01T11:00:00",
            updated_at="2024-01-01T11:00:00",
        )
        s.add_all([o1, o2])
        s.commit()
        found = find_open_order(5, session=s)
        assert found is not None
        assert found.id == o1.id
    finally:
        s.close()
