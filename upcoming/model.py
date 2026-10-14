"""Events, fuzzy release dates and countdown text. No Qt in here.

An event is a plain dict (that is what lands in events.json):

    {"id": "a1b2c3d4", "title": "Some Game", "when": "2027-02-04",
     "category": "Game", "note": "PS5, PC", "url": ""}

`when` can be as precise as the announcement is:

    2027-02-04   an exact day
    2027-02      sometime in February 2027
    2027-Q1      sometime in the first quarter
    2027         sometime in 2027
    TBA          no date yet
"""
from __future__ import annotations

import calendar
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

PRECISIONS = ("day", "month", "quarter", "year", "tba")
PRECISION_LABELS = {
    "day": "Exact day", "month": "Month", "quarter": "Quarter",
    "year": "Year", "tba": "TBA (no date yet)",
}

PALETTE = [
    "#56D07A", "#E04FB0", "#7C6CE8", "#3FC1E0", "#E0A03F",
    "#E0703F", "#9BD04F", "#4FA8E0", "#D2526E", "#E0C13F",
]

DEFAULT_CATEGORIES = {
    "Game": "#56D07A",
    "Movie": "#E04FB0",
    "TV": "#7C6CE8",
    "Event": "#3FC1E0",
    "Birthday": "#E0A03F",
}

_DAY = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_MONTH = re.compile(r"^(\d{4})-(\d{1,2})$")
_QUARTER = re.compile(r"^(\d{4})-?Q([1-4])$", re.I)
_YEAR = re.compile(r"^(\d{4})$")


# --------------------------------------------------------------------------- #
# dates
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class When:
    precision: str          # one of PRECISIONS
    start: date | None      # earliest possible day
    end: date | None        # latest possible day

    @property
    def dated(self) -> bool:
        return self.start is not None


def parse_when(s) -> When:
    s = str(s or "").strip()
    try:
        if m := _DAY.match(s):
            d = date(int(m[1]), int(m[2]), int(m[3]))
            return When("day", d, d)
        if m := _MONTH.match(s):
            y, mo = int(m[1]), int(m[2])
            return When("month", date(y, mo, 1),
                        date(y, mo, calendar.monthrange(y, mo)[1]))
        if m := _QUARTER.match(s):
            y, q = int(m[1]), int(m[2])
            m0 = 3 * (q - 1) + 1
            return When("quarter", date(y, m0, 1),
                        date(y, m0 + 2, calendar.monthrange(y, m0 + 2)[1]))
        if m := _YEAR.match(s):
            y = int(m[1])
            return When("year", date(y, 1, 1), date(y, 12, 31))
    except ValueError:
        pass
    return When("tba", None, None)


def canonical(s) -> str:
    """Normalise user input: '2027-2-4' -> '2027-02-04', 'q1 2027' handled too."""
    raw = str(s or "").strip()
    m = re.match(r"^Q([1-4])\s+(\d{4})$", raw, re.I)
    if m:
        raw = f"{m[2]}-Q{m[1]}"
    w = parse_when(raw)
    return build_when(w.precision, w.start) if w.dated else "TBA"


def build_when(precision: str, d: date | None) -> str:
    if precision == "tba" or d is None:
        return "TBA"
    if precision == "day":
        return d.isoformat()
    if precision == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if precision == "quarter":
        return f"{d.year:04d}-Q{(d.month - 1) // 3 + 1}"
    return f"{d.year:04d}"


def fmt_day(d: date, today: date) -> str:
    s = d.strftime("%a %d %b").replace(" 0", " ")
    return s if d.year == today.year else f"{s} {d.year}"


def fmt_when(s, today: date | None = None) -> str:
    today = today or date.today()
    w = parse_when(s)
    if w.precision == "day":
        return fmt_day(w.start, today)
    if w.precision == "month":
        return w.start.strftime("%B %Y")
    if w.precision == "quarter":
        return f"Q{(w.start.month - 1) // 3 + 1} {w.start.year}"
    if w.precision == "year":
        return str(w.start.year)
    return "TBA"


def group_label(s, today: date | None = None) -> str:
    """Section header the event is listed under."""
    w = parse_when(s)
    if w.precision in ("day", "month"):
        return w.start.strftime("%B %Y")
    return fmt_when(s, today)


def _months_between(a: date, b: date) -> float:
    return (b - a).days / 30.44


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


# --------------------------------------------------------------------------- #
# countdown
# --------------------------------------------------------------------------- #
@dataclass
class Countdown:
    big: str        # the number column: "114", "Today", "3–6", "TBA"
    small: str      # under it: "days", "days ago", "months"
    state: str      # future | today | past | soon | tba
    days: int | None = None   # days to the earliest possible date


