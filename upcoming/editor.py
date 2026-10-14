"""Add / edit events. Dates can be exact or fuzzy (month, quarter, year, TBA)."""
from __future__ import annotations

import copy
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QStackedWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import model

SURFACE = "#14151a"
PANEL = "#1a1c24"
INK = "#eef0f5"
INK_MUTED = "#7c8394"

STYLE = f"""
QDialog {{ background: {SURFACE}; }}
QLabel {{ color: {INK}; }}
QLabel#hint {{ color: {INK_MUTED}; }}
QLabel#preview {{
    background: {PANEL}; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 6px; padding: 8px 10px;
}}
QTreeWidget {{
    background: {PANEL}; color: {INK}; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 6px; outline: none;
}}
QTreeWidget::item {{ padding: 4px 2px; }}
QTreeWidget::item:selected {{ background: rgba(63,193,224,0.22); color: {INK}; }}
QHeaderView::section {{
    background: {SURFACE}; color: {INK_MUTED}; border: none;
    border-bottom: 1px solid rgba(255,255,255,0.10); padding: 4px 6px;
}}
QLineEdit, QComboBox, QSpinBox, QDateEdit, QPushButton {{
    background: {PANEL}; color: {INK};
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 5px; padding: 4px 8px; min-height: 18px;
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    width: 0px; border: none;
}}
QPushButton:hover, QComboBox:hover {{ border-color: rgba(255,255,255,0.3); }}
QCheckBox {{ color: {INK}; }}
QPushButton#swatch {{ border-radius: 10px; padding: 0; min-height: 0; }}
"""

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _dot(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def _year_box() -> QSpinBox:
    b = QSpinBox()
    b.setRange(1900, 2200)
    b.setValue(date.today().year)
    return b


class EditorDialog(QDialog):
    def __init__(self, events: list[dict], categories: dict[str, str],
                 select: str | None = None, new: bool = False, parent=None):
        super().__init__(parent)
        self.items = copy.deepcopy(events)
        self.cats = dict(categories)
        self._loading = False
        self._today = date.today()
        self.setWindowTitle("Upcoming — events")
        self.setStyleSheet(STYLE)
        self.resize(900, 520)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(14)

        # ---- left: list --------------------------------------------------- #
        left = QVBoxLayout()
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self._fill(self._current_id()))
        top.addWidget(self.search, 1)
        self.show_past = QCheckBox("Show past")
        self.show_past.toggled.connect(lambda: self._fill(self._current_id()))
        top.addWidget(self.show_past)
        left.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Date", "Title", "In"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setUniformRowHeights(True)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        self.tree.currentItemChanged.connect(lambda *_: self._on_select())
        left.addWidget(self.tree, 1)

        row = QHBoxLayout()
        b = QPushButton("Add")
        b.clicked.connect(self._add)
        row.addWidget(b)
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.clicked.connect(self._duplicate)
        row.addWidget(self.dup_btn)
        self.del_btn = QPushButton("Delete")
        self.del_btn.clicked.connect(self._delete)
        row.addWidget(self.del_btn)
        row.addStretch(1)
        b = QPushButton("Clear past…")
        b.setToolTip("Delete every event whose date has passed")
        b.clicked.connect(self._clear_past)
        row.addWidget(b)
        left.addLayout(row)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMinimumWidth(420)
        root.addWidget(lw, 5)

        # ---- right: form -------------------------------------------------- #
        right = QVBoxLayout()
        self.form_box = QWidget()
        f = QFormLayout(self.form_box)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setHorizontalSpacing(12)
        f.setVerticalSpacing(9)

        self.title = QLineEdit()
        self.title.setPlaceholderText("e.g. a game, a film, a birthday")
        self.title.textChanged.connect(self._changed)
        f.addRow("Title", self.title)

        self.precision = QComboBox()
        for p in model.PRECISIONS:
            self.precision.addItem(model.PRECISION_LABELS[p], p)
        self.precision.currentIndexChanged.connect(self._precision_changed)
        f.addRow("Date is", self.precision)

        self.date_pages = QStackedWidget()
        self.d_day = QDateEdit()
        self.d_day.setCalendarPopup(True)
        self.d_day.setDisplayFormat("ddd d MMMM yyyy")
        self.d_day.dateChanged.connect(self._changed)
        self.date_pages.addWidget(self.d_day)

        def pair(combo_items):
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            c = QComboBox()
            c.addItems(combo_items)
            c.currentIndexChanged.connect(self._changed)
            y = _year_box()
            y.valueChanged.connect(self._changed)
            lay.addWidget(c, 2)
            lay.addWidget(y, 1)
            return w, c, y

        w, self.m_month, self.m_year = pair(MONTHS)
        self.date_pages.addWidget(w)
        w, self.q_quarter, self.q_year = pair(["Q1 (Jan–Mar)", "Q2 (Apr–Jun)",
                                              "Q3 (Jul–Sep)", "Q4 (Oct–Dec)"])
        self.date_pages.addWidget(w)
        self.y_year = _year_box()
        self.y_year.valueChanged.connect(self._changed)
        self.date_pages.addWidget(self.y_year)
        tba = QLabel("No date yet — listed at the end")
        tba.setObjectName("hint")
        self.date_pages.addWidget(tba)
        f.addRow("When", self.date_pages)

        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setInsertPolicy(QComboBox.NoInsert)
        self.category.lineEdit().setPlaceholderText("Game, Movie, Birthday…")
        self.category.currentTextChanged.connect(self._category_changed)
        f.addRow("Category", self.category)

        sw = QHBoxLayout()
        sw.setSpacing(5)
        self.swatches = []
        for c in model.PALETTE:
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(20, 20)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, col=c: self._set_color(col))
            self.swatches.append((c, b))
            sw.addWidget(b)
        more = QPushButton("…")
        more.setFixedWidth(30)
        more.setToolTip("Custom colour")
        more.clicked.connect(self._pick_color)
        sw.addWidget(more)
        sw.addStretch(1)
        self.color_row = QWidget()
        self.color_row.setLayout(sw)
        sw.setContentsMargins(0, 0, 0, 0)
        f.addRow("Colour", self.color_row)

        self.note = QLineEdit()
        self.note.setPlaceholderText("Platforms, where, who… (shown under the title)")
        self.note.textChanged.connect(self._changed)
        f.addRow("Note", self.note)
        self.url = QLineEdit()
        self.url.setPlaceholderText("Optional — store page, trailer…")
        self.url.textChanged.connect(self._changed)
        f.addRow("Link", self.url)
        right.addWidget(self.form_box)

        hint = QLabel("Colour belongs to the category, so every event in it changes.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        right.addWidget(hint)

        self.preview = QLabel()
        self.preview.setObjectName("preview")
        self.preview.setTextFormat(Qt.RichText)
        right.addWidget(self.preview)
        right.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        rw = QWidget()
        rw.setLayout(right)
        root.addWidget(rw, 4)

        self._refresh_categories()
        if select and any(model.is_past(e, self._today) and e["id"] == select
                          for e in self.items):
            self.show_past.setChecked(True)
        self._fill(select)
        if new:
            self._add()
        self._sync_enabled()

    # ------------------------------------------------------------------ #
    # list
    # ------------------------------------------------------------------ #
    def _current_id(self) -> str | None:
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def _current(self) -> dict | None:
        eid = self._current_id()
        return next((e for e in self.items if e["id"] == eid), None)

    def _matches(self, e) -> bool:
        if not self.show_past.isChecked() and model.is_past(e, self._today):
            return False
        q = self.search.text().strip().lower()
        if not q:
            return True
        return any(q in (e.get(k) or "").lower() for k in ("title", "category", "note"))

    def _fill(self, select: str | None = None):
        self.tree.blockSignals(True)
        self.tree.clear()
        target = None
        for e in sorted(self.items, key=model.sort_key):
            if not self._matches(e) and e["id"] != select:
                continue
            it = QTreeWidgetItem()
            it.setData(0, Qt.UserRole, e["id"])
            self._paint_item(it, e)
            self.tree.addTopLevelItem(it)
            if e["id"] == select:
                target = it
        self.tree.blockSignals(False)
        if target is None and self.tree.topLevelItemCount():
            target = self.tree.topLevelItem(0)
        self.tree.setCurrentItem(target)
        self._on_select()

    def _paint_item(self, it: QTreeWidgetItem, e: dict):
        cd = model.countdown(e["when"], self._today)
        it.setText(0, model.fmt_when(e["when"], self._today))
        it.setText(1, e.get("title") or "Untitled")
        it.setText(2, f"{cd.big} {cd.small}".strip())
        it.setIcon(1, _dot(self._color(e.get("category", ""))))
        it.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
        muted = QColor(INK_MUTED)
        for col in (0, 2):
            it.setForeground(col, muted)
        if cd.state == "past":
            it.setForeground(1, muted)

    def _refresh_items(self):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            e = next((x for x in self.items if x["id"] == it.data(0, Qt.UserRole)), None)
            if e:
                self._paint_item(it, e)

    def _add(self):
        cur = self._current()
        e = model.new_event(category=(cur or {}).get("category", "Game") or "Game")
        e["title"] = ""
        self.items.append(e)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._fill(e["id"])
        self.title.setFocus()

    def _duplicate(self):
        e = self._current()
        if not e:
            return
        c = copy.deepcopy(e)
        c["id"] = model.new_id()
        c["title"] = (e.get("title") or "Untitled") + " (copy)"
        self.items.append(c)
        self._fill(c["id"])

    def _delete(self):
        e = self._current()
        if not e:
            return
        if QMessageBox.question(self, "Delete event",
                                f"Delete “{e.get('title') or 'Untitled'}”?",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        row = self.tree.indexOfTopLevelItem(self.tree.currentItem())
        self.items = [x for x in self.items if x["id"] != e["id"]]
        nxt = self.tree.topLevelItem(row + 1) or self.tree.topLevelItem(row - 1)
        self._fill(nxt.data(0, Qt.UserRole) if nxt else None)
        self._sync_enabled()

    def _clear_past(self):
        past = [e for e in self.items if model.is_past(e, self._today)]
        if not past:
            QMessageBox.information(self, "Clear past", "No past events.")
            return
        if QMessageBox.question(self, "Clear past",
                                f"Delete {model.plural(len(past), 'past event')}?",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        ids = {e["id"] for e in past}
        self.items = [e for e in self.items if e["id"] not in ids]
        self._fill(None)
        self._sync_enabled()

    def _sync_enabled(self):
        has = self._current() is not None
        for w in (self.form_box, self.dup_btn, self.del_btn):
            w.setEnabled(has)
        if not has:
            self.preview.setText("<span style='color:#7c8394'>No event selected</span>")

    # ------------------------------------------------------------------ #
    # categories / colour
    # ------------------------------------------------------------------ #
    def _color(self, cat: str) -> str:
        for n, c in self.cats.items():
            if n.lower() == (cat or "").lower():
                return c
        if not cat:
            return "#8A90A0"
        # A category typed but not saved yet: show the colour it will get.
        used = {c.upper() for c in self.cats.values()}
        free = [c for c in model.PALETTE if c.upper() not in used]
        return free[0] if free else model.PALETTE[len(self.cats) % len(model.PALETTE)]

    def _ensure_category(self, cat: str):
        if not cat or any(n.lower() == cat.lower() for n in self.cats):
            return
        used = {c.upper() for c in self.cats.values()}
        free = [c for c in model.PALETTE if c.upper() not in used]
        self.cats[cat] = free[0] if free else model.PALETTE[len(self.cats) % len(model.PALETTE)]

    def _refresh_categories(self):
        names = sorted({*self.cats, *(e["category"] for e in self.items if e.get("category"))},
                       key=str.lower)
        self._loading, was = True, self._loading
        text = self.category.currentText()
        self.category.clear()
        for n in names:
            self.category.addItem(_dot(self._color(n)), n)
        self._show_category(text)
        self._loading = was

    def _show_category(self, text: str):
        idx = self.category.findText(text, Qt.MatchFixedString)
        if idx >= 0:
            self.category.setCurrentIndex(idx)
        else:
            self.category.setCurrentIndex(-1)
            self.category.setEditText(text)

    def _mark_swatch(self, color: str):
        for c, b in self.swatches:
            ring = "#ffffff" if c.upper() == color.upper() else "rgba(0,0,0,0)"
            b.setStyleSheet(f"background: {c}; border: 2px solid {ring};")

    def _set_color(self, color: str):
        e = self._current()
        cat = (e or {}).get("category", "")
        if not cat:
            QMessageBox.information(self, "Colour", "Give the event a category first — "
                                    "colours belong to categories.")
            return
        key = next((n for n in self.cats if n.lower() == cat.lower()), cat)
        self.cats[key] = color
        self._mark_swatch(color)
        self._refresh_categories()
        self._refresh_items()
        self._update_preview(e)

    def _pick_color(self):
        e = self._current()
        c = QColorDialog.getColor(QColor(self._color((e or {}).get("category", ""))),
                                  self, "Category colour")
        if c.isValid():
            self._set_color(c.name().upper())

    def _category_changed(self, text):
        if self._loading:
            return
        e = self._current()
        if not e:
            return
        e["category"] = text.strip()
        self._mark_swatch(self._color(e["category"]))
        it = self.tree.currentItem()
        if it:
            self._paint_item(it, e)
        self._update_preview(e)

    # ------------------------------------------------------------------ #
    # form <-> event
    # ------------------------------------------------------------------ #
    def _on_select(self):
        e = self._current()
        self._sync_enabled()
        if not e:
            return
        self._loading = True
        try:
            self.title.setText(e.get("title", ""))
            self.note.setText(e.get("note", ""))
            self.url.setText(e.get("url", ""))
            self._show_category(e.get("category", ""))
            self._mark_swatch(self._color(e.get("category", "")))
            w = model.parse_when(e["when"])
            self.precision.setCurrentIndex(model.PRECISIONS.index(w.precision))
            self.date_pages.setCurrentIndex(model.PRECISIONS.index(w.precision))
            self._set_date_inputs(w.start or date(self._today.year + 1, 1, 1))
        finally:
            self._loading = False
        self._update_preview(e)

    def _set_date_inputs(self, d: date):
        self.d_day.setDate(QDate(d.year, d.month, d.day))
        self.m_month.setCurrentIndex(d.month - 1)
        self.m_year.setValue(d.year)
        self.q_quarter.setCurrentIndex((d.month - 1) // 3)
        self.q_year.setValue(d.year)
        self.y_year.setValue(d.year)

    def _date_from_inputs(self, precision: str) -> date:
        if precision == "day":
            q = self.d_day.date()
            return date(q.year(), q.month(), q.day())
        if precision == "month":
            return date(self.m_year.value(), self.m_month.currentIndex() + 1, 1)
        if precision == "quarter":
            return date(self.q_year.value(), self.q_quarter.currentIndex() * 3 + 1, 1)
        return date(self.y_year.value(), 1, 1)

    def _precision_changed(self, idx):
        if self._loading:
            return
        e = self._current()
        if not e:
            return
        old = model.parse_when(e["when"])
        new = model.PRECISIONS[idx]
        # Carry the date across so "Feb 2027" -> exact day starts at 1 Feb 2027.
        if old.dated:
            self._loading = True
            self._set_date_inputs(old.start)
            self._loading = False
        self.date_pages.setCurrentIndex(idx)
        e["when"] = model.build_when(new, self._date_from_inputs(new)) \
            if new != "tba" else "TBA"
        self._after_date_change(e)

    def _changed(self, *_):
        if self._loading:
            return
        e = self._current()
        if not e:
            return
        e["title"] = self.title.text().strip()
        e["note"] = self.note.text().strip()
        e["url"] = self.url.text().strip()
        prec = self.precision.currentData()
        new_when = (model.build_when(prec, self._date_from_inputs(prec))
                    if prec != "tba" else "TBA")
        if new_when != e["when"]:
            e["when"] = new_when
            self._after_date_change(e)
            return
        it = self.tree.currentItem()
        if it:
            self._paint_item(it, e)
        self._update_preview(e)

    def _after_date_change(self, e):
        # Re-sort so the list keeps reading in date order; keep the selection.
        focus = self.focusWidget()
        self._fill(e["id"])
        if focus is not None:
            focus.setFocus()

    def _update_preview(self, e):
        if not e:
            return
        cd = model.countdown(e["when"], self._today)
        color = self._color(e.get("category", ""))
        when = model.fmt_when(e["when"], self._today)
        count = {"today": "today!", "tba": "date to be announced",
                 "soon": f"any day now ({cd.small})"}.get(cd.state)
        if count is None:
            count = (f"{cd.big} {cd.small} ago".replace(" ago ago", " ago")
                     if cd.state == "past" and cd.small else
                     "already past" if cd.state == "past" else
                     f"in {cd.big} {cd.small}")
        title = (e.get("title") or "Untitled").replace("<", "&lt;")
        note = (e.get("note") or "").replace("<", "&lt;")
        self.preview.setText(
            f"<span style='color:{color}'>●</span>&nbsp; <b>{title}</b><br>"
            f"<span style='color:#9aa0ae'>{when}"
            f"{'&nbsp; · &nbsp;' + note if note else ''}</span><br>"
            f"<span style='color:{INK}'>{count}</span>")

    # ------------------------------------------------------------------ #
    def accept(self):
        blank = [e for e in self.items if not e.get("title")]
        if blank:
            for e in blank:
                e["title"] = "Untitled"
        super().accept()

    def edited(self) -> tuple[list[dict], dict[str, str]]:
        for e in self.items:
            self._ensure_category(e.get("category", ""))
        used = {(e.get("category") or "").lower() for e in self.items}
        cats = {n: c for n, c in self.cats.items()
                if n.lower() in used or n in model.DEFAULT_CATEGORIES}
        return self.items, cats
