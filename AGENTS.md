# AGENTS.md — calibre-plugins

Detail for anyone, person or code agent, working in this repository. The
README is the short version for people; this file is the one to keep true at
every release.

## Scope

This repository holds the calibre plugins for the veripublica EPUB tools, one
folder per tool. What is learned about calibre once (its plugin API,
packaging, icons, settings, background jobs) serves every plugin here.

| Folder | Plugin | Tool it runs | Tag | MobileRead thread |
|---|---|---|---|---|
| `epubveri/` | epubveri for calibre (Edit Book tool) | [epubveri](https://github.com/veripublica/epubveri), an EPUB validator | `epubveri-vX.Y.Z` | [375293](https://www.mobileread.com/forums/showthread.php?t=375293) |
| `epubveri-library/` | epubveri library for calibre (library action) | epubveri | `epubveri-library-vX.Y.Z` | [375207](https://www.mobileread.com/forums/showthread.php?t=375207) |
| `kepubverto/` | kepubverto for calibre | [kepubverto](https://github.com/veripublica/kepubverto), EPUB to KEPUB for Kobo | `kepubverto-vX.Y.Z` | [375915](https://www.mobileread.com/forums/showthread.php?t=375915) |

The two epubveri plugins moved here from
[epubveri-plugins](https://github.com/veripublica/epubveri-plugins) (a plain
copy of `plugins/calibre/` and `plugins/calibre-library/` at `937d3e5`; their
history stays there, under the tags `calibre-v…` and `calibre-library-v…`).
Unchanged for users: plugin names (`epubveri`, `epubveri library`), import
names, `JSONConfig` keys (`plugins/epubveri`, `plugins/epubveri_library`), data
folders (`epubveri-data`, `epubveri-library-data`), zip names, MobileRead
threads, and version numbers, which continue. Both are in calibre's plugin
index, which installs the first `.zip` on each thread's first post. Their
detail is still in their own READMEs. The root `icon.py` of the old repository
became each plugin's `make_icon.py`, geometry unchanged.

All three plugins ask for their icon with `get_icons('plugin.png', PLUGIN_NAME)`
(injected by calibre's zip loader), so a user's
`<config>/resources/images/<plugin name>/plugin.png` replaces it (measured in
calibre 9.18). The library plugin's setting `button` (`menu`, the default;
`selection`; `library`, which always asks) decides what the body of its
toolbar button does; the arrow always opens the menu.

A plugin for [epubsana](https://github.com/veripublica/epubsana) comes next.

What a plugin here does not do:

- **It does not contain the tool it runs.** It downloads the tool's binary
  from that tool's GitHub release, verifies it against the release's
  `SHA256SUMS.txt`, and runs it as a separate program, reading its JSON
  envelope. No binary is ever shipped in a plugin zip. The tools are
  AGPL-3.0-only or commercial; the plugins are GPL-3.0-only (they import
  calibre, which is GPL-3), and running a separate program keeps the two
  apart.
- **It never judges the book itself.** Outcomes and reasons are the tool's. A
  wrong conversion belongs in the tool's issue tracker.
- **It does not go through calibre's conversion pipeline.** That pipeline
  parses a book into calibre's own model and writes it out again before an
  output plugin sees it, which is what the tools exist to avoid. A plugin here
  is a library action that hands the tool the file stored in the library.
- **It shares no code with the other plugins.** Each folder carries its own
  copy of what it needs (`client/`, `build.py`, `tests/`), so auditing a
  plugin means reading one folder. A fix in one plugin's `client/` may have to
  be made in another by hand.

## kepubverto for calibre

### What it does

A GUI plugin (`InterfaceActionBase`, action `KepubvertoAction`). For each
selected book it reads the stored EPUB (`db.format_abspath(id, 'EPUB')`), runs
kepubverto on it into a fresh temporary folder, and adds the result to the
book as calibre's `KEPUB` format with `db.add_format(..., run_hooks=False)`,
so no file-type plugin changes it on the way in. The EPUB is only ever read.

The command for one book (`client/runner.py`, `command()`):

```
kepubverto -i <book.epub> -o <tmp>/book.kepub.epub --format json [--hyphens auto|none] [--css <value>]
```

`-f` is never passed: the output path is always new. Timeout 300 s per book.

The menu (both halves of the toolbar button open it):

- Convert the selected books to KEPUB
- Convert the whole library to KEPUB (its own menu section; always asks,
  naming the whole library and the number of books, with No as the default
  button; a selection of more than 20 books also asks, with Yes as default)
- Save the KEPUB as .kepub.epub…
- Show the last report
- Clear the marks it left
- Stop the running conversion
- Settings

The action is kept out of the device toolbar, device menus and search bar:
the selection is read from `library_view`, which still holds the library's
selection while a device view is showing.

### The run

- **A `ThreadedJob`** (`kepubverto_convert`): one line in the Jobs panel, a
  progress bar, a log and a cancel button. One run at a time.
- **The callback is wrapped in `Dispatcher`**, built on the GUI thread,
  because `ThreadedJob` calls it on the worker thread.
- **Stop goes through `job_manager.kill_job`.** A killed job still calls the
  callback with what the worker returned, so a cancelled run keeps the books
  already converted, in the library and in the report. A cancel takes effect
  between books.
- **The binary is resolved on the GUI side before the job starts**, so a
  long run never has its executable replaced halfway.
- **One kepubverto process per book, several at once** (a thread pool that
  only runs kepubverto). Only the job's own thread touches the report and the
  library. Workers: physical cores less two, at least one, and no more than
  the number of books; the setting can lower it.
- **The library is fixed for the run.** The worker holds the `new_api` it
  was started with, so switching libraries mid-run cannot send formats to the
  wrong one. A library switch drops the last report.

### Outcomes

One per book, in this order in the report:

| Outcome | When |
|---|---|
| Not converted (`failed`) | Exit 2 with `inputs[0].status: "error"`, a refusal with no envelope (its stderr is shown as it is), a timeout, no file written, or the KEPUB could not be added. |
| Converted, some documents left as they were (`partly`) | Exit 1: the book was written, some documents were copied byte for byte without spans. Each is a row detail with its container path. The KEPUB is added. |
| Skipped: no EPUB (`no epub`) | No EPUB format, or its file is missing. |
| Skipped: has a KEPUB (`has kepub`) | The book has a KEPUB and replacing is off. |
| Already a KEPUB (`already`) | `converted == 0` and `already_converted > 0`. kepubverto recognises its own output, kepubify's and calibre's by the `koboSpan` markup. Nothing is added. |
| Converted (`converted`) | Added. |

Every requested book gets a row; nothing is skipped silently. When all books
are clean the status bar says so; otherwise the report opens. *Show in
library* marks the selected rows (or, with none, every book not cleanly
converted) with the mark `kepubverto` and searches `marked:"=kepubverto"`.
*Clear the marks* removes only that mark. *Copy* puts tab-separated text on
the clipboard with the date, kepubverto and plugin versions, options, calibre
version and system.

### The envelope

kepubverto's `--format json`, as of 0.3.0 (`client/envelope.py`). The plugin
reads `tool_version`, and of `inputs[0]`: `status`, `error`, `output`,
`summary` (`documents`, `converted`, `already_converted`, `nothing_to_do`,
`left_alone`, `spans`) and `items` (one per document left as it was:
`code`, `severity`, `location`, `message`).

**stdout is parsed first, whatever the exit code.** Exit 2 can carry an
envelope (the book could not be read or written). Only a refusal (a `--css`
value, an output that exists) and a usage error leave stdout empty; then
stderr is the message.

### The binary

`client/binary.py` and `install.py`.

- **Where:** `<calibre config>/plugins/kepubverto-data/`, with an
  `install.json` record beside it. The name differs from the prefs file
  (`plugins/kepubverto.json`) on purpose. If the name is taken by a non-folder,
  the plugin says so and installs nothing.
- **What:** `kepubverto-<target>.tar.gz` (Linux, macOS) or `.zip` (Windows)
  from `https://github.com/veripublica/kepubverto/releases/latest/download/`,
  plus `SHA256SUMS.txt`. Targets: `aarch64`/`x86_64` × `apple-darwin`,
  `pc-windows-msvc`, `unknown-linux-gnu` (gnu, not musl). Inside each archive
  is one folder holding the binary; it is found by name, not by path.
  No GitHub API call is made.
- **Checks:** the archive against `SHA256SUMS.txt` (exact asset name) before
  extracting; extraction refuses members that would land outside the folder,
  absolute paths and links; the binary's own SHA-256 is recorded and checked
  before every run, and a changed binary is not run; `kepubverto -V` must
  report **0.3.0 or newer** (`MIN_CONVERTER_VERSION`, the first release with
  `--css`).
- **Updates:** at most once an hour, at the start of a run, never during one.
  The check compares the release's checksum for this platform with the
  recorded one, so it also catches an archive re-uploaded under the same tag.
  Timeout 5 s; offline or rate-limited, the copy already installed is used. A
  month without a successful check adds one line to the report.
- **First run** needs the network; after that the plugin works offline.

### Settings

`JSONConfig('plugins/kepubverto')`. The keys never change.

| Key | Default | Meaning |
|---|---|---|
| `hyphens` | `''` | `''`: `--hyphens` not passed (the book decides); `auto`; `none`. |
| `css` | `''` | One `--css` value, added after kepubverto's rules. kepubverto refuses CSS that refers to a file, has `@font-face`, or would add an epubveri finding. |
| `replace_existing` | `False` | Whether a book with a KEPUB gets a new one. Off, because an existing KEPUB may have been made on purpose. |
| `workers` | `0` | Books at once. 0 is automatic (see above); the maximum is physical cores less two. |
| `autoupdate` | `True` | Check for a newer kepubverto. Off, an old binary below the minimum is refused with a message. |

Only options a kepubverto release has are offered.

### Save the KEPUB as .kepub.epub

calibre names the `KEPUB` format `.kepub` in the library and in its Save to
disk; its KoboTouch driver already restores `.kepub.epub` on the device
(`KOBO.filename_callback`). Renaming the format would break the driver, so the
plugin offers a separate save instead: the selected books' KEPUBs to a folder,
as `<title> - <authors>.kepub.epub` (sanitized, stem cut at 150 characters),
never overwriting (`(2)`, `(3)`…).

### Why not calibre's own KEPUB

calibre 9.17 has a built-in `KEPUB Output` conversion plugin, and the
KoboTouch driver converts on send with the same module
(`calibre.ebooks.oeb.polish.kepubify`). The output plugin runs calibre's
conversion pipeline first. On one valid book (Emma), *Convert books → KEPUB*
in calibre 9.17 produced 61 errors in epubveri 0.33.0 and epubcheck 5.4.0, all
OPF-014 (`kobo.js` used but not declared); the plugin's KEPUB of the same book
had none, and was byte-identical to kepubverto's direct output. One book is an
example, not a measurement of the output plugin.

### Compatibility

Developed and tested on calibre 9.17 on macOS. `minimum_calibre_version` is
6.0 because `qt.core` arrived with calibre 6; it is not a claim about testing.
Platforms: Windows, macOS, Linux, wherever a kepubverto build exists.

### Icon

`plugin.png`: the k of KF Libron Bold (Nico Verbruggen,
[libron](https://github.com/nicoverbruggen/libron), SIL Open Font License 1.1)
on the calibre book, in the family's yellow. `make_icon.py` draws it from the
glyph outline; no font is in the plugin. A user's own
`<config>/resources/images/kepubverto/plugin.png` replaces it.

## Layout

```
LICENSE                  GPL-3.0-only, copied into every zip
kepubverto/
  __init__.py            plugin declaration, PLUGIN_VERSION_TUPLE, MIN_CONVERTER_VERSION
  action.py              menu, background job, report window glue
  convert.py             the run: jobs, worker pool, outcomes, report
  results.py             the report dialog
  export.py              Save the KEPUB as .kepub.epub
  config.py              settings page and prefs
  install.py             where the binary lives, update and integrity checks
  client/                binary download and checksum, runner, envelope parser
  plugin-import-name-kepubverto.txt
  plugin.png             the icon; make_icon.py draws it
  build.py               builds the zip
  forum.py               stages the published zip for the MobileRead post
  tests/test_plugin.py
  CHANGELOG.md, README.md
```

## Tests

In calibre's interpreter:

```sh
calibre-debug kepubverto/tests/test_plugin.py
```

(on macOS, `/Applications/calibre.app/Contents/MacOS/calibre-debug`). Set
`KEPUBVERTO_BINARY` to a kepubverto binary to include the tests that run the
real converter; without it they are skipped. A release needs them all run,
none skipped.

A headless script against a throwaway library must wait about 15 s before it
exits, or calibre 9's background page counter prints tracebacks into a
temporary folder that is already gone. They are not the plugin's.

Every release also gets a round by hand in calibre with the built zip,
installed with Preferences → Plugins → Load plugin from file (never with
`calibre-customize` while calibre is open).

## Build and release

```sh
python3 kepubverto/build.py      # → dist/kepubverto/kepubverto_calibre_vX.Y.Z.zip
```

The zip has `__init__.py`, `plugin-import-name-kepubverto.txt`, `plugin.png`
and `LICENSE` at its root, and no tests, build or forum scripts, icon script,
`__pycache__`, README, CHANGELOG or binary.

Each plugin is released on its own, by hand; there are no workflows. The
version is `PLUGIN_VERSION_TUPLE` in the plugin's `__init__.py`, a literal
tuple because calibre's plugin index reads it with an AST parse; it is the
only version calibre users see. The tag is `<plugin>-vX.Y.Z`. The GitHub
release carries the zip and a one-line `SHA256SUMS.txt`, and its notes are the
version's `CHANGELOG.md` section. The zip is then attached to the first post
of the plugin's MobileRead thread, replacing the old one.

## Licence

GPL-3.0-only, every file (`SPDX-License-Identifier: GPL-3.0-only`). The tools
the plugins run are licensed separately.
