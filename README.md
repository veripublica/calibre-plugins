# calibre-plugins

calibre plugins for the veripublica EPUB tools, in one repository: what is
learned about calibre once (its plugin API, packaging, icons, settings) serves
every tool's plugin, and a change in calibre is followed in one pass.

**Status:** being set up.

| Plugin | Tool | Status |
|---|---|---|
| [`kepubverto`](kepubverto) | [kepubverto](https://github.com/veripublica/kepubverto): EPUB to KEPUB for Kobo | released — [0.1.1](https://github.com/veripublica/calibre-plugins/releases/tag/kepubverto-v0.1.1) |

The epubveri plugins for calibre move here from
[epubveri-plugins](https://github.com/veripublica/epubveri-plugins), unchanged
for their users, once the plugins above have proved this repository's layout,
build and release flow.

## How the plugins work

A plugin does not contain the tool it runs. On the user's machine it downloads
the tool's binary from that tool's GitHub release, verifies it against the
release's `SHA256SUMS.txt`, and runs it as a separate program, reading its
JSON report. No tool code is linked into a plugin, and no binary is shipped in
a plugin package.

## Licence

GPL-3.0-only, everywhere in this repository ([LICENSE](LICENSE)). Each source
file says so in its header:

```
SPDX-License-Identifier: GPL-3.0-only
```

The tools the plugins run are licensed separately (AGPL-3.0-only or a
commercial licence); because a plugin only runs a tool as a separate program
and ships none of it, a plugin package carries none of the tools' code.
