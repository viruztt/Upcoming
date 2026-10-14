"""The floating, edge-docked list of upcoming dates."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QDesktopServices, QFont, QFontMetrics,
    QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon, QToolTip,
    QWidget,
)

from . import config as cfg_mod
from . import model

BG = QColor(14, 15, 20, 225)
TEXT = QColor(238, 240, 245)
MUTED = QColor(150, 156, 170)
FAINT = QColor(255, 255, 255, 22)
ACCENT = QColor("#3FC1E0")

SNAP_PX = 40          # release this close to an edge and the widget docks to it
PAD = 10


@dataclass
class Item:
    kind: str                 # title | plus | header | event | up | down | empty
    rect: QRectF
    text: str = ""
    event: dict | None = None


class UpcomingWindow(QWidget):
    def __init__(self, cfg: dict, store):
        super().__init__()
        self.cfg = cfg
        self.store = store
        self.items: list[Item] = []
        self.offset = 0
        self.total = 0
        self._hover: Item | None = None
        self._press_pos: QPoint | None = None
        self._press_item: Item | None = None
        self._drag_offset: QPoint | None = None
        self._dragged = False
        self._editor = None
        self._today = date.today()

        self.setWindowTitle("Upcoming")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self._apply_flags()
        self.setWindowOpacity(float(cfg.get("opacity", 0.93)))
        self.setMouseTracking(True)

        self._tray()
        self.relayout()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60_000)
        self.watch = QTimer(self)
        self.watch.timeout.connect(self._check_disk)
        self.watch.start(2000)
        QTimer.singleShot(3000, self._notify_today)

        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda *_: QTimer.singleShot(500, self.place))
        app.screenRemoved.connect(lambda *_: QTimer.singleShot(500, self.place))

    # ------------------------------------------------------------------ #
    # fonts
    # ------------------------------------------------------------------ #
    def _fonts(self):
        pt = float(self.cfg.get("font_size", 10))
        base = QFont(self.font())
        base.setPointSizeF(pt)

        def f(size, bold=False, spacing=None):
            x = QFont(base)
            x.setPointSizeF(max(6.5, size))
            x.setBold(bold)
            if spacing:
                x.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
            return x

        return {
            "heading": f(pt + 1.5, True),
            "header": f(pt - 2, True, 0.8),
            "title": f(pt, True),
            "meta": f(pt - 1),
            "big": f(pt + 3, True),
            "small": f(pt - 2),
        }

    def _count_w(self, fonts) -> int:
        big, small = QFontMetrics(fonts["big"]), QFontMetrics(fonts["small"])
        return max(big.horizontalAdvance("0000"), big.horizontalAdvance("Today"),
                   small.horizontalAdvance("this quarter")) + 2

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _events(self) -> list[dict]:
        return model.visible_events(
            self.store.events, int(self.cfg.get("keep_past_days", 3)),
            self.cfg.get("hidden_categories", []), self._today)

    def relayout(self) -> None:
        self._today = date.today()
        fonts = self._fonts()
        fm = {k: QFontMetrics(v) for k, v in fonts.items()}
        w = int(self.cfg.get("width", 300))
        rows = int(self.cfg.get("max_rows", 10))
        events = self._events()
        self.total = len(events)
        self.offset = max(0, min(self.offset, self.total - rows))
        shown = events[self.offset:self.offset + rows]

        items: list[Item] = []
        y = 6.0
        heading = (self.cfg.get("title") or "").strip()
        if heading:
            h = fm["heading"].height() + 10
            items.append(Item("title", QRectF(0, y, w, h), heading))
            s = h - 10
            items.append(Item("plus", QRectF(w - PAD - s, y + 5, s, s)))
            y += h
        if self.offset > 0:
            h = fm["meta"].height() + 6
            items.append(Item("up", QRectF(0, y, w, h), f"▲  {self.offset} earlier"))
            y += h

        last_group = None
        for ev in shown:
            if self.cfg.get("group_by_month", True):
                g = model.group_label(ev["when"], self._today)
                if g != last_group:
                    h = fm["header"].height() + 10
                    items.append(Item("header", QRectF(0, y, w, h), g.upper()))
                    y += h
                    last_group = g
            h = fm["title"].height() + fm["meta"].height() + 12
            items.append(Item("event", QRectF(0, y, w, h), event=ev))
            y += h

        below = self.total - self.offset - len(shown)
        if below > 0:
            h = fm["meta"].height() + 6
            items.append(Item("down", QRectF(0, y, w, h), f"▼  {below} more"))
            y += h
        if not self.total:
            h = fm["meta"].height() * 2 + 16
            text = ("Nothing coming up.\nRight-click → Add event"
                    if not self.store.events else "Nothing to show — check\n"
                    "the category filter or past-events setting")
            items.append(Item("empty", QRectF(0, y, w, h), text))
            y += h

        self.items = items
        self._hover = None
        self.setFixedSize(w, int(y + 6))
        self.update()
        self.place()

    def _item_at(self, pos) -> Item | None:
        p = QPointF(pos)
        hit = None
        for it in self.items:
            if it.rect.contains(p):
                hit = it          # 'plus' sits inside 'title'; the later one wins
        return hit

    # ------------------------------------------------------------------ #
    # painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.fillPath(path, BG)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
        p.drawPath(path)

        fonts = self._fonts()
        count_w = self._count_w(fonts)
        for it in self.items:
            getattr(self, f"_paint_{it.kind}")(p, it, fonts, count_w)

    def _paint_title(self, p, it, fonts, _cw):
        p.setFont(fonts["heading"])
        p.setPen(TEXT)
        p.drawText(it.rect.adjusted(PAD + 2, 0, -PAD - 30, 0),
                   Qt.AlignLeft | Qt.AlignVCenter, it.text)

    def _paint_plus(self, p, it, _f, _cw):
        hover = self._hover is it
        c = QColor(ACCENT)
        c.setAlpha(255 if hover else 150)
        p.setPen(QPen(c, 1.2))
        p.setBrush(QColor(63, 193, 224, 40) if hover else Qt.NoBrush)
        p.drawEllipse(it.rect.adjusted(1, 1, -1, -1))
        cx, cy, s = it.rect.center().x(), it.rect.center().y(), it.rect.width() * 0.25
        p.setPen(QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - s, cy), QPointF(cx + s, cy))
        p.drawLine(QPointF(cx, cy - s), QPointF(cx, cy + s))

    def _paint_header(self, p, it, fonts, _cw):
        fm = QFontMetrics(fonts["header"])
        p.setFont(fonts["header"])
        p.setPen(MUTED)
        tr = it.rect.adjusted(PAD + 2, 4, -PAD, 0)
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, it.text)
        x = tr.left() + fm.horizontalAdvance(it.text) + 8
        y = tr.center().y() + 0.5
        if x < tr.right():
            p.setPen(QPen(FAINT, 1.0))
            p.drawLine(QPointF(x, y), QPointF(tr.right(), y))

    def _paint_event(self, p, it, fonts, count_w):
        ev = it.event
        cd = model.countdown(ev["when"], self._today)
        color = QColor(self.store.color_for(ev.get("category", "")))
        row = it.rect.adjusted(4, 1, -4, -1)
        dim = cd.state == "past"

        if cd.state == "today":
            bg = QColor(color)
            bg.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(row, 6, 6)
        if self._hover is it:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(row, 6, 6)

        bar = QColor(color)
        if dim:
            bar.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(bar)
        p.drawRoundedRect(QRectF(PAD, row.top() + 6, 3.5, row.height() - 12), 1.75, 1.75)

        x = PAD + 12
        tw = self.width() - x - count_w - PAD - 8
        tfm, mfm = QFontMetrics(fonts["title"]), QFontMetrics(fonts["meta"])
        y0 = row.top() + (row.height() - tfm.height() - mfm.height()) / 2

        p.setFont(fonts["title"])
        p.setPen(MUTED if dim else TEXT)
        p.drawText(QRectF(x, y0, tw, tfm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   tfm.elidedText(ev.get("title") or "Untitled", Qt.ElideRight, int(tw)))
        meta = model.fmt_when(ev["when"], self._today)
        if ev.get("note"):
            meta += "  ·  " + ev["note"]
        p.setFont(fonts["meta"])
        p.setPen(MUTED)
        p.drawText(QRectF(x, y0 + tfm.height(), tw, mfm.height()),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   mfm.elidedText(meta, Qt.ElideRight, int(tw)))

        # countdown column
        cx = self.width() - PAD - count_w
        bfm, sfm = QFontMetrics(fonts["big"]), QFontMetrics(fonts["small"])
        big_c = MUTED if cd.state in ("past", "tba") else (
            QColor(color).lighter(115) if cd.state in ("today", "soon") or
            (cd.days is not None and cd.days <= 7) else TEXT)
        if cd.small:
            by = row.top() + (row.height() - bfm.height() - sfm.height() + 2) / 2
            p.setFont(fonts["big"])
            p.setPen(big_c)
            p.drawText(QRectF(cx, by, count_w, bfm.height()),
                       Qt.AlignRight | Qt.AlignVCenter, cd.big)
            p.setFont(fonts["small"])
            p.setPen(MUTED)
            p.drawText(QRectF(cx, by + bfm.height() - 2, count_w, sfm.height()),
                       Qt.AlignRight | Qt.AlignVCenter, cd.small)
        else:
            p.setFont(fonts["big"])
            p.setPen(big_c)
            p.drawText(QRectF(cx, row.top(), count_w, row.height()),
                       Qt.AlignRight | Qt.AlignVCenter, cd.big)

    def _paint_more(self, p, it, fonts, _cw):
        p.setFont(fonts["meta"])
        p.setPen(TEXT if self._hover is it else MUTED)
        p.drawText(it.rect, Qt.AlignCenter, it.text)

    _paint_up = _paint_more
    _paint_down = _paint_more

    def _paint_empty(self, p, it, fonts, _cw):
        p.setFont(fonts["meta"])
        p.setPen(MUTED)
        p.drawText(it.rect.adjusted(PAD, 0, -PAD, 0), Qt.AlignCenter, it.text)

    # ------------------------------------------------------------------ #
    # mouse
    # ------------------------------------------------------------------ #
    def event(self, e):
        if e.type() == QEvent.ToolTip:
            it = self._item_at(e.pos())
            tip = ""
            if it and it.kind == "event":
                tip = model.countdown_tooltip(it.event, self._today)
                tip += "\n\nDouble-click to edit"
            elif it and it.kind == "plus":
                tip = "Add event"
            elif it and it.kind in ("up", "down"):
                tip = "Click or scroll to see more"
            if tip:
                QToolTip.showText(e.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._press_item = self._item_at(e.position())
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._dragged = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            gp = e.globalPosition().toPoint()
            if not self._dragged and (gp - self._press_pos).manhattanLength() < 5:
                return
            self._dragged = True
            self.move(gp - self._drag_offset)
            return
        it = self._item_at(e.position())
        if it is not self._hover:
            self._hover = it
            self.setCursor(Qt.PointingHandCursor if it and it.kind in ("plus", "up", "down")
                           else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, _):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_offset is None:
            return
        self._drag_offset = None
        if not self._dragged:
            it = self._press_item
            if it and it.kind == "plus":
                self.edit_events(new=True)
            elif it and it.kind == "up":
                self.scroll(-max(1, int(self.cfg.get("max_rows", 10)) - 1))
            elif it and it.kind == "down":
                self.scroll(max(1, int(self.cfg.get("max_rows", 10)) - 1))
            return
        scr = QGuiApplication.screenAt(self.frameGeometry().center()) or self._screen()
        g = scr.availableGeometry()
        fg = self.frameGeometry()
        if abs(fg.right() - g.right()) <= SNAP_PX:
            self.cfg["dock"] = "right"
        elif abs(fg.left() - g.left()) <= SNAP_PX:
            self.cfg["dock"] = "left"
        else:
            self.cfg["dock"] = "none"
        self._save_position()
        self.place()
        self._save_position()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        it = self._item_at(e.position())
        if it and it.kind == "event":
            self.edit_events(select=it.event["id"])
        elif it is None or it.kind in ("title", "empty", "header"):
            self.edit_events()

    def wheelEvent(self, e):
        steps = -int(e.angleDelta().y() / 120)
        if steps:
            self.scroll(steps)
        e.accept()

    def scroll(self, steps: int) -> None:
        old = self.offset
        rows = int(self.cfg.get("max_rows", 10))
        self.offset = max(0, min(self.offset + steps, self.total - rows))
        if self.offset != old:
            self.relayout()

    # ------------------------------------------------------------------ #
    # placement
    # ------------------------------------------------------------------ #
    def _screen(self):
        pos = self.cfg.get("position") or {}
        if pos.get("x") is not None and pos.get("y") is not None:
            s = QGuiApplication.screenAt(QPoint(int(pos["x"]) + 5, int(pos["y"]) + 5))
            if s is not None:
                return s
        return QGuiApplication.primaryScreen()

    def place(self) -> None:
        if self._dragged and self._drag_offset is not None:
            return  # don't yank the window out from under a drag
        g = self._screen().availableGeometry()
        margin = int(self.cfg.get("margin", 12))
        pos = self.cfg.get("position") or {}
        dock = self.cfg.get("dock", "left")
        w, h = self.width(), self.height()

        if pos.get("y") is not None:
            y = int(pos["y"])
        else:
            va = self.cfg.get("valign", "center")
            y = (g.top() + margin if va == "top" else
                 g.bottom() - h - margin + 1 if va == "bottom" else
                 g.top() + (g.height() - h) // 2)
        if dock == "right":
            x = g.right() - w - margin + 1
        elif dock == "left":
            x = g.left() + margin
        elif pos.get("x") is not None:
            x = int(pos["x"])
        else:
            x = g.left() + margin
        x = max(g.left(), min(x, g.right() - w + 1))
        y = max(g.top(), min(y, g.bottom() - h + 1))
        self.move(x, y)

    def _save_position(self) -> None:
        self.cfg["position"] = {"x": self.x(), "y": self.y()}
        cfg_mod.save(self.cfg)

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _tick(self):
        new_day = date.today() != self._today
        self.relayout()
        if new_day:
            self._notify_today()

    def _check_disk(self):
        if self.store.changed_on_disk() and self.store.load():
            self.relayout()

    def _notify_today(self):
        today = date.today()
        if not self.cfg.get("notify_today", True):
            return
        if self.cfg.get("last_notified") == today.isoformat():
            return
        hidden = {c.lower() for c in self.cfg.get("hidden_categories", [])}
        todays = [e for e in self.store.events
                  if model.countdown(e["when"], today).state == "today"
                  and (e.get("category") or "").lower() not in hidden]
        self.cfg["last_notified"] = today.isoformat()
        cfg_mod.save(self.cfg)
        if todays and QSystemTrayIcon.supportsMessages():
            body = "\n".join(e["title"] + (f"  ({e['category']})" if e.get("category") else "")
                             for e in todays[:6])
            self.tray.showMessage("Today" if len(todays) == 1 else f"Today · {len(todays)}",
                                  body, self.tray.icon(), 8000)

    def edit_events(self, select: str | None = None, new: bool = False):
        from .editor import EditorDialog
        if self._editor is not None:
            self._editor.raise_()
            self._editor.activateWindow()
            return
        dlg = EditorDialog(self.store.events, self.store.categories,
                           select=select, new=new)
        self._editor = dlg
        self.watch.stop()
        try:
            if dlg.exec():
                events, cats = dlg.edited()
                self.store.replace_all(events, cats)
                self.store.save()
        finally:
            self._editor = None
            self.watch.start()
            self.relayout()

    def delete_event(self, eid: str):
        ev = self.store.get(eid)
        if not ev:
            return
        if QMessageBox.question(
                self, "Delete event", f"Delete “{ev['title']}”?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.store.remove(eid)
            self.store.save()
            self.relayout()

    # ------------------------------------------------------------------ #
    # menu
    # ------------------------------------------------------------------ #
    def contextMenuEvent(self, e):
        m = QMenu(self)
        it = self._item_at(e.pos())
        if it and it.kind == "event":
            ev = it.event
            m.addSection(ev["title"] or "Untitled")
            m.addAction("Edit…", lambda i=ev["id"]: self.edit_events(select=i))
            if ev.get("url"):
                m.addAction("Open link", lambda u=ev["url"]: QDesktopServices.openUrl(
                    QUrl.fromUserInput(u)))
            m.addAction("Delete…", lambda i=ev["id"]: self.delete_event(i))
            m.addSeparator()

        m.addAction("Add event…", lambda: self.edit_events(new=True))
        m.addAction("Edit events…", self.edit_events)
        m.addSeparator()

        cats = sorted({e["category"] for e in self.store.events if e.get("category")},
                      key=str.lower)
        if cats:
            cm = m.addMenu("Show categories")
            hidden = {c.lower() for c in self.cfg.get("hidden_categories", [])}
            for c in cats:
                a = cm.addAction(c)
                a.setCheckable(True)
                a.setChecked(c.lower() not in hidden)
                a.setIcon(_dot(self.store.color_for(c)))
                a.toggled.connect(lambda on, cat=c: self._toggle_category(cat, on))

        a = m.addAction("Group by month")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("group_by_month", True)))
        a.toggled.connect(lambda on: self._set("group_by_month", bool(on)))

        self._choices(m.addMenu("Keep past dates for"), "keep_past_days",
                      ((0, "Hide right away"), (1, "1 day"), (3, "3 days"),
                       (7, "1 week"), (30, "1 month")))
        self._choices(m.addMenu("Rows shown"), "max_rows",
                      ((5, "5"), (8, "8"), (10, "10"), (15, "15"), (20, "20"), (30, "30")))
        self._choices(m.addMenu("Width"), "width",
                      ((240, "Narrow"), (300, "Normal"), (360, "Wide"), (440, "Extra wide")))
        m.addAction("Rename heading…", self._rename)

        a = m.addAction("Notify me on the day")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("notify_today", True)))
        a.toggled.connect(lambda on: self._set("notify_today", bool(on)))
        m.addSeparator()

        self._choices(m.addMenu("Dock"), "dock",
                      (("left", "Left edge"), ("right", "Right edge"),
                       ("none", "Floating (drag anywhere)")), self._set_dock)
        self._choices(m.addMenu("Vertical position"), "valign",
                      (("top", "Top"), ("center", "Middle"), ("bottom", "Bottom")),
                      self._set_valign,
                      checked=(self.cfg.get("position") or {}).get("y") is None)
        self._choices(m.addMenu("Window layer"), "window_layer",
                      (("top", "Always on top"), ("normal", "Normal (can be covered)"),
                       ("bottom", "Always at the bottom")), self._set_layer)
        a = m.addAction("Click-through")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("click_through", False)))
        a.toggled.connect(self._set_click_through)
        self._choices(m.addMenu("Opacity"), "opacity",
                      tuple((v, f"{int(v * 100)}%") for v in (1.0, 0.93, 0.8, 0.65, 0.5)),
                      self._set_opacity)
        self._choices(m.addMenu("Text size"), "font_size",
                      tuple((v, f"{v} pt") for v in (8, 9, 10, 11, 12, 14)))
        m.addSeparator()
        m.addAction("Open data file", self._open_data)
        m.addAction("Reset position", self._reset_position)
        m.addAction("Quit", self.quit)
        m.exec(e.globalPos())

    def _choices(self, menu, key, options, handler=None, checked=True):
        handler = handler or (lambda k, v: self._set(k, v))
        grp = QActionGroup(menu)
        cur = self.cfg.get(key)
        for value, text in options:
            act = QAction(text, menu)
            act.setCheckable(True)
            same = abs(float(cur) - value) < 0.01 if isinstance(value, float) else cur == value
            act.setChecked(checked and same)
            act.triggered.connect(lambda _c, v=value, k=key: handler(k, v))
            grp.addAction(act)
            menu.addAction(act)

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def _set(self, key, value):
        self.cfg[key] = value
        cfg_mod.save(self.cfg)
        self.relayout()

    def _toggle_category(self, cat, on):
        hidden = [c for c in self.cfg.get("hidden_categories", []) if c.lower() != cat.lower()]
        if not on:
            hidden.append(cat)
        self._set("hidden_categories", hidden)

    def _rename(self):
        text, ok = QInputDialog.getText(self, "Heading", "Heading (blank hides it):",
                                        text=self.cfg.get("title", ""))
        if ok:
            self._set("title", text.strip())

    def _set_dock(self, _key, value):
        self.cfg["dock"] = value
        if value == "none":
            self.cfg["position"] = {"x": self.x(), "y": self.y()}
        cfg_mod.save(self.cfg)
        self.place()
        self._save_position()

    def _set_valign(self, _key, value):
        self.cfg["valign"] = value
        self.cfg["position"] = {"x": self.x(), "y": None}
        if self.cfg.get("dock") == "none":
            self.cfg["dock"] = "left"
        cfg_mod.save(self.cfg)
        self.place()

    def _apply_flags(self):
        layer = self.cfg.get("window_layer", "normal")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, layer == "top")
        self.setWindowFlag(Qt.WindowStaysOnBottomHint, layer == "bottom")
        self.setWindowFlag(Qt.WindowTransparentForInput,
                           bool(self.cfg.get("click_through", False)))

    def _set_layer(self, _key, value):
        self.cfg["window_layer"] = value
        cfg_mod.save(self.cfg)
        self._apply_flags()
        self.show()

    def _set_click_through(self, on):
        self.cfg["click_through"] = bool(on)
        cfg_mod.save(self.cfg)
        self._apply_flags()
        self.show()
        if self._ct_action.isChecked() != bool(on):
            self._ct_action.setChecked(bool(on))

    def _set_opacity(self, _key, v):
        self.cfg["opacity"] = v
        self.setWindowOpacity(v)
        cfg_mod.save(self.cfg)

    def _reset_position(self):
        self.cfg["dock"] = "left"
        self.cfg["valign"] = "center"
        self.cfg["position"] = {"x": None, "y": None}
        cfg_mod.save(self.cfg)
        self.place()
        self.show()

    def _open_data(self):
        path = str(self.store.path)
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # tray
    # ------------------------------------------------------------------ #
    def _tray(self):
        icon = QIcon(_calendar_icon())
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Upcoming")
        menu = QMenu()
        menu.addAction("Add event…", lambda: self.edit_events(new=True))
        menu.addAction("Edit events…", self.edit_events)
        menu.addAction("Bring to front", self._bring_to_front)
        menu.addAction("Show / hide", lambda: self.setVisible(not self.isVisible()))
        self._ct_action = menu.addAction("Click-through")
        self._ct_action.setCheckable(True)
        self._ct_action.setChecked(bool(self.cfg.get("click_through", False)))
        self._ct_action.toggled.connect(
            lambda on: on != bool(self.cfg.get("click_through")) and self._set_click_through(on))
        menu.addAction("Reset position", self._reset_position)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.setVisible(not self.isVisible())
            if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        self.setWindowIcon(icon)

    def _bring_to_front(self):
        """The widget has no taskbar button, so this is how you get it back."""
        self.show()
        self.raise_()
        self.activateWindow()

    def quit(self):
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        self.quit()
        e.accept()


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


def _calendar_icon() -> QPixmap:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(238, 240, 245))
    p.drawRoundedRect(QRectF(6, 10, 52, 48), 8, 8)
    p.setBrush(QColor("#E0703F"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(6, 10, 52, 18), 8, 8)
    path.addRect(QRectF(6, 20, 52, 8))
    p.drawPath(path.simplified())
    p.setBrush(QColor(20, 21, 26))
    for i in range(3):
        for j in range(2):
            p.drawRoundedRect(QRectF(14 + i * 14, 34 + j * 12, 8, 7), 1.5, 1.5)
    p.setBrush(QColor(60, 62, 70))
    p.drawRoundedRect(QRectF(18, 4, 6, 12), 3, 3)
    p.drawRoundedRect(QRectF(40, 4, 6, 12), 3, 3)
    p.end()
    return pm
