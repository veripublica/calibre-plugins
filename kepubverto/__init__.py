# kepubverto for calibre — plugin declaration
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
#
# GPL-3.0-only: this plugin imports calibre's own modules at runtime, and
# calibre is GPL-3.

from calibre.customize import InterfaceActionBase

#: Checked free on 2026-10-24 against calibre's plugin index (271 plugins) and
#: the code of the Kobo/KEPUB plugins in it. The name is also the prefs file
#: (`plugins/kepubverto.json`), so it is never renamed.
PLUGIN_NAME = 'kepubverto'
#: A literal tuple: calibre's plugin index reads it with an AST parse, and a
#: release that forgets to bump it is invisible as an update.
PLUGIN_VERSION_TUPLE = (0, 1, 0)
PLUGIN_VERSION = '.'.join(str(part) for part in PLUGIN_VERSION_TUPLE)

#: The oldest kepubverto this plugin runs (agreed with kepubverto,
#: 2026-10-24): 0.3.0 is the first release with `--css`.
MIN_CONVERTER_VERSION = (0, 3, 0)


class KepubvertoPlugin(InterfaceActionBase):
    """Registers the library-view action. One `Plugin` subclass per zip:
    calibre's loader keeps only the first one it finds."""

    #: calibre's identity key for the action (`gprefs['action-layout-*']`
    #: stores it). Change the caption, never this.
    name = PLUGIN_NAME
    version = PLUGIN_VERSION_TUPLE
    author = 'Baris Kayadelen (veripublica)'
    supported_platforms = ['windows', 'osx', 'linux']
    #: One line, like calibre's own entries, and without the plugin's name.
    description = ('Convert EPUB books to KEPUB for Kobo, adding the Kobo '
                   'markup and changing nothing else')
    #: `qt.core` arrived with calibre 6, so 6.0 is the oldest release this
    #: can load on. Not a claim about what has been tested.
    minimum_calibre_version = (6, 0, 0)

    #: Kept in its own module so calibre's command-line tools can load this
    #: file without Qt.
    actual_plugin = 'calibre_plugins.kepubverto.action:KepubvertoAction'

    #: `config_widget` alone does not open the settings page: Preferences /
    #: Plugins / Customize asks `is_customizable()` first, and the base class
    #: answers through the other mechanism (`customization_help`).
    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.kepubverto.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
