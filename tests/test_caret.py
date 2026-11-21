"""Motion and drawing lifecycle tests; real window tests run when a display is available."""
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock
from retronotes.caret_motion import CaretMotion, CaretPosition
from retronotes.caret import SmoothTextView, CARET_CSS
from retronotes.app import Gtk, Gdk, GLib


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.motion = CaretMotion()
        self.motion.update(CaretPosition(0, 0, 20), 0)

    def test_short_move_eases_out_then_stops_exactly(self):
        target = CaretPosition(10, 0, 20)
        self.motion.update(target, 0)
        points = [self.motion.sample(t).x for t in [0, 10000, 20000, 30000, 55000]]
        self.assertEqual(points[0], 0)
        self.assertEqual(points[-1], 10)
        self.assertEqual(points, sorted(points))
        self.assertGreater(points[1]-points[0], points[2]-points[1])
        self.assertFalse(self.motion.active)
        self.assertEqual(self.motion.sample(90000), target)

    def test_retarget_latest_without_queue_or_extended_deadline(self):
        self.motion.update(CaretPosition(10, 0, 20), 0)
        current = self.motion.sample(20000)
        latest = CaretPosition(20, 0, 20)
        self.assertEqual(self.motion.update(latest, 20000), current)
        self.assertEqual(self.motion.deadline, 55000)
        self.assertEqual(self.motion.sample(55000), latest)
        self.assertFalse(self.motion.active)

    def test_fast_input_is_bounded_and_arrives_at_latest_target(self):
        for n in range(1, 50):
            now = n*1000
            target = CaretPosition(n*10, 0, 20)
            position = self.motion.update(target, now)
            self.assertLessEqual(abs(position.x-target.x), 60)
        self.assertEqual(self.motion.sample(200000), target)
        self.assertFalse(self.motion.active)

    def test_backspace_and_adjacent_line_navigation(self):
        self.motion.update(CaretPosition(20, 0, 20), 0, snap=True)
        self.motion.update(CaretPosition(10, 0, 20), 0)
        self.assertTrue(self.motion.active)
        self.assertGreater(self.motion.sample(10000).x, 10)
        self.assertLess(self.motion.sample(20000).x, 20)
        self.motion.sample(55000)
        self.motion.update(CaretPosition(10, 24, 20), 60000)
        self.assertTrue(self.motion.active)
        self.assertEqual(self.motion.sample(115000), CaretPosition(10, 24, 20))
        self.motion.update(CaretPosition(10, 0, 20), 120000)
        self.assertEqual(self.motion.sample(175000), CaretPosition(10, 0, 20))

    def test_large_jumps_line_wrap_and_metrics_snap(self):
        for target in [CaretPosition(400, 0, 20), CaretPosition(0, 24, 20),
                       CaretPosition(0, 100, 20), CaretPosition(0, 100, 30)]:
            self.assertEqual(self.motion.update(target, 1000), target)
            self.assertFalse(self.motion.active)

    def test_viewport_or_pointer_snap_and_focus_reset(self):
        self.motion.update(CaretPosition(10, 0, 20), 0)
        target = CaretPosition(20, 0, 20)
        self.assertEqual(self.motion.update(target, 10000, snap=True), target)
        self.assertFalse(self.motion.active)
        self.motion.reset()
        self.assertIsNone(self.motion.sample(20000))
        self.assertEqual(self.motion.update(target, 20000), target)