def countdown(s, today: date | None = None) -> Countdown:
    today = today or date.today()
    w = parse_when(s)
    if not w.dated:
        return Countdown("TBA", "", "tba")
    if w.precision == "day":
        n = (w.start - today).days
        if n == 0:
            return Countdown("Today", "", "today", 0)
        if n > 0:
            return Countdown(f"{n:,}", "day" if n == 1 else "days", "future", n)
        return Countdown(f"{-n:,}", "day ago" if n == -1 else "days ago", "past", n)

    n = (w.start - today).days
    if today > w.end:
        ago = (today - w.end).days
        return Countdown("Past", "", "past", -ago)
    if today >= w.start:
        return Countdown("Soon", f"this {w.precision}", "soon", 0)
    if n < 45:
        # Close enough that days mean more than months: "at least n days".
        return Countdown(f"{n:,}+", "days", "future", n)
    lo = int(_months_between(today, w.start))
    hi = max(lo + 1, int(-(-_months_between(today, w.end) // 1)))
    return Countdown(f"{lo}–{hi}", "months", "future", n)


def countdown_tooltip(ev: dict, today: date | None = None) -> str:
    today = today or date.today()
    w = parse_when(ev.get("when"))
    lines = [ev.get("title") or "Untitled"]
    if ev.get("category"):
        lines[0] += f"  ·  {ev['category']}"
    if w.precision == "day":
        lines.append(w.start.strftime("%A %d %B %Y"))
        n = (w.start - today).days
        if n > 0:
            wk, d = divmod(n, 7)
            extra = (f"{plural(wk, 'week')}" + (f" {plural(d, 'day')}" if d else "")
                     if wk else "")
            lines.append(f"In {plural(n, 'day')}" + (f"  ({extra})" if extra else "")
                         + (f"  ·  ~{n / 30.44:.1f} months" if n >= 60 else ""))
        elif n == 0:
            lines.append("That's today!")
        else:
            lines.append(f"{plural(-n, 'day')} ago")
    elif w.dated:
        lines.append(f"Sometime {fmt_when(ev['when'], today)}  "
                     f"({fmt_day(w.start, today)} – {fmt_day(w.end, today)})")
        if today < w.start:
            lines.append(f"Earliest in {plural((w.start - today).days, 'day')}, "
                         f"latest in {plural((w.end - today).days, 'day')}")
    else:
        lines.append("No release date announced yet")
    if ev.get("note"):
        lines.append(ev["note"])
    if ev.get("url"):
        lines.append(ev["url"])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# ordering / filtering
# --------------------------------------------------------------------------- #
def sort_key(ev: dict):
    """Exact dates by day; fuzzy ones sit at the END of their window (a 'Q1'
    game comes after every dated March release), TBA last."""
    w = parse_when(ev.get("when"))
    if not w.dated:
        return (1, date.max, 9, (ev.get("title") or "").lower())
    return (0, w.end, PRECISIONS.index(w.precision), (ev.get("title") or "").lower())


def is_past(ev: dict, today: date | None = None) -> bool:
    today = today or date.today()
    w = parse_when(ev.get("when"))
    return w.dated and w.end < today


def past_age(ev: dict, today: date | None = None) -> int:
    today = today or date.today()
    w = parse_when(ev.get("when"))
    return (today - w.end).days if w.dated else 0


def visible_events(events: list[dict], keep_past_days: int = 7,
                   hidden_categories=(), today: date | None = None) -> list[dict]:
    today = today or date.today()
    hidden = {c.lower() for c in hidden_categories}
    out = []
    for ev in events:
        if (ev.get("category") or "").lower() in hidden:
            continue
        if is_past(ev, today) and past_age(ev, today) > keep_past_days:
            continue
        out.append(ev)
    return sorted(out, key=sort_key)


# --------------------------------------------------------------------------- #
# construction
# --------------------------------------------------------------------------- #
def new_id() -> str:
    return uuid.uuid4().hex[:8]


def new_event(title: str = "", when: str = "", category: str = "",
              note: str = "", url: str = "") -> dict:
    return {"id": new_id(), "title": title, "when": canonical(when) if when else
            (date.today() + timedelta(days=30)).isoformat(),
            "category": category, "note": note, "url": url}


def normalize(ev: dict) -> dict:
    out = new_event()
    out.update({k: v for k, v in ev.items() if v is not None})
    for k in ("id", "title", "category", "note", "url"):
        out[k] = str(out.get(k) or "").strip()
    out["id"] = out["id"] or new_id()
    out["when"] = canonical(out.get("when"))
    return out


def is_color(v) -> bool:
    return isinstance(v, str) and len(v) == 7 and v.startswith("#") and all(
        c in "0123456789abcdefABCDEF" for c in v[1:])


def sample_events(today: date | None = None) -> list[dict]:
    today = today or date.today()
    return [
        new_event("Example game", "2027-02-04", "Game", "PS5, Xbox, PC"),
        new_event("Example film", (today + timedelta(days=12)).isoformat(), "Movie",
                  "Cinemas"),
        new_event("Example sequel", f"{today.year + 1}-Q2", "Game", "PC"),
        new_event("Example remake", "TBA", "Game"),
    ]
