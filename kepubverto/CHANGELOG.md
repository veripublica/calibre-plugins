# Changelog: kepubverto for calibre

## [0.1.2] - 2026-10-25

### Changed

- *Convert the whole library to KEPUB* sits in its own section of the menu,
  away from *Convert the selected books*, so it is harder to pick by mistake.
- Its question names the whole library and the number of books, and its
  default button is No.

## [0.1.1] - 2026-10-24

### Changed

- The icon: a k on calibre's book, in the family's yellow, replacing the
  placeholder arrow. The k is KF Libron Bold's (Nico Verbruggen, SIL Open
  Font License), the Kobo build of a font made for e-readers.

## [0.1.0] - 2026-10-24

### Added

- Convert the selected books, or the whole library, to KEPUB with kepubverto,
  as a background job. The stored EPUB is converted as it is and the KEPUB is
  added to the book.
- *Save the KEPUB as .kepub.epub…*: the selected books' KEPUBs saved to a
  folder under kepubverto's own name, `<title> - <authors>.kepub.epub`.
- A report, one row per book, with *Show in library* and *Copy*.
- Settings: hyphenation, your own CSS, replacing an existing KEPUB, books
  converted at the same time, and update checks for kepubverto.
- kepubverto is downloaded on first use and verified against its release's
  `SHA256SUMS.txt`; kepubverto 0.3.0 or newer is required.
- A placeholder icon.
