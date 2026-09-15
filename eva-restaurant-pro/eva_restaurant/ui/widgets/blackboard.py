"""Order board / blackboard widget."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QGridLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.ui.widgets.sticky_note import StickyNote


class BlackboardWidget(QWidget):
    """Dark glass board that holds order tickets in a responsive grid."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(700, 500)
        self.notes: dict[int, StickyNote] = {}
        self._container = QWidget(self)
        self._rebuild_layout()

    def _rebuild_layout(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._container)
        self._grid_layout.setSpacing(18)
        self._grid_layout.setContentsMargins(26, 26, 26, 26)
        scroll.setWidget(self._container)
        outer.addWidget(scroll)
        self._scroll = scroll

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor("#171b24"))
        grad.setColorAt(1, QColor("#0d0f15"))
        p.fillRect(self.rect(), grad)
        glow = QRadialGradient(self.width() * 0.5, 0, self.width() * 0.7)
        glow.setColorAt(0, QColor(212, 160, 23, 22))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), glow)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawRoundedRect(6, 6, self.width() - 12, self.height() - 12, 18, 18)
        super().paintEvent(event)

    @staticmethod
    def _age_band(m: float) -> int:
        return 3 if m >= 20 else (2 if m >= 12 else (1 if m >= 6 else 0))

    @classmethod
    def _ticket_signature(cls, o: dict, age: float) -> tuple:
        """Everything a ticket actually displays, boiled down to one
        comparable value. Previously the board only rebuilt a ticket when
        status, the age color band, or priority changed — so editing an
        order's items, note, table number, or order type from the waiter
        tablet (which changes none of those three things) left the kitchen
        board silently showing the old, pre-edit ticket until it happened
        to be rebuilt for an unrelated reason. Comparing the full displayed
        content instead means *any* edit is picked up on the very next
        2.5s refresh, matching what the waiter actually sent."""
        items_sig = tuple(
            (it.get("food_id"), it.get("name"), it.get("size"), it.get("qty"), it.get("price"))
            for it in (o.get("items") or [])
        )
        return (
            o.get("status"),
            cls._age_band(age),
            int(o.get("priority") or 0),
            o.get("table_no"),
            o.get("order_type"),
            o.get("note") or "",
            o.get("total"),
            o.get("est_prep_min"),
            items_sig,
        )

    def set_orders(self, orders: list[dict], on_prepare, on_ready=None):
        active_ids = {o["id"] for o in orders}
        for oid in list(self.notes.keys()):
            if oid not in active_ids:
                self._fade_out_and_remove(oid)
        for o in orders:
            age = o.get("_age_min", 0)
            sig = self._ticket_signature(o, age)
            if o["id"] in self.notes:
                note = self.notes[o["id"]]
                if getattr(note, "_sig", None) != sig:
                    self._remove_note_widget(o["id"])
                    self._add_note(o, age, sig, on_prepare, on_ready)
            else:
                self._add_note(o, age, sig, on_prepare, on_ready)
        self._relayout()

    def _add_note(self, order, age_min, sig, on_prepare, on_ready=None):
        note = StickyNote(order, age_minutes=age_min)
        note._age_min = age_min
        note._sig = sig
        note.prepare_clicked.connect(on_prepare)
        if on_ready:
            note.ready_clicked.connect(on_ready)
        self.notes[order["id"]] = note
        note.setParent(self._container)
        note.show()
        eff = QGraphicsOpacityEffect(note)
        note.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", note)
        anim.setDuration(550)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        note._fade_anim = anim

    def _remove_note_widget(self, oid):
        note = self.notes.pop(oid, None)
        if note:
            note.setParent(None)
            note.deleteLater()

    def _fade_out_and_remove(self, oid):
        note = self.notes.get(oid)
        if not note:
            return
        eff = note.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(note)
            note.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", note)
        anim.setDuration(700)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)

        def _done():
            self._remove_note_widget(oid)
            self._relayout()

        anim.finished.connect(_done)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        note._fade_anim = anim

    def _relayout(self):
        while self._grid_layout.count():
            self._grid_layout.takeAt(0)
        cols = max(1, (self._container.width() - 52) // 236) if self._container.width() > 100 else 4
        cols = max(3, min(cols, 6))
        for i, (_oid, note) in enumerate(sorted(self.notes.items(), key=lambda x: x[0])):
            r, c = divmod(i, cols)
            self._grid_layout.addWidget(note, r, c, Qt.AlignCenter)


# ─────────────────────────────────────────────
# Orders page (board)
# ─────────────────────────────────────────────
