"""settings page."""
from __future__ import annotations

import shutil
import socket
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.core import (
    DB_PATH,
    checkpoint_wal,
    get_or_create_api_key,
    hash_password,
    load_settings,
    regenerate_api_key,
    save_settings,
)
from eva_restaurant.i18n import set_language, tr
from eva_restaurant.logging.error_logger import log_exception
from eva_restaurant.ui.styles import build_stylesheet


class SettingsPage(QWidget):
    def __init__(self, settings: dict, main_window):
        super().__init__()
        self.settings = settings
        self.main_window = main_window
        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 20, 24, 20)
        title = QLabel(tr("settings_title"))
        title.setObjectName("PageTitle")
        lay.addWidget(title)

        lang_g = QGroupBox(tr("language"))
        lg = QVBoxLayout()
        lg.addWidget(QLabel(tr("language_hint")))
        row = QHBoxLayout()
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("فارسی", "fa")
        self.lang_combo.addItem("پښتو", "ps")
        self.lang_combo.addItem("English", "en")
        idx = self.lang_combo.findData(self.settings.get("language", "fa"))
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        row.addWidget(self.lang_combo, 1)
        apply_lang = QPushButton(tr("apply_language"))
        apply_lang.setObjectName("PrimaryButton")
        apply_lang.clicked.connect(self.apply_language)
        row.addWidget(apply_lang)
        lg.addLayout(row)
        self.sound_chk = QCheckBox(tr("sound_new_order"))
        self.sound_chk.setChecked(bool(self.settings.get("sound_new_order", True)))
        self.aging_chk = QCheckBox(tr("ticket_aging"))
        self.aging_chk.setChecked(bool(self.settings.get("ticket_aging", True)))
        lg.addWidget(self.sound_chk)
        lg.addWidget(self.aging_chk)
        lang_g.setLayout(lg)
        lay.addWidget(lang_g)

        color_g = QGroupBox(tr("colors"))
        cf = QFormLayout()
        self.color_keys = [
            ("accent_color", "رنگ اصلی (طلایی)"),
            ("accent_color2", "رنگ دوم (بنفش)"),
            ("bg_color", "پس‌زمینه"),
            ("panel_color", "پنل‌ها"),
            ("text_color", "متن"),
            ("note_color", "رنگ کاغذ نت"),
        ]
        self.color_btns = {}
        for key, label in self.color_keys:
            btn = QPushButton(self.settings.get(key, "#d4a017"))
            btn.clicked.connect(lambda checked=False, k=key, b=btn: self.pick_color(k, b))
            self.color_btns[key] = btn
            cf.addRow(label + ":", btn)
        apply_c = QPushButton("اعمال رنگ‌ها")
        apply_c.setObjectName("PrimaryButton")
        apply_c.clicked.connect(self.apply_colors)
        cf.addRow(apply_c)
        color_g.setLayout(cf)
        lay.addWidget(color_g)

        net_g = QGroupBox("شبکه و آی‌پی (سرور تبلت گارسون)")
        nf = QFormLayout()
        self.host_edit = QLineEdit(str(self.settings.get("server_host", "0.0.0.0")))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(int(self.settings.get("server_port", 5050)))
        self.ip_info = QLabel()
        self.ip_info.setWordWrap(True)
        self.ip_info.setStyleSheet("color:#9aa4b2;font-size:12px;")
        self._refresh_ip_info()
        save_net = QPushButton("ذخیره تنظیمات شبکه")
        save_net.clicked.connect(self.save_network)
        nf.addRow("Host:", self.host_edit)
        nf.addRow("Port:", self.port_spin)
        nf.addRow(self.ip_info)
        nf.addRow(save_net)
        net_g.setLayout(nf)
        lay.addWidget(net_g)

        key_g = QGroupBox("کلید دسترسی API (برای تبلت‌های گارسون و حسابداری وب)")
        kf = QVBoxLayout()
        kf.addWidget(QLabel(
            "هر تبلت گارسون یا مرورگر حسابداری، اولین‌بار که باز می‌شود، همین "
            "کلید را می‌خواهد. یک‌بار وارد می‌شود و همان‌جا ذخیره می‌ماند."
        ))
        krow = QHBoxLayout()
        self.api_key_edit = QLineEdit(get_or_create_api_key())
        self.api_key_edit.setReadOnly(True)
        regen_btn = QPushButton("🔁 تولید کلید جدید")
        regen_btn.setObjectName("DangerButton")
        regen_btn.clicked.connect(self.regen_key)
        krow.addWidget(self.api_key_edit, 1)
        krow.addWidget(regen_btn)
        kf.addLayout(krow)
        warn = QLabel("⚠ تولید کلید جدید یعنی همه‌ی تبلت‌ها باید دوباره کلید را وارد کنند.")
        warn.setStyleSheet("color:#f5c76e; font-size:11px;")
        warn.setWordWrap(True)
        kf.addWidget(warn)
        key_g.setLayout(kf)
        lay.addWidget(key_g)

        pwd_g = QGroupBox("رمز عبور برنامه")
        pf = QHBoxLayout()
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        self.pwd_edit.setPlaceholderText("رمز جدید (خالی = حذف)")
        set_pwd = QPushButton("تنظیم رمز")
        set_pwd.clicked.connect(self.set_password)
        pf.addWidget(self.pwd_edit)
        pf.addWidget(set_pwd)
        pwd_g.setLayout(pf)
        lay.addWidget(pwd_g)

        name_g = QGroupBox(tr("restaurant_name"))
        nl = QHBoxLayout()
        self.rest_name = QLineEdit(self.settings.get("restaurant_name", "EVA Restaurant"))
        save_name = QPushButton(tr("save"))
        save_name.clicked.connect(self.save_restaurant_name)
        nl.addWidget(self.rest_name)
        nl.addWidget(save_name)
        name_g.setLayout(nl)
        lay.addWidget(name_g)

        bak_g = QGroupBox(tr("backup"))
        bl = QHBoxLayout()
        bak_btn = QPushButton("💾 " + tr("backup"))
        bak_btn.clicked.connect(self.backup_db)
        bl.addWidget(bak_btn)
        bak_g.setLayout(bl)
        lay.addWidget(bak_g)

        lay.addStretch()
        outer_scroll.setWidget(inner)
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(outer_scroll)

    def _refresh_ip_info(self):
        ips = []
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None):
                ip = info[4][0]
                if "." in ip and not ip.startswith("127."):
                    ips.append(ip)
        except Exception as e:
            log_exception("kitchen.SettingsPage._refresh_ip_info", e)
        port = self.port_spin.value()
        # Two web links exist, both on the same LAN as this computer.
        # Accounting has no web link; it's the desktop app itself, run on
        # the accountant's own laptop.
        lines = ["آدرس تبلت گارسون (روی همان وای‌فای):"]
        if ips:
            for ip in sorted(set(ips)):
                lines.append(f"  http://{ip}:{port}/")
        else:
            lines.append(f"  http://<IP-این-کامپیوتر>:{port}/")
        lines.append("")
        lines.append("آدرس تخته سفارشات آشپزخانه (فقط نمایش + شروع پخت/آماده):")
        if ips:
            for ip in sorted(set(ips)):
                lines.append(f"  http://{ip}:{port}/kitchen")
        else:
            lines.append(f"  http://<IP-این-کامپیوتر>:{port}/kitchen")
        lines.append("")
        lines.append(
            "⚠ این یک لینک وب است، نه یک برنامه. یک تلویزیون یا مانیتور ساده "
            "به‌تنهایی مرورگر ندارد و نمی‌تواند این لینک را باز کند. برای نمایش "
            "روی تلویزیون/مانیتور آشپزخانه، یکی از این‌ها را به آن HDMI وصل کنید "
            "و لینک بالا را در مرورگرش باز کنید:\n"
            "  • Fire TV Stick / Android TV Box (ارزان و ساده)\n"
            "  • یک تبلت یا گوشی قدیمی (با کابل یا آداپتور HDMI)\n"
            "  • یک مینی‌پی‌سی یا Raspberry Pi\n"
            "بعد از باز کردن لینک، مرورگر را روی حالت تمام‌صفحه (kiosk/fullscreen) "
            "بگذارید تا همیشه روشن و باز بماند. این کامپیوتر (که این برنامه رویش "
            "اجراست) باید روشن و به همین وای‌فای وصل بماند تا هر دو لینک کار کنند."
        )
        self.ip_info.setText("\n".join(lines))

    def save_restaurant_name(self):
        try:
            save_settings({"restaurant_name": self.rest_name.text().strip()})
            QMessageBox.information(self, tr("saved"), tr("name_saved"))
        except Exception as e:
            log_exception("kitchen.SettingsPage.save_restaurant_name", e)
            QMessageBox.critical(self, tr("error"), str(e))

    def backup_db(self):
        folder = QFileDialog.getExistingDirectory(self, tr("backup"))
        if not folder:
            return
        try:
            # In WAL mode, recent commits can still be sitting in the -wal
            # file — copying DB_PATH alone can silently miss the last few
            # orders. Checkpointing first folds everything back into the
            # main .db file so the copy is actually complete.
            checkpoint_wal()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = Path(folder) / f"eva_restaurant_backup_{ts}.db"
            shutil.copy2(DB_PATH, dest)
            QMessageBox.information(self, tr("success"), tr("backup_ok", path=str(dest)))
        except Exception as e:
            log_exception("kitchen.SettingsPage.backup_db", e)
            QMessageBox.critical(self, tr("error"), str(e))

    def apply_language(self):
        code = self.lang_combo.currentData() or "fa"
        try:
            save_settings({
                "language": code,
                "sound_new_order": self.sound_chk.isChecked(),
                "ticket_aging": self.aging_chk.isChecked(),
            })
            set_language(code)
            QMessageBox.information(self, tr("language"), tr("lang_changed"))
        except Exception as e:
            log_exception("kitchen.SettingsPage.apply_language", e)
            QMessageBox.critical(self, tr("error"), str(e))

    def pick_color(self, key, btn):
        c = QColorDialog.getColor(QColor(self.settings.get(key, "#d4a017")), self)
        if c.isValid():
            self.settings[key] = c.name()
            btn.setText(c.name())
            btn.setStyleSheet(f"background:{c.name()}; color:#fff;")

    def apply_colors(self):
        try:
            save_settings({k: self.settings.get(k) for k, _ in self.color_keys})
            QApplication.instance().setStyleSheet(build_stylesheet(load_settings()))
            QMessageBox.information(self, "رنگ", "رنگ‌ها اعمال شد.")
        except Exception as e:
            log_exception("kitchen.SettingsPage.apply_colors", e)
            QMessageBox.critical(self, tr("error"), str(e))

    def save_network(self):
        try:
            save_settings({
                "server_host": self.host_edit.text().strip() or "0.0.0.0",
                "server_port": self.port_spin.value(),
            })
            self._refresh_ip_info()
            QMessageBox.information(
                self, "شبکه",
                "ذخیره شد.\nبرای اعمال پورت جدید، برنامه را یک‌بار ببندید و دوباره باز کنید."
            )
        except Exception as e:
            log_exception("kitchen.SettingsPage.save_network", e)
            QMessageBox.critical(self, tr("error"), str(e))

    def regen_key(self):
        reply = QMessageBox.question(
            self, "کلید جدید", "کلید جدید ساخته شود؟ همه تبلت‌ها باید دوباره کلید را وارد کنند.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            new_key = regenerate_api_key()
            self.api_key_edit.setText(new_key)
            QMessageBox.information(self, "کلید", "کلید جدید ساخته و ذخیره شد.")
        except Exception as e:
            log_exception("kitchen.SettingsPage.regen_key", e)
            QMessageBox.critical(self, tr("error"), str(e))

    def set_password(self):
        pwd = self.pwd_edit.text()
        try:
            if pwd:
                h = hash_password(pwd)
                save_settings({"password_hash": h})
                QMessageBox.information(self, "رمز", "رمز تنظیم شد.")
            else:
                save_settings({"password_hash": ""})
                QMessageBox.information(self, "رمز", "رمز حذف شد.")
            self.pwd_edit.clear()
        except Exception as e:
            log_exception("kitchen.SettingsPage.set_password", e)
            QMessageBox.critical(self, tr("error"), str(e))


# ─────────────────────────────────────────────
# Stylesheet — luxury modern glass theme
# ─────────────────────────────────────────────
