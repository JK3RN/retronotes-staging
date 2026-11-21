import contextlib
from datetime import datetime
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from retronotes.core import DeleteConfirmation, Store, default_notes_dir, note_identity, safe_title
from retronotes.__main__ import main

PROJECT = Path(__file__).resolve().parents[1]


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'Notes')

    def test_title_normalization(self):
        self.assertEqual(safe_title('  Retroscope / Ideas: test?  '), 'Retroscope-Ideas-test')
        self.assertEqual(safe_title('Grüße 日本語 / FFT'), 'Grüße-日本語-FFT')
        self.assertEqual(safe_title(''), 'Untitled')
        self.assertEqual(safe_title('.. /\\ : ? *'), 'Untitled')
        self.assertLessEqual(len(safe_title('日'*200).encode()), 160)
        self.assertNotIn('/', safe_title('../../outside'))

    def test_timestamp_empty_collision_and_rename(self):
        with patch('retronotes.core.datetime') as date:
            date.now.return_value = datetime(2026, 10, 8, 11, 59, 52)
            first = self.store.create(title='Retroscope Ideas')
            second = self.store.create(title='Retroscope Ideas')
            empty = self.store.create()
        self.assertEqual(first.name, '2026-10-08_115952__Retroscope-Ideas.md')
        self.assertEqual(second.name, '2026-10-08_115952__Retroscope-Ideas--2.md')
        self.assertTrue(empty.name.endswith('__Untitled.md'))
        first.write_text('# Grüße\nNOTE: test')
        renamed = self.store.rename(first, 'Neue Idee')
        self.assertEqual(renamed.name, '2026-10-08_115952__Neue-Idee.md')
        self.assertEqual(renamed.read_text(), '# Grüße\nNOTE: test')
        self.assertFalse(first.exists())
        collision = self.store.rename(second, 'Neue Idee')
        self.assertTrue(collision.name.endswith('__Neue-Idee--2.md'))
        self.assertEqual(renamed.read_text(), '# Grüße\nNOTE: test')
        self.assertEqual(self.store.rename(renamed, 'Neue Idee'), renamed)

    def test_legacy_rename(self):
        old = self.store.root / 'Old Note.md'
        old.write_text('legacy')
        os.utime(old, (1700000000, 1700000000))
        timestamp = note_identity(old)[0].strftime('%Y-%m-%d_%H%M%S')
        self.assertTrue(self.store.rename(old, 'New').name.startswith(timestamp+'__'))

    def test_confirmation_cancel_expiry_and_changed_file(self):
        now = [0]
        confirm = DeleteConfirmation(lambda: now[0])
        path = self.store.create()
        self.assertFalse(confirm.request(path))
        self.assertTrue(path.exists())
        confirm.cancel()
        self.assertFalse(confirm.request(path))
        now[0] = 5
        self.assertFalse(confirm.request(path))
        path.write_text('changed')
        self.assertFalse(confirm.request(path))
        self.assertTrue(confirm.request(path))
        self.assertIsNone(confirm.pending)

    def test_trash_collision_and_index(self):
        first = self.store.create(title='Test')
        first.write_text('# unchanged\nGrüße')
        trashed = self.store.trash(first)
        self.assertFalse(first.exists())
        self.assertEqual(trashed.read_text(), '# unchanged\nGrüße')
        first.write_text('second')
        second = self.store.trash(first)
        self.assertNotEqual(trashed, second)
        self.assertEqual(trashed.read_text(), '# unchanged\nGrüße')
        self.assertEqual(second.read_text(), 'second')
        self.assertEqual(self.store.notes(), [])

    def test_symlink_moves_rejected(self):
        outside = self.root / 'outside.md'
        outside.write_text('outside')
        link = self.store.root / 'linked.md'
        link.symlink_to(outside)
        with self.assertRaises(OSError):
            self.store.trash(link)
        with self.assertRaises(OSError):
            self.store.rename(link, 'New')
        self.assertEqual(outside.read_text(), 'outside')

    def test_default_path_independent_of_cwd_and_override(self):
        previous = Path.cwd()
        with patch('pathlib.Path.home', return_value=self.root):
            os.chdir(self.root)
            try:
                self.assertEqual(default_notes_dir(), self.root / 'Notes')
                with contextlib.redirect_stdout(io.StringIO()):
                    main(['NOTE: default'])
                    main(['--notes-dir', str(self.root / 'override'), '# Override'])
            finally:
                os.chdir(previous)
        self.assertEqual(len(list((self.root / 'Notes').glob('*.md'))), 1)
        self.assertEqual(next((self.root / 'override').glob('*.md')).read_text(), '# Override\n')

    def test_direct_capture_never_imports_gtk(self):
        code = '''import importlib.abc, sys
class NoGtk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'gi' or fullname == 'retronotes.app':
            raise AssertionError('GUI loaded for direct capture')
sys.meta_path.insert(0, NoGtk())
from retronotes.__main__ import main
raise SystemExit(main(sys.argv[1:]))
'''
        result = subprocess.run([sys.executable, '-c', code, '--notes-dir', str(self.store.root),
                                 '# Grüße\nTODO: **日本語**'], cwd=PROJECT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).read_text(), '# Grüße\nTODO: **日本語**\n')

    def test_user_install_global_capture_update_uninstall(self):
        prefix = self.root / 'user prefix'
        args = [sys.executable, str(PROJECT / 'install.py'), '--prefix', str(prefix)]
        for _ in range(2):
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        env = dict(os.environ, PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH'], HOME=str(self.root))
        result = subprocess.run(['rnote', 'NOTE: installed Grüße'], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        note = Path(result.stdout.strip())
        self.assertEqual(note.parent, self.root / 'Notes')
        self.assertEqual(note.read_text(), 'NOTE: installed Grüße\n')
        result = subprocess.run(args+['--uninstall'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((prefix/'bin/rnote').exists())
        self.assertTrue(note.exists())

    def test_installer_does_not_follow_module_symlinks_on_update(self):
        prefix = self.root / 'prefix'
        command = [sys.executable, str(PROJECT / 'install.py'), '--prefix', str(prefix)]
        subprocess.run(command, check=True, capture_output=True)
        outside = self.root / 'outside.py'
        outside.write_text('untouched')
        module = prefix / 'share/retronotes/retronotes/core.py'
        module.unlink()
        module.symlink_to(outside)
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual(outside.read_text(), 'untouched')
        self.assertFalse(module.is_symlink())

    def test_installer_refuses_unrelated_launcher(self):
        prefix = self.root / 'prefix'
        (prefix/'bin').mkdir(parents=True)
        (prefix/'bin/rnote').write_text('another program')
        result = subprocess.run([sys.executable, str(PROJECT/'install.py'), '--prefix', str(prefix)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((prefix/'bin/rnote').read_text(), 'another program')

    def test_newest_first_and_old_notes_remain_searchable(self):
        older = self.store.root / '2026-10-07_120000__Old.md'
        newer = self.store.root / '2026-10-08_120000__New.md'
        older.write_text('')
        newer.write_text('')
        self.assertEqual(self.store.notes(), [newer, older])
        self.assertEqual(self.store.notes('old'), [older])

    def test_field_manual_export_matches_runtime(self):
        from retronotes.manual import FIELD_MANUAL
        exported = (PROJECT/'docs/FIELD_MANUAL.md').read_text()
        self.assertEqual(exported.split('```text\n', 1)[1].rsplit('```', 1)[0], FIELD_MANUAL)

    def test_smooth_caret_flag_and_native_default(self):
        from types import SimpleNamespace
        application = SimpleNamespace(run=lambda args: 0)
        for options, enabled in [([], False), (['--smooth-caret'], True)]:
            with patch('retronotes.app.Gtk.init_check', return_value=True), \
                 patch('retronotes.app.Gdk.Display.get_default', return_value=object()), \
                 patch('retronotes.app.NotesApp', return_value=application) as constructor:
                self.assertEqual(main(['--notes-dir', str(self.store.root)]+options), 0)
                self.assertEqual(constructor.call_args.args[-1], enabled)


if __name__ == '__main__':
    unittest.main()
