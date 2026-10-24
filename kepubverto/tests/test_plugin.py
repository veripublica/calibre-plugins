# kepubverto for calibre — tests
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Run these inside calibre's own interpreter, which is where the plugin runs:

    /Applications/calibre.app/Contents/MacOS/calibre-debug \\
        kepubverto/tests/test_plugin.py

The tests that run the real converter need a kepubverto binary: set
`KEPUBVERTO_BINARY`, or let the plugin install its own copy first. Without
one they are skipped, and the run says so.

**What these tests cannot see**: the toolbar, the Jobs panel, a real library
being written to. Every real defect in the family's calibre plugins was found
by a person clicking in calibre. Add a test each time that happens.
"""

import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import threading
import types
import unittest
import zipfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
ROOT = os.path.dirname(PLUGIN_DIR)

# Point `calibre_plugins.kepubverto` at the working tree and run the real
# `__init__.py` into it: an empty stand-in lacks module-level constants and
# produces failures production never has.
_pkg = sys.modules.setdefault('calibre_plugins',
                              types.ModuleType('calibre_plugins'))
if not hasattr(_pkg, '__path__'):
    _pkg.__path__ = []
_sub = types.ModuleType('calibre_plugins.kepubverto')
_sub.__path__ = [PLUGIN_DIR]
_sub.__file__ = os.path.join(PLUGIN_DIR, '__init__.py')
sys.modules['calibre_plugins.kepubverto'] = _sub
with open(_sub.__file__, encoding='utf-8') as _handle:
    exec(compile(_handle.read(), _sub.__file__, 'exec'), _sub.__dict__)

import calibre_plugins.kepubverto.config as cfg            # noqa: E402
import calibre_plugins.kepubverto.convert as convert       # noqa: E402
import calibre_plugins.kepubverto.install as install       # noqa: E402
from calibre_plugins.kepubverto.client import binary as bin_mod  # noqa: E402
from calibre_plugins.kepubverto.client import runner       # noqa: E402
from calibre_plugins.kepubverto.client.envelope import (   # noqa: E402
    EnvelopeError, parse_envelope)

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>
    <dc:title>T</dc:title><dc:language>en</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="Text/ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>"""
NAV = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
       'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>T</title></head><body>'
       '<nav epub:type="toc"><ol><li><a href="Text/ch1.xhtml">Ch1</a></li></ol></nav>'
       '</body></html>')
CH1 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title>t</title></head>'
       '<body><p>One sentence. Another sentence.</p></body></html>')
CONTAINER = ('<?xml version="1.0"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')
FILES = {
    'META-INF/container.xml': CONTAINER,
    'OEBPS/content.opf': OPF,
    'OEBPS/nav.xhtml': NAV,
    'OEBPS/Text/ch1.xhtml': CH1,
}


def build_epub(path):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                    compress_type=zipfile.ZIP_STORED)
        for name, text in FILES.items():
            zf.writestr(name, text)
    return path


def real_binary():
    """A kepubverto to run: `KEPUBVERTO_BINARY`, or the plugin's own copy."""
    candidates = [os.environ.get('KEPUBVERTO_BINARY')]
    try:
        candidates.append(install.binary_path())
    except Exception:                                   # noqa: BLE001
        pass
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def envelope_doc(status='ok', summary=None, items=(), error=None,
                 output='/tmp/out.kepub.epub', version='0.3.0+1ce1e8c'):
    book = {'path': '/tmp/in.epub', 'status': status, 'items': list(items)}
    if summary is not None:
        book['summary'] = summary
    if error is not None:
        book['error'] = error
    if output is not None and status != 'error':
        book['output'] = output
    return {'tool': 'kepubverto', 'tool_version': version, 'convention': '0.7',
            'status': status, 'inputs': [book]}


def summary(converted=3, already=0, nothing=0, left=0, spans=40):
    return {'documents': converted + already + nothing + left,
            'converted': converted, 'already_converted': already,
            'nothing_to_do': nothing, 'left_alone': left, 'spans': spans}


