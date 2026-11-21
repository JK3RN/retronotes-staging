import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch
from retronotes.app import NotesApp, Gtk, GLib
from retronotes.core import Store, palette


class ThemeWatchTests(unittest.TestCase):
    def test_live_palette_and_symlink_reconnection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / 'current'
            current.mkdir()
            first, second = root / 'first', root / 'second'
            first.mkdir()
            second.mkdir()
            (first/'colors.toml').write_text('accent = "#123456"')
            (second/'colors.toml').write_text('accent = "#abcdef"')
            theme = current/'theme'
            theme.symlink_to(first, target_is_directory=True)
            path = theme/'colors.toml'
            app = NotesApp(Store(root/'Notes'))
            colors = []
            app.apply_theme = lambda: colors.append(palette([path])['accent'])
            def wait_for_reload(count):
                context = GLib.MainContext.default()
                deadline = time.monotonic()+2
                while len(colors) < count and time.monotonic() < deadline:
                    while context.pending():
                        context.iteration(False)
                    time.sleep(.005)
                self.assertGreaterEqual(len(colors), count)
            try:
                with patch('retronotes.app.theme_paths', return_value=[path]):
                    app.watch_theme()
                    path.write_text('accent = "#223344"')
                    wait_for_reload(1)
                    self.assertEqual(colors[-1], '#223344')
                    count = len(colors)+1
                    theme.unlink()
                    theme.symlink_to(second, target_is_directory=True)
                    wait_for_reload(count)
                    self.assertEqual(colors[-1], '#abcdef')
                    count = len(colors)+1
                    path.write_text('accent = "#445566"')
                    wait_for_reload(count)
                    self.assertEqual(colors[-1], '#445566')
            finally:
                for monitor in app.monitors:
                    monitor.cancel()
                if app.theme_timer:
                    GLib.source_remove(app.theme_timer)

    def test_theme_css_and_fresh_color_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = NotesApp(Store(temporary))
            buffer = Gtk.TextBuffer()
            app.tags = {name: buffer.create_tag(name) for name in
                        ['heading', 'syntax', 'bold', 'code', 'token', 'warning', 'done', 'focus', 'fresh']}
            app.css = Gtk.CssProvider()
            errors = []
            app.css.connect('parsing-error', lambda _, section, error: errors.append(str(error)))
            colors = palette([])
            with patch('retronotes.app.palette', return_value=colors):
                app.apply_theme()
            self.assertEqual(errors, [])
            fresh = app.tags['fresh'].get_property('foreground-rgba')
            foreground = app.rgba(colors['foreground'], 1)
            self.assertGreater(fresh.green, foreground.green)
            self.assertGreater(fresh.red, foreground.red)


if __name__ == '__main__':
    unittest.main()
