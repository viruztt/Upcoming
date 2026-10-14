"""Entry point: python main.py  (or run.bat)

Flags:
  --list                          print every event with its countdown, then exit
  --add TITLE WHEN [CATEGORY] [NOTE]
                                  add an event; WHEN is 2027-02-04, 2027-02,
                                  2027-Q1, 2027 or TBA
  --remove TITLE                  delete an event (title, unique prefix or id)
  --selftest                      check the date maths and the data file, then exit

A running widget picks up --add / --remove within a couple of seconds.
"""
from __future__ import annotations

import sys


def _store():
    from upcoming import config as cfg_mod
    from upcoming.store import Store
    return Store(cfg_mod.data_path(cfg_mod.load()))


def list_events() -> int:
    from upcoming import model
    store = _store()
    print(f"Upcoming  —  {store.path}\n" + "-" * 72)
    events = sorted(store.events, key=model.sort_key)
    if not events:
        print("(no events)")
    for e in events:
        cd = model.countdown(e["when"])
        count = f"{cd.big} {cd.small}".strip()
        print(f"{model.fmt_when(e['when']):18} {count:>16}   {e['title'][:30]:30}"
              f"  {e.get('category', '')}")
    return 0


def add_event(args: list[str]) -> int:
    from upcoming import model
    if len(args) < 2:
        print("usage: main.py --add TITLE WHEN [CATEGORY] [NOTE]")
        return 2
    title, when = args[0], args[1]
    if model.canonical(when) == "TBA" and when.strip().upper() != "TBA":
        print(f"Can't read the date “{when}”. Use 2027-02-04, 2027-02, "
              "2027-Q1, 2027 or TBA.")
        return 2
    store = _store()
    ev = model.new_event(title, when, args[2] if len(args) > 2 else "",
                         " ".join(args[3:]) if len(args) > 3 else "")
    store.events.append(ev)
    store.ensure_category(ev["category"])
    if not store.save():
        print("Could not write the data file.")
        return 1
    cd = model.countdown(ev["when"])
    print(f"Added: {ev['title']} — {model.fmt_when(ev['when'])} ({cd.big} {cd.small})".rstrip())
    return 0


def remove_event(args: list[str]) -> int:
    if not args:
        print("usage: main.py --remove TITLE")
        return 2
    store = _store()
    ev = store.find(" ".join(args))
    if ev is None:
        print(f"No event matches “{' '.join(args)}”. Try --list.")
        return 1
    store.remove(ev["id"])
    store.save()
    print(f"Removed: {ev['title']}")
    return 0


def selftest() -> int:
    import tempfile
    from datetime import date
    from pathlib import Path

    from upcoming import model
    from upcoming.store import Store

    ok = True

    def check(label, cond, got=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"   -> {got}" if got else ""))

    print("Upcoming — self-test\n" + "-" * 50)
    t = date(2026, 10, 13)

    cd = model.countdown("2027-02-04", t)
    check("exact date countdown", (cd.big, cd.small) == ("114", "days"), f"{cd.big} {cd.small}")
    check("exact date label", model.fmt_when("2027-02-04", t) == "Thu 4 Feb 2027",
          model.fmt_when("2027-02-04", t))
    check("today", model.countdown("2026-10-13", t).state == "today")
    check("tomorrow is 1 day", model.countdown("2026-10-14", t).small == "day")
    check("past", model.countdown("2026-10-10", t).small == "days ago")
    cd = model.countdown("2027-Q1", t)
    check("quarter -> months range", cd.big == "2–6" and cd.small == "months",
          f"{cd.big} {cd.small}")
    cd = model.countdown("2026-11", t)
    check("next month -> at least n days", cd.big == "19+", f"{cd.big} {cd.small}")
    check("current month -> soon", model.countdown("2026-10", t).state == "soon")
    check("TBA", model.countdown("TBA", t).big == "TBA")
    check("input normalised", model.canonical("2027-2-4") == "2027-02-04"
          and model.canonical("q3 2027") == "2027-Q3"
          and model.canonical("rubbish") == "TBA")

    evs = [model.new_event(*a) for a in (("C", "2027-Q1"), ("B", "2027-03-30"),
                                         ("D", "TBA"), ("A", "2027-01-05"),
                                         ("E", "2027"), ("F", "2026-10-01"))]
    order = [e["title"] for e in model.visible_events(evs, keep_past_days=3, today=t)]
    check("ordering: dated, fuzzy at end of window, TBA last; old past hidden",
          order == ["A", "B", "C", "E", "D"], " ".join(order))
    order = [e["title"] for e in model.visible_events(evs, 30, today=t)]
    check("past kept while within keep_past_days", order[0] == "F", " ".join(order))
    hid = model.visible_events([model.new_event("G", "2027-01-01", "Game"),
                                model.new_event("M", "2027-01-01", "Movie")],
                               hidden_categories=["game"], today=t)
    check("category filter", [e["title"] for e in hid] == ["M"])
    check("month groups", model.group_label("2027-02-04", t) == "February 2027"
          and model.group_label("2027-Q1", t) == "Q1 2027")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.json"
        s = Store(path)
        check("fresh store seeds examples", len(s.events) == 4 and s.created_fresh)
        s.events.append(model.new_event("Something", "2027-06-01", "Concerts"))
        s.ensure_category("Concerts")
        check("save", s.save())
        again = Store(path)
        check("round-trip", len(again.events) == 5 and "Concerts" in again.categories
              and again.find("someth")["when"] == "2027-06-01")
        path.write_text("{broken", encoding="utf-8")
        check("falls back to .bak when the file is corrupt",
              len(Store(path, seed=False).events) == 4)

    print("\nresult:", "ALL PASS" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:  # an old code page shouldn't crash --list over a dash
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if "--list" in argv:
        return list_events()
    for flag, fn in (("--add", add_event), ("--remove", remove_event)):
        if flag in argv:
            return fn(argv[argv.index(flag) + 1:])

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Run:\n"
              "    pip install -r requirements.txt", file=sys.stderr)
        return 1

    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    from upcoming import config as cfg_mod
    from upcoming import theme
    from upcoming.store import Store
    from upcoming.widget import UpcomingWindow

    cfg = cfg_mod.load()

    app = QApplication(sys.argv)
    app.setApplicationName("Upcoming")
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app)

    # One instance per data file: two would overwrite each other's edits.
    key = "Upcoming-" + str(cfg_mod.data_path(cfg)).lower().replace("\\", "-").replace("/", "-")
    probe = QLocalSocket()
    probe.connectToServer(key)
    if probe.waitForConnected(400):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(400)
        probe.disconnectFromServer()
        print("Upcoming is already running — showing the existing one.")
        return 0
    QLocalServer.removeServer(key)
    server = QLocalServer()
    server.listen(key)

    store = Store(cfg_mod.data_path(cfg))
    win = UpcomingWindow(cfg, store)
    win.show()

    def _second_launch():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        win.show()
        win.raise_()
        win.activateWindow()

    server.newConnection.connect(_second_launch)
    app.aboutToQuit.connect(server.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