class PinnedPrefs(object):
    """`JSONConfig('plugins/kepubverto')` is the live file of whoever runs the
    tests. Every key a test writes is saved and put back. Add the key here in
    the same edit that writes it."""

    KEYS = ('autoupdate', 'hyphens', 'css', 'replace_existing', 'workers')

    def setUp(self):
        self._saved = {key: cfg.prefs[key] for key in self.KEYS}
        for key in self.KEYS:
            cfg.prefs[key] = cfg.prefs.defaults[key]

    def tearDown(self):
        for key, value in self._saved.items():
            cfg.prefs[key] = value


_app = None


def qt_app():
    """One QApplication for the run, under Fusion: `CalibreStyle` wants more
    of a running calibre than a test has (SIGBUS in `standardIcon`)."""
    global _app
    if _app is None:
        from calibre.gui2 import Application
        _app = Application([])
        _app.setStyle('Fusion')
    return _app


class EnvelopeTests(unittest.TestCase):

    def test_a_converted_book(self):
        env = parse_envelope(json.dumps(envelope_doc(summary=summary())))
        self.assertEqual(env.version, '0.3.0')
        self.assertEqual(env.output, '/tmp/out.kepub.epub')
        self.assertEqual(env.count('spans'), 40)
        self.assertFalse(env.already_kepub)
        self.assertFalse(env.could_not_convert)

    def test_a_kepub_coming_back_in(self):
        """kepubverto's measurement, 2026-10-24: converted 0, already 32."""
        env = parse_envelope(json.dumps(envelope_doc(
            summary=summary(converted=0, already=32, nothing=2, spans=0))))
        self.assertTrue(env.already_kepub)

    def test_nothing_converted_and_nothing_already_is_not_a_kepub(self):
        env = parse_envelope(json.dumps(envelope_doc(
            summary=summary(converted=0, nothing=2, spans=0))))
        self.assertFalse(env.already_kepub)

    def test_exit_2_with_an_envelope_is_read_not_raised(self):
        doc = envelope_doc(status='error', error='cannot convert x: not a ZIP')
        env = parse_envelope(json.dumps(doc), b'error: cannot convert', 2)
        self.assertTrue(env.could_not_convert)
        self.assertEqual(env.error, 'cannot convert x: not a ZIP')
        self.assertFalse(env.already_kepub)

    def test_a_refusal_raises_with_stderr_as_it_is(self):
        stderr = (b'error: --css value 1: would add a finding to the book\n'
                  b"  line 1, column 5: USAGE ADV-001: 'colr' is not a "
                  b'recognized CSS property\n')
        with self.assertRaises(EnvelopeError) as ctx:
            parse_envelope(b'', stderr, 2)
        self.assertIn('--css value 1', str(ctx.exception))
        self.assertIn('line 1, column 5', str(ctx.exception),
                      'every line of the refusal is shown')

    def test_no_output_at_all_still_says_something(self):
        with self.assertRaises(EnvelopeError) as ctx:
            parse_envelope(b'', b'', 2)
        self.assertIn('exited with 2', str(ctx.exception))

    def test_documents_left_alone_are_findings(self):
        items = [{'code': 'RSC-016', 'severity': 'fatal',
                  'location': 'OEBPS/Text/ch2.xhtml', 'message': 'not well-formed'}]
        env = parse_envelope(json.dumps(envelope_doc(
            status='problems', summary=summary(left=1), items=items)))
        self.assertEqual(env.findings[0].location, 'OEBPS/Text/ch2.xhtml')
        self.assertEqual(env.findings[0].code, 'RSC-016')


class RunnerTests(unittest.TestCase):

    def test_the_command_line(self):
        cmd = runner.command('/bin/k', '/a.epub', '/t/b.kepub.epub')
        self.assertEqual(cmd, ['/bin/k', '-i', '/a.epub', '-o', '/t/b.kepub.epub',
                               '--format', 'json'])
        self.assertNotIn('-f', cmd, 'the output is always new; -f is never needed')

    def test_hyphens_is_passed_only_for_its_two_values(self):
        self.assertEqual(runner.command('k', 'a', 'b', hyphens='auto')[-2:],
                         ['--hyphens', 'auto'])
        self.assertEqual(runner.command('k', 'a', 'b', hyphens='none')[-2:],
                         ['--hyphens', 'none'])
        for value in (None, '', 'on', 'AUTO'):
            self.assertNotIn('--hyphens',
                             runner.command('k', 'a', 'b', hyphens=value))

    def test_one_css_per_value_and_blank_values_dropped(self):
        cmd = runner.command('k', 'a', 'b', css=('p { margin: 0 }', '  ', ''))
        self.assertEqual(cmd.count('--css'), 1)
        self.assertEqual(cmd[-1], 'p { margin: 0 }')

    def test_a_missing_binary_is_reported_as_missing(self):
        with self.assertRaises(runner.ConverterNotFound):
            runner.run_kepubverto('/nonexistent/kepubverto', 'a', 'b')


