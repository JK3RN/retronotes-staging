"""Exercise real GTK text buffers without needing a window server."""
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from retronotes.app import NotesApp, Gtk, Gdk, GLib
from retronotes.core import Store


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = NotesApp(Store(self.temp.name))
        self.app.buffer = Gtk.TextBuffer()
        self.app.tags = {name: self.app.buffer.create_tag(name) for name in
                         ['heading', 'syntax', 'bold', 'code', 'token', 'warning', 'done', 'focus', 'fresh']}
        self.messages = []
        self.app.status = SimpleNamespace(set_text=self.messages.append)
        self.app.view = SimpleNamespace(get_visible_rect=lambda: SimpleNamespace(x=0, y=0, height=100),
                                        get_iter_at_location=lambda x, y: (True, self.app.buffer.get_start_iter()))
        self.app.path = self.app.store.create()
        self.app.fingerprint = self.app.file_stamp()

    def test_highlight_preserves_markdown(self):
        text = '# Heading\nTODO: **Important** `term`\nWARN: check\nDONE: done\n'
        self.app.buffer.set_text(text)
        self.app.highlight()
        self.assertEqual(self.app.text(), text)
        for word, tag in [('Heading', 'heading'), ('TODO:', 'token'), ('WARN:', 'warning'),
                          ('DONE:', 'done'), ('Important', 'bold'), ('term', 'code')]:
            it = self.app.buffer.get_iter_at_offset(text.index(word))
            self.assertTrue(it.has_tag(self.app.tags[tag]), word)
        self.app.highlight()  # repeated focus marks must remain valid

    def test_save_and_external_conflict(self):
        self.app.buffer.set_text('NOTE: saved')
        self.app.dirty = True
        self.assertTrue(self.app.save())
        self.assertEqual(self.app.path.read_text(), 'NOTE: saved')
        self.app.path.write_text('external change')
        self.app.dirty = True
        self.assertFalse(self.app.save())
        self.assertTrue(self.app.dirty)
        self.assertEqual(self.app.path.read_text(), 'external change')

    def test_failed_save_prevents_close(self):
        self.app.buffer.set_text('unsaved')
        self.app.dirty = True
        self.app.path.unlink()
        self.assertTrue(self.app.close_requested())
        self.assertTrue(self.app.dirty)

    def test_glow_is_short_lived_and_preserves_unicode(self):
        self.app.buffer.connect_after('insert-text', self.app.inserted)
        self.app.buffer.insert_at_cursor('λ', -1)
        it = self.app.buffer.get_start_iter()
        self.assertTrue(it.has_tag(self.app.tags['fresh']))
        self.assertTrue(self.app.glow_timer)
        GLib.source_remove(self.app.glow_timer)
        self.app.clear_glow()
        self.assertFalse(self.app.buffer.get_start_iter().has_tag(self.app.tags['fresh']))
        self.assertEqual(self.app.text(), 'λ')
        self.assertFalse(self.app.glow_ranges)
        self.assertEqual(self.app.glow_timer, 0)

    def test_glow_off_and_large_pastes_do_not_schedule_effects(self):
        self.app.buffer.connect_after('insert-text', self.app.inserted)
        self.app.glow_enabled = False
        self.app.buffer.insert_at_cursor('x', -1)
        self.app.glow_enabled = True
        self.app.buffer.insert_at_cursor('p'*100, -1)
        self.assertEqual(self.app.glow_timer, 0)
        self.assertFalse(self.app.glow_ranges)

    def test_quick_capture_saves_before_close_and_stays_on_error(self):
        self.app.window = SimpleNamespace(close=Mock())
        self.app.quick = True
        self.app.buffer.set_text('# Capture Grüße')
        self.app.dirty = True
        self.app.finish_quick()
        self.assertEqual(self.app.path.read_text(), '# Capture Grüße')
        self.app.window.close.assert_called_once()
        self.app.window.close.reset_mock()
        self.app.path.write_text('changed externally')
        self.app.dirty = True
        self.app.finish_quick()
        self.app.window.close.assert_not_called()

    def test_rename_current_note_continues_saving_to_new_path(self):
        self.app.mode = 'rename'
        original = self.app.path
        self.app.rename_path = original
        self.app.entry = SimpleNamespace(get_text=lambda: 'New Identity')
        self.app.show_panel = Mock()
        self.app.title = SimpleNamespace(set_text=Mock())
        self.app.window = SimpleNamespace(set_title=Mock())
        self.app.buffer.set_text('NOTE: before rename')
        self.app.dirty = True
        self.app.entry_activate()
        self.assertFalse(original.exists())
        self.assertTrue(self.app.path.name.endswith('__New-Identity.md'))
        self.app.buffer.set_text('NOTE: after rename')
        self.app.dirty = True
        self.assertTrue(self.app.save())
        self.assertEqual(self.app.path.read_text(), 'NOTE: after rename')
        self.app.show_panel.assert_called_once_with('notes')

    def test_single_delete_and_escape_cannot_move_file(self):
        path = self.app.store.create(title='Other note')
        path.write_text('preserved')
        self.app.panel_hint = SimpleNamespace(set_text=Mock())
        self.app.panel = SimpleNamespace(set_visible=Mock())
        self.app.manual = SimpleNamespace(set_visible=Mock())
        self.app.view.grab_focus = Mock()
        self.app.delete_selected(path)
        self.assertTrue(path.exists())
        self.app.close_panel()
        self.app.delete_selected(path)
        self.assertTrue(path.exists())
        self.app.query_changed = Mock()
        self.app.delete_selected(path)
        self.assertFalse(path.exists())
        self.assertEqual(next((self.app.store.root/'.trash').glob('*.md')).read_text(), 'preserved')

    def test_r_and_d_in_search_remain_normal_text(self):
        self.app.mode = 'notes'
        self.app.panel = SimpleNamespace(get_visible=lambda: True)
        # GTK Entry's internally focused text child may own focus.
        self.app.entry = SimpleNamespace(has_focus=lambda: False)
        self.app.window = SimpleNamespace(get_focus=lambda: SimpleNamespace(is_ancestor=lambda widget: widget is self.app.entry))
        self.app.list = SimpleNamespace(get_selected_row=lambda: SimpleNamespace(get_index=lambda: 0))
        self.app.matches = [self.app.path]
        self.app.delete_selected = Mock()
        self.app.show_panel = Mock()
        for key in [Gdk.KEY_r, Gdk.KEY_d, Gdk.KEY_h]:
            self.assertFalse(self.app.key_pressed(None, key, 0, Gdk.ModifierType(0)))
        self.app.delete_selected.assert_not_called()
        self.app.show_panel.assert_not_called()

    def test_find_wraps_and_markdown_quote_list_tags(self):
        text = '- Item\n> Quote\n## Heading\nIDEA: test NOTE: test FIX: test'
        self.app.buffer.set_text(text)
        self.app.highlight()
        for marker in ['-', '>', '##']:
            self.assertTrue(self.app.buffer.get_iter_at_offset(text.index(marker)).has_tag(self.app.tags['syntax']))
        self.app.mode = 'find'
        self.app.entry = SimpleNamespace(get_text=lambda: 'Item')
        self.app.view.scroll_to_iter = Mock()
        self.app.buffer.place_cursor(self.app.buffer.get_end_iter())
        self.app.entry_activate()
        start, end = self.app.buffer.get_selection_bounds()
        self.assertEqual(self.app.buffer.get_text(start, end, True), 'Item')

    def test_held_d_and_typing_in_editor_cannot_confirm_delete(self):
        self.app.mode = 'notes'
        self.app.panel = SimpleNamespace(get_visible=lambda: True)
        self.app.entry = SimpleNamespace(has_focus=lambda: False)
        focus = [SimpleNamespace(is_ancestor=lambda widget: widget is self.app.list)]
        self.app.window = SimpleNamespace(get_focus=lambda: focus[0])
        self.app.list = SimpleNamespace(get_selected_row=lambda: SimpleNamespace(get_index=lambda: 0))
        self.app.matches = [self.app.path]
        self.app.delete_selected = Mock()
        self.app.key_pressed(None, Gdk.KEY_d, 0, Gdk.ModifierType(0))
        self.app.key_pressed(None, Gdk.KEY_d, 0, Gdk.ModifierType(0))
        self.app.delete_selected.assert_called_once()
        self.app.key_released(None, Gdk.KEY_d, 0, Gdk.ModifierType(0))
        self.app.key_pressed(None, Gdk.KEY_d, 0, Gdk.ModifierType(0))
        self.assertEqual(self.app.delete_selected.call_count, 2)
        self.app.key_released(None, Gdk.KEY_d, 0, Gdk.ModifierType(0))
        focus[0] = SimpleNamespace(is_ancestor=lambda widget: False)
        self.assertFalse(self.app.key_pressed(None, Gdk.KEY_d, 0, Gdk.ModifierType(0)))
        self.assertEqual(self.app.delete_selected.call_count, 2)

    def test_contiguous_typing_batches_glow_marks(self):
        self.app.buffer.connect_after('insert-text', self.app.inserted)
        for _ in range(200):
            self.app.buffer.insert_at_cursor('x', -1)
        self.assertEqual(len(self.app.glow_ranges), 1)
        GLib.source_remove(self.app.glow_timer)
        self.app.clear_glow()
        self.assertEqual(self.app.text(), 'x'*200)

    def test_invalid_utf8_and_nul_preserve_open_note(self):
        original = self.app.path
        self.app.buffer.set_text('current text')
        other = self.app.store.create(title='Invalid')
        for raw, message in ((b'\xff', 'invalid UTF-8'), (b'before\x00after', 'NUL bytes')):
            with self.subTest(message=message):
                other.write_bytes(raw)
                self.assertFalse(self.app.load(other))
                self.assertEqual(self.app.path, original)
                self.assertEqual(self.app.text(), 'current text')
                self.assertIn(message, self.messages[-1])
                self.assertEqual(other.read_bytes(), raw)

    def test_file_changing_during_open_preserves_existing_editor(self):
        original = self.app.path
        self.app.buffer.set_text('current text')
        other = self.app.store.create(title='Other')
        other.write_text('external text')
        from unittest.mock import patch
        with patch.object(self.app, 'file_stamp', side_effect=[(1, 1, 1), (2, 2, 2)]):
            self.assertFalse(self.app.load(other))
        self.assertEqual(self.app.path, original)
        self.assertEqual(self.app.text(), 'current text')

    def test_shortened_glow_expires_without_manual_cleanup(self):
        import time
        from retronotes.app import GLOW_DURATION_MS, GLOW_STRENGTH
        self.assertEqual(GLOW_DURATION_MS, 60)
        self.assertLess(GLOW_STRENGTH, .22)
        self.app.buffer.connect_after('insert-text', self.app.inserted)
        self.app.buffer.insert_at_cursor('日本語', -1)
        start = time.monotonic()
        context = GLib.MainContext.default()
        while self.app.glow_timer and time.monotonic()-start < .5:
            while context.pending():
                context.iteration(False)
            time.sleep(.002)
        self.assertEqual(self.app.glow_timer, 0)
        self.assertFalse(self.app.glow_ranges)
        self.assertFalse(self.app.buffer.get_start_iter().has_tag(self.app.tags['fresh']))
        self.assertEqual(self.app.text(), '日本語')


if __name__ == '__main__':
    unittest.main()
