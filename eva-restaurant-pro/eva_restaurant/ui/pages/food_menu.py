"""food_menu page."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from eva_restaurant.core import (
    UPLOAD_DIR,
    Food,
    delete_food_image,
    get_session,
    now_iso,
)
from eva_restaurant.i18n import tr
from eva_restaurant.logging.error_logger import log_exception


class FoodMenuPage(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.current_id = None
        self.image_path = ""
        self.setup_ui()
        self.load_foods()

    def setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)

        title = QLabel(tr("food_menu"))
        title.setObjectName("PageTitle")
        lay.addWidget(title)

        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([tr("name"), tr("small"), tr("medium"), tr("large"), tr("category"), tr("active")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_selected)
        ll.addWidget(self.table)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.mode_lbl = QLabel(tr("new_profile"))
        self.mode_lbl.setStyleSheet("color: #39d98a; font-weight: 700;")
        rl.addWidget(self.mode_lbl)

        form_g = QGroupBox(tr("food_details"))
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.price_s = QDoubleSpinBox()
        self.price_s.setRange(0, 1_000_000)
        self.price_s.setDecimals(0)
        self.price_m = QDoubleSpinBox()
        self.price_m.setRange(0, 1_000_000)
        self.price_m.setDecimals(0)
        self.price_l = QDoubleSpinBox()
        self.price_l.setRange(0, 1_000_000)
        self.price_l.setDecimals(0)
        for sp in (self.price_s, self.price_m, self.price_l):
            sp.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.cat_edit = QComboBox()
        self.cat_edit.setEditable(True)
        self.cat_edit.addItems(["Main", "Appetizer", "Drink", "Dessert", "Grill", "Traditional"])
        self.prep_spin = QSpinBox()
        self.prep_spin.setRange(1, 120)
        self.prep_spin.setValue(15)
        self.prep_spin.setSuffix(" ′")
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText(tr("description"))
        self.avail_chk = QCheckBox(tr("available"))
        self.avail_chk.setChecked(True)
        self.img_lbl = QLabel(tr("no_photo"))
        self.img_lbl.setFixedHeight(100)
        self.img_lbl.setAlignment(Qt.AlignCenter)
        self.img_lbl.setStyleSheet("background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.12);border-radius:10px;")
        img_btn = QPushButton(tr("upload_photo"))
        img_btn.clicked.connect(self.upload_image)

        form.addRow(tr("food_name"), self.name_edit)
        form.addRow(tr("price_small"), self.price_s)
        form.addRow(tr("price_medium"), self.price_m)
        form.addRow(tr("price_large"), self.price_l)
        form.addRow(tr("category"), self.cat_edit)
        form.addRow(tr("prep_minutes"), self.prep_spin)
        form.addRow(tr("description"), self.desc_edit)
        form.addRow("", self.avail_chk)
        form.addRow(tr("photo"), self.img_lbl)
        form.addRow("", img_btn)
        form_g.setLayout(form)
        rl.addWidget(form_g)

        btns = QHBoxLayout()
        self.save_btn = QPushButton(tr("save_profile"))
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_food)
        clear_btn = QPushButton(tr("clear"))
        clear_btn.clicked.connect(self.clear_form)
        del_btn = QPushButton(tr("delete"))
        del_btn.setObjectName("DangerButton")
        del_btn.clicked.connect(self.delete_food)
        btns.addWidget(self.save_btn)
        btns.addWidget(clear_btn)
        btns.addWidget(del_btn)
        rl.addLayout(btns)
        rl.addStretch()
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split)

    def load_foods(self):
        session = get_session()
        try:
            foods = session.query(Food).order_by(Food.name).all()
            self.table.setRowCount(0)
            for i, f in enumerate(foods):
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(f.name))
                self.table.setItem(i, 1, QTableWidgetItem(f"{f.price_small:,.0f}"))
                self.table.setItem(i, 2, QTableWidgetItem(f"{f.price_medium:,.0f}"))
                self.table.setItem(i, 3, QTableWidgetItem(f"{f.price_large:,.0f}"))
                self.table.setItem(i, 4, QTableWidgetItem(f.category or ""))
                self.table.setItem(i, 5, QTableWidgetItem("✓" if f.available else "—"))
                self.table.item(i, 0).setData(Qt.UserRole, f.id)
        except Exception as e:
            log_exception("kitchen.FoodMenuPage.load_foods", e)
            QMessageBox.critical(self, tr("error"), "بارگذاری فهرست غذاها ناموفق بود.")
        finally:
            session.close()

    def clear_form(self):
        self.current_id = None
        self.image_path = ""
        self.name_edit.clear()
        self.price_s.setValue(0)
        self.price_m.setValue(0)
        self.price_l.setValue(0)
        self.cat_edit.setCurrentIndex(0)
        self.prep_spin.setValue(15)
        self.desc_edit.clear()
        self.avail_chk.setChecked(True)
        self.img_lbl.setText(tr("no_photo"))
        self.img_lbl.setPixmap(QPixmap())
        self.save_btn.setText(tr("save_profile"))
        self.mode_lbl.setText(tr("new_profile"))
        self.mode_lbl.setStyleSheet("color: #39d98a; font-weight: 700;")

    def edit_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        fid = self.table.item(row, 0).data(Qt.UserRole)
        session = get_session()
        try:
            f = session.query(Food).get(fid)
            if not f:
                return
            self.current_id = f.id
            self.name_edit.setText(f.name)
            self.price_s.setValue(f.price_small or 0)
            self.price_m.setValue(f.price_medium or 0)
            self.price_l.setValue(f.price_large or 0)
            self.cat_edit.setCurrentText(f.category or "Main")
            self.prep_spin.setValue(int(getattr(f, "prep_minutes", 15) or 15))
            self.desc_edit.setText(getattr(f, "description", "") or "")
            self.avail_chk.setChecked(bool(f.available))
            self.image_path = f.image_path or ""
            if self.image_path and Path(self.image_path).exists():
                pix = QPixmap(self.image_path).scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.img_lbl.setPixmap(pix)
            else:
                self.img_lbl.setText(tr("no_photo"))
            self.save_btn.setText(tr("update_profile"))
            self.mode_lbl.setText(tr("edit_profile", name=f.name))
            self.mode_lbl.setStyleSheet("color: #f5c76e; font-weight: 700;")
        except Exception as e:
            log_exception("kitchen.FoodMenuPage.edit_selected", e, context={"food_id": fid})
        finally:
            session.close()

    def upload_image(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "عکس غذا", "", "Images (*.png *.jpg *.jpeg *.webp)")
            if not path:
                return
            ext = Path(path).suffix.lower() or ".jpg"
            dest = UPLOAD_DIR / f"food_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
            shutil.copy2(path, dest)
            self.image_path = str(dest)
            pix = QPixmap(str(dest)).scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_lbl.setPixmap(pix)
        except Exception as e:
            log_exception("kitchen.FoodMenuPage.upload_image", e)
            QMessageBox.critical(self, tr("error"), "بارگذاری عکس ناموفق بود.")

    def save_food(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("error"), tr("required_name"))
            return
        session = get_session()
        try:
            if self.current_id is None:
                if session.query(Food).filter_by(name=name).first():
                    QMessageBox.warning(self, tr("warning"), tr("duplicate"))
                    return
                f = Food(name=name, created_at=now_iso())
                session.add(f)
            else:
                f = session.query(Food).get(self.current_id)
                if not f:
                    return
                f.name = name
            old_image = f.image_path or ""
            f.price_small = self.price_s.value()
            f.price_medium = self.price_m.value()
            f.price_large = self.price_l.value()
            f.category = self.cat_edit.currentText().strip()
            f.prep_minutes = self.prep_spin.value()
            f.description = self.desc_edit.text().strip()[:300]
            f.available = self.avail_chk.isChecked()
            f.image_path = self.image_path
            session.commit()
            if old_image and old_image != self.image_path:
                delete_food_image(old_image)  # replaced photo — drop the orphaned file
            QMessageBox.information(self, tr("saved"), tr("saved_ok", name=name))
            self.clear_form()
            self.load_foods()
        except Exception as e:
            session.rollback()
            log_exception("kitchen.FoodMenuPage.save_food", e, context={"name": name})
            QMessageBox.critical(self, tr("error"), "ذخیره غذا ناموفق بود. جزئیات ثبت شد.")
        finally:
            session.close()

    def delete_food(self):
        if self.current_id is None:
            QMessageBox.information(self, tr("delete"), tr("select_first"))
            return
        reply = QMessageBox.question(self, tr("delete"), tr("delete_confirm"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        session = get_session()
        try:
            f = session.query(Food).get(self.current_id)
            if f:
                image_path = f.image_path or ""
                session.delete(f)
                session.commit()
                delete_food_image(image_path)
            self.clear_form()
            self.load_foods()
        except Exception as e:
            session.rollback()
            log_exception("kitchen.FoodMenuPage.delete_food", e, context={"food_id": self.current_id})
            QMessageBox.critical(self, tr("error"), "حذف غذا ناموفق بود.")
        finally:
            session.close()


# ─────────────────────────────────────────────
# Accounting page (desktop)
# ─────────────────────────────────────────────
