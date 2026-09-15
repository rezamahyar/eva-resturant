#!/usr/bin/env python3
"""Shared database layer for EVA Restaurant."""

import binascii
import hashlib
import hmac
import json
import os
import secrets
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "food_images"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "eva_restaurant.db"
SETTINGS_PATH = DATA_DIR / "settings.json"

Base = declarative_base()
engine = create_engine(
    f"sqlite:///{DB_PATH}", echo=False,
    connect_args={"check_same_thread": False, "timeout": 15},
)
SessionLocal = sessionmaker(bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """WAL lets readers and writers work concurrently instead of blocking
    each other; without this, the desktop app and the Flask server thread
    (used by every waiter tablet) start throwing 'database is locked'
    errors as soon as more than one write happens at the same moment."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


class Food(Base):
    __tablename__ = "foods"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    price_small = Column(Float, default=0.0)
    price_medium = Column(Float, default=0.0)
    price_large = Column(Float, default=0.0)
    category = Column(String, default="Main")
    image_path = Column(String, default="")
    available = Column(Boolean, default=True)
    created_at = Column(String, default="")
    description = Column(String, default="")
    prep_minutes = Column(Integer, default=15)  # estimated kitchen prep time



# ---------------------------------------------------------------------------
# FUTURE NORMALIZATION PATH (order_items)
# Currently items live as JSON in Order.items_json for simplicity and speed.
# When daily volume or analytics needs grow, introduce:
#
#   class OrderItem(Base):
#       __tablename__ = "order_items"
#       id, order_id (FK), food_id (FK), name, size, qty, unit_price, line_total
#
# Migration can be done online: keep writing JSON while also writing rows,
# then switch readers, then drop the JSON column. Business rules
# (is_locked / find_open_order) stay untouched.
# ---------------------------------------------------------------------------

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    table_no = Column(Integer, nullable=False, index=True)
    status = Column(String, default="pending", index=True)  # pending | preparing | ready | delivered | paid | cancelled
    items_json = Column(Text, default="[]")
    total = Column(Float, default=0.0)
    note = Column(String, default="")
    waiter_name = Column(String, default="")
    created_at = Column(String, default="", index=True)
    updated_at = Column(String, default="")
    delivered_at = Column(String, default="")
    order_type = Column(String, default="dine_in")  # dine_in | takeaway
    priority = Column(Integer, default=0)  # 0 normal · 1 rush · 2 VIP
    cancelled_at = Column(String, default="")


class AppSettings(Base):
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    value = Column(Text, default="")


class ErrorLog(Base):
    """Central, persistent record of every error the system catches.

    Every unexpected failure anywhere in the app (desktop UI, background
    server thread, Flask API, or the browser-based waiter/accounting pages)
    is written here so it can be reviewed later from Settings → گزارش خطاها.
    """
    __tablename__ = "error_logs"
    id = Column(Integer, primary_key=True)
    created_at = Column(String, default="", index=True)
    level = Column(String, default="ERROR")          # ERROR | WARNING | CRITICAL
    source = Column(String, default="")               # e.g. "server.api_orders_create"
    message = Column(Text, default="")
    traceback = Column(Text, default="")
    context_json = Column(Text, default="")            # extra structured info (request path, payload, etc.)
    resolved = Column(Boolean, default=False)


Index("ix_orders_status_created", Order.status, Order.created_at)

Base.metadata.create_all(engine)


# ─── lightweight migrations for existing DBs ───
def _migrate():
    try:
        with engine.connect() as conn:
            ocols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(orders)").fetchall()]
            fcols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(foods)").fetchall()]
            alters = []
            if "order_type" not in ocols:
                alters.append("ALTER TABLE orders ADD COLUMN order_type VARCHAR DEFAULT 'dine_in'")
            if "priority" not in ocols:
                alters.append("ALTER TABLE orders ADD COLUMN priority INTEGER DEFAULT 0")
            if "cancelled_at" not in ocols:
                alters.append("ALTER TABLE orders ADD COLUMN cancelled_at VARCHAR DEFAULT ''")
            if "description" not in fcols:
                alters.append("ALTER TABLE foods ADD COLUMN description VARCHAR DEFAULT ''")
            if "prep_minutes" not in fcols:
                alters.append("ALTER TABLE foods ADD COLUMN prep_minutes INTEGER DEFAULT 15")
            for sql in alters:
                conn.exec_driver_sql(sql)
            if alters:
                conn.commit()
    except Exception:
        # Migration failures must never prevent the app from starting; the
        # worst case is a missing optional column, which callers already
        # guard against with getattr(..., default).
        traceback.print_exc()


_migrate()


DEFAULT_SETTINGS = {
    "password_hash": "",
    "server_host": "0.0.0.0",
    "server_port": 5050,
    "accent_color": "#d4a017",
    "accent_color2": "#8a5cf6",
    "bg_color": "#0b0e14",
    "panel_color": "#141a24",
    "text_color": "#eef1f6",
    "note_color": "#f5d76e",
    "blackboard_color": "#12161d",
    "restaurant_name": "EVA Restaurant",
    "currency": "AFN",
    "max_tables": 30,
    "language": "fa",
    "sound_new_order": True,
    "ticket_aging": True,
    "api_key": "",
}


def get_session():
    return SessionLocal()


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception:
            log_error("db.load_settings", "settings.json could not be parsed; using defaults")
    return s


def save_settings(data: dict):
    current = load_settings()
    current.update(data)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)


# ─── API key (protects the web/API layer for waiter tablets & accounting) ──
def get_or_create_api_key() -> str:
    """Every waiter tablet / accounting browser must send this key. It is
    generated once on first run and persisted; staff enter it once per
    device (stored in that device's browser) and never see it again."""
    key = load_settings().get("api_key") or ""
    if not key:
        key = secrets.token_hex(20)
        save_settings({"api_key": key})
    return key


def regenerate_api_key() -> str:
    """Invalidates the old key — every device will need to be re-entered."""
    key = secrets.token_hex(20)
    save_settings({"api_key": key})
    return key


# ─── password hashing (salted PBKDF2, with legacy sha256 verify) ────────
def hash_password(pwd: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, 200_000)
    return "pbkdf2$" + binascii.hexlify(salt).decode() + "$" + binascii.hexlify(dk).decode()


def verify_password(pwd: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, salt_hex, hash_hex = stored.split("$", 2)
            salt = binascii.unhexlify(salt_hex)
            expected = binascii.unhexlify(hash_hex)
        except (ValueError, binascii.Error):
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, 200_000)
        return hmac.compare_digest(dk, expected)
    # legacy unsalted sha256 hash from older installs — still verified so
    # existing passwords keep working; gets upgraded next time it's changed.
    return hmac.compare_digest(hashlib.sha256(pwd.encode("utf-8")).hexdigest(), stored)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_items(items_json: str):
    try:
        return json.loads(items_json or "[]")
    except Exception:
        log_error("db.parse_items", f"invalid items_json: {items_json!r}")
        return []


# ─── central error persistence ──────────────────────────
def log_error(source: str, message: str, exc: Exception = None, level: str = "ERROR", context: dict = None):
    """Persist one error/warning row. Never raises — logging must not itself crash the app."""
    tb = ""
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        session = SessionLocal()
        try:
            row = ErrorLog(
                created_at=now_iso(),
                level=level,
                source=source[:200],
                message=str(message)[:4000],
                traceback=tb[:20000],
                context_json=json.dumps(context or {}, ensure_ascii=False, default=str)[:4000],
            )
            session.add(row)
            session.commit()
        finally:
            session.close()
    except Exception:
        # Absolute last resort: at least get it into the log file on disk.
        try:
            with open(LOG_DIR / "fallback.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | {source} | {message}\n{tb}\n")
        except Exception:
            pass


def recent_errors(limit: int = 100):
    session = SessionLocal()
    try:
        return (
            session.query(ErrorLog)
            .order_by(ErrorLog.id.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def clear_errors():
    session = SessionLocal()
    try:
        session.query(ErrorLog).delete()
        session.commit()
    finally:
        session.close()


# ─── live-update support ─────────────────────────────────
def data_version() -> str:
    """Cheap fingerprint of the orders table. The /api/stream endpoint polls
    this server-side (instead of every browser tab polling the full order
    list) and only pushes to clients when it actually changes."""
    session = SessionLocal()
    try:
        count, max_id, max_updated = session.query(
            func.count(Order.id), func.max(Order.id), func.max(Order.updated_at)
        ).one()
        return f"{count}:{max_id}:{max_updated}"
    finally:
        session.close()


# ─── sales analytics ──────────────────────────────────────
def sales_report(days: int = 14) -> dict:
    """Daily sales, top items, hourly heatmap and category mix over the last
    `days` days ending today (cancelled orders excluded). Thin wrapper around
    `sales_report_range` so both entry points share one query/aggregation
    path — a bug fixed in one is automatically fixed in the other."""
    cutoff = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    return sales_report_range(cutoff, today)


def sales_report_range(start_date: str, end_date: str) -> dict:
    """Same shape as `sales_report`, but for an explicit inclusive date range
    (`YYYY-MM-DD` strings) instead of "last N days from now". This is what
    lets the accounting screen answer "what happened on this one day" or
    "what happened between these two dates" — a single day is just
    start_date == end_date.

    Cancelled orders are excluded, matching `sales_report`'s definition of
    "sales", so the two never disagree about what counts as revenue.
    """
    if not start_date:
        start_date = end_date
    if not end_date:
        end_date = start_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    # created_at is an ISO string ("YYYY-MM-DDTHH:MM:SS"); comparing it
    # lexicographically against plain date strings works as long as we use
    # a half-open upper bound of "the day after end_date" instead of a
    # naive `<= end_date`, which would silently exclude every order placed
    # after midnight on the last day (i.e. any order at all on that date).
    end_exclusive = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    session = SessionLocal()
    try:
        rows = (
            session.query(Order)
            .filter(Order.status != "cancelled")
            .filter(Order.created_at >= start_date)
            .filter(Order.created_at < end_exclusive)
            .all()
        )
        # Soft scalability guard: very large histories stay correct but
        # we surface a warning so operators know when it is time to move
        # aggregation into SQL or switch to Postgres.
        if len(rows) > 8000:
            import logging
            logging.getLogger("eva.db").warning(
                "sales_report_range loaded %s rows; consider SQL aggregation or Postgres for this volume",
                len(rows),
            )
        daily = defaultdict(float)
        hourly = defaultdict(float)
        item_stats = defaultdict(lambda: {"qty": 0, "revenue": 0.0})
        type_stats = defaultdict(float)
        status_counts = defaultdict(int)
        for o in rows:
            day = (o.created_at or "")[:10]
            hour = (o.created_at or "")[11:13]
            if day:
                daily[day] += o.total or 0
            if hour.isdigit():
                hourly[int(hour)] += o.total or 0
            otype = getattr(o, "order_type", None) or "dine_in"
            type_stats[otype] += o.total or 0
            status_counts[o.status or "?"] += 1
            for it in parse_items(o.items_json):
                name = str(it.get("name") or "?")
                qty = int(it.get("qty") or 0)
                price = float(it.get("price") or 0)
                item_stats[name]["qty"] += qty
                item_stats[name]["revenue"] += qty * price
        top_items = sorted(item_stats.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:12]
        return {
            "daily": [{"date": d, "total": round(v, 2)} for d, v in sorted(daily.items())],
            "hourly": [{"hour": h, "total": round(hourly.get(h, 0), 2)} for h in range(24)],
            "top_items": [
                {"name": n, "qty": v["qty"], "revenue": round(v["revenue"], 2)} for n, v in top_items
            ],
            "by_type": {k: round(v, 2) for k, v in type_stats.items()},
            "status_counts": dict(status_counts),
            "order_count": len(rows),
            "grand_total": round(sum(daily.values()), 2),
            "start_date": start_date,
            "end_date": end_date,
        }
    finally:
        session.close()


def estimate_prep_minutes(items: list, session=None) -> int:
    """Rough kitchen load estimate from cart items. Falls back to 12 min
    per unique dish when no prep_minutes are stored on the food profile.

    Accepts an optional existing `session` so callers that already loop
    over many orders (e.g. the kitchen board refreshing every 2.5s) can
    reuse one session/connection instead of opening a brand new one per
    order per item — that pattern gets expensive as order volume grows.
    """
    if not items:
        return 0
    owns_session = session is None
    session = session or SessionLocal()
    try:
        total = 0
        for it in items:
            fid = int(it.get("food_id") or 0)
            qty = max(1, int(it.get("qty") or 1))
            mins = 12
            if fid:
                f = session.get(Food, fid)
                if f and getattr(f, "prep_minutes", None):
                    mins = int(f.prep_minutes) or 12
            # parallel cooking assumption: +40% per extra unit of same dish
            total += mins + int(mins * 0.4 * (qty - 1))
        return max(5, min(90, total))
    finally:
        if owns_session:
            session.close()


# ─── order status invariants (single source of truth) ────────────────────
# A "locked" order is final: nothing may change its status, items, table,
# or notes anymore. Previously this rule was only enforced inside
# server.py's HTTP routes; the desktop app wrote to the same rows through
# a second, direct-DB-access path that had no such check. Centralizing it
# here means every current and future caller — desktop or web — enforces
# the same invariant automatically.
LOCKED_STATUSES = {"paid", "cancelled"}


def is_locked(status: str) -> bool:
    return (status or "") in LOCKED_STATUSES


# ─── one-active-order-per-table invariant ─────────────────────────────────
# A table is "open" as long as it has an order that isn't paid/cancelled yet
# (pending → preparing → ready → delivered are all still "the table's tab is
# running"). While a table is open, staff must add to / edit that existing
# order instead of starting a second, parallel one for the same table —
# otherwise the kitchen board and the bill can silently diverge into two
# tickets nobody is tracking together. `is_locked` and `OPEN_STATUSES` are
# complementary and, together with VALID_STATUSES in server.py, must cover
# every status: OPEN_STATUSES ∪ LOCKED_STATUSES == VALID_STATUSES.
OPEN_STATUSES = {"pending", "preparing", "ready", "delivered"}


def find_open_order(table_no: int, session=None) -> Optional["Order"]:
    """The table's current open order, if any. Returns the oldest one when
    more than one exists (e.g. leftover from data created before this rule
    existed), since that's the ticket staff have most likely already been
    adding to."""
    owns_session = session is None
    session = session or SessionLocal()
    try:
        return (
            session.query(Order)
            .filter(Order.table_no == table_no)
            .filter(Order.status.in_(OPEN_STATUSES))
            .order_by(Order.id.asc())
            .first()
        )
    finally:
        if owns_session:
            session.close()


# ─── food image lifecycle ─────────────────────────────────────────────────
def delete_food_image(image_path: str):
    """Best-effort removal of a food photo file that is no longer referenced
    (replaced by a new upload, or the food profile itself was deleted).
    Never raises — a stray leftover file is not worth crashing over, but we
    do log it so orphaned files aren't invisible forever."""
    if not image_path:
        return
    try:
        p = Path(image_path)
        if p.exists() and p.is_file() and str(UPLOAD_DIR) in str(p.resolve().parent):
            p.unlink()
    except Exception as e:
        log_error("db.delete_food_image", f"could not remove {image_path!r}", exc=e)


# ─── WAL-safe backup ───────────────────────────────────────────────────────
def checkpoint_wal():
    """Force all WAL-journaled writes into the main .db file. Must be called
    before copying DB_PATH with shutil — otherwise, since journal_mode=WAL,
    the most recent commits can still be sitting in the -wal file and a raw
    file copy of just the .db file can silently miss them."""
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