class DrawingHarness:
    """GTK boundary substitutes; executes production drawing/lifecycle methods.

    Geometry is synthetic here; actual Pango/window coordinates have separate GUI tests.
    """
    def __init__(self):
        self.motion = CaretMotion()
        self.buffer = Gtk.TextBuffer()
        self.tick_id = 0
        self.force_snap = True
        self.viewport = None
        self.preedit = False
        self.focused = self.mapped = self.sensitive = self.editable = True
        self.cursor_visible = True
        self.overwrite = False
        self.animations = True
        self.weak_offset = 0
        self.now = 0
        self.css = set()
        self.visible = SimpleNamespace(x=0, y=0, width=500, height=300)
        self.color = Gdk.RGBA()
        self.queue_draw = Mock()
        self.add_tick_callback = Mock(return_value=1)
        self.remove_tick_callback = Mock()
        self.buffer.connect('mark-set', self.cursor_changed)
        self.buffer.connect('notify::has-selection', self.state_changed)

    def __getattr__(self, name):
        # Bind real methods without constructing a widget in a headless test.
        return getattr(SmoothTextView, name).__get__(self, type(self))

    def has_focus(self): return self.focused
    def get_mapped(self): return self.mapped
    def is_sensitive(self): return self.sensitive
    def get_editable(self): return self.editable
    def get_cursor_visible(self): return self.cursor_visible
    def get_overwrite(self): return self.overwrite
    def get_settings(self): return SimpleNamespace(get_property=lambda _: self.animations)
    def get_buffer(self): return self.buffer
    def get_visible_rect(self): return self.visible
    def get_frame_clock(self): return SimpleNamespace(get_frame_time=lambda: self.now)
    def add_css_class(self, name): self.css.add(name)
    def remove_css_class(self, name): self.css.discard(name)
    def has_css_class(self, name): return name in self.css

    def get_cursor_locations(self, _):
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        def rect(offset):
            return SimpleNamespace(x=it.get_line_offset()*10+offset, y=it.get_line()*24, height=20)
        return rect(0), rect(self.weak_offset)

    def draw(self):
        snapshot = SimpleNamespace(append_color=Mock())
        self.do_snapshot_layer(Gtk.TextViewLayer.ABOVE_TEXT, snapshot)
        return snapshot


class DrawingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.view = DrawingHarness()
        self.view.draw()  # transparent native paint takes effect on the next frame
        self.view.draw()

    def test_input_mark_is_immediate_while_only_visual_position_moves(self):
        self.view.buffer.insert_at_cursor('λ', -1)
        self.assertEqual(self.view.buffer.get_iter_at_mark(self.view.buffer.get_insert()).get_offset(), 1)
        self.view.draw()
        self.assertEqual(self.view.motion.position.x, 0)
        self.assertEqual(self.view.motion.target.x, 10)
        self.assertEqual(self.view.tick_id, 1)
        self.view.now = 55000
        self.assertFalse(self.view.tick(self.view, self.view.get_frame_clock()))
        self.assertEqual(self.view.tick_id, 0)
        self.assertEqual(self.view.motion.position.x, 10)
        self.assertTrue(self.view.cursor_visible)

    def test_one_tick_callback_for_many_targets_and_no_double_cursor_activation(self):
        fresh = DrawingHarness()
        self.assertFalse(fresh.draw().append_color.called)
        self.assertTrue(fresh.has_css_class('smooth-caret'))
        self.assertTrue(fresh.draw().append_color.called)
        for n in range(3):
            self.view.now = n*10000
            self.view.buffer.insert_at_cursor('x', -1)
            self.view.draw()
        self.view.add_tick_callback.assert_called_once()
        self.assertEqual(self.view.motion.target.x, 30)
        self.assertEqual(self.view.motion.deadline, 55000)

    def test_selection_and_ime_fall_back_then_snap_to_native_position(self):
        self.view.buffer.set_text('λ日本語')
        self.view.draw()
        self.view.buffer.select_range(self.view.buffer.get_end_iter(), self.view.buffer.get_start_iter())
        self.assertFalse(self.view.draw().append_color.called)
        self.assertFalse(self.view.has_css_class('smooth-caret'))
        self.assertEqual(self.view.tick_id, 0)
        self.view.buffer.place_cursor(self.view.buffer.get_end_iter())
        self.view.preedit_changed(self.view, '日本')
        self.assertFalse(self.view.draw().append_color.called)
        self.assertTrue(self.view.cursor_visible)
        self.view.preedit_changed(self.view, '')
        self.view.draw()
        self.view.draw()
        self.assertEqual(self.view.motion.position.x, 40)
        self.assertFalse(self.view.motion.active)

    def test_scroll_resize_pointer_focus_and_reduced_motion(self):
        self.view.buffer.insert_at_cursor('x', -1)
        self.view.draw()
        self.view.visible.y = 24
        self.view.viewport_changed()
        self.view.draw()
        self.assertFalse(self.view.motion.active)
        self.assertEqual(self.view.tick_id, 0)
        self.view.buffer.insert_at_cursor('x', -1)
        self.view.draw()
        self.view.pointer_pressed()
        self.view.draw()
        self.assertFalse(self.view.motion.active)
        self.view.visible.width = 250
        self.view.draw()
        self.assertFalse(self.view.motion.active)
        self.view.focused = False
        self.view.state_changed()
        self.assertFalse(self.view.has_css_class('smooth-caret'))
        self.view.focused = True
        self.view.animations = False
        self.assertFalse(self.view.draw().append_color.called)
        self.assertTrue(self.view.cursor_visible)

    def test_bidi_overwrite_and_unmap_restore_native_caret(self):
        self.view.weak_offset = 20
        self.assertFalse(self.view.draw().append_color.called)
        self.assertFalse(self.view.has_css_class('smooth-caret'))
        self.view.weak_offset = 0
        self.view.overwrite = True
        self.assertFalse(self.view.draw().append_color.called)
        self.view.overwrite = False
        self.view.draw()
        self.view.draw()
        self.view.suspend()
        self.assertFalse(self.view.has_css_class('smooth-caret'))
        self.assertEqual(self.view.tick_id, 0)
        self.assertIsNone(self.view.motion.position)

    def test_transparency_css_parses(self):
        provider = Gtk.CssProvider()
        errors = []
        provider.connect('parsing-error', lambda _, section, error: errors.append(str(error)))
        provider.load_from_data(CARET_CSS.encode())
        self.assertEqual(errors, [])