def _fake_archive(name, binary_name, payload=b'#!/bin/sh\necho kepubverto 0.3.0\n'):
    """An archive in kepubverto's layout: one folder holding the binary."""
    folder = name.replace('.tar.gz', '').replace('.zip', '')
    buf = io.BytesIO()
    if name.endswith('.zip'):
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('%s/%s' % (folder, binary_name), payload)
            zf.writestr('%s/LICENSE' % folder, 'AGPL')
    else:
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            for member, data in (('%s/%s' % (folder, binary_name), payload),
                                 ('%s/LICENSE' % folder, b'AGPL')):
                info = tarfile.TarInfo(member)
                info.size = len(data)
                info.mode = 0o755
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class BinaryTests(unittest.TestCase):

    def test_asset_names_match_the_release(self):
        """The eight names on v0.3.0 (gh release view, 2026-10-24), less the
        musl four this plugin does not use."""
        published = {
            'kepubverto-aarch64-apple-darwin.tar.gz',
            'kepubverto-x86_64-apple-darwin.tar.gz',
            'kepubverto-aarch64-pc-windows-msvc.zip',
            'kepubverto-x86_64-pc-windows-msvc.zip',
            'kepubverto-aarch64-unknown-linux-gnu.tar.gz',
            'kepubverto-x86_64-unknown-linux-gnu.tar.gz',
        }
        ours = {bin_mod.asset_name(t) for t in set(bin_mod._TARGETS.values())}
        self.assertEqual(ours, published)

    def test_parse_version_drops_build_metadata(self):
        self.assertEqual(bin_mod.parse_version('kepubverto 0.3.0+1ce1e8c'),
                         (0, 3, 0))
        self.assertEqual(bin_mod.parse_version('v0.10.2'), (0, 10, 2))
        self.assertIsNone(bin_mod.parse_version(''))
        self.assertIsNone(bin_mod.parse_version('kepubverto x.y'))

    def test_checksums_match_on_the_exact_name(self):
        text = ('%s  kepubverto-x86_64-apple-darwin.tar.gz\n'
                '%s *kepubverto-aarch64-apple-darwin.tar.gz\n'
                'garbage line\n') % ('a' * 64, 'B' * 64)
        sums = bin_mod.parse_checksums(text)
        self.assertEqual(sums['kepubverto-aarch64-apple-darwin.tar.gz'], 'b' * 64)
        self.assertEqual(len(sums), 2)

    def _download(self, archive_name, data, listed_sha=None):
        sums = '%s  %s\n' % (listed_sha or hashlib.sha256(data).hexdigest(),
                             archive_name)

        def fake_get(url, timeout=None):
            if url.endswith(bin_mod.CHECKSUMS_NAME):
                return sums.encode()
            if url.endswith(archive_name):
                return data
            raise AssertionError(url)

        saved = (bin_mod._get, bin_mod.asset_name)
        dest = tempfile.mkdtemp()
        try:
            bin_mod._get = fake_get
            bin_mod.asset_name = lambda triple=None: archive_name
            return bin_mod.download_binary(dest), dest
        finally:
            bin_mod._get, bin_mod.asset_name = saved

    def test_the_binary_is_found_inside_the_archive_folder(self):
        """kepubverto's correction: the binary is in `kepubverto-<target>/`,
        not at the archive root."""
        name = 'kepubverto-aarch64-apple-darwin.tar.gz'
        (path, archive_sha, binary_sha), dest = self._download(
            name, _fake_archive(name, bin_mod.binary_filename()))
        try:
            self.assertEqual(os.path.dirname(path), dest)
            self.assertEqual(binary_sha, bin_mod.sha256_of(path))
            self.assertTrue(os.access(path, os.X_OK))
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    def test_a_zip_archive_works_too(self):
        name = 'kepubverto-x86_64-pc-windows-msvc.zip'
        (path, _a, _b), dest = self._download(
            name, _fake_archive(name, bin_mod.binary_filename()))
        try:
            self.assertTrue(os.path.isfile(path))
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    def test_a_checksum_mismatch_installs_nothing(self):
        name = 'kepubverto-aarch64-apple-darwin.tar.gz'
        with self.assertRaises(bin_mod.DownloadError) as ctx:
            self._download(name, _fake_archive(name, bin_mod.binary_filename()),
                           listed_sha='0' * 64)
        self.assertIn('checksum mismatch', str(ctx.exception))

    def test_a_zip_member_outside_the_folder_is_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('../escape', 'x')
        dest = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf:
                with self.assertRaises(bin_mod.DownloadError):
                    bin_mod._safe_extract_zip(zf, dest)
        finally:
            shutil.rmtree(dest, ignore_errors=True)


