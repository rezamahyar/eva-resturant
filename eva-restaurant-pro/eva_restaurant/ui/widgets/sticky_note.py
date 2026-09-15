"""Kitchen ticket (StickyNote) widget — European KDS style."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from eva_restaurant.core import estimate_prep_minutes, load_settings
from eva_restaurant.i18n import tr


def add_glow(widget, color="#d4a017", blur=28, alpha=90, dx=0, dy=6):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    c = QColor(color)
    c.setAlpha(alpha)
    eff.setColor(c)
    eff.setOffset(dx, dy)
    widget.setGraphicsEffect(eff)
    return eff


# ─────────────────────────────────────────────
# Order ticket widget (glass card, replaces the old flat sticky note)
# ─────────────────────────────────────────────


class StickyNote(QFrame):
    """European KDS-style glass ticket: age colors, priority, prep estimate.

    The board is a read + cook-status display only: it can move a ticket
    pending → preparing → ready, because that's the kitchen's own workflow.
    Editing an order, marking it delivered, and cancelling it are all
    front-of-house actions now done exclusively from the waiter's tablet
    (see templates/waiter.html) — a ticket here can no longer be dismissed
    or changed by anyone standing at the kitchen screen.
    """
    prepare_clicked = Signal(int)
    ready_clicked = Signal(int)

    def __init__(self, order: dict, age_minutes: float = 0, parent=None):
        super().__init__(parent)
        self.order_id = order["id"]
        self.order = order
        self.setFixedSize(236, 268)
        self.setObjectName("TicketCard")

        priority = int(order.get("priority") or 0)
        use_aging = load_settings().get("ticket_aging", True)
        if priority >= 2:
            border_c, glow = "#c084fc", "#c084fc"  # VIP violet
        elif priority >= 1:
            border_c, glow = "#ff6b6b", "#ff6b6b"  # rush red
        elif use_aging and age_minutes >= 20:
            border_c, glow = "#ff5c5c", "#ff5c5c"
        elif use_aging and age_minutes >= 12:
            border_c, glow = "#ff9f43", "#ff9f43"
        elif use_aging and age_minutes >= 6:
            border_c, glow = "#f5c76e", "#f5c76e"
        else:
            border_c, glow = "#39d98a", "#39d98a"

        status = order.get("status", "pending")
        self.setStyleSheet(f"""
            QFrame#TicketCard {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(30,36,48,240), stop:1 rgba(18,22,30,240));
                border: 1.8px solid {border_c};
                border-radius: 16px;
            }}
            QLabel {{ background: transparent; color: #eef1f6; }}
            QPushButton {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12); border-radius: 9px;
                color: #eef1f6; font-weight: 700; font-size: 11px; padding: 7px 6px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.14); }}
            QPushButton#CancelBtn {{
                background: rgba(255,92,92,0.12); border: 1px solid rgba(255,92,92,0.35);
                color: #ff8a8a; font-size: 10px; padding: 5px 6px;
            }}
            QPushButton#CancelBtn:hover {{ background: rgba(255,92,92,0.22); }}
        """)
        add_glow(self, color=glow, blur=28, alpha=80 if priority else 70)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(13, 11, 13, 11)
        lay.setSpacing(3)

        head = QHBoxLayout()
        pri_icons = {1: "⚡ ", 2: "★ "}
        table_lbl = QLabel(f"{pri_icons.get(priority, '')}{tr('table')} {order['table_no']}")
        table_lbl.setStyleSheet("font-size: 16px; font-weight: 800;")
        head.addWidget(table_lbl)
        head.addStretch()
        age_dot = QLabel("●")
        age_dot.setStyleSheet(f"color:{border_c}; font-size:12px;")
        head.addWidget(age_dot)
        age_lbl = QLabel(tr("minutes_ago", m=int(age_minutes)))
        age_lbl.setStyleSheet(f"font-size: 11px; font-weight: 800; color: {border_c};")
        head.addWidget(age_lbl)
        lay.addLayout(head)

        st_map = {
            "pending": tr("pending"), "preparing": tr("preparing"),
            "ready": tr("ready"), "delivered": tr("delivered"),
        }
        otype = order.get("order_type") or "dine_in"
        type_txt = tr("takeaway") if otype == "takeaway" else tr("dine_in")
        pri_txt = {1: " · RUSH", 2: " · VIP"}.get(priority, "")
        meta = QLabel(f"{st_map.get(status, status)} · {type_txt}{pri_txt}")
        meta.setStyleSheet("font-size: 11px; font-weight: 700; color:#9aa4b2;")
        lay.addWidget(meta)

        est = order.get("est_prep_min") or estimate_prep_minutes(order.get("items") or [])
        time_row = QHBoxLayout()
        time_lbl = QLabel((order.get("created_at") or "")[11:19])
        time_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        time_row.addWidget(time_lbl)
        time_row.addStretch()
        if est:
            est_lbl = QLabel(f"⏱ ~{est}′")
            est_lbl.setStyleSheet("font-size: 11px; color: #8b9bb4; font-weight: 600;")
            time_row.addWidget(est_lbl)
        lay.addLayout(time_row)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.08);")
        lay.addWidget(line)

        items_box = QLabel()
        items_box.setWordWrap(True)
        items_box.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        size_map = {"small": "S", "medium": "M", "large": "L"}
        lines = []
        for it in order.get("items") or []:
            sz = size_map.get(it.get("size", ""), it.get("size", ""))
            lines.append(f"• {it.get('name','')} ({sz}) ×{it.get('qty',1)}")
        items_box.setText("\n".join(lines[:6]) + ("\n…" if len(lines) > 6 else ""))
        items_box.setStyleSheet("font-size: 12px; font-weight: 600;")
        lay.addWidget(items_box, 1)

        if order.get("note"):
            n = QLabel(f"📝 {order['note'][:52]}")
            n.setStyleSheet("font-size: 10px; color: #f5c76e; font-weight: 600;")
            n.setWordWrap(True)
            lay.addWidget(n)

        currency = load_settings().get("currency", "AFN")
        total = QLabel(f"{order.get('total', 0):,.0f} {currency}")
        total.setStyleSheet("font-size: 15px; font-weight: 800; color:#d4a017;")
        lay.addWidget(total)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        if status == "pending":
            b1 = QPushButton(tr("cooking"))
            b1.clicked.connect(lambda: self.prepare_clicked.emit(self.order_id))
            btns.addWidget(b1)
        if status in ("pending", "preparing"):
            b_ready = QPushButton(tr("ready"))
            b_ready.clicked.connect(lambda: self.ready_clicked.emit(self.order_id))
            btns.addWidget(b_ready)
        if btns.count():
            lay.addLayout(btns)
        elif status == "ready":
            waiting = QLabel(tr("awaiting_pickup"))
            waiting.setAlignment(Qt.AlignCenter)
            waiting.setStyleSheet("font-size: 11px; font-weight: 700; color:#39d98a;")
            lay.addWidget(waiting)


