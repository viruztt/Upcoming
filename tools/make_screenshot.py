"""Render the Upcoming widget with demo events to docs/screenshot.png.

Uses made-up events, never your own data/events.json.
    python tools/make_screenshot.py [output.png]
Set QT_SCALE_FACTOR=2 for a high-DPI image.
"""
import json, sys, tempfile, os
from datetime import date, timedelta
from pathlib import Path
app_dir = Path(__file__).resolve().parent.parent
out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else app_dir / "docs" / "screenshot.png"
out.parent.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(app_dir))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QColor, QImage, QLinearGradient
from PySide6.QtCore import Qt, QPoint
from upcoming import config as cfg_mod, model, theme
from upcoming.store import Store
from upcoming.widget import UpcomingWindow

t = date.today()
d = lambda n: (t + timedelta(days=n)).isoformat()
ym = lambda n: f"{(t.replace(day=1)+timedelta(days=32*n)).year}-{(t.replace(day=1)+timedelta(days=32*n)).month:02d}"
demo = [
    model.new_event("Mum's birthday", d(0), "Birthday", ""),
    model.new_event("Indie band live", d(4), "Event", "City Arena"),
    model.new_event("Space opera, part two", d(12), "Movie", "Cinemas"),
    model.new_event("Big open-world RPG", d(38), "Game", "PS5, Xbox, PC"),
    model.new_event("Detective series S3", d(61), "TV", "Streaming"),
    model.new_event("Racing sim", ym(4), "Game", "PC"),
    model.new_event("Platformer sequel", f"{t.year+1}-Q2", "Game", "Switch 2"),
    model.new_event("Classic remake", "TBA", "Game", ""),
]
tmp = Path(tempfile.mkdtemp()) / "events.json"
cfg = json.loads(json.dumps(cfg_mod.DEFAULTS))
cfg.update({"data_path": str(tmp), "max_rows": 12, "notify_today": False, "dock": "none",
            "position": {"x": 40, "y": 40}, "opacity": 1.0})
app = QApplication([])
theme.apply(app)
store = Store(tmp, seed=False); store.events = demo; store.save()
win = UpcomingWindow(cfg, store)
win.show(); app.processEvents()
img = win.grab().toImage()
dpr = img.devicePixelRatio(); img.setDevicePixelRatio(1)
pad = int(28*dpr)
bg = QImage(img.width()+2*pad, img.height()+2*pad, QImage.Format_ARGB32)
p = QPainter(bg)
g = QLinearGradient(0, 0, bg.width(), bg.height())
g.setColorAt(0, QColor("#1f3b57")); g.setColorAt(1, QColor("#3a2448"))
p.fillRect(bg.rect(), g)
p.drawImage(QPoint(pad, pad), img); p.end()
bg.save(str(out))
print(out, bg.width(), bg.height())