class InstallTests(unittest.TestCase):

    def test_the_data_folder_name(self):
        self.assertEqual(os.path.basename(install.data_dir(create=False)),
                         'kepubverto-data')

    @unittest.skipIf(os.name == 'nt', 'uses a shell script as the binary')
    def test_an_old_converter_is_refused(self):
        folder = tempfile.mkdtemp()
        try:
            fake = os.path.join(folder, 'kepubverto')
            for version, refused in (('0.2.3+46fd2f1', True),
                                     ('0.3.0+1ce1e8c', False),
                                     ('1.0.0', False)):
                with open(fake, 'w') as handle:
                    handle.write('#!/bin/sh\necho kepubverto %s\n' % version)
                os.chmod(fake, 0o755)
                failure = install.version_failure(fake)
                self.assertEqual(bool(failure), refused, version)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class StubDB(object):
    """The three `new_api` calls `collect_jobs` makes."""

    def __init__(self, books):
        self.books = books  # {id: (title, epub path or None, has kepub)}

    def field_for(self, name, book_id):
        return self.books[book_id][0]

    def format_abspath(self, book_id, fmt):
        return self.books[book_id][1] if fmt == 'EPUB' else None

    def has_format(self, book_id, fmt):
        return fmt == 'KEPUB' and self.books[book_id][2]


class CollectTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.epub = build_epub(os.path.join(self.dir, 'a.epub'))
        self.db = StubDB({
            1: ('Has EPUB', self.epub, False),
            2: ('No EPUB', None, False),
            3: ('Missing file', os.path.join(self.dir, 'gone.epub'), False),
            4: ('Has KEPUB', self.epub, True),
        })

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_every_book_is_accounted_for(self):
        report = convert.ConversionReport()
        jobs = convert.collect_jobs(self.db, [1, 2, 3, 4], report)
        self.assertEqual([j[0] for j in jobs], [1])
        self.assertEqual({b.book_id: b.outcome for b in report.books},
                         {2: convert.NO_EPUB, 3: convert.NO_EPUB,
                          4: convert.HAS_KEPUB})
        self.assertEqual(report.requested, 4)

    def test_replacing_converts_a_book_that_has_a_kepub(self):
        report = convert.ConversionReport()
        jobs = convert.collect_jobs(self.db, [4], report, replace=True)
        self.assertEqual([j[0] for j in jobs], [4])


