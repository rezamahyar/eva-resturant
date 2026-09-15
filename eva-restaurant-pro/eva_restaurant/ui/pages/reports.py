"""reports page."""
from __future__ import annotations

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.core import (
    load_settings,
    sales_report,
    sales_report_range,
)
from eva_restaurant.i18n import tr
from eva_restaurant.logging.error_logger import log_exception


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        title = QLabel("📊 " + tr("custom_report"))
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch()
        ref = QPushButton("🔄 " + tr("refresh"))
        ref.clicked.connect(self.refresh_top_items)
        top.addWidget(ref)
        lay.addLayout(top)

        self.top_items_lbl = QLabel("—")
        self.top_items_lbl.setWordWrap(True)
        self.top_items_lbl.setStyleSheet("color:#9aa4b2; font-size:12px; padding:2px 2px 8px 2px;")
        lay.addWidget(self.top_items_lbl)

        # ── custom reporting: pick one specific day, or a date range, and
        # see that period's totals.
        rep_g = QGroupBox(tr("custom_report"))
        rep_v = QVBoxLayout()
        mode_row = QHBoxLayout()
        self.rep_mode_day = QRadioButton(tr("report_single_day"))
        self.rep_mode_range = QRadioButton(tr("report_range"))
        self.rep_mode_day.setChecked(True)
        self.rep_mode_day.toggled.connect(self._sync_report_mode)
        mode_row.addWidget(self.rep_mode_day)
        mode_row.addWidget(self.rep_mode_range)
        mode_row.addStretch()
        rep_v.addLayout(mode_row)

        pick_row = QHBoxLayout()
        today = QDate.currentDate()
        self.rep_day = QDateEdit(today)
        self.rep_day.setCalendarPopup(True)
        self.rep_day.setDisplayFormat("yyyy-MM-dd")
        self.rep_from = QDateEdit(today.addDays(-6))
        self.rep_from.setCalendarPopup(True)
        self.rep_from.setDisplayFormat("yyyy-MM-dd")
        self.rep_to = QDateEdit(today)
        self.rep_to.setCalendarPopup(True)
        self.rep_to.setDisplayFormat("yyyy-MM-dd")
        self.rep_from.setEnabled(False)
        self.rep_to.setEnabled(False)
        pick_row.addWidget(QLabel(tr("day")))
        pick_row.addWidget(self.rep_day)
        pick_row.addWidget(QLabel(tr("from")))
        pick_row.addWidget(self.rep_from)
        pick_row.addWidget(QLabel(tr("to")))
        pick_row.addWidget(self.rep_to)
        rep_btn = QPushButton("📊 " + tr("show_report"))
        rep_btn.setObjectName("PrimaryButton")
        rep_btn.clicked.connect(self.run_custom_report)
        pick_row.addWidget(rep_btn)
        rep_v.addLayout(pick_row)

        self.rep_result = QTextEdit()
        self.rep_result.setReadOnly(True)
        self.rep_result.setPlaceholderText(tr("report_placeholder"))
        rep_v.addWidget(self.rep_result)
        rep_g.setLayout(rep_v)
        lay.addWidget(rep_g, 1)

        QTimer.singleShot(300, self.refresh_top_items)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_top_items)
        self.timer.start(5000)

    def refresh_top_items(self):
        try:
            report = sales_report(14)
            top = report.get("top_items") or []
            if top:
                parts = [f"{it['name']} ({it['qty']})" for it in top[:5]]
                self.top_items_lbl.setText("🏆 پرفروش‌ترین‌های ۱۴ روز اخیر: " + " · ".join(parts))
            else:
                self.top_items_lbl.setText("🏆 هنوز داده‌ای برای پرفروش‌ترین‌ها نیست.")
        except Exception as e:
            log_exception("kitchen.ReportsPage.refresh_top_items", e)

    def _sync_report_mode(self):
        day_mode = self.rep_mode_day.isChecked()
        self.rep_day.setEnabled(day_mode)
        self.rep_from.setEnabled(not day_mode)
        self.rep_to.setEnabled(not day_mode)

    def run_custom_report(self):
        currency = load_settings().get("currency", "AFN")
        if self.rep_mode_day.isChecked():
            start = end = self.rep_day.date().toString("yyyy-MM-dd")
        else:
            start = self.rep_from.date().toString("yyyy-MM-dd")
            end = self.rep_to.date().toString("yyyy-MM-dd")
            if self.rep_from.date() > self.rep_to.date():
                start, end = end, start
        try:
            report = sales_report_range(start, end)
        except Exception as e:
            log_exception("kitchen.ReportsPage.run_custom_report", e, context={"start": start, "end": end})
            QMessageBox.critical(self, tr("error"), "تولید گزارش ناموفق بود.")
            return

        span = start if start == end else f"{start} → {end}"
        lines = [f"═══ {tr('custom_report')}: {span} ═══", ""]
        lines.append(f"{tr('today_sales')}: {report['grand_total']:,.0f} {currency}")
        lines.append(f"{tr('today_orders')}: {report['order_count']}")
        avg = (report["grand_total"] / report["order_count"]) if report["order_count"] else 0
        lines.append(f"{tr('avg_ticket')}: {avg:,.0f} {currency}")
        if report["order_count"]:
            statuses = ", ".join(f"{k}: {v}" for k, v in sorted(report["status_counts"].items()))
            lines.append(f"{tr('statuses')}: {statuses}")
        if start != end and report["daily"]:
            lines.append("")
            lines.append(f"── {tr('daily_report')} ──")
            for row in report["daily"]:
                lines.append(f"  {row['date']}: {row['total']:,.0f} {currency}")
        top = report.get("top_items") or []
        if top:
            lines.append("")
            lines.append("── 🏆 " + tr("top_items") + " ──")
            for it in top[:8]:
                lines.append(f"  {it['name']} ×{it['qty']} — {it['revenue']:,.0f} {currency}")
        elif not report["order_count"]:
            lines.append("")
            lines.append(tr("no_orders_period"))
        self.rep_result.setPlainText("\n".join(lines))


# ─────────────────────────────────────────────
# Settings page
# ─────────────────────────────────────────────
