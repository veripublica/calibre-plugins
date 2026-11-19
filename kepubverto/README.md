# kepubverto for calibre

This plugin converts the EPUBs in your calibre library to KEPUB, for reading
on a Kobo, with [kepubverto](https://github.com/veripublica/kepubverto). The
KEPUB is added to each book next to the EPUB, and the EPUB isn't changed.

The plugin gives kepubverto the EPUB exactly as it is stored in your library.
calibre's own Convert books rewrites a book before it makes the KEPUB, and on
a valid book I tried that rewrite left 61 errors. kepubverto only adds the
markup a Kobo needs, so a book that was valid stays valid.

Select some books, click the kepubverto button and choose Convert the selected
books to KEPUB. It runs in the background, and when it's done you get a report
for any book that needs a look. calibre names the format .kepub, and its Kobo
driver sends it to the device as .kepub.epub. If you copy books by hand, Save
the KEPUB as .kepub.epub in the same menu gives you that name. The settings
cover hyphenation, your own CSS and whether to replace a KEPUB you already
have.

The first conversion downloads kepubverto from its GitHub releases and checks
it, so it needs an internet connection; after that the plugin works offline.
I develop and test it with calibre 9.17 on macOS.

What each setting and each line of the report means is in
[AGENTS.md](../AGENTS.md). Questions and problems are welcome in the
[MobileRead thread](https://www.mobileread.com/forums/showthread.php?t=375915)
or in [Issues](https://github.com/veripublica/calibre-plugins/issues).

The plugin is GPL-3.0-only ([LICENSE](../LICENSE)). kepubverto itself is
AGPL-3.0-only or commercial; the plugin runs it as a separate program and
ships none of it. The icon's k is drawn from KF Libron Bold by Nico Verbruggen
(SIL Open Font License); no font is included.
