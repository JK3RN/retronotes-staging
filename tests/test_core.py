import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from retronotes.core import SaveConflict, Store, palette, DEFAULT


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)

    def test_roundtrip_and_permissions(self):
        path = self.store.create()
        path.chmod(0o640)
        text = '# Grüße\n\nTODO: **Test**\n`λ`\n'
        self.store.save(path, text)
        self.assertEqual(path.read_text(), text)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.root.glob('.*')), [])

    def test_private_creation_and_trash_with_permissive_umask(self):
        previous = os.umask(0)
        try:
            store = Store(self.root / 'private')
            self.assertEqual(store.root.stat().st_mode & 0o777, 0o700)
            path = store.create()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            trashed = store.trash(path)
            self.assertEqual(trashed.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(trashed.stat().st_mode & 0o777, 0o600)
        finally:
            os.umask(previous)

    def test_only_regular_markdown_files_inside_the_store(self):
        outside = self.root / 'elsewhere'
        outside.mkdir()
        note = outside / 'Outside.md'
        note.write_text('untouched')
        link = self.root / 'Link.md'
        link.symlink_to(note)
        fifo = self.root / 'Pipe.md'
        os.mkfifo(fifo)
        bad_suffix = self.root / 'Other.txt'
        bad_suffix.write_text('untouched')
        self.assertEqual(self.store.notes(), [])
        for path in (note, link, fifo, bad_suffix):
            with self.subTest(path=path.name):
                with self.assertRaises(OSError):
                    self.store.read(path)
                with self.assertRaises(OSError):
                    self.store.save(path, 'replacement')
        self.assertEqual(note.read_text(), 'untouched')
        self.assertEqual(bad_suffix.read_text(), 'untouched')

    def test_edit_during_temp_sync_wins_over_autosave(self):
        path = self.store.create()
        path.write_text('original')
        initial = self.store.stamp(path)
        real_fsync = os.fsync

        def external_edit(fd):
            path.write_text('changed externally while temporary file was syncing')
            real_fsync(fd)

        with patch('retronotes.core.os.fsync', side_effect=external_edit):
            with self.assertRaises(SaveConflict):
                self.store.save(path, 'pending', expected=initial)
        self.assertEqual(path.read_text(), 'changed externally while temporary file was syncing')
        self.assertEqual(list(self.root.glob('.*')), [])

    def test_replace_failure_preserves_note(self):
        path = self.store.create()
        path.write_text('original')
        with patch('retronotes.core.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.store.save(path, 'replacement')
        self.assertEqual(path.read_text(), 'original')
        self.assertEqual(list(self.root.glob('.*')), [])

    def test_unique_creation_and_fuzzy_search(self):
        self.assertNotEqual(self.store.create(), self.store.create())
        (self.root / 'Retro Tools.md').write_text('')
        (self.root / 'ignore.txt').write_text('')
        self.assertEqual([p.name for p in self.store.notes('rtls')], ['Retro Tools.md'])
        self.assertEqual(self.store.notes('zzzz'), [])

    def test_theme_fallback_and_validation(self):
        path = self.root / 'colors.toml'
        self.assertEqual(palette([path]), DEFAULT)
        path.write_text('invalid = [')
        self.assertEqual(palette([path]), DEFAULT)
        path.write_text('background = "#223344"\nblue = "#abcdef"\nred = "invalid"')
        colors = palette([path])
        self.assertEqual(colors['background'], '#223344')
        self.assertEqual(colors['accent'], '#abcdef')
        self.assertEqual(colors['critical'], DEFAULT['critical'])


if __name__ == '__main__':
    unittest.main()
