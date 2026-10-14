# Upcoming

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![Qt](https://img.shields.io/badge/UI-PySide6-41cd52) ![License](https://img.shields.io/badge/license-MIT-green)

A small desktop widget that lists dates you're waiting for — game releases,
films, birthdays, concerts — in date order, with how many days are left. It
docks to the left edge of the screen, vertically centred, by default.

```
┌──────────────────────────────────┐
│ Upcoming                      ⊕  │
│ OCTOBER 2026 ─────────────────── │
│ ▌ Concert                     4  │
│ ▌ Sat 17 Oct · Arena        days │
│ NOVEMBER 2026 ────────────────── │
│ ▌ Big RPG                    38  │
│ ▌ Fri 20 Nov · PS5, PC      days │
│ FEBRUARY 2027 ────────────────── │
│ ▌ Some game                 114  │
│ ▌ Thu 4 Feb 2027            days │
│ Q2 2027 ──────────────────────── │
│ ▌ A sequel                  5–9  │
│ ▌ Q2 2027                 months │
│ TBA ──────────────────────────── │
│ ▌ A remake                  TBA  │
└──────────────────────────────────┘
```

## Requirements

* Windows 10 or 11
* Python 3.10 or newer on `PATH` ([python.org](https://www.python.org/downloads/))
* [PySide6](https://pypi.org/project/PySide6/) — installed automatically by `run.bat`

## Running it

```
git clone https://github.com/viruztt/Upcoming.git
cd Upcoming
run.bat
```

Or download the ZIP from GitHub, extract it, and double-click **`run.bat`**.
The first run creates a `.venv` beside the script, installs PySide6, then
launches with `pythonw` (no console window). A fresh
install starts with a few example events — edit or delete them.

Then run **`install_startup.bat`** once so it starts with Windows.
**`remove_startup.bat`** undoes it. If you move the folder, run
`install_startup.bat` again.

* **`list.bat`** prints every event with its countdown to a console.
* **`selftest.bat`** checks the date maths and the data file.

## Dates don't have to be exact

Release dates are often announced vaguely, so each event's date can be:

| Date is | Stored as | Listed as | Countdown |
|---|---|---|---|
| Exact day | `2027-02-04` | Thu 4 Feb 2027 | **114** days |
| Month | `2027-02` | February 2027 | **3–5** months |
| Quarter | `2027-Q1` | Q1 2027 | **2–6** months |
| Year | `2027` | 2027 | **2–15** months |
| TBA | `TBA` | TBA | **TBA** |

Fuzzy dates show the range of months they could still be (or *n+ days* when
the window starts within about six weeks), and *Soon — this month / quarter /
year* once that window has started. They sort to the **end** of their window, so
"Q1 2027" comes after every dated March 2027 release; TBA sits at the bottom.
When a date firms up, change *Date is* to *Exact day* and the day picker
starts at the beginning of the old window.

## Using it

* **⊕** (top right), right-click → **Add event…**, or the tray icon adds an
  event. **Double-click** an event to edit it; double-click the heading for the
  full list.
* The editor has search, *Show past*, *Duplicate*, and **Clear past…** to delete
  everything that has already happened.
* **Categories** are free text (Game, Movie, TV, Event, Birthday to start
  with). Each category has one colour, used for the bar beside its events; new
  categories get the next free colour. Right-click → **Show categories** hides
  whole categories from the widget.
* **Note** appears under the title (platforms, venue, who). **Link** adds
  *Open link* to the event's right-click menu.
* **Scroll** over the widget, or click *▲ n earlier* / *▼ n more*, when there
  are more events than *Rows shown*.
* **Today**: the row is highlighted, and a tray notification lists the day's
  events (once per day; switch off with *Notify me on the day*).
* **Past dates** stay listed, dimmed, for *Keep past dates for* (3 days by
  default), then drop off the widget. They stay in the editor until you delete
  them.
* **Drag** the widget anywhere. Let go within 40 px of the left or right edge
  and it docks there; let go elsewhere and it floats. *Dock* and *Vertical
  position* in the menu do the same.
* **Window layer**: *Always on top*, *Normal*, or *Always at the bottom*. The
  widget has no taskbar button — use **Bring to front** on the tray icon if you
  lose it. *Click-through* can be switched off from the tray too.

## From the command line

```
python main.py --list
python main.py --add "Some Game" 2027-02-04 Game "PS5, PC"
python main.py --add "Another Game" 2027-Q3 Game
python main.py --remove "some game"
```

A running widget picks the change up within a couple of seconds.

## Where the data lives

`data/events.json` next to the app — indented JSON you can edit by hand (the
widget reloads when the file changes):

```json
{"version": 1,
 "categories": {"Game": "#56D07A", "Movie": "#E04FB0", "TV": "#7C6CE8"},
 "events": [
  {"id": "a1b2c3d4", "title": "Some Game", "when": "2027-02-04",
   "category": "Game", "note": "PS5, PC", "url": ""},
  {"id": "e5f6a7b8", "title": "A sequel", "when": "2027-Q2",
   "category": "Game", "note": "", "url": ""}
 ]}
```

Saves go through a temp file and an atomic rename with one rolling `.bak`,
which is loaded if the main file is ever unreadable. Set `data_path` in
`config.json` to keep the events elsewhere (OneDrive, say).

## Configuration

`config.json` is written next to `main.py` whenever you change something from
the menu.

| Key | Meaning |
|---|---|
| `dock` | `left` (default), `right`, or `none` for floating |
| `valign` | `top`, `center` (default), `bottom` — where a docked widget sits until dragged |
| `margin` | Gap to the screen edge when docked, in pixels |
| `title` | The heading; blank hides the heading row (the ⊕ goes with it) |
| `width` | Widget width in pixels |
| `max_rows` | Events shown at once; scroll for the rest |
| `group_by_month` | Month / quarter / year section headers |
| `keep_past_days` | How long a passed date stays on the widget |
| `hidden_categories` | Categories left off the widget |
| `notify_today` | Tray notification for today's events |
| `window_layer` | `top`, `normal`, or `bottom` |
| `opacity`, `font_size`, `click_through` | Appearance |
| `data_path` | Where the events live (blank = `data/events.json`) |

## Only one at a time

A second launch just re-shows the widget that is already running. Point a
second copy at a different `data_path` if you want two lists.

## Layout

```
main.py               entry point (--list, --add, --remove, --selftest)
run.bat               first-run installer + launcher
install_startup.bat   add/remove the Windows startup shortcut
remove_startup.bat
list.bat              print all events
selftest.bat          date maths + data file check
upcoming/
  model.py            fuzzy dates, countdowns, ordering (no Qt)
  store.py            events.json + category colours, atomic save, reload
  config.py           JSON settings
  widget.py           the docked list, menus, tray
  editor.py           the add/edit dialog
  theme.py            dark Fusion theme for menus and dialogs
```

Your events (`data/`) and settings (`config.json`) are git-ignored, so they
never end up in the repository.

## License

[MIT](LICENSE)