class FakeRunner(object):
    """Stands in for `runner.run_kepubverto`: answers per input path."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, binary, path, output, hyphens=None, css=(), timeout=None):
        self.calls.append((path, output, hyphens, tuple(css)))
        answer = self.answers[os.path.basename(path)]
        if isinstance(answer, Exception):
            raise answer
        doc = dict(answer)
        if doc['inputs'][0].get('status') != 'error':
            with open(output, 'wb') as handle:
                handle.write(b'kepub')
            doc['inputs'] = [dict(doc['inputs'][0], output=output)]
        return parse_envelope(json.dumps(doc))


class ConvertTests(unittest.TestCase):

    def setUp(self):
        self.saved = runner.run_kepubverto
        self.added = []

    def tearDown(self):
        runner.run_kepubverto = self.saved

    def add_format(self, book_id, fmt, path, replace):
        with open(path, 'rb') as handle:
            self.added.append((book_id, fmt, handle.read(), replace))
        return True

    def run_books(self, answers, add_format=None, **kwargs):
        runner.run_kepubverto = FakeRunner(answers)
        jobs = [(i + 1, name.upper(), '/lib/%s' % name)
                for i, name in enumerate(answers)]
        return convert.convert_books('/bin/kepubverto', jobs,
                                     add_format or self.add_format, **kwargs)

    def test_each_outcome(self):
        left = [{'code': 'RSC-016', 'severity': 'fatal',
                 'location': 'OEBPS/x.xhtml', 'message': 'bad'}]
        report = self.run_books({
            'clean.epub': envelope_doc(summary=summary()),
            'partly.epub': envelope_doc(status='problems',
                                        summary=summary(left=1), items=left),
            'already.epub': envelope_doc(summary=summary(converted=0, already=5)),
            'broken.epub': envelope_doc(status='error', error='not a ZIP'),
            'refused.epub': EnvelopeError('error: --css value 1: @font-face'),
        }, workers=3)
        outcomes = {b.title: b.outcome for b in report.books}
        self.assertEqual(outcomes, {
            'CLEAN.EPUB': convert.CONVERTED,
            'PARTLY.EPUB': convert.PARTLY,
            'ALREADY.EPUB': convert.ALREADY,
            'BROKEN.EPUB': convert.FAILED,
            'REFUSED.EPUB': convert.FAILED,
        })
        self.assertEqual(sorted(a[0] for a in self.added), [1, 2],
                         'a partly converted book is added; nothing else is')
        self.assertTrue(all(a[1] == 'KEPUB' for a in self.added))
        refused = next(b for b in report.books if b.title == 'REFUSED.EPUB')
        self.assertIn('@font-face', refused.error)
        self.assertEqual(report.tool_version, '0.3.0+1ce1e8c')

    def test_the_report_keeps_the_order_asked(self):
        names = ['b%02d.epub' % i for i in range(12)]
        report = self.run_books({n: envelope_doc(summary=summary())
                                 for n in names}, workers=4)
        self.assertEqual([b.title for b in report.books],
                         [n.upper() for n in names])

    def test_options_reach_the_converter(self):
        self.run_books({'a.epub': envelope_doc(summary=summary())},
                       hyphens='auto', css=('p { margin: 0 }',))
        _path, _out, hyphens, css = runner.run_kepubverto.calls[0]
        self.assertEqual(hyphens, 'auto')
        self.assertEqual(css, ('p { margin: 0 }',))

    def test_a_failed_add_is_a_failed_book_not_a_failed_run(self):
        def boom(*_args):
            raise OSError('disk full')
        report = self.run_books({'a.epub': envelope_doc(summary=summary()),
                                 'b.epub': envelope_doc(summary=summary())},
                                add_format=boom)
        self.assertEqual({b.outcome for b in report.books}, {convert.FAILED})
        self.assertIn('disk full', report.books[0].error)

    def test_a_kepub_that_appeared_meanwhile_is_not_replaced(self):
        report = self.run_books({'a.epub': envelope_doc(summary=summary())},
                                add_format=lambda *a: False)
        self.assertEqual(report.books[0].outcome, convert.HAS_KEPUB)

    def test_cancelling_keeps_what_was_converted(self):
        abort = threading.Event()
        converted = []

        def add_and_cancel(book_id, fmt, path, replace):
            converted.append(book_id)
            abort.set()
            return True

        report = self.run_books({'b%02d.epub' % i: envelope_doc(summary=summary())
                                 for i in range(10)},
                                add_format=add_and_cancel, abort=abort,
                                workers=1)
        self.assertTrue(report.cancelled)
        self.assertEqual(len(report.books), len(converted))
        self.assertLess(len(report.books), 10)

    def test_no_temporary_files_are_left(self):
        before = set(os.listdir(tempfile.gettempdir()))
        self.run_books({'a.epub': envelope_doc(summary=summary())})
        after = set(os.listdir(tempfile.gettempdir()))
        self.assertFalse([n for n in after - before
                          if n.startswith('kepubverto-')])


@unittest.skipIf(real_binary() is None,
                 'no kepubverto binary: set KEPUBVERTO_BINARY')
class RealConverterTests(unittest.TestCase):
    """The contract, against the real binary."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.binary = real_binary()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_convert_then_convert_again(self):
        epub = build_epub(os.path.join(self.dir, 'a.epub'))
        out = os.path.join(self.dir, 'a.kepub.epub')
        env = runner.run_kepubverto(self.binary, epub, out)
        self.assertEqual(env.input_status, 'ok')
        self.assertTrue(os.path.isfile(out))
        self.assertGreater(env.count('spans'), 0)
        again = runner.run_kepubverto(self.binary, out,
                                      os.path.join(self.dir, 'b.kepub.epub'))
        self.assertTrue(again.already_kepub)

    def test_an_unreadable_book_carries_an_envelope(self):
        bad = os.path.join(self.dir, 'bad.epub')
        with open(bad, 'w') as handle:
            handle.write('not a zip')
        env = runner.run_kepubverto(self.binary, bad,
                                    os.path.join(self.dir, 'c.kepub.epub'))
        self.assertTrue(env.could_not_convert)
        self.assertTrue(env.error)

    def test_a_refused_css_is_kepubvertos_own_words(self):
        epub = build_epub(os.path.join(self.dir, 'a.epub'))
        with self.assertRaises(EnvelopeError) as ctx:
            runner.run_kepubverto(self.binary, epub,
                                  os.path.join(self.dir, 'd.kepub.epub'),
                                  css=('@font-face { font-family: x }',))
        self.assertIn('@font-face', str(ctx.exception))

    def test_the_binary_is_new_enough(self):
        self.assertIsNone(install.version_failure(self.binary))


