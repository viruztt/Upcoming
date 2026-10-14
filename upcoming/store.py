"""Events on disk: data/events.json.

Written atomically (temp file + os.replace) with one rolling .bak. The file is
meant to be readable and hand-editable: the widget reloads when it changes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import model

VERSION = 1


class Store:
    def __init__(self, path: str | os.PathLike, seed: bool = True):
        self.path = Path(path)
        self.events: list[dict] = []
        self.categories: dict[str, str] = dict(model.DEFAULT_CATEGORIES)
        self._mtime = 0.0
        self.created_fresh = False
        if not self.load() and seed:
            self.events = model.sample_events()
            self.created_fresh = True
            self.save()

    # ------------------------------------------------------------------ #
    def load(self) -> bool:
        for candidate in (self.path, self.path.with_suffix(".json.bak")):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            items = raw.get("events") if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                continue
            out, seen = [], set()
            for ev in items:
                if not isinstance(ev, dict):
                    continue
                ev = model.normalize(ev)
                while ev["id"] in seen:
                    ev["id"] = model.new_id()
                seen.add(ev["id"])
                out.append(ev)
            self.events = out
            cats = raw.get("categories") if isinstance(raw, dict) else None
            if isinstance(cats, dict):
                self.categories = {str(k): v for k, v in cats.items() if model.is_color(v)}
            for ev in out:
                self.ensure_category(ev.get("category", ""))
            self._mtime = self._disk_mtime()
            return True
        return False

    def save(self) -> bool:
        self.events.sort(key=model.sort_key)
        payload = json.dumps({"version": VERSION, "categories": self.categories,
                              "events": self.events}, indent=2, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                try:
                    os.replace(self.path, self.path.with_suffix(".json.bak"))
                except Exception:
                    pass
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.path)
            self._mtime = self._disk_mtime()
            return True
        except Exception:
            return False

    def _disk_mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def changed_on_disk(self) -> bool:
        m = self._disk_mtime()
        return bool(m) and m != self._mtime

    # ------------------------------------------------------------------ #
    def color_for(self, category: str) -> str:
        if not category:
            return "#8A90A0"
        for name, c in self.categories.items():
            if name.lower() == category.lower():
                return c
        return "#8A90A0"

    def ensure_category(self, category: str) -> None:
        """Give a new category the next unused palette colour."""
        if not category or any(n.lower() == category.lower() for n in self.categories):
            return
        used = {c.upper() for c in self.categories.values()}
        free = [c for c in model.PALETTE if c.upper() not in used]
        self.categories[category] = (free or model.PALETTE)[
            0 if free else len(self.categories) % len(model.PALETTE)]

    def get(self, eid: str) -> dict | None:
        return next((e for e in self.events if e["id"] == eid), None)

    def find(self, text: str) -> dict | None:
        """Exact id, then case-insensitive title, then unique title prefix."""
        key = text.strip().lower()
        for e in self.events:
            if e["id"].lower() == key:
                return e
        named = [e for e in self.events if e["title"].lower() == key]
        if named:
            return named[0]
        pref = [e for e in self.events if e["title"].lower().startswith(key)]
        return pref[0] if len(pref) == 1 else None

    def remove(self, eid: str) -> None:
        self.events = [e for e in self.events if e["id"] != eid]

    def replace_all(self, events: list[dict], categories: dict[str, str]) -> None:
        self.events = [model.normalize(e) for e in events]
        self.categories = {k: v for k, v in categories.items() if model.is_color(v)}
        for e in self.events:
            self.ensure_category(e["category"])
