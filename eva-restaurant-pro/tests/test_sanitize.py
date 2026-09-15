"""Unit tests for server-side price sanitization (real sanitize_items)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from eva_restaurant.server import sanitize_items


def _food(name="Kabuli", small=100, medium=150, large=200):
    return SimpleNamespace(
        name=name,
        price_small=small,
        price_medium=medium,
        price_large=large,
    )


def _session_with_foods(foods: dict):
    """Minimal session mock that supports session.get(Food, fid)."""
    session = MagicMock()

    def _get(model, fid):
        return foods.get(fid)

    session.get.side_effect = _get
    return session


def test_sanitize_overrides_client_price_with_server_price():
    food = _food()
    session = _session_with_foods({1: food})
    raw = [{"food_id": 1, "name": "Kabuli", "size": "medium", "qty": 2, "price": 1}]
    result = sanitize_items(raw, session)
    assert len(result) == 1
    assert result[0]["price"] == 150
    assert result[0]["qty"] == 2
    assert result[0]["size"] == "medium"


def test_sanitize_falls_back_when_food_missing():
    session = _session_with_foods({})
    raw = [{"food_id": 999, "name": "Ghost", "size": "small", "qty": 1, "price": 42}]
    result = sanitize_items(raw, session)
    assert len(result) == 1
    assert result[0]["price"] == 42
    assert result[0]["name"] == "Ghost"


def test_sanitize_clamps_qty_and_rejects_garbage():
    food = _food(name="Tea", small=20, medium=20, large=20)
    session = _session_with_foods({1: food})
    raw = [
        {"food_id": 1, "size": "small", "qty": 0, "price": 20},   # qty -> 1
        {"food_id": 1, "size": "XL", "qty": 5, "price": 20},      # size -> medium
        "not a dict",
        {"food_id": "bad", "qty": 1},
        None,
    ]
    result = sanitize_items(raw, session)
    assert len(result) == 2
    assert result[0]["qty"] == 1
    assert result[0]["size"] == "small"
    assert result[1]["size"] == "medium"
    assert result[1]["qty"] == 5


def test_sanitize_empty_input():
    session = _session_with_foods({})
    assert sanitize_items([], session) == []
    assert sanitize_items(None, session) == []


def test_sanitize_fills_name_from_food_when_missing():
    food = _food(name="Qabuli")
    session = _session_with_foods({3: food})
    raw = [{"food_id": 3, "size": "large", "qty": 1, "price": 999}]
    result = sanitize_items(raw, session)
    assert result[0]["name"] == "Qabuli"
    assert result[0]["price"] == 200  # large price
