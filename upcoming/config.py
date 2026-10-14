"""Appearance settings — a plain JSON file next to the app.

The events themselves live in data/events.json (see store.py).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_DATA_PATH = APP_DIR / "data" / "events.json"

DOCKS = ("right", "left", "none")
VALIGNS = ("top", "center", "bottom")

DEFAULTS = {
    "dock": "left",           # "right" | "left" | "none" (free floating)
    "valign": "center",       # where a docked widget sits until you drag it
    "margin": 12,             # gap to the screen edge when docked
    "title": "Upcoming",      # heading; blank hides the heading row
    "width": 300,
    "max_rows": 10,           # events shown at once; scroll the list for more
    "group_by_month": True,
    "keep_past_days": 3,      # how long a passed date stays listed
    "hidden_categories": [],
    "notify_today": True,     # tray notification for today's events
    "font_size": 10,
    "opacity": 0.93,
    "window_layer": "normal",  # "top" | "normal" | "bottom"
    "click_through": False,
    "data_path": "",
    "last_notified": "",
    "position": {"x": None, "y": None},
}


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        except Exception:
            pass
    if cfg["dock"] not in DOCKS:
        cfg["dock"] = "left"
    if cfg["valign"] not in VALIGNS:
        cfg["valign"] = "center"
    if cfg["window_layer"] not in ("top", "normal", "bottom"):
        cfg["window_layer"] = "normal"
    if not isinstance(cfg.get("hidden_categories"), list):
        cfg["hidden_categories"] = []
    if not isinstance(cfg.get("position"), dict):
        cfg["position"] = {"x": None, "y": None}
    for key, lo, hi in (("width", 200, 700), ("max_rows", 3, 40),
                        ("keep_past_days", 0, 365), ("margin", 0, 200)):
        try:
            cfg[key] = max(lo, min(hi, int(cfg[key])))
        except Exception:
            cfg[key] = DEFAULTS[key]
    return cfg


def save(cfg: dict) -> None:
    try:
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass


def data_path(cfg: dict) -> Path:
    p = (cfg.get("data_path") or "").strip()
    return Path(p) if p else DEFAULT_DATA_PATH
