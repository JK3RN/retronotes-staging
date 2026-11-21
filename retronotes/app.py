import re
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
from .core import DeleteConfirmation, SaveConflict, note_identity, palette, theme_paths
from .manual import FIELD_MANUAL

GLOW_DURATION_MS = 60
GLOW_STRENGTH = .12


class NotesApp(Gtk.Application):
    def __init__(self, store, quick=False, focus=True, glow=True, smooth_caret=False):
        super().__init__(application_id='org.retrotools.Notes', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.store, self.quick, self.focus_line = store, quick, focus
        self.smooth_caret = smooth_caret
        self.path = None
        self.dirty = False
        self.loading = False
        self.save_timer = self.highlight_timer = 0
        self.monitors = []
        self.focus_range = None
        self.fingerprint = None
        self.theme_timer = 0
        self.glow_enabled = glow
        self.glow_timer = 0
        self.glow_ranges = []
        self.deletion = DeleteConfirmation()
        self.delete_key_down = False
        self.index_cache = None

    def do_activate(self):
        self.window = Gtk.ApplicationWindow(application=self, title='Retro Notes')
        self.window.set_default_size(640 if self.quick else 900, 360 if self.quick else 680)
        self.window.add_css_class('retronotes')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(box)
        self.window.set_child(self.overlay)
        self.manual = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.manual.add_css_class('retronotes')
        manual_header = Gtk.Label(label='FIELD MANUAL    /    ESC CLOSE', xalign=0)
        manual_header.add_css_class('instrument')
        self.manual.append(manual_header)
        manual_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        manual_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                   wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=16, right_margin=16)
        manual_view.get_buffer().set_text(FIELD_MANUAL)
        manual_scroll.set_child(manual_view)
        self.manual.append(manual_scroll)
        self.manual_view = manual_view
        self.overlay.add_overlay(self.manual)
        self.manual.set_visible(False)
        self.title = Gtk.Label(label='RETRO // NOTES    0.2', xalign=0)
        self.title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.title.add_css_class('instrument')
        box.append(self.title)
        box.append(Gtk.Separator())
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.panel.set_visible(False)
        box.append(self.panel)
        self.entry = Gtk.Entry(placeholder_text='NOTES / search')
        self.panel_heading = Gtk.Label(xalign=0)
        self.panel_heading.add_css_class('instrument')
        self.panel.append(self.panel_heading)
        self.panel.append(self.entry)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect('row-activated', lambda _, row: self.open_selected(row))
        picker_scroll = Gtk.ScrolledWindow()
        picker_scroll.set_max_content_height(230)
        picker_scroll.set_propagate_natural_height(True)
        picker_scroll.set_child(self.list)
        self.picker_scroll = picker_scroll
        self.panel.append(picker_scroll)
        self.panel_hint = Gtk.Label(xalign=0, wrap=True)
        self.panel_hint.add_css_class('instrument')
        self.panel.append(self.panel_hint)
        self.list.connect('row-selected', self.selection_changed)
        self.entry.connect('changed', self.query_changed)
        self.entry.connect('activate', self.entry_activate)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        box.append(scroll)
        view_type = Gtk.TextView
        if self.smooth_caret:
            from .caret import SmoothTextView
            view_type = SmoothTextView
        self.view = view_type(monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=26, right_margin=26, top_margin=20, bottom_margin=20)
        self.view.set_pixels_above_lines(3)
        self.view.set_pixels_below_lines(3)
        scroll.set_child(self.view)
        scroll.get_vadjustment().connect('value-changed', self.scrolled)
        self.buffer = self.view.get_buffer()
        self.buffer.set_enable_undo(True)
        self.tags = {}
        for name in ['heading', 'syntax', 'bold', 'code', 'token', 'warning', 'done', 'focus', 'fresh']:
            self.tags[name] = self.buffer.create_tag(name)
        self.buffer.connect('changed', self.changed)
        self.buffer.connect_after('insert-text', self.inserted)
        self.buffer.connect('mark-set', self.mark_set)
        box.append(Gtk.Separator())
        self.status = Gtk.Label(xalign=0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.add_css_class('instrument')
        box.append(self.status)
        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect('key-pressed', self.key_pressed)
        key.connect('key-released', self.key_released)
        self.window.add_controller(key)
        self.window.connect('close-request', self.close_requested)
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply_theme()
        self.watch_theme()
        self.view.set_sensitive(False)
        try:
            notes = self.store.notes()
            if self.quick or notes:
                self.load(self.store.create(True) if self.quick else notes[0])
            else:
                self.set_status('NO NOTE / CTRL+N NEW / F1 MANUAL')
        except OSError as error:
            self.set_status(f'NOTE ERROR / {error}')
        self.window.present()
        if self.path is None and not self.quick:
            self.show_panel('new')
        elif self.path is not None:
            self.view.grab_focus()

    def watch_theme(self):
        for monitor in self.monitors:
            monitor.cancel()
        self.monitors.clear()
        # The parent observes theme symlink replacement; reconnect file watches afterward.
        for path in theme_paths():
            for directory in [path.parent, path.parent.parent]:
                try:
                    monitor = Gio.File.new_for_path(str(directory)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
                    monitor.connect('changed', self.theme_changed)
                    self.monitors.append(monitor)
                except GLib.Error:
                    pass

    def theme_changed(self, *_):
        if not self.theme_timer:
            self.theme_timer = GLib.timeout_add(100, self.reload_theme)

    def reload_theme(self):
        self.theme_timer = 0
        self.apply_theme()
        self.watch_theme()
        return False

    def apply_theme(self):
        c = palette()
        caret_css = ''
        if self.smooth_caret:
            from .caret import CARET_CSS
            caret_css = CARET_CSS
            self.view.set_caret_color(c['accent'])
        self.css.load_from_data((f'''
        .retronotes, .retronotes textview text {{ background: {c['background']}; color: {c['foreground']}; }}
        .retronotes * {{ font-family: monospace; }}
        .retronotes textview {{ font-size: 16px; caret-color: {c['accent']}; }}
        .retronotes .instrument {{ color: {c['accent']}; font-size: 11px; padding: 10px 16px; }}
        .retronotes separator {{ background: alpha({c['foreground']}, 0.22); min-height: 1px; }}
        .retronotes entry, .retronotes list, .retronotes row {{ background: {c['background']}; color: {c['foreground']}; border-radius: 0; }}
        .retronotes row:selected {{ background: alpha({c['accent']}, 0.15); }}
        .retronotes row {{ padding: 6px 16px; }}
        ''' + caret_css).encode())
        for name in ['heading', 'token', 'done']:
            self.tags[name].set_property('foreground', c['accent'])
        self.tags['heading'].set_property('weight', Pango.Weight.BOLD)
        self.tags['bold'].set_property('weight', Pango.Weight.BOLD)
        self.tags['syntax'].set_property('foreground', c['foreground'])
        self.tags['syntax'].set_property('foreground-rgba', self.rgba(c['foreground'], .65))
        self.tags['code'].set_property('foreground', c['warning'])
        self.tags['warning'].set_property('foreground', c['critical'])
        self.tags['token'].set_property('weight', Pango.Weight.BOLD)
        self.tags['focus'].set_property('background-rgba', self.rgba(c['accent'], .045))
        fresh = self.rgba(c['foreground'], 1)
        for channel in ['red', 'green', 'blue']:
            value = getattr(fresh, channel)
            setattr(fresh, channel, value + (1-value)*GLOW_STRENGTH)
        self.tags['fresh'].set_property('foreground-rgba', fresh)

    @staticmethod
    def rgba(color, alpha):
        value = Gdk.RGBA()
        value.parse(color)
        value.alpha = alpha
        return value

    def inserted(self, buffer, location, text, length):
        if self.loading or not self.glow_enabled or len(text) > 32 or '\n' in text:
            return
        end = location.copy()
        start = self.buffer.get_iter_at_offset(max(0, end.get_offset()-len(text)))
        self.buffer.apply_tag(self.tags['fresh'], start, end)
        # Adjacent insertions share two marks for the short-lived batch.
        covered = False
        if self.glow_ranges:
            previous_start, previous_end = self.glow_ranges[-1]
            covered = (self.buffer.get_iter_at_mark(previous_start).get_offset() <= start.get_offset()
                       and self.buffer.get_iter_at_mark(previous_end).get_offset() >= end.get_offset())
        if not covered:
            self.glow_ranges.append((self.buffer.create_mark(None, start, True),
                                     self.buffer.create_mark(None, end, False)))
        if not self.glow_timer:
            self.glow_timer = GLib.timeout_add(GLOW_DURATION_MS, self.clear_glow)

    def clear_glow(self):
        self.glow_timer = 0
        for start, end in self.glow_ranges:
            self.buffer.remove_tag(self.tags['fresh'], self.buffer.get_iter_at_mark(start), self.buffer.get_iter_at_mark(end))
            self.buffer.delete_mark(start)
            self.buffer.delete_mark(end)
        self.glow_ranges.clear()
        return False

    def reset_effects(self):
        if self.glow_timer:
            GLib.source_remove(self.glow_timer)
        self.clear_glow()
        if self.focus_range:
            for mark in self.focus_range:
                self.buffer.delete_mark(mark)
            self.focus_range = None

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def load(self, path):
        if not self.save():
            return False
        try:
            before = self.file_stamp(path)
            text = self.store.read(path)
            if '\x00' in text:
                self.status.set_text('OPEN ERROR / NUL bytes in note')
                return False
            after = self.file_stamp(path)
            if before != after:
                self.status.set_text('OPEN CONFLICT / file changed while reading / retry')
                return False
        except UnicodeError:
            self.status.set_text('OPEN ERROR / invalid UTF-8')
            return False
        except OSError as error:
            self.status.set_text(f'OPEN ERROR / {error}')
            return False
        self.loading = True
        self.reset_effects()
        self.path = path
        self.fingerprint = after
        self.focus_range = None
        self.buffer.set_enable_undo(False)
        self.buffer.set_text(text)
        self.buffer.set_enable_undo(True)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.loading = False
        self.dirty = False
        self.view.set_sensitive(True)
        self.update_title()
        self.highlight()
        self.set_status('✓ SAVED')
        return True

    def update_title(self):
        path = self.path
        self.title.set_text(f'RETRO // {"QUICK NOTE" if self.quick else "NOTES"}    /    {path.name}')
        self.window.set_title(f'{path.name} — Retro Notes')

    def set_status(self, state):
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        hint = 'CTRL+ENTER SAVE + CLOSE' if self.quick else 'CTRL+N NEW   CTRL+P OPEN   CTRL+F FIND'
        self.status.set_text(f'{state}    /    {it.get_line()+1}:{it.get_line_offset()+1}    /    {hint}')

    def changed(self, *_):
        if self.loading:
            return
        self.dirty = True
        self.set_status('● MODIFIED')
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(500, self.autosave)
        if not self.highlight_timer:
            self.highlight_timer = GLib.idle_add(self.highlight)

    def autosave(self):
        self.save_timer = 0
        self.save()
        return False

    def file_stamp(self, path=None):
        return self.store.stamp(path if path is not None else self.path)

    def scrolled(self, *_):
        if self.buffer.get_char_count() >= 60000 and not self.highlight_timer:
            self.highlight_timer = GLib.idle_add(self.highlight)

    def save(self):
        if not self.dirty or self.path is None:
            return True
        try:
            self.fingerprint = self.store.save(self.path, self.text(), expected=self.fingerprint)
        except SaveConflict:
            self.status.set_text('SAVE CONFLICT / file changed externally / copy text before closing')
            return False
        except OSError as error:
            self.status.set_text(f'SAVE ERROR / {error} / CTRL+S RETRY')
            return False
        self.dirty = False
        self.set_status('✓ SAVED')
        return True

    def highlight(self):
        self.highlight_timer = 0
        start, end = self.buffer.get_bounds()
        # Retag the visible paragraph range, avoiding document-wide regex work on each key.
        top = self.view.get_visible_rect()
        first = self.view.get_iter_at_location(top.x, top.y)[1]
        last = self.view.get_iter_at_location(top.x, top.y + top.height)[1]
        lo = self.buffer.get_iter_at_line(max(0, first.get_line()-20))[1].get_offset()
        hi_line = min(self.buffer.get_line_count()-1, last.get_line()+20)
        hi = self.buffer.get_iter_at_line(hi_line)[1]
        hi.forward_to_line_end()
        # Full highlighting is bounded to small notes; larger notes use the viewport.
        if self.buffer.get_char_count() < 60000:
            lo, hi = 0, end
        region_start = self.buffer.get_iter_at_offset(lo)
        for name, tag in self.tags.items():
            if name not in ['focus', 'fresh']:
                self.buffer.remove_tag(tag, region_start, hi)
        text = self.buffer.get_text(region_start, hi, True)
        patterns = [('heading', r'(?m)^#{1,6} .+$'), ('syntax', r'(?m)^(?:#{1,6}|[-*+] |\d+\. |>)'),
                    ('bold', r'\*\*[^\n*]+\*\*'), ('code', r'`[^\n`]+`'),
                    ('token', r'\b(?:TODO|IDEA|NOTE|FIX):'), ('warning', r'\bWARN:'), ('done', r'\bDONE:')]
        for name, pattern in patterns:
            for match in re.finditer(pattern, text):
                self.buffer.apply_tag(self.tags[name], self.buffer.get_iter_at_offset(lo+match.start()),
                                      self.buffer.get_iter_at_offset(lo+match.end()))
        self.mark_set()
        return False

    def mark_set(self, *args):
        if args and args[2].get_name() != 'insert':
            return
        if not hasattr(self, 'status'):
            return
        if self.focus_range:
            start, end = self.focus_range
            self.buffer.remove_tag(self.tags['focus'], self.buffer.get_iter_at_mark(start), self.buffer.get_iter_at_mark(end))
            self.buffer.delete_mark(start)
            self.buffer.delete_mark(end)
            self.focus_range = None
        if self.focus_line:
            it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
            it.set_line_offset(0)
            finish = it.copy()
            finish.forward_line()
            self.buffer.apply_tag(self.tags['focus'], it, finish)
            self.focus_range = (self.buffer.create_mark(None, it, True), self.buffer.create_mark(None, finish, False))

    def close_panel(self):
        self.deletion.cancel()
        self.panel.set_visible(False)
        self.manual.set_visible(False)
        self.view.grab_focus()

    def show_panel(self, mode, path=None):
        self.deletion.cancel()
        self.manual.set_visible(False)
        self.mode = mode
        self.rename_path = path
        self.panel.set_visible(True)
        self.picker_scroll.set_visible(mode == 'notes')
        self.entry.set_visible(True)
        labels = {'notes': 'NOTE INDEX', 'new': 'NEW NOTE', 'rename': 'RENAME NOTE', 'find': 'FIND'}
        self.panel_heading.set_text(labels[mode])
        self.entry.set_placeholder_text('NAME' if mode in ['new', 'rename'] else 'SEARCH')
        self.index_cache = None
        self.entry.set_text(note_identity(path)[1] if path else '')
        self.query_changed()
        if mode != 'notes':
            self.panel_hint.set_text('ENTER APPLY / ESC CANCEL' if mode != 'find' else 'ENTER NEXT MATCH / ESC CLOSE')
        self.entry.grab_focus()
        if path:
            self.entry.select_region(0, -1)

    def query_changed(self, *_):
        if getattr(self, 'mode', '') != 'notes':
            return
        self.deletion.cancel()
        if self.index_cache is None:
            try:
                self.index_cache = [(p, *note_identity(p)) for p in self.store.notes()]
            except OSError as error:
                self.index_cache = []
                self.status.set_text(f'INDEX ERROR / {error}')
        query = self.entry.get_text().casefold()
        def match(path):
            chars = iter(path.name.casefold())
            return all(any(c == x for c in chars) for x in query)
        self.matches = [p for p, date, title in self.index_cache if match(p)]
        matched = set(self.matches)
        child = self.list.get_first_child()
        while child:
            self.list.remove(child)
            child = self.list.get_first_child()
        for path, date, title in self.index_cache:
            if path not in matched:
                continue
            label = Gtk.Label(label=f'{date:%d.%m %H:%M}   {title}', xalign=0,
                              ellipsize=Pango.EllipsizeMode.END)
            self.list.append(label)
        self.list.select_row(self.list.get_row_at_index(0))
        self.selection_changed()

    def selection_changed(self, *_):
        self.deletion.cancel()
        if getattr(self, 'mode', '') != 'notes':
            return
        row = self.list.get_selected_row()
        selected = row.get_index()+1 if row else 0
        self.panel_hint.set_text(f'{len(self.matches)} NOTES / {selected}/{len(self.matches)}\n'
                                 'ENTER OPEN / TAB RESULTS / R RENAME / D D TRASH / ESC CLOSE')

    def entry_activate(self, *_):
        if self.mode == 'notes':
            self.open_selected(self.list.get_selected_row())
        elif self.mode in ['new', 'rename']:
            if not self.save():
                return
            try:
                if self.mode == 'new':
                    path = self.store.create(title=self.entry.get_text())
                    if not self.load(path):
                        return
                else:
                    old = self.rename_path
                    # Also guard a clean currently open note against external edits.
                    if old == self.path and self.file_stamp() != self.fingerprint:
                        self.status.set_text('RENAME CONFLICT / file changed externally')
                        return
                    path = self.store.rename(old, self.entry.get_text())
                    if old == self.path:
                        self.path = path
                        self.fingerprint = self.file_stamp()
                        self.update_title()
            except OSError as error:
                self.status.set_text(f'NOTE ERROR / {error}')
                return
            if self.mode == 'rename':
                self.show_panel('notes')
            else:
                self.close_panel()
        else:
            query = self.entry.get_text()
            if not query:
                return
            it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
            found = it.forward_search(query, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
            if not found:
                found = self.buffer.get_start_iter().forward_search(query, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
            if found:
                self.buffer.select_range(found[1], found[0])
                self.view.scroll_to_iter(found[0], .15, False, 0, 0)
            else:
                self.status.set_text('FIND / NO MATCH')

    def open_selected(self, row):
        if row and self.load(self.matches[row.get_index()]):
            self.close_panel()

    def delete_selected(self, path):
        try:
            if path == self.path:
                if not self.save():
                    self.deletion.cancel()
                    return
                if self.file_stamp() != self.fingerprint:
                    self.status.set_text('DELETE CONFLICT / file changed externally')
                    self.deletion.cancel()
                    return
            if not self.deletion.request(path):
                self.panel_hint.set_text(f'DELETE {note_identity(path)[1]} ?\nPRESS D AGAIN WITHIN 4s / ESC CANCEL')
                return
            self.store.trash(path)
            if path == self.path:
                self.loading = True
                self.reset_effects()
                self.buffer.set_enable_undo(False)
                self.buffer.set_text('')
                self.buffer.set_enable_undo(True)
                self.loading = False
                self.path = self.fingerprint = None
                self.dirty = False
                self.view.set_sensitive(False)
                self.title.set_text('RETRO // NOTES / NO NOTE')
                self.window.set_title('Retro Notes')
                self.set_status('MOVED TO .trash / CTRL+N NEW / CTRL+P OPEN')
            self.index_cache = None
            self.query_changed()
        except OSError as error:
            self.deletion.cancel()
            self.status.set_text(f'TRASH ERROR / {error}')

    def key_pressed(self, _, key, code, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if key == Gdk.KEY_Escape:
            self.close_panel()
            return True
        if key == Gdk.KEY_F1:
            self.deletion.cancel()
            self.panel.set_visible(False)
            self.manual.set_visible(True)
            self.manual_view.grab_focus()
            return True
        panel_notes = self.panel.get_visible() and self.mode == 'notes'
        focus = self.window.get_focus()
        search_focus = self.entry.has_focus() or (focus is not None and focus.is_ancestor(self.entry))
        results_focus = focus is not None and focus.is_ancestor(self.list)
        if panel_notes and key in [Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab]:
            row = self.list.get_selected_row()
            if search_focus and row:
                row.grab_focus()
            else:
                self.entry.grab_focus()
            self.deletion.cancel()
            return True
        if panel_notes and key in [Gdk.KEY_Down, Gdk.KEY_Up]:
            row = self.list.get_selected_row()
            index = (row.get_index() if row else (-1 if key == Gdk.KEY_Down else 1))
            if not search_focus:
                index += 1 if key == Gdk.KEY_Down else -1
            row = self.list.get_row_at_index(max(0, min(index, len(self.matches)-1)))
            self.list.select_row(row)
            if row:
                row.grab_focus()
            return True
        letter = Gdk.keyval_to_unicode(key)
        letter = chr(letter).lower() if letter else ''
        # Unmodified R/D act only on results, never in the editable search field.
        if panel_notes and not ctrl and not (state & Gdk.ModifierType.ALT_MASK) and results_focus:
            row = self.list.get_selected_row()
            if row and letter in ['r', 'd']:
                path = self.matches[row.get_index()]
                if letter == 'r':
                    self.show_panel('rename', path)
                else:
                    if not self.delete_key_down:
                        self.delete_key_down = True
                        self.delete_selected(path)
                return True
        if not ctrl:
            return False
        if key in [Gdk.KEY_Return, Gdk.KEY_KP_Enter] and self.quick:
            return self.finish_quick()
        if letter == 's':
            self.save()
        elif letter == 'n':
            if self.save():
                self.show_panel('new')
        elif letter in ['p', 'f']:
            self.show_panel('notes' if letter == 'p' else 'find')
        elif letter == 'w':
            self.window.close()
        else:
            return False
        return True

    def key_released(self, _, key, code, state):
        if key in [Gdk.KEY_d, Gdk.KEY_D]:
            self.delete_key_down = False

    def finish_quick(self):
        if self.save():
            self.window.close()
        return True

    def close_requested(self, *_):
        return not self.save()
