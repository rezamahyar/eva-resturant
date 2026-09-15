#!/usr/bin/env python3
"""
EVA Restaurant — Flask API + Waiter/Accounting Web UI
Run standalone:  python server.py
Or started automatically by the desktop kitchen app.
"""

import json
import secrets
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from eva_restaurant.core import (
    UPLOAD_DIR,
    Food,
    Order,
    data_version,
    delete_food_image,
    estimate_prep_minutes,
    find_open_order,
    get_or_create_api_key,
    get_session,
    is_locked,
    load_settings,
    now_iso,
    parse_items,
    recent_errors,
    sales_report,
)
from eva_restaurant.logging.error_logger import (
    get_logger,
    install_flask_error_handlers,
    log_exception,
    log_message,
)

BASE_DIR = Path(__file__).resolve().parent.parent  # project root
logger = get_logger("server")

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "static"))
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
install_flask_error_handlers(app, source_prefix="server")

VALID_STATUSES = {"pending", "preparing", "ready", "delivered", "paid", "cancelled"}
VALID_SIZES = {"small", "medium", "large"}
VALID_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def require_api_key(view):
    """Guards every state-changing / data-reading API route. The waiter
    tablet asks staff for this key once and stores it in that browser;
    without it, nobody on the network can see or touch orders or the menu."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        supplied = request.headers.get("X-Api-Key") or request.args.get("key") or ""
        expected = get_or_create_api_key()
        if not supplied or not secrets.compare_digest(supplied, expected):
            return jsonify({"ok": False, "error": "دسترسی نامعتبر است. کلید API را بررسی کنید."}), 401
        return view(*args, **kwargs)
    return wrapper


# ─── helpers ─────────────────────────────────
def order_to_dict(o: Order, session=None) -> dict:
    items = parse_items(o.items_json)
    return {
        "id": o.id,
        "table_no": o.table_no,
        "status": o.status,
        "items": items,
        "total": o.total,
        "note": o.note or "",
        "waiter_name": o.waiter_name or "",
        "created_at": o.created_at or "",
        "updated_at": o.updated_at or "",
        "delivered_at": o.delivered_at or "",
        "order_type": getattr(o, "order_type", None) or "dine_in",
        "priority": int(getattr(o, "priority", 0) or 0),
        "cancelled_at": getattr(o, "cancelled_at", "") or "",
        "est_prep_min": estimate_prep_minutes(items, session=session),
    }


def food_to_dict(f: Food) -> dict:
    img = ""
    if f.image_path and Path(f.image_path).exists():
        img = f"/food_images/{Path(f.image_path).name}"
    return {
        "id": f.id,
        "name": f.name,
        "price_small": f.price_small or 0,
        "price_medium": f.price_medium or 0,
        "price_large": f.price_large or 0,
        "category": f.category or "Main",
        "image": img,
        "available": bool(f.available),
        "description": getattr(f, "description", "") or "",
        "prep_minutes": int(getattr(f, "prep_minutes", 15) or 15),
    }


def calc_total(items: list) -> float:
    total = 0.0
    for it in items:
        total += float(it.get("price", 0)) * int(it.get("qty", 1))
    return round(total, 2)


SIZE_PRICE_FIELD = {"small": "price_small", "medium": "price_medium", "large": "price_large"}


def sanitize_items(raw_items: list, session) -> list:
    """Clean up a cart payload from the browser AND re-derive each item's
    price from the Food table instead of trusting whatever number the
    client sent. Previously `price` came straight from the waiter tablet's
    in-browser cache with only a `>= 0` clamp — a stale cache or a UI bug
    (or a tampered request) could silently change what an order is billed
    for, and nothing downstream (accounting, sales reports) would ever
    notice. The client-sent price is now only a fallback for items with no
    matching food_id (kept so nothing hard-crashes on old/odd data)."""
    clean = []
    for it in raw_items or []:
        if not isinstance(it, dict):
            continue
        try:
            qty = max(1, min(999, int(it.get("qty") or 1)))
            size = str(it.get("size") or "medium").strip().lower()
            if size not in VALID_SIZES:
                size = "medium"
            fid = int(it.get("food_id") or 0)
            name = str(it.get("name") or "").strip()[:120]

            price = max(0.0, float(it.get("price") or 0))  # fallback only
            food = session.get(Food, fid) if fid else None
            if food:
                real_price = getattr(food, SIZE_PRICE_FIELD[size], None)
                if real_price is not None:
                    price = max(0.0, float(real_price))
                if not name:
                    name = food.name
            elif fid:
                log_message("server.sanitize_items", f"food_id {fid} not found; using client price", level="WARNING")

            clean.append({
                "food_id": fid,
                "name": name,
                "size": size,
                "qty": qty,
                "price": price,
            })
        except (TypeError, ValueError):
            log_message("server.sanitize_items", f"skipped malformed item: {it!r}")
            continue
    return clean


# ─── pages ───────────────────────────────────
# Two web pages exist: the waiter tablet (takes orders, edits, delivers,
# cancels) and the kitchen board (view + advance status only — no editing,
# no accounting). Accounting stays desktop-only (no separate web page/link).
@app.route("/")
def index():
    return render_template("waiter.html", settings=load_settings())


@app.route("/kitchen")
def kitchen_page():
    return render_template("kitchen.html", settings=load_settings())


@app.route("/food_images/<path:filename>")
def food_image(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


# ─── API: foods ──────────────────────────────
@app.route("/api/foods", methods=["GET"])
@require_api_key
def api_foods():
    session = get_session()
    try:
        only_available = request.args.get("available") == "1"
        q = session.query(Food).order_by(Food.name)
        if only_available:
            q = q.filter(Food.available == True)  # noqa: E712
        return jsonify([food_to_dict(f) for f in q.all()])
    finally:
        session.close()


@app.route("/api/foods", methods=["POST"])
@require_api_key
def api_foods_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "نام غذا الزامی است"}), 400
    session = get_session()
    try:
        if session.query(Food).filter_by(name=name).first():
            return jsonify({"ok": False, "error": "غذایی با این نام قبلاً ثبت شده"}), 400
        f = Food(
            name=name,
            price_small=max(0.0, float(data.get("price_small") or 0)),
            price_medium=max(0.0, float(data.get("price_medium") or 0)),
            price_large=max(0.0, float(data.get("price_large") or 0)),
            category=(data.get("category") or "Main").strip()[:60],
            image_path=data.get("image_path") or "",
            available=bool(data.get("available", True)),
            description=(data.get("description") or "").strip()[:300],
            prep_minutes=max(1, min(120, int(data.get("prep_minutes") or 15))),
            created_at=now_iso(),
        )
        session.add(f)
        session.commit()
        return jsonify({"ok": True, "food": food_to_dict(f)})
    except (TypeError, ValueError) as e:
        session.rollback()
        log_message("server.api_foods_create", f"bad input: {e}", context={"body": data})
        return jsonify({"ok": False, "error": "مقادیر ورودی نامعتبر است"}), 400
    finally:
        session.close()


@app.route("/api/foods/<int:fid>", methods=["PUT"])
@require_api_key
def api_foods_update(fid):
    data = request.get_json(silent=True) or {}
    session = get_session()
    try:
        f = session.get(Food, fid)
        if not f:
            return jsonify({"ok": False, "error": "not found"}), 404
        if "name" in data and (data["name"] or "").strip():
            new_name = data["name"].strip()
            dup = session.query(Food).filter(Food.name == new_name, Food.id != fid).first()
            if dup:
                return jsonify({"ok": False, "error": "غذایی با این نام قبلاً ثبت شده"}), 400
            f.name = new_name
        if "price_small" in data:
            f.price_small = max(0.0, float(data["price_small"] or 0))
        if "price_medium" in data:
            f.price_medium = max(0.0, float(data["price_medium"] or 0))
        if "price_large" in data:
            f.price_large = max(0.0, float(data["price_large"] or 0))
        if "category" in data:
            f.category = (data["category"] or "Main").strip()[:60]
        if "available" in data:
            f.available = bool(data["available"])
        if "image_path" in data:
            new_image = data["image_path"] or ""
            old_image = f.image_path or ""
            if old_image and old_image != new_image:
                delete_food_image(old_image)  # replaced photo — remove the orphaned file
            f.image_path = new_image
        if "description" in data:
            f.description = (data.get("description") or "").strip()[:300]
        if "prep_minutes" in data:
            try:
                f.prep_minutes = max(1, min(120, int(data["prep_minutes"] or 15)))
            except (TypeError, ValueError):
                pass
        session.commit()
        return jsonify({"ok": True, "food": food_to_dict(f)})
    except (TypeError, ValueError) as e:
        session.rollback()
        log_message("server.api_foods_update", f"bad input: {e}", context={"body": data, "fid": fid})
        return jsonify({"ok": False, "error": "مقادیر ورودی نامعتبر است"}), 400
    finally:
        session.close()


@app.route("/api/foods/<int:fid>", methods=["DELETE"])
@require_api_key
def api_foods_delete(fid):
    session = get_session()
    try:
        f = session.get(Food, fid)
        if not f:
            return jsonify({"ok": False, "error": "not found"}), 404
        image_path = f.image_path or ""
        session.delete(f)
        session.commit()
        delete_food_image(image_path)  # food gone — its photo file has no owner left
        return jsonify({"ok": True})
    finally:
        session.close()


@app.route("/api/foods/upload", methods=["POST"])
@require_api_key
def api_foods_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "error": "empty filename"}), 400
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in VALID_IMAGE_EXT:
        return jsonify({"ok": False, "error": "invalid image type"}), 400
    name = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{ext}")
    dest = UPLOAD_DIR / name
    file.save(str(dest))
    return jsonify({"ok": True, "path": str(dest), "url": f"/food_images/{name}"})


# ─── API: orders ─────────────────────────────
@app.route("/api/orders", methods=["GET"])
@require_api_key
def api_orders():
    status = request.args.get("status")
    table_no = request.args.get("table_no")
    session = get_session()
    try:
        q = session.query(Order).order_by(Order.id.desc())
        if status:
            statuses = [s.strip() for s in status.split(",") if s.strip() in VALID_STATUSES]
            if statuses:
                q = q.filter(Order.status.in_(statuses))
        if table_no:
            try:
                q = q.filter(Order.table_no == int(table_no))
            except ValueError:
                return jsonify({"ok": False, "error": "invalid table_no"}), 400
        try:
            limit = max(1, min(500, int(request.args.get("limit") or 100)))
        except ValueError:
            limit = 100
        orders = q.limit(limit).all()
        return jsonify([order_to_dict(o, session=session) for o in orders])
    finally:
        session.close()


@app.route("/api/orders", methods=["POST"])
@require_api_key
def api_orders_create():
    data = request.get_json(silent=True) or {}
    try:
        table_no = int(data.get("table_no"))
        if table_no <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "شماره میز نامعتبر است"}), 400

    session = get_session()
    try:
        # A table with an already-open order (anything before paid/cancelled)
        # must not get a second, parallel order — that lets a table's bill
        # and the kitchen board silently split into two untracked tickets.
        # Staff add more items by editing the existing order instead
        # (PUT /api/orders/<id>); the frontend detects this proactively, but
        # this check is the source of truth against races (two waiters
        # tapping "send" for the same table at nearly the same moment).
        existing = find_open_order(table_no, session=session)
        if existing:
            return jsonify({
                "ok": False,
                "error": "این میز سفارش بازی دارد. برای افزودن غذا، همان سفارش را ویرایش کنید.",
                "existing_order_id": existing.id,
            }), 409

        items = sanitize_items(data.get("items"), session)
        if not items:
            return jsonify({"ok": False, "error": "حداقل یک غذا لازم است"}), 400
        total = calc_total(items)

        otype = (data.get("order_type") or "dine_in").strip()
        if otype not in ("dine_in", "takeaway"):
            otype = "dine_in"
        try:
            priority = max(0, min(2, int(data.get("priority") or 0)))
        except (TypeError, ValueError):
            priority = 0
        o = Order(
            table_no=table_no,
            status="pending",
            items_json=json.dumps(items, ensure_ascii=False),
            total=total,
            note=(data.get("note") or "").strip()[:500],
            waiter_name=(data.get("waiter_name") or "").strip()[:80],
            order_type=otype,
            priority=priority,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        session.add(o)
        session.commit()
        return jsonify({"ok": True, "order": order_to_dict(o, session=session)})
    finally:
        session.close()


@app.route("/api/orders/<int:oid>", methods=["PUT"])
@require_api_key
def api_orders_update(oid):
    data = request.get_json(silent=True) or {}
    session = get_session()
    try:
        o = session.get(Order, oid)
        if not o:
            return jsonify({"ok": False, "error": "not found"}), 404
        if is_locked(o.status):
            return jsonify({"ok": False, "error": "این سفارش دیگر قابل ویرایش نیست"}), 400
        if "items" in data:
            items = sanitize_items(data["items"], session)
            if not items:
                return jsonify({"ok": False, "error": "حداقل یک غذا لازم است"}), 400
            o.items_json = json.dumps(items, ensure_ascii=False)
            o.total = calc_total(items)
        if "table_no" in data:
            try:
                o.table_no = int(data["table_no"])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "شماره میز نامعتبر است"}), 400
        if "note" in data:
            o.note = (data.get("note") or "").strip()[:500]
        if "waiter_name" in data:
            o.waiter_name = (data.get("waiter_name") or "").strip()[:80]
        if "order_type" in data:
            otype = (data.get("order_type") or "dine_in").strip()
            o.order_type = otype if otype in ("dine_in", "takeaway") else "dine_in"
        if "priority" in data:
            try:
                o.priority = max(0, min(2, int(data.get("priority") or 0)))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "اولویت نامعتبر است"}), 400
        if "status" in data:
            new_status = (data["status"] or "").strip()
            if new_status not in VALID_STATUSES:
                return jsonify({"ok": False, "error": "وضعیت نامعتبر است"}), 400
            o.status = new_status
            if new_status == "delivered":
                o.delivered_at = now_iso()
        o.updated_at = now_iso()
        session.commit()
        return jsonify({"ok": True, "order": order_to_dict(o, session=session)})
    finally:
        session.close()


@app.route("/api/orders/<int:oid>/status", methods=["POST"])
@require_api_key
def api_orders_status(oid):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in VALID_STATUSES:
        return jsonify({"ok": False, "error": "invalid status"}), 400
    session = get_session()
    try:
        o = session.get(Order, oid)
        if not o:
            return jsonify({"ok": False, "error": "not found"}), 404
        if is_locked(o.status) and status != o.status:
            return jsonify({"ok": False, "error": "این سفارش قفل شده است"}), 400
        o.status = status
        o.updated_at = now_iso()
        if status == "delivered":
            o.delivered_at = now_iso()
        if status == "cancelled":
            o.cancelled_at = now_iso()
        session.commit()
        return jsonify({"ok": True, "order": order_to_dict(o, session=session)})
    finally:
        session.close()


@app.route("/api/orders/<int:oid>/cancel", methods=["POST"])
@require_api_key
def api_orders_cancel(oid):
    """Soft-cancel an open order (never deletes history)."""
    session = get_session()
    try:
        o = session.get(Order, oid)
        if not o:
            return jsonify({"ok": False, "error": "not found"}), 404
        if is_locked(o.status):
            return jsonify({"ok": False, "error": "این سفارش دیگر قابل لغو نیست"}), 400
        o.status = "cancelled"
        o.cancelled_at = now_iso()
        o.updated_at = now_iso()
        session.commit()
        return jsonify({"ok": True, "order": order_to_dict(o, session=session)})
    finally:
        session.close()


# ─── API: accounting ─────────────────────────
@app.route("/api/accounting/tables", methods=["GET"])
@require_api_key
def api_accounting_tables():
    """Open (unpaid) totals grouped by table."""
    session = get_session()
    try:
        open_statuses = ("pending", "preparing", "ready", "delivered")
        orders = (
            session.query(Order)
            .filter(Order.status.in_(open_statuses))
            .order_by(Order.table_no, Order.id)
            .all()
        )
        by_table = {}
        for o in orders:
            t = o.table_no
            if t not in by_table:
                by_table[t] = {"table_no": t, "orders": [], "total": 0.0}
            d = order_to_dict(o, session=session)
            by_table[t]["orders"].append(d)
            by_table[t]["total"] += o.total or 0
        result = sorted(by_table.values(), key=lambda x: x["table_no"])
        for row in result:
            row["total"] = round(row["total"], 2)
        return jsonify(result)
    finally:
        session.close()


@app.route("/api/accounting/pay_table/<int:table_no>", methods=["POST"])
@require_api_key
def api_pay_table(table_no):
    """Mark all open orders for a table as paid."""
    session = get_session()
    try:
        orders = (
            session.query(Order)
            .filter(Order.table_no == table_no)
            .filter(Order.status.in_(("pending", "preparing", "ready", "delivered")))
            .all()
        )
        for o in orders:
            o.status = "paid"
            o.updated_at = now_iso()
        session.commit()
        return jsonify({"ok": True, "paid_count": len(orders)})
    finally:
        session.close()


@app.route("/api/settings", methods=["GET"])
@require_api_key
def api_settings():
    s = load_settings()
    s = {k: v for k, v in s.items() if k not in ("password_hash", "api_key")}
    return jsonify(s)


# ─── API: live updates (Server-Sent Events) ──
@app.route("/api/stream")
def api_stream():
    """Push-style updates for the waiter tablet (and the desktop app's own
    polling). Browsers can't
    attach custom headers to EventSource, so the key travels as a query
    param here — everything else uses the X-Api-Key header."""
    supplied = request.args.get("key") or ""
    expected = get_or_create_api_key()
    if not supplied or not secrets.compare_digest(supplied, expected):
        return jsonify({"ok": False, "error": "دسترسی نامعتبر است"}), 401

    def gen():
        last = None
        idle = 0
        yield "retry: 3000\n\n"
        while True:
            try:
                cur = data_version()
            except Exception as e:
                log_message("server.api_stream", f"version check failed: {e}", level="WARNING")
                cur = last
            if cur != last:
                last = cur
                idle = 0
                yield f"data: {json.dumps({'changed': True})}\n\n"
            else:
                idle += 1
                if idle >= 20:  # ~20s idle -> keep-alive so the connection isn't dropped
                    idle = 0
                    yield ": keep-alive\n\n"
            time.sleep(1)

    return app.response_class(gen(), mimetype="text/event-stream")


# ─── API: sales analytics ────────────────────
@app.route("/api/accounting/report", methods=["GET"])
@require_api_key
def api_accounting_report():
    try:
        days = max(1, min(90, int(request.args.get("days") or 14)))
    except (TypeError, ValueError):
        days = 14
    return jsonify(sales_report(days))


@app.route("/api/verify_key", methods=["GET"])
@require_api_key
def api_verify_key():
    return jsonify({"ok": True})


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "time": now_iso()})


# ─── API: centralized error reporting ────────
@app.route("/api/client_error", methods=["POST"])
def api_client_error():
    """Lets the waiter tablet's browser page report JS errors so
    they land in the same central error log as backend errors."""
    data = request.get_json(silent=True) or {}
    log_message(
        "browser." + str(data.get("page") or "unknown"),
        str(data.get("message") or "unknown client error")[:2000],
        level="WARNING",
        context={
            "stack": str(data.get("stack") or "")[:4000],
            "url": str(data.get("url") or ""),
            "user_agent": request.headers.get("User-Agent", ""),
        },
    )
    return jsonify({"ok": True})


@app.route("/api/errors", methods=["GET"])
@require_api_key
def api_errors():
    """Read-only view of recent server-side errors, used by the desktop
    Settings → Error Log screen."""
    try:
        limit = max(1, min(500, int(request.args.get("limit") or 100)))
    except ValueError:
        limit = 100
    rows = recent_errors(limit)
    return jsonify([{
        "id": r.id,
        "created_at": r.created_at,
        "level": r.level,
        "source": r.source,
        "message": r.message,
        "traceback": r.traceback,
    } for r in rows])


def run_server(host=None, port=None, debug=False):
    s = load_settings()
    host = host or s.get("server_host", "0.0.0.0")
    port = int(port or s.get("server_port", 5050))
    logger.info("EVA Restaurant server starting on %s:%s", host, port)
    try:
        app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)
    except Exception as e:
        log_exception("server.run_server", e, context={"host": host, "port": port})
        raise


if __name__ == "__main__":
    run_server(debug=True)
