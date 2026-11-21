"""Optional native TextView drawing layer; does not replace input or navigation."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Gdk, Graphene, GLib
from .caret_motion import CaretMotion, CaretPosition

# Only hide the paint. cursor-visible=False also changes native arrow navigation.
CARET_CSS = '''
.retronotes textview.smooth-caret,
.retronotes textview.smooth-caret text {
    caret-color: transparent;
    -gtk-secondary-caret-color: transparent;
}
'''


class SmoothTextView(Gtk.TextView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.motion = CaretMotion()
        self.tick_id = 0
        self.preedit = False
        self.force_snap = True
        self.viewport = None
        self.adjustments = []
        self.color = Gdk.RGBA()
        self.color.parse('#91e5ad')
        buffer = self.get_buffer()
        buffer.connect('mark-set', self.cursor_changed)
        buffer.connect('notify::has-selection', self.state_changed)
        self.connect('preedit-changed', self.preedit_changed)
        for prop in ['has-focus', 'editable', 'sensitive', 'overwrite']:
            self.connect(f'notify::{prop}', self.state_changed)
        for prop in ['vadjustment', 'hadjustment']:
            self.connect(f'notify::{prop}', self.bind_adjustments)
        self.connect('unmap', self.suspend)
        click = Gtk.GestureClick()
        click.set_button(0)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        # Observe pointer placement without claiming the gesture or replacing selection.
        click.connect('pressed', self.pointer_pressed)
        self.add_controller(click)
        self.bind_adjustments()

    def set_caret_color(self, color):
        self.color.parse(color)
        self.queue_draw()

    def can_draw_caret(self):
        return (self.has_focus() and self.get_mapped() and self.is_sensitive() and self.get_editable()
                and self.get_settings().get_property('gtk-enable-animations')
                and self.get_cursor_visible() and not self.get_overwrite()
                and not self.preedit and not self.get_buffer().get_has_selection())

    def cursor_changed(self, buffer, location, mark):
        if mark.get_name() in ['insert', 'selection_bound']:
            self.state_changed()
            self.queue_draw()

    def state_changed(self, *_):
        if not self.can_draw_caret():
            self.suspend()
        else:
            self.queue_draw()

    def preedit_changed(self, _, text):
        self.preedit = bool(text)
        self.force_snap = True
        self.state_changed()

    def pointer_pressed(self, *_):
        self.force_snap = True
        self.stop_tick()

    def bind_adjustments(self, *_):
        for adjustment, handler in self.adjustments:
            adjustment.disconnect(handler)
        self.adjustments.clear()
        for adjustment in [self.get_hadjustment(), self.get_vadjustment()]:
            if adjustment is not None:
                handler = adjustment.connect('value-changed', self.viewport_changed)
                self.adjustments.append((adjustment, handler))

    def viewport_changed(self, *_):
        self.force_snap = True
        self.stop_tick()
        self.queue_draw()

    def stop_tick(self):
        if self.tick_id:
            self.remove_tick_callback(self.tick_id)
            self.tick_id = 0

    def suspend(self, *_):
        self.stop_tick()
        self.motion.reset()
        self.force_snap = True
        self.remove_css_class('smooth-caret')

    def tick(self, widget, clock):
        if not self.can_draw_caret():
            self.tick_id = 0
            self.motion.reset()
            self.remove_css_class('smooth-caret')
            return False
        self.motion.sample(clock.get_frame_time())
        self.queue_draw()
        if not self.motion.active:
            self.tick_id = 0
            return False
        return True

    def do_snapshot_layer(self, layer, snapshot):
        if layer != Gtk.TextViewLayer.ABOVE_TEXT:
            return
        if not self.can_draw_caret():
            self.suspend()
            return
        # GTK has laid out and drawn text before this hook. Both coordinates are in
        # buffer space, with native scroll transform and clipping already applied.
        strong, weak = self.get_cursor_locations(None)
        if strong.height <= 0 or (strong.x, strong.y) != (weak.x, weak.y):
            # Preserve native split carets at bidirectional boundaries.
            self.suspend()
            return
        visible = self.get_visible_rect()
        viewport = (visible.x, visible.y, visible.width, visible.height)
        snap = self.force_snap or viewport != self.viewport
        self.viewport = viewport
        self.force_snap = False
        clock = self.get_frame_clock()
        now = clock.get_frame_time() if clock else GLib.get_monotonic_time()
        target = CaretPosition(strong.x, strong.y, strong.height)
        position = self.motion.update(target, now, snap=snap)
        if not self.has_css_class('smooth-caret'):
            # This frame's native text/caret has already been painted. Wait for the
            # transparent CSS to apply before drawing ours, avoiding a double caret.
            self.add_css_class('smooth-caret')
            self.queue_draw()
            return
        rectangle = Graphene.Rect()
        rectangle.init(position.x, position.y, 1.5, position.height)
        snapshot.append_color(self.color, rectangle)
        if self.motion.active and not self.tick_id:
            self.tick_id = self.add_tick_callback(self.tick)
        elif not self.motion.active:
            self.stop_tick()
