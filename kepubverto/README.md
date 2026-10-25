# kepubverto for calibre

Convert the EPUBs in your calibre library to **KEPUB**, the Kobo variant of
EPUB, with [kepubverto](https://github.com/veripublica/kepubverto). The KEPUB
is added to each book as calibre's `KEPUB` format, beside the EPUB, which is
not changed.

> **Released as [0.1.2](https://github.com/veripublica/calibre-plugins/releases/tag/kepubverto-v0.1.2).** Developed and tested on calibre 9.17 on macOS.
> `minimum_calibre_version` is 6.0 because that is the oldest release it can
> load on (`qt.core` arrived with calibre 6); it is not a claim about testing.

## What it does

kepubverto adds the markup a Kobo reader uses to track reading position, page
through a chapter quickly and show reading statistics, and nothing else: it
inserts its markup at byte offsets and leaves every other byte of a document
as it was. A book that was valid before the conversion is still valid after
it.

The plugin hands kepubverto **the EPUB stored in your library, as it is**. It
does not go through calibre's conversion pipeline, which rewrites a book
before an output format sees it.

## Using it

The **kepubverto** button opens a menu:

- **Convert the selected books to KEPUB**
- **Convert the whole library to KEPUB**: asks first, with the number of
  books.
- **Save the KEPUB as .kepub.epub…**: saves the selected books' KEPUBs to a
  folder you choose, as `<title> - <authors>.kepub.epub`, never overwriting a
  file. calibre keeps the format as `KEPUB` and names it `.kepub` in the
  library and in its own Save to disk; `.kepub.epub` is the name kepubverto
  and a Kobo use. calibre's Kobo driver already sends it to the device as
  `.kepub.epub`.
- **Show the last report**
- **Clear the marks it left**
- **Stop the running conversion**: what is already converted stays.
- **Settings**

A conversion runs in the background as a calibre job, with a progress bar and
a log in the Jobs panel; calibre stays usable. When every book converted
cleanly, the status bar says so. Otherwise a report opens, one row per book,
with what needs a look first:

| Result | Meaning |
|---|---|
| Not converted | kepubverto could not read or write the book, or refused a setting; its reason is shown as it gave it. |
| Converted, some documents left as they were | Written and added, but some documents could not be converted and were copied unchanged; they are named. |
| Skipped: no EPUB | The book has no EPUB, or its file is missing. |
| Skipped: has a KEPUB | The book already has a KEPUB, and replacing is off. |
| Already a KEPUB | The EPUB already carries Kobo's markup; nothing was added. |
| Converted | Added. |

**Show in library** marks the selected books (or, with none selected, every
book that was not converted cleanly) and filters the library to them.
**Copy** puts the report on the clipboard as tab-separated text, with the date,
the kepubverto and plugin versions, the options, calibre and the system.

## Settings

- **Hyphenation**: as the book says (nothing added), on, or off.
- **Your own CSS**, added after kepubverto's rules. kepubverto refuses CSS
  that refers to a file, has `@font-face`, or would add a finding epubveri
  reports, and the report then shows its reason.
- **Replace an existing KEPUB**: off by default.
- **Books converted at the same time**: automatic is the number of physical
  cores less two.
- **Check for a newer kepubverto**: at most once an hour, never during a
  conversion.

## The converter

No kepubverto binary is shipped in the plugin. On first use the plugin
downloads it from kepubverto's latest
[GitHub release](https://github.com/veripublica/kepubverto/releases/latest),
verifies the archive against the release's `SHA256SUMS.txt`, and keeps it in
`<calibre config>/plugins/kepubverto-data/`. The binary is checked against
its recorded hash before every run. The plugin needs kepubverto 0.3.0 or
newer.

## Tests

```sh
/Applications/calibre.app/Contents/MacOS/calibre-debug kepubverto/tests/test_plugin.py
```

Set `KEPUBVERTO_BINARY` to a kepubverto binary to include the tests that run
the real converter; without it they are skipped.

## Licence

The icon's k is drawn from the outline of KF Libron Bold by Nico Verbruggen
([libron](https://github.com/nicoverbruggen/libron), SIL Open Font License
1.1); no font is included in the plugin. `make_icon.py` draws the icon.

GPL-3.0-only ([LICENSE](../LICENSE)). kepubverto itself is AGPL-3.0-only or a
commercial licence; the plugin runs it as a separate program and ships none
of it.
