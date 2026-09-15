"""Orders / Kitchen board page."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.core import (
    Order,
    estimate_prep_minutes,
    get_session,
    is_locked,
    load_settings,
    now_iso,
    parse_items,
)
from eva_restaurant.i18n import tr
from eva_restaurant.logging.error_logger import log_exception
from eva_restaurant.ui.widgets.blackboard import BlackboardWidget


class OrdersPage(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self._status_filter = "all"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel(tr("kitchen_board"))
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch()
        self.count_lbl = QLabel(tr("active_orders", n=0))
        self.count_lbl.setStyleSheet("color: #9aa4b2; font-size: 13px;")
        top.addWidget(self.count_lbl)
        refresh = QPushButton("🔄 " + tr("refresh"))
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        lay.addLayout(top)

        # Status filter chips — European KDS style
        filt = QHBoxLayout()
        filt.setSpacing(8)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        for key, label in [
            ("all", tr("filter_all")),
            ("pending", tr("pending")),
            ("preparing", tr("preparing")),
            ("ready", tr("ready")),
        ]:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setMinimumHeight(34)
            if key == "all":
                b.setChecked(True)
            b.clicked.connect(lambda checked=False, k=key: self._set_filter(k))
            self._filter_group.addButton(b)
            filt.addWidget(b)
        filt.addStretch()
        lay.addLayout(filt)

        self.board = BlackboardWidget()
        lay.addWidget(self.board, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2500)
        QTimer.singleShot(400, self.refresh)

    def _set_filter(self, key: str):
        self._status_filter = key
        self.refresh()

    def refresh(self):
        session = get_session()
        try:
            q = (
                session.query(Order)
                .filter(Order.status.in_(("pending", "preparing", "ready")))
            )
            if self._status_filter != "all":
                q = q.filter(Order.status == self._status_filter)
            # Priority first, then oldest first — classic KDS discipline
            rows = q.order_by(Order.priority.desc(), Order.id.asc()).limit(120).all()
            orders = []
            ids = []
            now = datetime.now()
            for o in rows:
                age = 0.0
                try:
                    if o.created_at:
                        created = datetime.fromisoformat(o.created_at)
                        age = max(0.0, (now - created).total_seconds() / 60.0)
                except Exception as e:
                    log_exception("kitchen.OrdersPage.refresh.age_parse", e, context={"order_id": o.id})
                items = parse_items(o.items_json)
                otype = getattr(o, "order_type", None) or "dine_in"
                orders.append({
                    "id": o.id, "table_no": o.table_no, "status": o.status,
                    "items": items, "total": o.total,
                    "note": o.note or "", "created_at": o.created_at or "",
                    "order_type": otype,
                    "priority": int(getattr(o, "priority", 0) or 0),
                    # reuse this same session instead of opening a new one per
                    # order/item — this loop runs every 2.5s and can cover
                    # dozens of active tickets on a busy night.
                    "est_prep_min": estimate_prep_minutes(items, session=session),
                    "_age_min": age,
                })
                ids.append(o.id)

            prev = getattr(self, "_known_ids", set())
            new_ids = set(ids) - prev
            if new_ids and prev and load_settings().get("sound_new_order", True):
                QApplication.beep()
            self._known_ids = set(ids)

            self.count_lbl.setText(tr("active_orders", n=len(orders)))
            self.board.set_orders(orders, self.mark_preparing, self.mark_ready)
        except Exception as e:
            log_exception("kitchen.OrdersPage.refresh", e)
        finally:
            session.close()

    def _set_status(self, oid: int, status: str):
        session = get_session()
        try:
            o = session.query(Order).get(oid)
            if o:
                if is_locked(o.status) and status != o.status:
                    # Mirrors the same invariant server.py enforces on the
                    # API side, now sourced from db.py so both write paths
                    # agree — a paid/cancelled ticket can no longer surface
                    # in the board UI, but this keeps it true regardless.
                    QMessageBox.warning(self, tr("warning"), "این سفارش قفل شده و دیگر قابل تغییر نیست.")
                    return
                o.status = status
                o.updated_at = now_iso()
                if status == "delivered":
                    o.delivered_at = now_iso()
                if status == "cancelled":
                    o.cancelled_at = now_iso()
                session.commit()
        except Exception as e:
            session.rollback()
            log_exception("kitchen.OrdersPage._set_status", e, context={"order_id": oid, "status": status})
            QMessageBox.critical(self, tr("error"), "به‌روزرسانی سفارش ناموفق بود. جزئیات ثبت شد.")
        finally:
            session.close()
        self.refresh()

    def mark_ready(self, oid: int):
        self._set_status(oid, "ready")

    def mark_preparing(self, oid: int):
        self._set_status(oid, "preparing")


# ─────────────────────────────────────────────
# Food menu page
# ─────────────────────────────────────────────
