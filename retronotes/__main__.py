import argparse
from pathlib import Path
from .core import Store, default_notes_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description='Retro Notes — Markdown instrument')
    parser.add_argument('text', nargs='?', help='create a quick note directly, without opening a window')
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--notes-dir', type=Path, default=default_notes_dir())
    parser.add_argument('--no-focus-line', action='store_true')
    parser.add_argument('--no-glow', action='store_true', help='disable experimental fresh character glow')
    parser.add_argument('--smooth-caret', action='store_true', help='enable experimental visual caret interpolation for A/B testing')
    parser.add_argument('--version', action='version', version='Retro Notes 0.2.0')
    args = parser.parse_args(argv)
    try:
        store = Store(args.notes_dir)
        if args.text is not None:
            path = store.create(True)
            store.save(path, args.text + '\n')
            print(path)
            return 0
        from .app import NotesApp, Gtk, Gdk
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            parser.exit(1, 'rnote: Keine grafische Sitzung erreichbar (Wayland/X11). Text-Capture ist weiterhin möglich.\n')
        return NotesApp(store, args.quick, not args.no_focus_line, not args.no_glow, args.smooth_caret).run([])
    except (OSError, ImportError, ValueError) as error:
        parser.exit(1, f'rnote: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
