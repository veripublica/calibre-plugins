# calibre-plugins

These are the calibre plugins for my EPUB tools. If you keep your books in
[calibre](https://calibre-ebook.com/), a plugin here runs one of the tools on
the books in your library.

| Plugin | What it does | Latest | Download |
|---|---|---|---|
| epubveri for calibre | Checks the book open in calibre's editor against the EPUB specification and lists what it finds | [0.4.6](https://github.com/veripublica/calibre-plugins/releases/tag/epubveri-v0.4.6) | [epubveri_calibre_v0.4.6.zip](https://github.com/veripublica/calibre-plugins/releases/download/epubveri-v0.4.6/epubveri_calibre_v0.4.6.zip) |
| epubveri library for calibre | Checks every book in your library and shows which ones have problems | [0.5.4](https://github.com/veripublica/calibre-plugins/releases/tag/epubveri-library-v0.5.4) | [epubveri_calibre_library_v0.5.4.zip](https://github.com/veripublica/calibre-plugins/releases/download/epubveri-library-v0.5.4/epubveri_calibre_library_v0.5.4.zip) |
| kepubverto for calibre | Adds a KEPUB for Kobo readers to each book, next to the EPUB, which it doesn't change | [0.1.2](https://github.com/veripublica/calibre-plugins/releases/tag/kepubverto-v0.1.2) | [kepubverto_calibre_v0.1.2.zip](https://github.com/veripublica/calibre-plugins/releases/download/kepubverto-v0.1.2/kepubverto_calibre_v0.1.2.zip) |

Download the zip and add it in calibre with Preferences, Plugins, Load plugin
from file. On first use the plugin downloads its tool itself, checks it, and
keeps it up to date.

The two epubveri plugins moved here from
[epubveri-plugins](https://github.com/veripublica/epubveri-plugins), where
their releases before 0.4.6 and 0.5.4 still are. If you use them, nothing
changes for you, and calibre keeps updating them as before. A plugin for
epubsana is next.

Each plugin's own README ([epubveri](epubveri/README.md),
[epubveri library](epubveri-library/README.md),
[kepubverto](kepubverto/README.md)) explains how to use it, and
[AGENTS.md](AGENTS.md) has the technical detail. You can report problems in
[Issues](https://github.com/veripublica/calibre-plugins/issues) or in each
plugin's MobileRead thread:
[epubveri](https://www.mobileread.com/forums/showthread.php?t=375293),
[epubveri library](https://www.mobileread.com/forums/showthread.php?t=375207),
[kepubverto](https://www.mobileread.com/forums/showthread.php?t=375915).

The plugins are GPL-3.0-only ([LICENSE](LICENSE)). The tools they run are
licensed separately. A plugin only runs its tool as a separate program and
ships none of it.
