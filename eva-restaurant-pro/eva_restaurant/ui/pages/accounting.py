"""accounting page."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.core import (
    Order,
    get_session,
    load_settings,
    now_iso,
    parse_items,
)
from eva_restaurant.i18n import tr
from eva_restaurant.logging.error_logger import log_exception
from eva_restaurant.ui.widgets.sticky_note import add_glow


class AccountingPage(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self._cache = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        title = QLabel(tr("accounting_title"))
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch()
        print_btn = QPushButton("🖨 " + tr("save"))
        print_btn.setToolTip("Print / preview receipt for selected table")
        print_btn.clicked.connect(self.print_receipt)
        top.addWidget(print_btn)
        ref = QPushButton("🔄 " + tr("refresh"))
        ref.clicked.connect(self.refresh)
        top.addWidget(ref)
        lay.addLayout(top)

        cards = QHBoxLayout()
        self.c_sales = self._kpi(tr("today_sales"), "0")
        self.c_orders = self._kpi(tr("today_orders"), "0")
        self.c_tables = self._kpi(tr("today_tables"), "0")
        self.c_avg = self._kpi(tr("avg_ticket"), "0", "gold")
        for w in (self.c_sales, self.c_orders, self.c_tables, self.c_avg):
            cards.addWidget(w)
        lay.addLayout(cards)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            tr("table"), tr("orders_count"), tr("total_amount"), tr("statuses"), tr("actions")
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(180)
        self.detail.setPlaceholderText(tr("detail_placeholder"))
        lay.addWidget(self.detail)

        self.table.itemSelectionChanged.connect(self.show_detail)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        QTimer.singleShot(300, self.refresh)

    def _kpi(self, title, value, kind="default"):
        frame = QFrame()
        frame.setObjectName("KpiCard")
        add_glow(frame, color="#000000", blur=22, alpha=60, dy=4)
        v = QVBoxLayout(frame)
        v.setContentsMargins(18, 14, 18, 14)
        t = QLabel(title)
        t.setStyleSheet("color:#9aa4b2;font-size:11px;font-weight:600;background:transparent;")
        v.addWidget(t)
        val = QLabel(value)
        color = "#d4a017" if kind == "gold" else "#eef1f6"
        val.setStyleSheet(f"color:{color};font-size:23px;font-weight:800;background:transparent;")
        v.addWidget(val)
        frame.value_label = val
        return frame

    def refresh(self):
        session = get_session()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            all_today = session.query(Order).filter(Order.created_at.startswith(today)).all()
            paid_or_open = [o for o in all_today if o.status != "cancelled"]
            sales = sum(o.total or 0 for o in paid_or_open)
            n_orders = len(paid_or_open)
            tables = {o.table_no for o in paid_or_open}
            avg = (sales / n_orders) if n_orders else 0
            currency = load_settings().get("currency", "AFN")
            self.c_sales.value_label.setText(f"{sales:,.0f} {currency}")
            self.c_orders.value_label.setText(str(n_orders))
            self.c_tables.value_label.setText(str(len(tables)))
            self.c_avg.value_label.setText(f"{avg:,.0f} {currency}")

            orders = (
                session.query(Order)
                .filter(Order.status.in_(("pending", "preparing", "ready", "delivered")))
                .order_by(Order.table_no)
                .all()
            )
            by_table: dict[int, list] = {}
            for o in orders:
                by_table.setdefault(o.table_no, []).append(o)
            self._cache = by_table
            self.table.setRowCount(0)
            for i, (tno, lst) in enumerate(sorted(by_table.items())):
                self.table.insertRow(i)
                total = sum(o.total or 0 for o in lst)
                statuses = ", ".join(sorted({o.status for o in lst}))
                self.table.setItem(i, 0, QTableWidgetItem(str(tno)))
                self.table.setItem(i, 1, QTableWidgetItem(str(len(lst))))
                self.table.setItem(i, 2, QTableWidgetItem(f"{total:,.0f} {currency}"))
                self.table.setItem(i, 3, QTableWidgetItem(statuses))
                btn = QPushButton(tr("settle"))
                btn.setObjectName("PrimaryButton")
                btn.clicked.connect(lambda checked=False, tn=tno: self.pay_table(tn))
                self.table.setCellWidget(i, 4, btn)
        except Exception as e:
            log_exception("kitchen.AccountingPage.refresh", e)
        finally:
            session.close()

    def show_detail(self):
        row = self.table.currentRow()
        if row < 0:
            return
        tno = int(self.table.item(row, 0).text())
        lst = self._cache.get(tno, [])
        currency = load_settings().get("currency", "AFN")
        size_map = {"small": "کوچک", "medium": "متوسط", "large": "بزرگ"}
        lines = [f"═══ میز {tno} ═══"]
        grand = 0
        for o in lst:
            lines.append(f"\nسفارش #{o.id} [{o.status}] — {o.created_at}")
            for it in parse_items(o.items_json):
                line = (it.get("price", 0) or 0) * (it.get("qty", 1) or 1)
                grand += line
                lines.append(
                    f"  • {it.get('name')} ({size_map.get(it.get('size'), it.get('size'))}) "
                    f"×{it.get('qty')} = {line:,.0f} {currency}"
                )
            if o.note:
                lines.append(f"  📝 {o.note}")
        lines.append(f"\nجمع کل میز: {grand:,.0f} {currency}")
        self.detail.setPlainText("\n".join(lines))

    def print_receipt(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, tr("accounting"), tr("detail_placeholder"))
            return
        tno = int(self.table.item(row, 0).text())
        lst = self._cache.get(tno, [])
        if not lst:
            return
        size_map = {"small": tr("small"), "medium": tr("medium"), "large": tr("large")}
        s = load_settings()
        name = s.get("restaurant_name", "EVA Restaurant")
        currency = s.get("currency", "AFN")
        lines = [
            name.center(32), "=" * 32, f"{tr('table')} {tno}".center(32),
            datetime.now().strftime("%Y-%m-%d  %H:%M"), "-" * 32,
        ]
        grand = 0.0
        for o in lst:
            for it in parse_items(o.items_json):
                line = (it.get("price") or 0) * (it.get("qty") or 1)
                grand += line
                sz = size_map.get(it.get("size"), it.get("size", ""))
                lines.append(f"{it.get('name','')} ({sz}) x{it.get('qty',1)}")
                lines.append(f"  {line:,.0f} {currency}")
            if o.note:
                lines.append(f"  * {o.note}")
        lines += ["-" * 32, f"{tr('total_amount')}: {grand:,.0f} {currency}", "=" * 32, ""]
        receipt = "\n".join(lines)
        dlg = QMessageBox(self)
        dlg.setWindowTitle(tr("accounting"))
        dlg.setText(receipt)
        dlg.setStandardButtons(QMessageBox.Ok)
        self.detail.setPlainText(receipt)
        dlg.exec()

    def pay_table(self, table_no: int):
        reply = QMessageBox.question(
            self, tr("settle"), tr("settle_confirm", n=table_no),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
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
            QMessageBox.information(self, tr("settle"), tr("settled", n=len(orders)))
            self.refresh()
        except Exception as e:
            session.rollback()
            log_exception("kitchen.AccountingPage.pay_table", e, context={"table_no": table_no})
            QMessageBox.critical(self, tr("error"), "تسویه میز ناموفق بود.")
        finally:
            session.close()


# ─────────────────────────────────────────────
# Reports page — sales analytics, split out of Accounting so it has its
# own place in the sidebar: "last 14 days" best-sellers plus a custom
# single-day / date-range report.
# ─────────────────────────────────────────────