class ConfigTests(PinnedPrefs, unittest.TestCase):

    def test_hyphens(self):
        self.assertIsNone(cfg.hyphens())
        cfg.prefs['hyphens'] = 'auto'
        self.assertEqual(cfg.hyphens(), 'auto')
        cfg.prefs['hyphens'] = 'sometimes'
        self.assertIsNone(cfg.hyphens(), 'a hand-edited value is ignored')

    def test_css(self):
        self.assertEqual(cfg.css_values(), ())
        cfg.prefs['css'] = '   \n'
        self.assertEqual(cfg.css_values(), ())
        cfg.prefs['css'] = 'p { margin: 0 }'
        self.assertEqual(cfg.css_values(), ('p { margin: 0 }',))

    def test_replacing_is_off_by_default(self):
        self.assertFalse(cfg.replace_existing())

    def test_workers_are_clamped(self):
        cfg.prefs['workers'] = 999
        self.assertEqual(cfg.workers(), convert.worker_cap())


class ConfigWidgetTests(PinnedPrefs, unittest.TestCase):

    def test_it_saves_what_it_shows(self):
        qt_app()
        cfg.prefs['hyphens'] = 'none'
        cfg.prefs['css'] = 'p { margin: 0 }'
        widget = cfg.ConfigWidget()
        self.assertEqual(widget.hyphens.currentData(), 'none')
        self.assertEqual(widget.css.toPlainText(), 'p { margin: 0 }')
        widget.hyphens.setCurrentIndex(widget.hyphens.findData('auto'))
        widget.replace_existing.setChecked(True)
        widget.autoupdate.setChecked(False)
        widget.save_settings()
        self.assertEqual(cfg.prefs['hyphens'], 'auto')
        self.assertTrue(cfg.prefs['replace_existing'])
        self.assertFalse(cfg.prefs['autoupdate'])