HAS_DISPLAY = Gtk.init_check() and Gdk.Display.get_default() is not None


@unittest.skipUnless(HAS_DISPLAY, 'requires a graphical GTK session')
class NativeWindowTests(unittest.TestCase):
    def setUp(self):
        self.window = Gtk.Window(default_width=400, default_height=200)
        self.addCleanup(self.window.destroy)
        settings = self.window.get_settings()
        animations = settings.get_property('gtk-enable-animations')
        self.addCleanup(settings.set_property, 'gtk-enable-animations', animations)
        settings.set_property('gtk-enable-animations', True)
        self.window.add_css_class('retronotes')
        self.view = SmoothTextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_child(self.view)
        self.window.set_child(self.scroll)
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(CARET_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider, 600)
        self.addCleanup(Gtk.StyleContext.remove_provider_for_display,
                        Gdk.Display.get_default(), self.provider)
        self.window.present()
        self.view.grab_focus()
        self.wait_for(self.view.can_draw_caret, 'GTK window did not become ready to draw the caret')

    def wait_for(self, condition, message):
        deadline = time.monotonic() + 2
        while not condition():
            if time.monotonic() >= deadline:
                self.fail(message)
            self.pump(.01)

    @staticmethod
    def pump(seconds):
        until = time.monotonic()+seconds
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending(): context.iteration(False)
            time.sleep(.002)

    def test_unicode_native_arrows_backspace_and_selection(self):
        buffer = self.view.get_buffer()
        buffer.insert_at_cursor('λ日本語🙂', -1)
        self.pump(.1)
        self.assertTrue(self.view.get_cursor_visible())
        self.view.emit('move-cursor', Gtk.MovementStep.LOGICAL_POSITIONS, -1, False)
        self.assertEqual(buffer.get_iter_at_mark(buffer.get_insert()).get_offset(), 4)
        self.view.emit('backspace')
        self.assertEqual(buffer.get_text(*buffer.get_bounds(), True), 'λ日本🙂')
        buffer.select_range(buffer.get_start_iter(), buffer.get_end_iter())
        self.pump(.03)
        self.assertFalse(self.view.has_css_class('smooth-caret'))
        self.assertTrue(self.view.get_cursor_visible())

    def test_real_scroll_and_caret_geometry(self):
        buffer = self.view.get_buffer()
        buffer.set_text('line λ日本語\n'*100)
        buffer.place_cursor(buffer.get_start_iter())
        self.pump(.1)
        self.view.emit('move-cursor', Gtk.MovementStep.BUFFER_ENDS, 1, False)
        def settled_at_cursor():
            strong, _ = self.view.get_cursor_locations(None)
            target = CaretPosition(strong.x, strong.y, strong.height)
            return self.view.motion.target == target and not self.view.motion.active and self.view.tick_id == 0

        self.wait_for(settled_at_cursor, 'Rendered caret did not settle at the GTK cursor after scrolling')


if __name__ == '__main__':
    unittest.main()
