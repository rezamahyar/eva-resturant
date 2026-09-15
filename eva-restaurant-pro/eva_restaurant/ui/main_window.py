"""Main application window."""
from __future__ import annotations

import socket
import sys
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.core import load_settings, verify_password
from eva_restaurant.i18n import tr
from eva_restaurant.logging.error_logger import get_logger, log_exception
from eva_restaurant.ui.pages.accounting import AccountingPage
from eva_restaurant.ui.pages.food_menu import FoodMenuPage
from eva_restaurant.ui.pages.orders import OrdersPage
from eva_restaurant.ui.pages.reports import ReportsPage
from eva_restaurant.ui.pages.settings import SettingsPage

logger = get_logger("kitchen")

class ServerThread(threading.Thread):
    def __init__(self, host="0.0.0.0", port=5050):
        super().__init__(daemon=True)
        self.host = host
        self.port = port

    def run(self):
        try:
            from eva_restaurant.server import run_server
            run_server(host=self.host, port=self.port, debug=False)
        except Exception as e:
            log_exception("kitchen.ServerThread", e, context={"host": self.host, "port": self.port})




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.setWindowTitle(self.settings.get("restaurant_name", "EVA Restaurant"))
        self.setMinimumSize(1320, 820)

        pwd = self.settings.get("password_hash") or ""
        if pwd:
            entered, ok = QInputDialog.getText(self, "رمز عبور", "رمز را وارد کنید:", QLineEdit.Password)
            if not ok or not verify_password(entered, pwd):
                sys.exit(0)

        self.setup_ui()
        self.start_server()

    def start_server(self):
        host = self.settings.get("server_host", "0.0.0.0")
        port = int(self.settings.get("server_port", 5050))
        self.server_thread = ServerThread(host=host, port=port)
        self.server_thread.start()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent = self.settings.get("accent_color", "#d4a017")
        accent2 = self.settings.get("accent_color2", "#8a5cf6")

        # Header — glass bar with a subtle gold→violet accent line
        header = QFrame()
        header.setFixedHeight(80)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(255,255,255,0.05), stop:1 rgba(255,255,255,0.015));
                border-bottom: 1px solid rgba(255,255,255,0.10);
            }
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(26, 0, 26, 0)
        logo = QLabel("EVA")
        logo.setStyleSheet(
            f"font-size: 32px; font-weight: 800; letter-spacing: 6px; color: {accent};"
        )
        hl.addWidget(logo)
        sub = QVBoxLayout()
        sub.setSpacing(0)
        t1 = QLabel("RESTAURANT")
        t1.setStyleSheet(f"color:{accent2}; font-size:11px; font-weight:700; letter-spacing:3px;")
        t2 = QLabel(self.settings.get("restaurant_name", "Kitchen Display System"))
        t2.setStyleSheet("color:#7a8496; font-size:11px;")
        sub.addWidget(t1)
        sub.addWidget(t2)
        hl.addLayout(sub)
        hl.addStretch()
        self.server_lbl = QLabel("سرور تبلت: در حال اجرا…")
        self.server_lbl.setStyleSheet("color:#39d98a; font-size:12px; font-weight:600;")
        hl.addWidget(self.server_lbl)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(248)
        sidebar.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.02); border-right: 1px solid rgba(255,255,255,0.08); }"
        )
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 22, 14, 18)
        sl.setSpacing(6)

        menu_style = f"""
            QPushButton {{
                background: transparent; color: #c7cedb; border: none;
                border-radius: 12px; text-align: left; padding: 6px 18px;
                font-weight: 600; font-size: 13px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.06); color: #f0f4fa; }}
            QPushButton:checked {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(212,160,23,0.20), stop:1 rgba(138,92,246,0.10));
                color: {accent}; border-left: 3px solid {accent}; font-weight: 700;
            }}
        """
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        items = [
            (f"📋  {tr('orders')}", 0),
            (f"🍽  {tr('menu')}", 1),
            (f"💰  {tr('accounting')}", 2),
            (f"📊  {tr('custom_report')}", 3),
            (f"⚙️  {tr('settings')}", 4),
        ]
        for text, idx in items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setMinimumHeight(52)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(menu_style)
            btn.clicked.connect(lambda checked=False, i=idx: self.stack.setCurrentIndex(i))
            self.btn_group.addButton(btn, idx)
            sl.addWidget(btn)
            if idx == 0:
                btn.setChecked(True)
        sl.addStretch()
        hint = QLabel("تبلت گارسون روی\nهمان وای‌فای")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#5b6472; font-size:11px;")
        sl.addWidget(hint)
        body.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.orders_page = OrdersPage(self.settings)
        self.food_page = FoodMenuPage(self.settings)
        self.acc_page = AccountingPage(self.settings)
        self.reports_page = ReportsPage()
        self.settings_page = SettingsPage(self.settings, self)
        self.stack.addWidget(self.orders_page)
        self.stack.addWidget(self.food_page)
        self.stack.addWidget(self.acc_page)
        self.stack.addWidget(self.reports_page)
        self.stack.addWidget(self.settings_page)
        body.addWidget(self.stack, 1)
        root.addLayout(body)

        QTimer.singleShot(1500, self._update_server_label)

    def _update_server_label(self):
        port = int(load_settings().get("server_port", 5050))
        ip = "127.0.0.1"
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                cand = info[4][0]
                if "." in cand and not cand.startswith("127."):
                    ip = cand
                    break
        except Exception as e:
            log_exception("kitchen.MainWindow._update_server_label", e)
        self.server_lbl.setText(f"گارسون: http://{ip}:{port}  ·  آشپزخانه: http://{ip}:{port}/kitchen")