class ResultsTests(unittest.TestCase):

    def report(self):
        report = convert.ConversionReport()
        report.requested = 3
        ok = convert.BookResult(1, 'Clean', outcome=convert.CONVERTED)
        ok.summary = summary()
        bad = convert.BookResult(2, 'Broken', outcome=convert.FAILED)
        bad.error = 'not a ZIP'
        skip = convert.BookResult(3, 'Paper', outcome=convert.NO_EPUB)
        report.books = [ok, bad, skip]
        report.tool_version = '0.3.0+1ce1e8c'
        return report

    def test_the_report_puts_what_needs_a_look_first(self):
        self.assertEqual([b.title for b in self.report().sorted_books()],
                         ['Broken', 'Paper', 'Clean'])

    def test_the_text_says_what_produced_it(self):
        qt_app()
        from calibre_plugins.kepubverto.results import ResultsDialog
        dialog = ResultsDialog(None, self.report(), lambda ids, label: None)
        text = dialog.text()
        self.assertIn('kepubverto 0.3.0+1ce1e8c', text)
        self.assertIn('plugin %s' % _sub.PLUGIN_VERSION, text)
        self.assertIn('2\tBroken\tNot converted\tnot a ZIP', text)

    def test_show_with_nothing_selected_shows_the_books_to_look_at(self):
        qt_app()
        from calibre_plugins.kepubverto.results import ResultsDialog
        shown = []
        dialog = ResultsDialog(None, self.report(),
                               lambda ids, label: shown.append(ids))
        dialog.show_selected()
        self.assertEqual(shown, [[2, 3]])


class ActionTests(unittest.TestCase):

    def test_it_imports(self):
        qt_app()
        import calibre_plugins.kepubverto.action as action
        self.assertEqual(action.KepubvertoAction.name, 'kepubverto')

    def test_the_mark_search_is_an_exact_match(self):
        import calibre_plugins.kepubverto.action as action
        self.assertEqual(action.MARK_SEARCH, 'marked:"=kepubverto"')

    def test_every_menu_method_is_reachable(self):
        """Read from the source: `genesis` needs a running calibre."""
        import ast
        path = os.path.join(PLUGIN_DIR, 'action.py')
        with open(path, encoding='utf-8') as handle:
            tree = ast.parse(handle.read(), path)
        cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef) and n.name == 'KepubvertoAction')
        genesis = next(n for n in cls.body
                       if isinstance(n, ast.FunctionDef) and n.name == 'genesis')
        wired = {n.attr for n in ast.walk(genesis) if isinstance(n, ast.Attribute)}
        for name in ('start', 'save_selected', 'show_last_report',
                     'clear_marks', 'stop_run', 'show_settings'):
            self.assertIn(name, wired, '%s is defined and nothing reaches it'
                          % name)

    def test_stopping_goes_through_the_manager(self):
        import calibre_plugins.kepubverto.action as action
        killed = []

        class Job(object):
            type = action.JOB_TYPE

            def kill(self):                              # pragma: no cover
                raise AssertionError('went to the job, not the manager')

        job = Job()

        class Manager(object):
            @staticmethod
            def unfinished_jobs():
                return [job, type('Other', (), {'type': 'other'})()]

            @staticmethod
            def kill_job(j, view):
                killed.append(j)

        gui = type('G', (), {'job_manager': Manager()})()
        stub = type('Stub', (), {'gui': gui,
                                 '_our_jobs': action.KepubvertoAction._our_jobs})()
        action.KepubvertoAction.stop_run(stub)
        self.assertEqual(killed, [job])

    def test_showing_books_keeps_other_marks(self):
        import calibre_plugins.kepubverto.action as action

        class Data(object):
            marked_ids = {7: 'someone else', 8: 'kepubverto'}

            def set_marked_ids(self, marks):
                self.marked_ids = marks

        data = Data()
        noop = staticmethod(lambda *a, **k: None)
        gui = type('G', (), {
            'current_db': type('D', (), {'data': data})(),
            'search': type('S', (), {'set_search_string': noop})(),
            'status_bar': type('B', (), {'show_message': noop})()})()
        stub = type('Stub', (), {'gui': gui})()
        action.KepubvertoAction.show_books(stub, [1, 2], 'x')
        self.assertEqual(data.marked_ids,
                         {7: 'someone else', 1: 'kepubverto', 2: 'kepubverto'})


class ExportDB(object):
    """The `new_api` calls `save_kepubs` makes."""

    def __init__(self, books, fail=()):
        self.books = books  # {id: (title, authors, kepub bytes or None)}
        self.fail = set(fail)

    def field_for(self, name, book_id):
        return self.books[book_id][0 if name == 'title' else 1]

    def has_format(self, book_id, fmt):
        return fmt == 'KEPUB' and self.books[book_id][2] is not None

    def copy_format_to(self, book_id, fmt, dest):
        with open(dest, 'wb') as handle:
            handle.write(b'partial')
            if book_id in self.fail:
                raise OSError('disk full')
            handle.write(self.books[book_id][2])


class ExportTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_file_is_named_kepub_epub(self):
        """Baris, 2026-10-24: kepubverto names its output `.kepub.epub` on
        purpose, and calibre's own Save to disk writes `.kepub`."""
        from calibre_plugins.kepubverto import export
        db = ExportDB({1: ('Emma', ['Jane Austen'], b'K')})
        saved, without, failed = export.save_kepubs(db, [1], self.dir)
        self.assertEqual([os.path.basename(p) for p in saved],
                         ['Emma - Jane Austen.kepub.epub'])
        with open(saved[0], 'rb') as handle:
            self.assertEqual(handle.read(), b'partialK')
        self.assertEqual((without, failed), ([], []))

    def test_nothing_is_overwritten(self):
        from calibre_plugins.kepubverto import export
        db = ExportDB({1: ('Emma', ['Jane Austen'], b'K')})
        export.save_kepubs(db, [1], self.dir)
        saved, _w, _f = export.save_kepubs(db, [1], self.dir)
        self.assertEqual(os.path.basename(saved[0]),
                         'Emma - Jane Austen (2).kepub.epub')

    def test_books_without_a_kepub_and_failures_are_reported(self):
        from calibre_plugins.kepubverto import export
        db = ExportDB({1: ('A', [], None), 2: ('B', ['X'], b'K')}, fail={2})
        saved, without, failed = export.save_kepubs(db, [1, 2], self.dir)
        self.assertEqual(saved, [])
        self.assertEqual(without, [1])
        self.assertEqual(failed[0][:2], (2, 'B'))
        self.assertEqual(os.listdir(self.dir), [],
                         'a failed copy leaves no half-written file')

    def test_names_are_safe_on_every_platform(self):
        from calibre_plugins.kepubverto import export
        stem = export.file_stem('What? A/B: C', ['Ann', 'Bob'])
        self.assertFalse(set(stem) & set('/\\:?*"<>|'), stem)
        self.assertIn('Ann & Bob', stem)
        self.assertEqual(export.file_stem('', None), 'Unknown')
        self.assertLessEqual(len(export.file_stem('x' * 400, ['y'])),
                             export.MAX_STEM)


class BuildTests(unittest.TestCase):

    def test_the_zip_is_what_calibre_installs(self):
        # Loaded by path under its own name: calibre's interpreter already has
        # a module called `build`.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'kepubverto_build', os.path.join(PLUGIN_DIR, 'build.py'))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        path = build.build()
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
        self.assertIn('kepubverto_calibre_v%s.zip' % _sub.PLUGIN_VERSION,
                      os.path.basename(path))
        for required in ('__init__.py', 'plugin-import-name-kepubverto.txt',
                         'plugin.png', 'LICENSE', 'action.py',
                         'client/binary.py'):
            self.assertIn(required, names)
        for name in names:
            self.assertFalse(name.startswith(('tests/', 'build.py',
                                              'make_icon.py')), name)
            self.assertNotIn('__pycache__', name)
            self.assertNotIn(os.path.basename(name),
                             ('kepubverto', 'kepubverto.exe'))


class SourceTests(unittest.TestCase):

    def test_every_source_file_is_gpl_3_only(self):
        for dirpath, _dirs, files in os.walk(PLUGIN_DIR):
            if '__pycache__' in dirpath:
                continue
            for name in files:
                if not name.endswith('.py'):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, encoding='utf-8') as handle:
                    head = handle.read(600)
                self.assertIn('SPDX-License-Identifier: GPL-3.0-only', head, path)
                self.assertNotIn('any later version', head, path)

    def test_the_shipped_icon_is_the_one_make_icon_draws(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'kepubverto_make_icon', os.path.join(PLUGIN_DIR, 'make_icon.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with open(os.path.join(PLUGIN_DIR, 'plugin.png'), 'rb') as handle:
            self.assertEqual(handle.read(), module.png(module.pixels()))


def run():
    """Build the suite from this module's namespace: `unittest.main()`
    collects nothing under `calibre-debug` and reports that as success."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for obj in list(globals().values()):
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            suite.addTests(loader.loadTestsFromTestCase(obj))
    if not suite.countTestCases():
        raise SystemExit('no tests were collected; the suite is not running')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    run()
